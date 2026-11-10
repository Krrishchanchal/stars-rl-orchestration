"""Three serial repetitions of each method on the same declared case.

These are runtime repetitions, not independent scenario samples.
"""
from pathlib import Path
from dataclasses import asdict
import argparse,json,gzip,time
from stars_rl.config import scenario_from_dict
from stars_rl.topology.trace import build_trace
from stars_rl.simulation import simulate

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 t=build_trace(scenario_from_dict(json.loads(a.input.read_text())));rows=[]
 methods=['stars-fixed','mono-temporal','hier-only','mono-delay']
 for repeat in range(3):
  # Rotate order to avoid always giving the same method the first run.
  for method in methods[repeat:]+methods[:repeat]:
   result=simulate(t,method,rho=.5,total_budget_seconds=10)
   with gzip.open(a.output/f'{repeat}-{method}.json.gz','wt',encoding='utf8') as f:json.dump(asdict(result),f,allow_nan=False)
   failed=next((w for w in result.windows if w.status not in ('committed','not_attempted')),None)
   rows.append(dict(repeat=repeat,method=method,status=result.status,approved_windows=sum(w.status=='committed' for w in result.windows),reason=failed.reason if failed else '',decision_seconds=sum(w.elapsed_seconds for w in result.windows)))
   (a.output/'results.json').write_text(json.dumps(rows,indent=2));print(rows[-1],flush=True)
 (a.output/'status.json').write_text(json.dumps(dict(status='completed',episodes=len(rows),scope='runtime repetitions of same trace; not independent scenario samples')))
if __name__=='__main__':main()
