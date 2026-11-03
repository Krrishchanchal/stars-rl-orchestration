"""Independent Q/temporal objective checks plus complete physical feasibility."""
from copy import deepcopy
from dataclasses import asdict
import math
import time

from stars_rl.models import validate_deployment_structure
from .deployment import validate_export, _plain
from .residuals import Residuals, finite


def validate_monolithic(scenario,window,export,*,mode,previous=None,radio_coefficients=None):
    started=time.perf_counter()
    out={'valid':False,'status':'schema_error','errors':[],'deployment':None,'objective':None}
    try:
        _plain(export)
        if mode not in {'Q','temporal'}:raise ValueError('unknown monolithic objective')
        if mode=='temporal':
            if previous is None:raise ValueError('temporal objective requires original committed state')
            validate_deployment_structure(previous,scenario)
            if previous.window_index >= window.window_index:raise ValueError('invalid previous window')
        users=window.user_ids
        da={(u,s):f'd_alpha[{u},{s}]' for u in users for s in window.satellite_ids} if mode=='temporal' else {}
        dx={(u,s,g):f'd_xi[{u},{s},{g}]' for u in users for s in window.satellite_ids for g in window.ground_station_ids} if mode=='temporal' else {}
        db={(u,k,f,i.instance_id,i.satellite_id):f'd_beta[{u},{k},{f},{i.instance_id},{i.satellite_id}]'
            for u in users for k,f in enumerate(scenario.slice_for_user(u).chain)
            for i in scenario.instances if i.function_type_id==f} if mode=='temporal' else {}
        raw=export['solver_result']['values']
        if type(raw) is not dict:raise ValueError('raw mapping required')
        for k,v in raw.items():finite(v,k)
        auxiliary=set(da.values())|set(dx.values())|set(db.values())
        if export['solver_result']['has_incumbent']:
            if not auxiliary<=raw.keys():raise ValueError('missing objective auxiliaries')
        elif raw:raise ValueError('absent incumbent has raw values')
        base=deepcopy(export);base['solver_result']['values']={k:v for k,v in raw.items() if k not in auxiliary}
        full=validate_export(scenario,window,base,radio_coefficients=radio_coefficients)
        out['deployment']=full.to_dict();out['status']=full.status;out['errors']=list(full.errors)
        if not full.valid:return out
        finite(export['solver_result']['objective'],'objective')
        rows=Residuals()
        if mode=='Q':
            encoded=math.fsum(full.recomputed[u]['raw_total_delay_seconds']/scenario.slice_for_user(u).delay_limit_seconds for u in users)/len(users)
            actual=math.fsum(full.recomputed[u]['physical_total_delay_seconds']/scenario.slice_for_user(u).delay_limit_seconds for u in users)/len(users)
            components={'Q':actual,'reconstruction_scope':'physical delay errors governed by original per-user second budgets'}
        else:
            old_a={(a.user_id,a.satellite_id) for a in previous.access}
            old_x={(a.user_id,a.satellite_id,a.ground_station_id) for a in previous.egress}
            old_b={(a.user_id,a.stage_index,*a.instance.identity) for a in previous.allocations}
            for domain,prefix,old in ((da,'alpha',old_a),(dx,'xi',old_x),(db,'beta',old_b)):
                for k,n in domain.items():
                    value=raw.get(f"{prefix}[{','.join(map(str,k))}]",0);d=raw[n]
                    rows.ge('counts',n+':lower',d,0);rows.le('counts',n+':upper',d,1)
                    rows.ge('counts',n+':positive',d,value-int(k in old));rows.ge('counts',n+':negative',d,int(k in old)-value)
            c=export['candidate']['deployment']
            new_a={(a['user_id'],a['satellite_id']) for a in c['access']}
            new_x={(a['user_id'],a['satellite_id'],a['ground_station_id']) for a in c['egress']}
            new_b={(a['user_id'],a['stage_index'],a['instance']['function_type_id'],a['instance']['instance_id'],a['instance']['satellite_id']) for a in c['allocations']}
            stages=sum(len(scenario.slice_for_user(u).chain) for u in users)
            components={'D_alpha':len(new_a^old_a)/(2*len(users)),'D_xi':len(new_x^old_x)/(2*len(users)), 'D_beta':len(new_b^old_b)/(2*stages)}
            actual=math.fsum(components.values())
            encoded=(math.fsum(raw[n] for n in (*da.values(),*dx.values()))/(2*len(users))
                     +math.fsum(raw[n] for n in db.values())/(2*stages))
            if actual-encoded>1e-8:out['errors'].append('encoded objective underestimates actual changes')
        if abs(encoded-export['solver_result']['objective'])>1e-8:out['errors'].append('encoded objective mismatch')
        out['objective']={'mode':mode,'encoded':encoded,'actual':actual,'components':components,'residuals':[asdict(r) for r in rows.rows]}
        out['valid']=not out['errors'] and all(r.passed for r in rows.rows)
        out['status']='valid' if out['valid'] else 'rejected'
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError) as exc:
        out['status']='schema_error';out['errors']=[str(exc)]
    finally:out['elapsed_seconds']=time.perf_counter()-started
    return out
