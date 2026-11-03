"""Hand-derived hierarchy/placement tradeoffs and full-feasibility rescue."""
from copy import deepcopy
from dataclasses import asdict, replace
from itertools import product
import json
import time

import pytest

from stars_rl.config import deployment_from_dict
from stars_rl.metrics import change_metrics
from stars_rl.models import AccessChoice, AccessWindow, Deployment, EgressChoice, InstanceKey, StageAllocation
from stars_rl.optimization.backend import solve, submit_start
from stars_rl.optimization.monolithic import export_solution
from stars_rl.optimization.repair import repair_previous
from stars_rl.optimization.stage1 import AssociationReference, run_stage1
from stars_rl.optimization.stage2 import build_stage2_model, partial_stage2_start, run_stage2
from stars_rl.topology.trace import build_trace
from stars_rl.validation.stage2 import validate_stage2

pytestmark=pytest.mark.solver


def windows(s,count=3):
    return replace(s,window_count=count,metadata=replace(s.metadata,interval_end_seconds=count*s.window_seconds),
                   access_schedule=tuple(AccessWindow(k,s.access_schedule[0].links) for k in range(count)))


def previous(s,host='a'):
    return Deployment(0,(AccessChoice('u0',host),),(EgressChoice('u0',host,'g0'),),
                      (StageAllocation('u0',0,InstanceKey('f0','i0',host),20),))


def reference(w,host='a'):
    return AssociationReference(w.window_index,(AccessChoice('u0',host),),(EgressChoice('u0',host,'g0'),))


def checked(s,w,m,v,rates):
    r=solve(m,stage='stage2',objective_name='hierarchy_and_placement',objective_units='dimensionless',time_limit=5)
    d=export_solution(m,s,w,v.full,r)
    c=validate_stage2(s,w,d,v.stage1_reference,v.original_previous,weights=v.weights,radio_coefficients=rates)
    assert c['valid'],c
    return r,d,c


def test_stage1_bad_radio_reference_rescued_by_free_stage2(full_case,tmp_path):
    s,_,rates=full_case(ground=(('a','g0'),),capacities={'a':0,'b':100})
    s=windows(s);links=tuple(replace(link,distance_m=100000 if link.satellite_id=='a' else 500000) for link in s.access_schedule[0].links)
    s=replace(s,access_schedule=tuple(AccessWindow(k,links) for k in range(3)))
    trace=build_trace(s);w=trace.windows[0]
    rates={k:(500000 if k[1]=='a' else 12000000) for k in rates}
    t0=time.perf_counter();first=run_stage1(s,w,started_at=t0)
    assert first.stage1_reference.access==(AccessChoice('u0','a'),)
    out=run_stage2(s,w,first,started_at=t0,radio_coefficients=rates)
    assert out.status=='validated',asdict(out)
    assert out.final_deployment.access==(AccessChoice('u0','b'),)
    assert out.validation['objective']['H']==.5 and out.validation['objective']['D_beta']==0
    assert out.stage_result.objective==pytest.approx(.5)
    assert out.start.prevalidation=='unknown_partial'
    # Fixing the reference would destroy this feasible deployment.
    m,v=build_stage2_model(s,w,first.stage1_reference,radio_coefficients=rates)
    m.addCons(v.full.discrete.alpha[('u0','a')]==1)
    assert solve(m,stage='fixed_diagnostic',objective_name='hierarchy',objective_units='dimensionless',time_limit=3).raw_status=='infeasible'
    repaired=repair_previous(s,trace.windows[1],out.final_deployment)
    assert repaired.repair_candidate.access==out.final_deployment.access
    assert repaired.repair_candidate.placements[0].instance==out.final_deployment.allocations[0].instance
    (tmp_path/'stage2_rescue.json').write_text(json.dumps({'stage1':asdict(first),'stage2':asdict(out),'next_reference':asdict(repaired)},indent=2))


@pytest.mark.parametrize('rho,expected_host,expected_objective',[(.5,'b',.5),(2,'a',1)])
def test_hand_tradeoff_ratio_and_matching_cold_warm(full_case,tmp_path,rho,expected_host,expected_objective):
    s,_,rates=full_case(edges=(),delay=1)
    s=windows(s);trace=build_trace(s);w=trace.windows[1];p=previous(s);ref=reference(w,'b')
    records=[]
    for warm in (False,True):
        m,v=build_stage2_model(s,w,ref,p,weights=(1,rho),radio_coefficients=rates)
        start=submit_start(m,partial_stage2_start(v),kind='partial') if warm else None
        r,d,c=checked(s,w,m,v,rates)
        assert r.raw_status=='optimal' and r.objective==pytest.approx(expected_objective,abs=1e-8)
        final=deployment_from_dict(d['candidate']['deployment'],s)
        assert final.allocations[0].instance.satellite_id==expected_host
        assert final.access[0].satellite_id==final.egress[0].satellite_id==expected_host
        metrics=change_metrics(s,p,final,previous_available=True)
        assert metrics.host_changes==int(expected_host!='a')
        next_ref=repair_previous(s,trace.windows[2],final)
        assert next_ref.repair_candidate.access==final.access
        assert next_ref.repair_candidate.placements[0].instance==final.allocations[0].instance
        records.append({'start':asdict(start) if start else None,'export':d,'validation':c,'metrics':asdict(metrics)})
        assert v.full.diagnostics['stage2_model_size']['variables']>v.full.diagnostics['base_full_model_size']['variables']
    (tmp_path/f'stage2_tradeoff_{rho}.json').write_text(json.dumps(records,indent=2))


@pytest.mark.parametrize('access,egress,host,instance',list(product(('a','b'),('a','b'),('a','b'),('i0','i1'))))
def test_all_deviation_branches_and_fixed_normalization(full_case,access,egress,host,instance):
    s,_,rates=full_case(delay=1);s=windows(s);w=build_trace(s).windows[1];p=previous(s)
    m,v=build_stage2_model(s,w,reference(w),p,radio_coefficients=rates)
    for k,b in v.full.discrete.alpha.items():m.addCons(b==int(k==('u0',access)))
    for k,b in v.full.discrete.xi.items():m.addCons(b==int(k==('u0',egress,'g0')))
    selected=('u0',0,'f0',instance,host)
    for k,b in v.full.discrete.beta.items():m.addCons(b==int(k==selected))
    r,d,c=checked(s,w,m,v,rates)
    h=(int(access!='a')+int(egress!='a'))/2
    beta=int((host,instance)!=('a','i0'))
    assert c['objective']['H']==h and c['objective']['D_beta']==beta
    assert r.objective==pytest.approx(h+beta,abs=1e-8)
    for k,b in v.h_alpha.items():assert r.values[b.name]==int((k==('u0',access))!=(k==('u0','a')))
    for k,b in v.h_xi.items():assert r.values[b.name]==int((k==('u0',egress,'g0'))!=(k==('u0','a','g0')))
    for k,b in v.d_beta.items():assert r.values[b.name]==int((k==selected)!=(k==('u0',0,'f0','i0','a')))


def test_invalid_complete_start_withheld_then_cold_feasible_solution(full_case):
    s,w,rates=full_case(nodes=('a',));m,v=build_stage2_model(s,w,reference(w),radio_coefficients=rates)
    start=submit_start(m,{b.name:0 for b in m.getVars()},kind='complete')
    assert start.prevalidation=='infeasible' and not start.submission_attempted
    r,d,c=checked(s,w,m,v,rates)
    assert c['objective']['D_beta']==0 and not v.d_beta


def test_zero_weights_do_not_make_auxiliaries_into_actual_metrics(full_case):
    s,_,rates=full_case(nodes=('a',));s=windows(s);w=build_trace(s).windows[1]
    m,v=build_stage2_model(s,w,reference(w),previous(s),weights=(0,0),radio_coefficients=rates)
    for b in (*v.h_alpha.values(),*v.h_xi.values(),*v.d_beta.values()):m.addCons(b==1)
    # Keep the same placement to make actual D_beta exactly0.
    m.addCons(v.full.discrete.beta[('u0',0,'f0','i0','a')]==1)
    r,d,c=checked(s,w,m,v,rates)
    assert c['objective']['H']==c['objective']['D_beta']==c['objective']['actual']==0


@pytest.mark.parametrize('cpu',[20,40])
def test_tied_cpu_allocations_preserve_discrete_metrics_no_secondary_objective(full_case,cpu):
    s,w,rates=full_case(nodes=('a',),delay=1);m,v=build_stage2_model(s,w,reference(w),radio_coefficients=rates)
    key=('u0',0,'f0','i0','a');m.addCons(v.full.discrete.beta[key]==1)
    m.addCons(v.full.resources.terms[key].g==cpu/20)
    r,d,c=checked(s,w,m,v,rates)
    assert r.objective==0 and c['objective']['H']==c['objective']['D_beta']==0
    assert d['candidate']['deployment']['allocations'][0]['cpu_mips']==pytest.approx(cpu)


@pytest.mark.parametrize('corruption',['h_alpha','h_xi','d_beta','unknown','nan','objective','raw_cpu'])
def test_independent_corruption_rejection(full_case,corruption):
    s,_,rates=full_case(nodes=('a',));s=windows(s);w=build_trace(s).windows[1];p=previous(s)
    m,v=build_stage2_model(s,w,reference(w),p,radio_coefficients=rates);r,d,c=checked(s,w,m,v,rates)
    d=deepcopy(d);raw=d['solver_result']['values']
    if corruption in ('h_alpha','h_xi','d_beta'):
        key=next(k for k in raw if k.startswith(corruption+'['));raw[key]=2
    if corruption=='unknown':raw['unknown_aux[u0]']=0
    if corruption=='nan':raw[next(k for k in raw if k.startswith('h_alpha['))]=float('nan')
    if corruption=='objective':d['solver_result']['objective']=99
    if corruption=='raw_cpu':raw['g[u0,0,f0,i0,a]']=999
    bad=validate_stage2(s,w,d,reference(w),p,radio_coefficients=rates)
    assert not bad['valid']


def test_multiuser_multistage_normalization(full_case):
    s,_,rates=full_case(users=2,chain=('f0','f1'));s=windows(s);w=build_trace(s).windows[1]
    p=Deployment(0,tuple(AccessChoice(u,'a') for u in ('u0','u1')),
                   tuple(EgressChoice(u,'a','g0') for u in ('u0','u1')),
                   tuple(StageAllocation(u,k,InstanceKey(f,'i0','a'),20) for u in ('u0','u1') for k,f in enumerate(('f0','f1'))))
    ref=AssociationReference(1,p.access,p.egress);m,v=build_stage2_model(s,w,ref,p,radio_coefficients=rates)
    for k,b in v.full.discrete.alpha.items():m.addCons(b==int(k in {('u0','b'),('u1','a')}))
    for k,b in v.full.discrete.xi.items():m.addCons(b==int(k in {('u0','a','g0'),('u1','a','g0')}))
    selected={('u0',0,'f0','i1','a'),('u0',1,'f1','i0','a'),('u1',0,'f0','i0','a'),('u1',1,'f1','i0','a')}
    for k,b in v.full.discrete.beta.items():m.addCons(b==int(k in selected))
    r,d,c=checked(s,w,m,v,rates)
    assert c['objective']['H']==c['objective']['D_beta']==.25
    assert r.objective==pytest.approx(.5,abs=1e-8)


@pytest.mark.parametrize('valid_start',[False,True])
def test_runner_validates_complete_start_before_submission(full_case,valid_start):
    s,w,rates=full_case(nodes=('a',));first=run_stage1(s,w,started_at=0,clock=lambda:0)
    m,v=build_stage2_model(s,w,first.stage1_reference,radio_coefficients=rates)
    r,d,c=checked(s,w,m,v,rates)
    values=r.values if valid_start else {name:0 for name in r.values}
    out=run_stage2(s,w,first,started_at=0,clock=lambda:0,radio_coefficients=rates,
                   start_values=values,start_kind='complete')
    assert out.status=='validated'
    assert out.start.prevalidation==('feasible' if valid_start else 'infeasible')
    assert out.start.submission_attempted==valid_start


def test_nonoptimal_valid_incumbent_can_deploy_with_own_status(full_case):
    s,w,rates=full_case(nodes=('a',));first=run_stage1(s,w,started_at=0,clock=lambda:0)
    def adapter(model,**kw):
        r=solve(model,**kw)
        return replace(r,raw_status='timelimit',outcome='feasible_nonoptimal')
    out=run_stage2(s,w,first,started_at=0,clock=lambda:0,solve_fn=adapter,radio_coefficients=rates)
    assert out.status=='validated' and out.stage_result.raw_status=='timelimit'
    assert out.stage_result.absolute_gap==0 and out.stage_result.relative_gap is None


def test_late_independent_validation_withholds_final_deployment(full_case,monkeypatch):
    import stars_rl.optimization.stage2 as module
    s,w,rates=full_case(nodes=('a',));first=run_stage1(s,w,started_at=0,clock=lambda:0);t=[0]
    original=module.validate_stage2
    def delayed(*args,**kw):
        report=original(*args,**kw);t[0]=11;return report
    monkeypatch.setattr(module,'validate_stage2',delayed)
    out=run_stage2(s,w,first,started_at=0,clock=lambda:t[0],radio_coefficients=rates)
    assert out.validation['valid'] and out.export['candidate'] is not None
    assert out.status=='late' and out.final_deployment is None


def test_small_auxiliary_errors_cannot_accumulate_into_underreported_objective(full_case):
    s,w,rates=full_case(nodes=('a','b','c','d','e'))
    ref=reference(w);m,v=build_stage2_model(s,w,ref,radio_coefficients=rates)
    m.addCons(v.full.discrete.alpha[('u0','a')]==1)
    m.addCons(v.full.discrete.xi[('u0','a','g0')]==1)
    r,d,c=checked(s,w,m,v,rates)
    raw=d['solver_result']['values']
    keys=[k for k in raw if k.startswith(('h_alpha[','h_xi['))]
    for k in keys:raw[k]=-9e-9
    d['solver_result']['objective']=-9e-9*len(keys)/4
    bad=validate_stage2(s,w,d,ref,radio_coefficients=rates)
    assert not bad['valid'] and bad['deployment']['valid']
    assert all(row['passed'] for row in bad['objective']['residuals'])
    assert 'underestimates' in bad['errors'][0]
