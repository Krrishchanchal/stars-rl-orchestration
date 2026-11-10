"""Run the frozen implementation on a declared authored/physical matrix.

Run with the installed project interpreter from the repository root. No changes
to optimization, physical family definitions, training gates or model semantics.
"""
from pathlib import Path
from dataclasses import asdict
import argparse,copy,csv,gzip,hashlib,json,subprocess,time,traceback
import yaml
from stars_rl.config import scenario_from_dict
from stars_rl.topology.trace import build_trace,trace_to_dict
from stars_rl.topology.physical import generate_physical
from stars_rl.topology.audit import audit_trace
from stars_rl.simulation import simulate

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 root=Path(__file__).resolve().parents[1];template=yaml.safe_load((root/'experiments/inputs/authored-16users-v1.yaml').read_text())
 def save(name,value):
  path=out/name;path.parent.mkdir(parents=True,exist_ok=True)
  if path.suffix=='.gz':
   with gzip.open(path,'wt',encoding='utf8') as f:json.dump(value,f,allow_nan=False)
  else:path.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf8')
 cases=[]
 def case(name,n=16,sats=4,moving=4,cpu=1000,demand=None,delay=None):
  s=copy.deepcopy(template);s.update(scenario_id=name,family_id='final-authored-matrix-v1')
  s['metadata'].update(scenario_group_id=name,root_lineage_id='final-authored-matrix-v1',layout_id=name)
  s['satellites']=[dict(id=f's{i}',cpu_capacity_mips=cpu,access_capacity=5,egress_capacity=5,max_active_instances=4) for i in range(sats)]
  s['instances']=[dict(function_type_id=f,instance_id='i0',satellite_id=f's{i}') for i in range(sats) for f in ('f0','f1')]
  s['users']=[dict(id=f'u{i:02}',slice_id=f'slice{i%2}',coordinates=None) for i in range(n)]
  s['access_schedule']=[dict(window_index=t,links=[dict(user_id=u['id'],satellite_id=f's{(i+int(t>0 and i<moving))%sats}',distance_m=500000) for i,u in enumerate(s['users'])]) for t in range(3)]
  s['ground_links']=[dict(satellite_id=f's{i}',ground_station_id='g0',distance_m=500000) for i in range(sats)]
  if demand is not None:
   for sl in s['slices']:sl['demand_mbps']=demand
  if delay is not None:
   for sl in s['slices']:sl['delay_limit_seconds']=delay
  cases.append((name,s))
 for n in (4,8,16,24,32):case(f'load-{n}',n=n)
 for sats in (2,4,8,12,20):case(f'satellites-{sats}',sats=sats)
 for moved in (0,4,8,16):case(f'handover-{moved}',moving=moved)
 for cpu in (100,200,500,1000):case(f'cpu-{cpu}',cpu=cpu)
 for demand in (2,5,10,20):case(f'demand-{demand}',demand=demand)
 for delay in (.005,.01,.02,.05):case(f'delay-{delay}',delay=delay)
 revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
 save('protocol.json',dict(code_revision=revision,budget_seconds=10,solver_seed=0,threads=1,authored_cases=[k for k,_ in cases],physical_seeds=list(range(5)),physical_families=['paper-inputs-v1','development-physical-v1'],notes=['one-factor changes around 16 users, four satellites, four migrating users','authored networks have no ISLs; every user has exactly one access option','satellite CPU 1000 MIPS and access/egress pools five except named interventions','no native training without existing readiness evidence; no seed screening','four methods compared at each handover intensity; other stress cases use stars-fixed','one trace per authored case: descriptive results, no inferential confidence intervals']))
 rows=[];seen={}
 for name,config in cases:
  trace=build_trace(scenario_from_dict(config));save(f'inputs/{name}.json',config)
  methods=['stars-fixed','mono-temporal','hier-only','mono-delay'] if name.startswith('handover-') else ['stars-fixed']
  for method in methods:
   key=(trace.content_hash,method)
   if key in seen:
    row=dict(seen[key]);row.update(case=name,reused_from=seen[key]['case']);rows.append(row);save('authored-results.json',rows);continue
   print('START',name,method,flush=True);started=time.perf_counter()
   try:
    result=simulate(trace,method,rho=.5,total_budget_seconds=10);raw=asdict(result)
    save(f'episodes/{name}-{method}.json.gz',raw)
    good=[w for w in result.windows if w.status=='committed'];failed=next((w for w in result.windows if w.status not in ('committed','not_attempted')),None)
    costs=[sum(getattr(w.metrics,k) for k in ('d_alpha','d_xi','d_beta')) for w in good]
    J=sum(.95**i*v for i,v in enumerate(costs))
    if failed is not None:J+=.95**failed.window_index*4*sum(.95**j for j in range(len(result.windows)-failed.window_index))
    delays=[v['physical_total_delay_seconds'] for w in good for v in w.commit_validation['deployment']['recomputed'].values()]
    row=dict(case=name,users=len(trace.scenario.users),satellites=len(trace.scenario.satellites),method=method,status=result.status,approved_windows=len(good),failure_reason=failed.reason if failed else '',J=J if result.transition_valid else None,access_switches=sum(w.metrics.access_switches for w in good),host_moves=sum(w.metrics.host_changes for w in good),assignment_changes=sum(w.metrics.assignment_changes for w in good),max_committed_delay_ms=max(delays)*1000 if delays else None,decision_seconds=sum(w.elapsed_seconds for w in result.windows),wall_seconds=time.perf_counter()-started,reused_from='')
   except Exception as exc:
    save(f'errors/{name}-{method}.json',dict(error=str(exc),traceback=traceback.format_exc()));row=dict(case=name,method=method,status='implementation_error',wall_seconds=time.perf_counter()-started)
   seen[key]=row;rows.append(row);save('authored-results.json',rows);print('END',name,method,row['status'],flush=True)
 physical=[]
 for family in ('paper-inputs-v1','development-physical-v1'):
  for seed in range(5):
   label=f'{family}-seed{seed}';print('PHYSICAL',label,flush=True);t=time.perf_counter()
   try:
    trace,stats=generate_physical(family,seed);audit=audit_trace(trace);save(f'physical/{label}-trace.json.gz',trace_to_dict(trace));save(f'physical/{label}-audit.json',audit)
    w=audit['windows'];row=dict(family=family,seed=seed,windows=len(w),necessary_passed=sum(x['preflight']['passed'] for x in w),min_access_flow=min(x['preflight']['access']['flow'] for x in w),max_access_flow=max(x['preflight']['access']['flow'] for x in w),initial_passed=w[0]['preflight']['passed'],seconds=time.perf_counter()-t)
    if all(x['preflight']['passed'] for x in w):
     result=simulate(trace,'stars-fixed',rho=.5,total_budget_seconds=60);save(f'physical/{label}-episode.json.gz',asdict(result));row['episode_status']=result.status
    else:row['episode_status']='preflight_failed_full_episode_not_solved'
   except Exception as exc:row=dict(family=family,seed=seed,error=str(exc),traceback=traceback.format_exc())
   physical.append(row);save('physical-results.json',physical)
 for filename,data in [('authored-results.csv',rows),('physical-results.csv',physical)]:
  fields=list(dict.fromkeys(k for r in data for k in r))
  with (out/filename).open('w',newline='',encoding='utf8') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)
 save('status.json',dict(status='completed',authored_records=len(rows),unique_authored_solves=len(seen),physical_records=len(physical)))
if __name__=='__main__':main()
