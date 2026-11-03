"""Native methods, final-state persistence, shared inputs and initialization."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import pytest
import yaml

from stars_rl.baselines import METHODS
from stars_rl.simulation import simulate

pytestmark=pytest.mark.solver


@pytest.mark.parametrize('method',tuple(METHODS))
def test_three_windows_force_association_and_sf_move_then_retain(episode_trace,tmp_path,method):
    trace,rates=episode_trace();before=(trace.artifact_hash,deepcopy(rates))
    result=simulate(trace,method,total_budget_seconds=2,radio_coefficients_by_window=rates)
    assert result.status=='success',asdict(result)
    assert all(w.status=='committed' for w in result.windows)
    first,moved,retained=result.windows
    assert first.metrics.initial_setup and first.metrics.assignment_changes==first.metrics.access_switches==0
    assert (moved.metrics.access_switches,moved.metrics.egress_switches,moved.metrics.assignment_changes,moved.metrics.host_changes)==(1,1,1,1)
    assert retained.metrics.access_switches==retained.metrics.assignment_changes==0
    assert moved.previous_committed is first.committed_deployment
    assert retained.previous_committed is moved.committed_deployment
    assert result.last_committed is retained.committed_deployment
    assert result.last_committed.allocations[0].instance.satellite_id=='s1'
    assert (trace.artifact_hash,rates)==before
    if method=='mono-temporal':
        assert first.stages['monolithic'].objective_name=='Q'
        assert moved.stages['monolithic'].objective_name=='temporal'
        assert moved.commit_validation['objective']['actual']==3
        assert moved.final_outcome.start.prevalidation=='unknown_partial'
    elif method=='mono-delay':
        assert all(w.final_outcome.start is None for w in result.windows)
        assert all(w.stages['monolithic'].objective_name=='Q' for w in result.windows)
        # Independent literal Q for u0 at first window: access500km+GS300km,
        # minimum processing.12/100s, serialization12000/12e6s, D=.05s.
        expected=(800000/299792458+.0012+.001)/.05
        assert first.commit_validation['objective']['actual']==pytest.approx(expected,rel=0,abs=1e-8)
        assert first.stages['monolithic'].objective==pytest.approx(expected,rel=0,abs=1e-8)
        assert first.stages['monolithic'].absolute_gap<=1e-8
    elif method=='hier-only':
        assert all(w.stage1_outcome.original_previous is None for w in result.windows)
        assert all(w.stage1_outcome.start is None for w in result.windows)
        assert all(w.stages['stage1'].objective_name=='propagation' for w in result.windows)
        assert all(w.commit_validation['objective']['D_beta']==0 for w in result.windows)
        assert all(w.final_outcome.start.specified_variables==3 for w in result.windows)
    else:
        assert first.rho==.5 and moved.rho==1
        assert moved.stage1_outcome.original_previous is first.committed_deployment
        assert moved.commit_validation['objective']['H']==.5
    (tmp_path/f'episode_{method}.json').write_text(json.dumps(asdict(result),indent=2,allow_nan=False))


def test_no_change_fixed_half_ratio_and_isolated_repeated_calls(episode_trace):
    trace,rates=episode_trace(forced=False)
    a=simulate(trace,rho=.5,total_budget_seconds=2,radio_coefficients_by_window=rates)
    b=simulate(trace,rho=.5,total_budget_seconds=2,radio_coefficients_by_window=rates)
    assert a.status==b.status=='success'
    assert a.windows[0].previous_committed is b.windows[0].previous_committed is None
    assert all(w.metrics.access_switches==w.metrics.assignment_changes==0 for w in (*a.windows,*b.windows))
    assert all(w.rho==.5 for w in a.windows)


@pytest.mark.parametrize('method',tuple(METHODS))
def test_common_initial_state_separate_study_and_no_native_solve(episode_trace,method,tmp_path):
    trace,rates=episode_trace()
    native=simulate(trace,'mono-delay',total_budget_seconds=2,radio_coefficients_by_window=rates)
    assert native.status=='success',asdict(native)
    seed=deepcopy(native.windows[0].export);snapshot=deepcopy(seed)
    common=simulate(trace,method,total_budget_seconds=2,radio_coefficients_by_window=rates,initial_export=seed)
    assert common.status=='success' and common.initialization_study=='common_initial_state'
    assert native.initialization_study=='native_initialization'
    assert all(s.raw_status=='not_attempted' for s in common.windows[0].stages.values())
    assert common.windows[0].committed_deployment==native.windows[0].committed_deployment
    assert seed==snapshot
    (tmp_path/f'common_{method}.json').write_text(json.dumps(asdict(common),indent=2,allow_nan=False))


def test_baseline_yaml_matches_supported_packages():
    config=yaml.safe_load((Path(__file__).resolve().parents[2]/'configs/baselines.yaml').read_text())
    assert config['failure_policy']=='terminate_episode'
    assert set(config['methods'])==set(METHODS)
    for method,spec in METHODS.items():
        assert config['methods'][method]['initial_objective']==spec.initial_objective
        assert config['methods'][method]['later_objective']==spec.later_objective
        assert config['methods'][method]['prior_start']==spec.prior_start


@pytest.mark.parametrize('method',['MINLP','stars-random','stars-q'])
def test_no_invented_author_baseline_or_unimplemented_policy(episode_trace,method):
    trace,rates=episode_trace()
    with pytest.raises(ValueError,match='unsupported'):
        simulate(trace,method,radio_coefficients_by_window=rates)
