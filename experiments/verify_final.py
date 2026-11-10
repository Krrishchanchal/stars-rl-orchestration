"""Revalidate every committed authored deployment from the saved raw records."""
from pathlib import Path
import gzip,json
from stars_rl.config import scenario_from_dict,deployment_from_dict
from stars_rl.topology.trace import build_trace
from stars_rl.validation.stage2 import validate_stage2
from stars_rl.validation.monolithic import validate_monolithic
from stars_rl.optimization.stage1 import AssociationReference
from stars_rl.models import AccessChoice,EgressChoice
root=Path(__file__).resolve().parent/'results';matrix=root/'final-matrix';checks=[]
rows=json.loads((matrix/'authored-results.json').read_text())
work=[(matrix/f"inputs/{r['case']}.json",matrix/f"episodes/{r['case']}-{r['method']}.json.gz") for r in rows if not r.get('reused_from')]
work += [(matrix/f"inputs/{r['case']}.json",matrix/f"episodes/{r['case']}.json.gz") for r in json.loads((matrix/'capacity-extension.json').read_text())]
work += [(matrix/'inputs/handover-4.json',file) for file in (root/'budget-repetitions').glob('*.json.gz')]
count=0
for config,path in work:
 trace=build_trace(scenario_from_dict(json.loads(config.read_text())))
 with gzip.open(path,'rt') as f:result=json.load(f)
 for w in result['windows']:
  if w['status']!='committed':continue
  previous=deployment_from_dict(w['previous_committed'],trace.scenario) if w['previous_committed'] is not None else None
  if w['stage1_outcome'] is not None:
   ref=w['stage1_outcome']['stage1_reference'];reference=AssociationReference(ref['window_index'],tuple(AccessChoice(**v) for v in ref['access']),tuple(EgressChoice(**v) for v in ref['egress']))
   previous=previous if 'hier-only' not in path.name else None
   checked=validate_stage2(trace.scenario,trace.windows[w['window_index']],w['export'],reference,previous,weights=(1,0 if w['rho'] is None else w['rho']))
  else:
   mode='temporal' if 'mono-temporal' in path.name and previous is not None else 'Q'
   checked=validate_monolithic(trace.scenario,trace.windows[w['window_index']],w['export'],mode=mode,previous=previous)
  assert checked['valid'],(str(path),w['window_index'],checked['errors'])
  count+=1
 checks.append(dict(episode=str(path.relative_to(root)),status=result['status']))
out=dict(status='passed',authored_episode_records=len(work),committed_deployments_revalidated=count,solver_calls=0,episodes=checks)
(root/'independent-revalidation.json').write_text(json.dumps(out,indent=2));print({k:v for k,v in out.items() if k!='episodes'})
