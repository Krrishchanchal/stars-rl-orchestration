"""Boundary and larger-population cases; preserve original five-slot pools."""
from pathlib import Path
from dataclasses import asdict
import argparse,json,gzip,time
from stars_rl.config import scenario_from_dict
from stars_rl.topology.trace import build_trace
from stars_rl.simulation import simulate
def main():
 p=argparse.ArgumentParser();p.add_argument('--results',required=True,type=Path);p.add_argument('--wait-for',type=Path);a=p.parse_args();root=a.results.resolve()
 while a.wait_for is not None and not a.wait_for.exists():time.sleep(1)
 rows=[]
 for n,sats in [(20,4),(32,8),(64,16)]:
  s=json.loads((root/'inputs/load-16.json').read_text());name=f'extended-users{n}-satellites{sats}';s['scenario_id']=name;s['metadata'].update(scenario_group_id=name,layout_id=name)
  s['satellites']=[dict(id=f's{i}',cpu_capacity_mips=1000,access_capacity=5,egress_capacity=5,max_active_instances=4) for i in range(sats)]
  s['instances']=[dict(function_type_id=f,instance_id='i0',satellite_id=f's{i}') for i in range(sats) for f in ('f0','f1')]
  s['users']=[dict(id=f'u{i:02}',slice_id=f'slice{i%2}',coordinates=None) for i in range(n)]
  s['access_schedule']=[dict(window_index=t,links=[dict(user_id=u['id'],satellite_id=f's{(i+int(t>0 and i<4))%sats}',distance_m=500000) for i,u in enumerate(s['users'])]) for t in range(3)]
  s['ground_links']=[dict(satellite_id=f's{i}',ground_station_id='g0',distance_m=500000) for i in range(sats)]
  (root/f'inputs/{name}.json').write_text(json.dumps(s,indent=2));trace=build_trace(scenario_from_dict(s));r=simulate(trace,'stars-fixed',rho=.5,total_budget_seconds=10)
  with gzip.open(root/f'episodes/{name}.json.gz','wt') as f:json.dump(asdict(r),f,allow_nan=False)
  good=[w for w in r.windows if w.status=='committed'];failed=next((w for w in r.windows if w.status not in ('committed','not_attempted')),None)
  row=dict(case=name,users=n,satellites=sats,status=r.status,approved_windows=len(good),reason=failed.reason if failed else '',access_switches=sum(w.metrics.access_switches for w in good),host_moves=sum(w.metrics.host_changes for w in good),decision_seconds=sum(w.elapsed_seconds for w in r.windows))
  rows.append(row);(root/'capacity-extension.json').write_text(json.dumps(rows,indent=2));print(row,flush=True)
 (root/'capacity-extension-status.json').write_text(json.dumps(dict(status='completed',episodes=len(rows))))
if __name__=='__main__':main()
