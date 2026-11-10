"""Attempt physical episodes with initially passing audits, under supervision."""
from pathlib import Path
from dataclasses import asdict
import argparse,gzip,json,subprocess,sys,time
from stars_rl.topology.benchmark import peak_memory

def main():
 p=argparse.ArgumentParser();p.add_argument('--results',required=True,type=Path);p.add_argument('--worker');a=p.parse_args();root=a.results.resolve()
 if a.worker:
  from stars_rl.topology.trace import trace_from_dict
  from stars_rl.simulation import simulate
  with gzip.open(root/'physical'/f'{a.worker}-trace.json.gz','rt') as f:trace=trace_from_dict(json.load(f))
  r=simulate(trace,'stars-fixed',rho=.5,total_budget_seconds=60)
  with gzip.open(root/'physical'/f'{a.worker}-prefix.json.gz','wt') as f:json.dump(asdict(r),f,allow_nan=False)
  return
 records=[]
 for row in json.loads((root/'physical-results.json').read_text()):
  if not row.get('initial_passed'):continue
  label=f"{row['family']}-seed{row['seed']}";start=time.perf_counter();peak=0;reason=None
  with (root/'physical'/f'{label}-prefix.log').open('w') as log:
   child=subprocess.Popen([sys.executable,__file__,'--results',str(root),'--worker',label],stdout=log,stderr=subprocess.STDOUT)
   while child.poll() is None:
    peak=max(peak,peak_memory(child.pid) or 0)
    if peak>2*1024**3:reason='supervisor_memory_limit_2GiB';child.kill();break
    if time.perf_counter()-start>180:reason='supervisor_wall_limit_180s';child.kill();break
    time.sleep(.2)
   child.wait()
  result=dict(family=row['family'],seed=row['seed'],wall_seconds=time.perf_counter()-start,parent_pid_peak_bytes=peak,memory_measurement_scope='PID only; Windows venv launcher may have child processes; not a process-tree memory certificate',exit=child.returncode,supervisor_reason=reason)
  path=root/'physical'/f'{label}-prefix.json.gz'
  if path.exists():
   with gzip.open(path,'rt') as f:data=json.load(f)
   result.update(episode_status=data['status'],approved_windows=sum(w['status']=='committed' for w in data['windows']),window_statuses=[dict(index=w['window_index'],status=w['status'],reason=w['reason']) for w in data['windows'] if w['status']!='not_attempted'])
  records.append(result);(root/'physical-prefix-results.json').write_text(json.dumps(records,indent=2));print(result,flush=True)
if __name__=='__main__':main()
