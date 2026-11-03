"""Stage I normalization/validator corruption and deterministic budget fakes."""
from dataclasses import replace
import pytest

from stars_rl.optimization.objectives import weights_checked
from stars_rl.optimization.stage1 import run_stage1, build_stage1_model
from stars_rl.optimization.result import StageResult
from stars_rl.validation.association import validate_association


def raw_case(s,w,p,reference_mode='original'):
    m,v=build_stage1_model(s,w,p,reference_mode=reference_mode)
    values={var.name:0.0 for var in m.getVars()}
    for u,sat in (('u0','s1'),('u1','s0')):values[f'alpha[{u},{sat}]']=1
    for u in ('u0','u1'):values[f'xi[{u},s0,g0]']=1
    values['d_alpha[u0,s0]']=values['d_alpha[u0,s1]']=1
    return values,v


def test_normalization_includes_unavailable_old_choice(temporal_case):
    s,w,p=temporal_case;values,v=raw_case(s,w,p)
    c=validate_association(s,w,values,.5,mode='temporal',reference=p,weights=(1,1))
    assert c['valid'] and c['deviations']==(.5,0)
    assert 'alpha[u0,s0]' not in values and values['d_alpha[u0,s0]']==1


@pytest.mark.parametrize('corruption',['nan','unknown','count','binary','deviation','objective'])
def test_independent_validator_rejects_injected_defects(temporal_case,corruption):
    s,w,p=temporal_case;values,v=raw_case(s,w,p);obj=.5
    if corruption=='nan':values['alpha[u0,s1]']=float('nan')
    if corruption=='unknown':values['z[s0,1]']=1
    if corruption=='count':values['alpha[u1,s1]']=1
    if corruption=='binary':values['alpha[u0,s1]']=.5
    if corruption=='deviation':values['d_alpha[u0,s0]']=0
    if corruption=='objective':obj=0
    assert not validate_association(s,w,values,obj,mode='temporal',reference=p,weights=(1,1))['valid']


@pytest.mark.parametrize('weights',[(-1,1),(float('nan'),1),(1,),('1',1)])
def test_bad_weights(weights):
    with pytest.raises(ValueError):weights_checked(weights)


def test_nonoptimal_incumbent_reference_preserves_status_and_gaps(temporal_case):
    s,w,p=temporal_case
    def fake(model,**kw):
        values,v=raw_case(s,w,p,'repaired')
        values['d_alpha[u0,s0]']=values['d_alpha[u0,s1]']=0
        return StageResult('stage1',kw['objective_name'],kw['objective_units'],raw_status='timelimit',
                           has_incumbent=True,objective=0,primal_bound=0,dual_bound=0,
                           absolute_gap=0,relative_gap=None,relative_gap_reason='zero_bound',values=values)
    out=run_stage1(s,w,p,clock=lambda:0,started_at=0,solve_fn=fake)
    assert out.status=='reference_ready' and out.stage_result.raw_status=='timelimit'
    assert out.stage_result.relative_gap is None and out.stage_result.relative_gap_reason=='zero_bound'


@pytest.mark.parametrize('cause',['timelimit','infeasible'])
def test_no_incumbent_never_uses_repair_as_reference(temporal_case,cause):
    s,w,p=temporal_case
    def fake(model,**kw):return StageResult('stage1',kw['objective_name'],kw['objective_units'],raw_status=cause)
    out=run_stage1(s,w,p,clock=lambda:0,started_at=0,solve_fn=fake)
    assert out.reason==cause and out.stage1_reference is None and out.repair_candidate is not None


def test_budget_includes_prior_work_and_passes_remaining_allowance(temporal_case):
    s,w,p=temporal_case;calls=[]
    def fake(model,**kw):
        calls.append(kw['time_limit']);return StageResult('stage1',kw['objective_name'],kw['objective_units'],raw_status='timelimit')
    out=run_stage1(s,w,p,started_at=0,clock=lambda:1,total_budget_seconds=10,solve_fn=fake)
    assert calls==[.5] and out.stage1_deadline_seconds==1.5
    calls.clear();out=run_stage1(s,w,p,started_at=0,clock=lambda:2,total_budget_seconds=10,solve_fn=fake)
    assert not calls and out.stage_result.raw_status=='not_attempted'


def test_late_solver_cannot_supply_reference(temporal_case):
    s,w,p=temporal_case;time=[0]
    def fake(model,**kw):
        values,v=raw_case(s,w,p,'repaired');values['d_alpha[u0,s0]']=values['d_alpha[u0,s1]']=0
        time[0]=2
        return StageResult('stage1',kw['objective_name'],kw['objective_units'],raw_status='optimal',has_incumbent=True,objective=0,values=values)
    out=run_stage1(s,w,p,started_at=0,clock=lambda:time[0],solve_fn=fake)
    assert out.stage1_reference is None and out.reason=='stage1_deadline_exceeded'


def test_late_validation_keeps_diagnostics_but_withholds_reference(temporal_case,monkeypatch):
    import stars_rl.optimization.stage1 as stage1
    s,w,p=temporal_case;time=[0]
    def fake(model,**kw):
        values,v=raw_case(s,w,p,'repaired');values['d_alpha[u0,s0]']=values['d_alpha[u0,s1]']=0
        return StageResult('stage1',kw['objective_name'],kw['objective_units'],raw_status='timelimit',has_incumbent=True,objective=0,values=values)
    original=stage1.validate_association
    def delayed(*args,**kwargs):
        report=original(*args,**kwargs);time[0]=2;return report
    monkeypatch.setattr(stage1,'validate_association',delayed)
    out=run_stage1(s,w,p,started_at=0,clock=lambda:time[0],solve_fn=fake)
    assert out.validation['valid'] and out.stage1_reference is None
    assert out.stage_result.validation=='valid' and out.reason=='stage1_deadline_exceeded'


def test_repair_time_exhaustion_prevents_model_build(temporal_case,monkeypatch):
    import stars_rl.optimization.stage1 as stage1
    s,w,p=temporal_case;time=[0];original=stage1.repair_previous
    def delayed(*args):
        result=original(*args);time[0]=2;return result
    def forbidden(*args):raise AssertionError('model must not build after deadline')
    monkeypatch.setattr(stage1,'repair_previous',delayed)
    monkeypatch.setattr(stage1,'build_association_model',forbidden)
    out=run_stage1(s,w,p,started_at=0,clock=lambda:time[0])
    assert out.stage1_reference is None and out.stage_result.raw_status=='not_attempted'


def test_malformed_solver_incumbent_aborts_instead_of_network_failure(temporal_case):
    s,w,p=temporal_case
    def fake(model,**kw):
        return StageResult('stage1',kw['objective_name'],kw['objective_units'],raw_status='optimal',has_incumbent=True,objective=float('nan'),values={})
    with pytest.raises(ValueError,match='malformed'):
        run_stage1(s,w,p,clock=lambda:0,started_at=0,solve_fn=fake)


def test_validator_has_no_optimization_imports():
    import ast
    from pathlib import Path
    path=Path(__file__).resolve().parents[2]/'src/stars_rl/validation/association.py'
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node,ast.ImportFrom):
            assert not (node.module or '').startswith(('stars_rl.optimization','pyscipopt'))
        if isinstance(node,ast.Import):
            assert not any(n.name.startswith(('stars_rl.optimization','pyscipopt')) for n in node.names)


def test_missing_repair_and_explicit_propagation_mode(temporal_case):
    s,w,p=temporal_case
    empty=replace(w,access_distances_m=((None,None,None),(None,None,None)))
    out=run_stage1(s,empty,p,clock=lambda:0,started_at=0)
    assert out.reason=='no_visible_repair_reference' and out.stage1_reference is None
    # Hierarchy-only later windows may explicitly request propagation without
    # a temporal prior; default temporal mode must not silently do this.
    with pytest.raises(ValueError,match='committed'):
        build_stage1_model(s,w)
    m,v=build_stage1_model(s,w,objective_mode='propagation')
    assert v.objective_reference is None


def test_clock_crossing_deadline_before_repair_prevents_work(temporal_case,monkeypatch):
    import stars_rl.optimization.stage1 as stage1
    s,w,p=temporal_case;times=iter((0,2))
    def clock():return next(times,2)
    def forbidden(*args):raise AssertionError('repair must not run after deadline')
    monkeypatch.setattr(stage1,'repair_previous',forbidden)
    out=run_stage1(s,w,p,started_at=0,clock=clock)
    assert out.stage1_reference is None and out.stage_result.raw_status=='not_attempted'
