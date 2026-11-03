"""Deterministic runtime adapters; no wall-clock timeout races."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from stars_rl.optimization.result import StageResult
from stars_rl.optimization.stage1 import AssociationReference
from stars_rl.optimization.stage2 import run_stage2
from stars_rl.models import AccessChoice, EgressChoice


def stage1(w):
    ref=AssociationReference(w.window_index,(AccessChoice('u0','s1'),AccessChoice('u1','s0')),
                              tuple(EgressChoice(u,'s0','g0') for u in ('u0','u1')))
    return SimpleNamespace(status='reference_ready',reason='validated_association_incumbent',stage1_reference=ref,
                           stage_result=StageResult('stage1','normalized_association_deviation','dimensionless',validation='valid'),
                           validation={'valid':True})


@pytest.mark.parametrize('cause',['timelimit','infeasible'])
def test_shared_budget_and_no_incumbent_cause(temporal_case,cause):
    s,w,p=temporal_case;calls=[]
    def fake(model,**kw):
        calls.append(kw['time_limit'])
        return StageResult('stage2',kw['objective_name'],kw['objective_units'],raw_status=cause)
    out=run_stage2(s,w,stage1(w),p,started_at=0,total_budget_seconds=10,clock=lambda:2,solve_fn=fake)
    assert calls==[7.5]  # Unused Stage I time is not subtracted again.
    assert out.reason==cause and out.final_deployment is None
    assert out.validation['status']=='no_incumbent'


def test_no_stage1_reference_means_stage2_not_attempted(temporal_case,monkeypatch):
    import stars_rl.optimization.stage2 as module
    s,w,p=temporal_case;first=stage1(w);first.status='stage1_no_reference';first.reason='timelimit'
    def forbidden(*args,**kw):raise AssertionError('no model without Stage I reference')
    monkeypatch.setattr(module,'build_stage2_model',forbidden)
    out=run_stage2(s,w,first,p,started_at=0,clock=lambda:0)
    assert out.stage_result.raw_status=='not_attempted' and out.reason=='stage1_no_reference:timelimit'


def test_solve_cutoff_prevents_build_and_no_extra_budget(temporal_case,monkeypatch):
    import stars_rl.optimization.stage2 as module
    s,w,p=temporal_case
    def forbidden(*args,**kw):raise AssertionError('deadline expired')
    monkeypatch.setattr(module,'build_stage2_model',forbidden)
    out=run_stage2(s,w,stage1(w),p,started_at=0,clock=lambda:9.6)
    assert out.stage_result.raw_status=='not_attempted' and out.final_deployment is None
    assert out.reason=='deadline_before_build'


def test_late_solver_retains_status_not_final_state(temporal_case):
    s,w,p=temporal_case;t=[2]
    def fake(model,**kw):
        t[0]=11
        return StageResult('stage2',kw['objective_name'],kw['objective_units'],raw_status='timelimit')
    out=run_stage2(s,w,stage1(w),p,started_at=0,clock=lambda:t[0],solve_fn=fake)
    assert out.status=='late' and out.stage_result.raw_status=='timelimit' and out.final_deployment is None


@pytest.mark.parametrize('bad_values',[{'tau[u0,0,f0,i0,s0]':0},{'alpha[u0,s1]':.5},{'unknown[u0]':1}])
def test_incompatible_partial_start_not_submitted(temporal_case,bad_values):
    s,w,p=temporal_case
    with pytest.raises(ValueError,match='compatible binaries'):
        run_stage2(s,w,stage1(w),p,started_at=0,clock=lambda:0,start_values=bad_values)


def test_reference_validation_and_previous_chronology(temporal_case):
    from stars_rl.optimization.stage2 import build_stage2_model
    s,w,p=temporal_case;ref=stage1(w).stage1_reference
    with pytest.raises(ValueError,match='window'):
        build_stage2_model(s,w,replace(ref,window_index=0),p)
    with pytest.raises(ValueError,match='invisible'):
        build_stage2_model(s,w,replace(ref,access=p.access),p)
    with pytest.raises(ValueError,match='precede'):
        build_stage2_model(s,w,ref,replace(p,window_index=1))
    with pytest.raises(ValueError,match='previous'):
        build_stage2_model(s,w,ref)
    # Explicit hierarchy-only objective can omit temporal placement state.
    m,v=build_stage2_model(s,w,ref,weights=(1,0))
    assert not v.d_beta
