"""Failure termination preserves prior commit and distinct not-attempted rows."""
from dataclasses import asdict
from copy import deepcopy
import json
import pytest

from stars_rl.simulation import simulate,RuntimeServices
from stars_rl.optimization.backend import solve
from stars_rl.optimization.result import StageResult
from stars_rl.optimization.stage1 import run_stage1
from stars_rl.optimization.stage2 import run_stage2

pytestmark=pytest.mark.solver


def test_empty_visibility_stops_without_overwriting_state(episode_trace,tmp_path):
    trace,rates=episode_trace(empty_window=1)
    result=simulate(trace,total_budget_seconds=2,radio_coefficients_by_window=rates)
    assert result.status=='failed' and result.failure_window==1 and result.transition_valid
    success,failed,remaining=result.windows
    assert success.status=='committed' and failed.status=='failed' and remaining.status=='not_attempted'
    assert 'stage1_no_reference' in failed.reason
    assert failed.stages['stage2'].raw_status=='not_attempted'
    assert result.last_committed is success.committed_deployment
    assert failed.committed_deployment is None and failed.metrics.assignment_changes is None
    assert failed.metrics.outage==1 and remaining.metrics is None
    (tmp_path/'episode_failure.json').write_text(json.dumps(asdict(result),indent=2,allow_nan=False))


def test_full_infeasibility_not_stage1_failure(episode_trace):
    trace,rates=episode_trace(cpu=0)
    result=simulate(trace,total_budget_seconds=2,radio_coefficients_by_window=rates)
    first=result.windows[0]
    assert result.status=='failed' and result.transition_valid and result.last_committed is None
    assert first.stages['stage1'].has_incumbent
    assert first.stages['stage2'].raw_status=='infeasible'
    assert first.reason=='infeasible' and first.failure_stage=='stage2'


def test_bad_common_seed_is_infrastructure_not_network_failure(episode_trace):
    trace,rates=episode_trace()
    native=simulate(trace,'mono-delay',total_budget_seconds=2,radio_coefficients_by_window=rates)
    assert native.status=='success',asdict(native)
    seed=deepcopy(native.windows[0].export);seed['solver_result']['values']['unknown[u0]']=1
    result=simulate(trace,initial_export=seed,total_budget_seconds=2,radio_coefficients_by_window=rates)
    assert result.status=='infrastructure_error' and not result.transition_valid and result.last_committed is None
    assert result.windows[0].metrics is None


def test_exception_is_structured_abort_not_modeled_failure(episode_trace):
    trace,rates=episode_trace()
    def broken(*args,**kwargs):raise RuntimeError('controlled infrastructure error')
    result=simulate(trace,services=RuntimeServices(stage1=broken),radio_coefficients_by_window=rates)
    assert result.status=='infrastructure_error' and not result.transition_valid
    assert result.runtime_adapter=='injected_test_adapter'
    assert result.windows[0].error['type']=='RuntimeError'
    assert result.windows[0].stages['stage1'].raw_status=='infrastructure_error'
    assert all(w.status=='not_attempted' for w in result.windows[1:])


def test_stage1_timeout_without_incumbent_leaves_stage2_not_attempted(episode_trace):
    trace,rates=episode_trace()
    def absent(model,**kw):return StageResult('stage1',kw['objective_name'],kw['objective_units'],raw_status='timelimit')
    def first(*args,**kw):return run_stage1(*args,**kw,solve_fn=absent)
    def forbidden(*args,**kw):raise AssertionError('Stage II must not run without reference')
    result=simulate(trace,services=RuntimeServices(stage1=first,stage2=forbidden,clock=lambda:0),radio_coefficients_by_window=rates)
    w=result.windows[0]
    assert result.status=='failed' and result.transition_valid
    assert w.stages['stage1'].raw_status=='timelimit' and w.stages['stage2'].raw_status=='not_attempted'
    assert w.reason=='stage1_no_reference:timelimit'


def test_stage2_timeout_without_incumbent_is_not_infeasibility(episode_trace):
    trace,rates=episode_trace()
    def absent(model,**kw):return StageResult('stage2',kw['objective_name'],kw['objective_units'],raw_status='timelimit')
    def final(*args,**kw):return run_stage2(*args,**kw,solve_fn=absent)
    result=simulate(trace,services=RuntimeServices(stage2=final,clock=lambda:0),radio_coefficients_by_window=rates)
    w=result.windows[0]
    assert result.status=='failed' and result.transition_valid and w.reason=='timelimit'
    assert w.stages['stage1'].has_incumbent and not w.stages['stage2'].has_incumbent


def test_timed_out_valid_stage1_reference_and_one_shared_allowance(episode_trace):
    from dataclasses import replace
    trace,rates=episode_trace();clock=[0];calls=[]
    def first_solve(model,**kw):
        calls.append(('stage1',kw['time_limit']));r=solve(model,**kw);clock[0]+=1
        return replace(r,raw_status='timelimit',outcome='feasible_nonoptimal')
    def second_solve(model,**kw):
        calls.append(('stage2',kw['time_limit']));r=solve(model,**kw);clock[0]+=.2;return r
    def first(*args,**kw):return run_stage1(*args,**kw,solve_fn=first_solve)
    def final(*args,**kw):return run_stage2(*args,**kw,solve_fn=second_solve)
    result=simulate(trace,services=RuntimeServices(stage1=first,stage2=final,clock=lambda:clock[0]),radio_coefficients_by_window=rates)
    assert result.status=='success',asdict(result)
    for stage,allowance in calls:assert allowance==pytest.approx(1.5 if stage=='stage1' else 8.5)
    assert all(w.stages['stage1'].raw_status=='timelimit' for w in result.windows)
    assert all(w.stages['stage2'].has_incumbent for w in result.windows)
    assert all(w.elapsed_seconds==pytest.approx(1.2) for w in result.windows)
    assert result.windows[1].stages['stage1'].objective_units=='dimensionless'
    assert result.windows[0].stages['stage1'].objective_units=='seconds'


def test_late_commit_validation_cannot_persist_state(episode_trace,monkeypatch):
    import stars_rl.simulation as module
    trace,rates=episode_trace();clock=[0];original=module.validate_stage2
    def delayed(*args,**kw):
        checked=original(*args,**kw);clock[0]=11;return checked
    monkeypatch.setattr(module,'validate_stage2',delayed)
    result=simulate(trace,services=RuntimeServices(clock=lambda:clock[0]),radio_coefficients_by_window=rates)
    w=result.windows[0]
    assert result.status=='failed' and result.transition_valid and w.status=='late'
    assert w.commit_validation['valid'] and w.export['candidate'] is not None
    assert w.committed_deployment is result.last_committed is None


def test_numerical_rejection_not_outage_or_overwrite(episode_trace):
    trace,rates=episode_trace()
    def altered(s,w,*args,**kw):
        out=run_stage2(s,w,*args,**kw)
        if w.window_index==1:
            raw=out.export['solver_result']['values'];key=next(k for k in raw if k.startswith('h_xi['));raw[key]=2
        return out
    result=simulate(trace,services=RuntimeServices(stage2=altered,clock=lambda:0),radio_coefficients_by_window=rates)
    assert result.status=='numerical_rejection' and not result.transition_valid
    assert result.last_committed is result.windows[0].committed_deployment
    assert result.windows[1].metrics is None and result.windows[1].committed_deployment is None
    assert result.windows[2].status=='not_attempted'


def test_nonfinite_raw_output_aborts_without_becoming_network_infeasibility(episode_trace):
    trace,rates=episode_trace()
    def altered(*args,**kw):
        out=run_stage2(*args,**kw);raw=out.export['solver_result']['values']
        raw[next(k for k in raw if k.startswith('g['))]=float('nan');return out
    result=simulate(trace,services=RuntimeServices(stage2=altered,clock=lambda:0),radio_coefficients_by_window=rates)
    assert result.status=='infrastructure_error' and not result.transition_valid
    assert result.last_committed is None and result.windows[0].metrics is None


def test_missing_radio_table_is_structured_input_abort(episode_trace):
    trace,rates=episode_trace();del rates[1]
    result=simulate(trace,total_budget_seconds=2,radio_coefficients_by_window=rates)
    assert result.status=='infrastructure_error' and result.failure_window==1
    assert result.last_committed is result.windows[0].committed_deployment
    assert result.windows[1].error['type']=='KeyError'


def test_crossing_deadline_immediately_before_commit_check_skips_work(episode_trace,monkeypatch):
    import stars_rl.simulation as module
    trace,rates=episode_trace();state={'after':False,'reads':0}
    def clock():
        if not state['after']:return 0
        state['reads']+=1;return 9.9 if state['reads']==1 else 10.1
    def final(*args,**kw):
        out=run_stage2(*args,**kw);state['after']=True;return out
    def forbidden(*args,**kw):raise AssertionError('must not validate after deadline')
    monkeypatch.setattr(module,'validate_stage2',forbidden)
    result=simulate(trace,services=RuntimeServices(stage2=final,clock=clock),radio_coefficients_by_window=rates)
    assert result.windows[0].status=='late' and result.windows[0].error is None
    assert result.last_committed is None
