"""Independent Stage II deviations/objective plus complete C08 deployment check.

Only explicitly registered objective auxiliaries are removed from a copied view
for the base validator; every such auxiliary is separately checked here.
"""
from copy import deepcopy
from dataclasses import asdict
import math
import time

from stars_rl.models import validate_deployment_structure
from .deployment import validate_export, _plain
from .residuals import Residuals, finite


def validate_reference(scenario, window, reference):
    if reference.window_index != window.window_index:
        raise ValueError("Stage I reference window differs")
    users = set(window.user_ids)
    if (len(reference.access) != len(users) or len(reference.egress) != len(users)
            or {a.user_id for a in reference.access} != users or {x.user_id for x in reference.egress} != users):
        raise ValueError("reference needs exactly one access/egress per user")
    for a in reference.access:
        if window.access_distance(a.user_id,a.satellite_id) is None:
            raise ValueError("invisible Stage I access reference")
    for x in reference.egress:
        if window.ground_distance(x.satellite_id,x.ground_station_id) is None:
            raise ValueError("invisible Stage I gateway reference")
    for sat in scenario.satellites:
        if (sum(a.satellite_id == sat.id for a in reference.access) > sat.access_capacity
                or sum(x.satellite_id == sat.id for x in reference.egress) > sat.egress_capacity):
            raise ValueError("Stage I reference exceeds association capacity")


def validate_stage2(scenario, window, export, reference, previous=None, *, weights=(1,1), radio_coefficients=None):
    started = time.perf_counter()
    report = {"valid": False, "status": "schema_error", "errors": [], "deployment": None, "objective": None}
    try:
        _plain(export)  # Includes all unknown/auxiliary values before comparisons.
        validate_reference(scenario,window,reference)
        if len(weights) != 2 or any(type(w) not in (int,float) or not math.isfinite(w) or w < 0 for w in weights):
            raise ValueError("invalid objective weights")
        if previous is not None:
            validate_deployment_structure(previous,scenario)
            if previous.window_index >= window.window_index:
                raise ValueError("previous deployment must precede current window")
        elif window.window_index > 0 and weights[1] > 0:
            raise ValueError("temporal placement objective requires previous deployment")
        users = tuple(window.user_ids)
        ha = {(u,s):f"h_alpha[{u},{s}]" for u in users for s in window.satellite_ids}
        hx = {(u,s,g):f"h_xi[{u},{s},{g}]" for u in users for s in window.satellite_ids for g in window.ground_station_ids}
        beta = tuple((u,k,f,i.instance_id,i.satellite_id) for u in users
                     for k,f in enumerate(scenario.slice_for_user(u).chain)
                     for i in sorted(scenario.instances,key=lambda i:i.identity) if i.function_type_id == f)
        db = {k:f"d_beta[{','.join(map(str,k))}]" for k in beta} if previous is not None else {}
        auxiliary = set(ha.values()) | set(hx.values()) | set(db.values())
        raw = export['solver_result']['values']
        if type(raw) is not dict:
            raise ValueError('raw values must be a mapping')
        for key,value in raw.items():finite(value,key)
        if not export['solver_result']['has_incumbent'] and raw != {}:
            raise ValueError('absent incumbent has raw auxiliary/decision values')
        if export['solver_result']['has_incumbent'] and not auxiliary <= raw.keys():
            raise ValueError("missing Stage II auxiliary IDs")
        base = deepcopy(export)
        base['solver_result']['values'] = {k:v for k,v in raw.items() if k not in auxiliary}
        deployment = validate_export(scenario,window,base,radio_coefficients=radio_coefficients)
        report['deployment'] = deployment.to_dict()
        report['status'] = deployment.status
        if not deployment.valid:
            report['errors'] = list(deployment.errors)
            return report
        finite(export['solver_result']['objective'],'objective')
        old_a = {(a.user_id,a.satellite_id) for a in reference.access}
        old_x = {(x.user_id,x.satellite_id,x.ground_station_id) for x in reference.egress}
        old_b = {(a.user_id,a.stage_index,*a.instance.identity) for a in previous.allocations} if previous else set()
        rows = Residuals()
        def variable(prefix,key):return f"{prefix}[{','.join(map(str,key))}]"
        for domain, prefix, old in ((ha,'alpha',old_a),(hx,'xi',old_x),(db,'beta',old_b)):
            for k,n in domain.items():
                d = raw[n]; value = raw.get(variable(prefix,k),0)
                rows.ge('counts',n+':lower',d,0);rows.le('counts',n+':upper',d,1)
                rows.ge('counts',n+':positive',d,value-int(k in old))
                rows.ge('counts',n+':negative',d,int(k in old)-value)
        c = export['candidate']['deployment']
        new_a = {(a['user_id'],a['satellite_id']) for a in c['access']}
        new_x = {(a['user_id'],a['satellite_id'],a['ground_station_id']) for a in c['egress']}
        new_b = {(a['user_id'],a['stage_index'],a['instance']['function_type_id'],a['instance']['instance_id'],a['instance']['satellite_id']) for a in c['allocations']}
        stages = sum(len(scenario.slice_for_user(u).chain) for u in users)
        h = (len(new_a^old_a)+len(new_x^old_x))/(4*len(users))
        d_beta = len(new_b^old_b)/(2*stages) if previous is not None else 0
        encoded_h = math.fsum(raw[n] for n in (*ha.values(),*hx.values()))/(4*len(users))
        encoded_beta = math.fsum(raw[n] for n in db.values())/(2*stages)
        encoded = weights[0]*encoded_h + weights[1]*encoded_beta
        if abs(encoded-export['solver_result']['objective']) > 1e-8:
            report['errors'].append('encoded objective mismatch')
        actual = weights[0]*h+weights[1]*d_beta
        if actual-encoded > 1e-8:
            report['errors'].append('encoded objective underestimates actual discrete objective')
        report['objective'] = {'H':h,'D_beta':d_beta,'actual':weights[0]*h+weights[1]*d_beta,
                               'encoded':encoded,'residuals':[asdict(r) for r in rows.rows]}
        report['valid'] = not report['errors'] and all(r.passed for r in rows.rows)
        report['status'] = 'valid' if report['valid'] else 'rejected'
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError) as exc:
        report['status']='schema_error';report['errors']=[str(exc)]
    finally:
        report['elapsed_seconds']=time.perf_counter()-started
    return report
