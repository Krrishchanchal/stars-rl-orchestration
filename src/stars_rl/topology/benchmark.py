"""Fresh-process single-window size ladder; never crop a physical scenario."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from stars_rl.models import (Scenario,Radio,FunctionType,Slice,User,GroundStation,Satellite,InstanceKey,
    AccessWindow,AccessLink,GroundLink,ISLLink,TraceMetadata,GenerationMetadata)

LADDER=((2,1),(4,2),(8,4),(12,6),(20,10),(60,30))
MEMORY_BUDGET=2*1024**3


def peak_memory(pid=None):
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD),*[(n,ctypes.c_size_t) for n in ('peak','working','quota_peak_paged','quota_paged','quota_peak_nonpaged','quota_nonpaged','pagefile','peak_pagefile','private')]]
        kernel=ctypes.windll.kernel32;api=ctypes.windll.psapi.GetProcessMemoryInfo
        kernel.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD);kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetCurrentProcess.restype=wintypes.HANDLE
        handle=kernel.GetCurrentProcess() if pid is None else kernel.OpenProcess(0x410,False,pid)
        if not handle:return None
        try:
            counters=Counters();counters.cb=ctypes.sizeof(counters)
            api.argtypes=(wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD);api.restype=wintypes.BOOL
            return counters.peak if api(handle,ctypes.byref(counters),ctypes.sizeof(counters)) else None
        finally:
            if pid is not None:
                kernel.CloseHandle.argtypes=(wintypes.HANDLE,);kernel.CloseHandle(handle)
    if pid is not None:
        try:
            for line in Path(f'/proc/{pid}/status').read_text().splitlines():
                if line.startswith('VmHWM:'):return int(line.split()[1])*1024
        except OSError:return None
    else:
        import resource
        value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value if sys.platform=='darwin' else value*1024


def fixture(sats,users):
    ids=tuple(f's{k:02d}' for k in range(sats));uids=tuple(f'u{k:02d}' for k in range(users))
    return Scenario(1,f'ladder-v2-{sats}-{users}','size-ladder-authored-v2','analytical_fixture',1,60,
        TraceMetadata('size-ladder-v2','size-ladder','authored-chain','authored-layout','fixed-small-demand',None,0,60,GenerationMetadata('authored',None,None,(),())),
        Radio(14e9,.1,15,40,100e6,290,'exogenous',0,299792458,1.380649e-23),
        tuple(FunctionType(f'f{k}',10,10,5) for k in range(2)),(Slice('slice0',('f0','f1'),2,12000,.05),),
        tuple(User(u,'slice0',None) for u in uids),(GroundStation('g0',None),),
        tuple(Satellite(n,2000,5,5,8) for n in ids),tuple(InstanceKey(f'f{k}',f'i{i}',n) for k in range(2) for i in range(2) for n in ids),
        (AccessWindow(0,tuple(AccessLink(u,n,500000) for u in uids for n in ids)),),
        tuple(GroundLink(n,'g0',500000) for n in ids),tuple(ISLLink(a,b,100000) for a,b in zip(ids,ids[1:])))


def worker(sats,users,output,budget):
    from stars_rl.config import scenario_to_dict
    from stars_rl.topology.trace import build_trace
    from stars_rl.simulation import simulate
    from stars_rl.experiments.manifest import atomic_json
    if (sats,users) not in LADDER or 3*users*sats*sats>250000:raise ValueError('worker pair requires a separately approved larger-model experiment')
    started=time.perf_counter();trace=build_trace(fixture(sats,users));offline=time.perf_counter()-started
    result=simulate(trace,rho=.5,total_budget_seconds=budget)
    atomic_json(output,{'family':'size-ladder-authored-v2','pair':[sats,users],'chain_length':2,'instances_per_type_host':2,'access_capacity':5,'egress_capacity':5,
        'memory_scope':'peak process working set includes interpreter/imports/SCIP','peak_process_memory_bytes':peak_memory(),
        'offline_trace_seconds':offline,'scenario':scenario_to_dict(trace.scenario),'result':asdict(result)})


def benchmark_ladder(output,sizes=LADDER[:3],budget=10):
    from stars_rl.experiments.manifest import atomic_json,read_json
    if tuple(sizes)!=LADDER[:len(sizes)] or not sizes:raise ValueError('ladder must be an ordered prefix starting at2:1')
    if type(budget) not in (int,float) or not 0<budget<=60:raise ValueError('benchmark budget must be0..60s')
    output=Path(output);output.mkdir(parents=True,exist_ok=False);records=[];previous=None
    for sats,users in sizes:
        estimated=25*users*sats+10*sats+3*users*sats*sats
        links=3*users*sats*sats
        forecast=None if previous is None else int(previous['peak_process_memory_bytes']*estimated/previous['variables'])
        row={'pair':[sats,users],'estimated_variables':estimated,'estimated_links':links,'memory_forecast_bytes':forecast}
        if links>250000 or (forecast is not None and forecast>MEMORY_BUDGET):
            row.update(status='blocked',reason='size or measured proportional memory forecast requires a separate approved larger experiment');records.append(row);break
        path=output/f'{sats}-{users}.json';started=time.perf_counter()
        process=subprocess.Popen([sys.executable,'-m','stars_rl.topology.benchmark','--worker',str(sats),str(users),'--output',str(path),'--budget',str(budget)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        monitored=0;reason=None
        while process.poll() is None:
            memory=peak_memory(process.pid);monitored=max(monitored,memory or 0)
            if monitored>MEMORY_BUDGET:reason='memory_budget_exceeded';process.kill();break
            if time.perf_counter()-started>budget+30:reason='supervisor_wall_limit';process.kill();break
            time.sleep(.05)
        _,stderr=process.communicate();row['worker_wall_seconds']=time.perf_counter()-started
        if reason or process.returncode!=0:
            row.update(status='blocked',reason=reason or 'worker_error',diagnostic=stderr.decode(errors='replace'));records.append(row);break
        data=read_json(path);w=data['result']['windows'][0];stage=w['stages']['stage2']
        peak=max(monitored,data['peak_process_memory_bytes'] or 0)
        row.update(status=data['result']['status'],peak_process_memory_bytes=peak,
            variables=stage['model_counts'].get('original_variables'),constraints=stage['model_counts'].get('original_constraints'),
            presolved_variables=stage['model_counts'].get('transformed_variables'),presolved_constraints=stage['model_counts'].get('transformed_constraints'),
            decision_seconds=w['elapsed_seconds'],first_valid_incumbent_seconds=stage['first_valid_incumbent_time'],
            first_valid_incumbent_reason=stage['first_valid_incumbent_reason'],stage_times=stage['timings'],
            raw_status=stage['raw_status'],primal_bound=stage['primal_bound'],dual_bound=stage['dual_bound'],
            progress=stage['progress_log'],artifact=path.name)
        records.append(row)
        if row['status']!='success' or peak>MEMORY_BUDGET or not row['variables'] or peak==0:break
        previous=row
    result={'schema_version':1,'scope':'authored single-window diagnostic, not a reduced/cropped physical case',
            'budget_seconds':budget,'memory_budget_bytes':MEMORY_BUDGET,'forecast_scope':'prior measured process peak scaled by next/previous variable count; not a guarantee',
            'records':records,'large_physical_experiments_authorized':False}
    atomic_json(output/'ladder.json',result);return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker',nargs=2,type=int);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--budget',type=float,default=10);parser.add_argument('--sizes',nargs='+',default=['2:1','4:2','8:4'])
    args=parser.parse_args()
    if args.worker:worker(*args.worker,args.output,args.budget)
    else:print(json.dumps(benchmark_ladder(args.output,tuple(tuple(map(int,s.split(':'))) for s in args.sizes),args.budget),indent=2))


if __name__=='__main__':main()
