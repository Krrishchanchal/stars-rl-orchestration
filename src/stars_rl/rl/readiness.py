"""Fail-closed scientific launch gates and an explicit total compute estimate."""
from pathlib import Path
import hashlib
import json
import math

from stars_rl.experiments.manifest import checked_path,file_hash,read_json
from stars_rl.topology.audit import preflight


def compute_estimate(traces,episodes,budget):
    if type(episodes) is not int or episodes<1 or type(budget) not in (int,float) or not math.isfinite(budget) or budget<=0:
        raise ValueError('positive episode count and finite budget required')
    lengths=[len(t.windows) for t in traces]
    if not lengths:raise ValueError('training traces required')
    # Ordering can permute trace cycles. Use the longest horizon for a safe bound.
    windows=dict(training=episodes*max(lengths),sensitivity=5*sum(lengths),validation=sum(lengths),
                 evaluation=6*sum(lengths)) # five fixed ratios plus one frozen policy
    return dict(schema_version=1,kind='conservative budget bound; not measured pilot throughput',
                window_budget_seconds=budget,phase_windows=windows,
                stage_solve_upper_bounds={k:2*v for k,v in windows.items()},
                constructed_gate_solve_allowance=233,
                total_solver_call_upper_bound=2*sum(windows.values())+233,
                decision_budget_upper_seconds=budget*sum(windows.values())+10*233,
                initialization_included=True,post_decision_io_generation_and_plotting_seconds=None,
                limitation='Add measured offline/artifact time and pilot throughput before any larger launch.')


def assess_readiness(traces,budget,profile,evidence_path=None,episodes=1):
    """Only current physical training is eligible; analytical tests are separate.

    Evidence is a JSON map of constructed/scaling reports and ordered successful
    run/sensitivity paths. Resolve paths beside that map, hash every used file,
    revalidate deployment artifacts, and check positive cross-weight margins.
    """
    reasons=[];hashes={}
    for trace in traces:
        if trace.scenario.orbit is None:reasons.append('Analytical/toy trace is not a representative physical training family')
        elif not all(preflight(trace.scenario,w)['passed'] for w in trace.windows):
            reasons.append('Physical trace fails necessary coverage/resource checks: '+trace.content_hash)
    if episodes>3:reasons.append('Larger launch blocked until a measured solver-backed pilot is reviewed; maximum pilot is 3 episodes')
    if evidence_path is None:
        reasons.append('Missing saved constructed, scaling, successful-episode and representative action evidence')
        return dict(passed=False,reasons=reasons,evidence_hashes=hashes)
    evidence_path=Path(evidence_path).resolve()
    evidence=read_json(evidence_path);hashes['evidence']=file_hash(evidence_path)
    if type(evidence) is not dict or set(evidence)!={'constructed','scaling','successful_runs','sensitivity'}:
        raise ValueError('invalid readiness evidence fields')
    def load(relative):
        p=checked_path(evidence_path.parent,relative);hashes[relative]=file_hash(p)
        return read_json(p)
    constructed=load(evidence['constructed'])
    if not constructed.get('constructed_gate_passed') or constructed.get('runtime_profile')!=profile:
        reasons.append('Constructed action certificate missing or from incompatible code/runtime')
    scaling=load(evidence['scaling'])
    measured=[r for r in scaling.get('records',[]) if r.get('status')=='success'
              and r.get('raw_status')=='optimal' and 0<r.get('peak_process_memory_bytes',0)<=2*1024**3]
    if scaling.get('budget_seconds')!=budget or any(not any(r['pair'][0]>=len(t.scenario.satellites)
        and r['pair'][1]>=len(t.scenario.users) for r in measured) for t in traces):
        reasons.append('No compatible measured scaling ladder covering every requested size/budget')
    if any(t.scenario.orbit is not None for t in traces) and scaling.get('large_physical_experiments_authorized') is not True:
        reasons.append('Saved ladder explicitly does not authorize physical-scale experiments')
    if any(type(evidence[k]) is not list or len(evidence[k])!=len(traces) for k in ('successful_runs','sensitivity')):
        raise ValueError('one ordered successful run and sensitivity report per trace required')
    from stars_rl.experiments.runner import validate_run
    for trace,run_name,action_name in zip(traces,evidence['successful_runs'],evidence['sensitivity']):
        run=checked_path(evidence_path.parent,run_name)
        validated=validate_run(run)
        manifest=read_json(run/'manifest.json');hashes[run_name+'/manifest.json']=file_hash(run/'manifest.json')
        settings=read_json(run/'settings.json')
        if (not validated['valid'] or validated['episode_status']!='success'
            or validated['trace_content_hash']!=trace.content_hash or validated['approved_windows']!=len(trace.windows)
            or manifest['runtime_profile']!=profile or settings.get('window_budget_seconds')!=budget):
            reasons.append('Missing compatible fully independently validated episode: '+run_name)
        report=load(action_name)
        if report.get('trace_content_hash')!=trace.content_hash or report.get('runtime_profile')!=profile:
            reasons.append('Sensitivity identity/code/runtime mismatch: '+action_name);continue
        if not _positive_effect(trace,report,budget):reasons.append('No certified positive-margin representative ratio effect: '+action_name)
    return dict(passed=not reasons,reasons=reasons,evidence_hashes=hashes)


def _positive_effect(trace,report,budget):
    from stars_rl.config import deployment_from_dict
    from stars_rl.models import AccessChoice,EgressChoice
    from stars_rl.optimization.stage1 import AssociationReference
    from stars_rl.validation.stage2 import validate_stage2
    for window in report.get('windows',[]):
        source=window['pre_action_state'];index=source['index']
        if type(index) is not int or not 0<=index<len(trace.windows):continue
        if index==0:continue
        if source['trace']!=trace.content_hash or window.get('budget_seconds')!=budget or window.get('runtime_adapter')!='standard':continue
        previous=deployment_from_dict(source['previous'],trace.scenario)
        points=[]
        actions=window['actions']
        from .actions import RATIOS
        fingerprint=hashlib.sha256(json.dumps(source,sort_keys=True,allow_nan=False).encode()).hexdigest()
        if ([r['action'] for r in actions]!=list(range(5)) or [r['rho'] for r in actions]!=list(RATIOS)
            or any(r['pre_action_fingerprint']!=fingerprint for r in actions)):continue
        for row in actions:
            if row['info']['failure'] or row['stages']['stage2']['status']!='optimal':continue
            if row['export']['solver_result']['raw_status']!='optimal':continue
            gap=row['stages']['stage2']['absolute_gap']
            if gap is None or gap>1e-8:continue
            ref=row.get('stage1_reference')
            if ref is None:continue
            reference=AssociationReference(ref['window_index'],tuple(AccessChoice(**a) for a in ref['access']),
                                           tuple(EgressChoice(**e) for e in ref['egress']))
            checked=validate_stage2(trace.scenario,trace.windows[index],row['export'],reference,previous,weights=(1,row['rho']))
            if checked['valid']:
                o=checked['objective'];points.append((row['rho'],o['H'],o['D_beta'],ref))
        for rho,h,b,ref in points:
            for other_rho,other_h,other_b,other_ref in points:
                if ref==other_ref and (other_h+rho*other_b)-(h+rho*b)>1e-8 and (h+other_rho*b)-(other_h+other_rho*other_b)>1e-8:
                    return True
    return False
