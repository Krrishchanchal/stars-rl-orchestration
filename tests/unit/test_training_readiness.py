"""Scientific gates fail closed; compute plan includes every declared phase."""
from types import SimpleNamespace
import pytest

from stars_rl.rl.readiness import assess_readiness,compute_estimate,_positive_effect
from stars_rl.rl.actions import RATIOS
from stars_rl.experiments.manifest import atomic_json


def trace():
    return SimpleNamespace(windows=[0,1,2],content_hash='trace',scenario=SimpleNamespace(orbit=None))


def test_compute_includes_initialization_sensitivity_validation_and_evaluation():
    plan=compute_estimate([trace()],3,2)
    assert plan['phase_windows']==dict(training=9,sensitivity=15,validation=3,evaluation=18)
    assert plan['total_solver_call_upper_bound']==323
    assert plan['decision_budget_upper_seconds']==2420
    assert plan['initialization_included']
    assert plan['post_decision_io_generation_and_plotting_seconds'] is None


@pytest.mark.parametrize('episodes,budget',[(0,1),(True,2),(1,-1),(1,float('nan'))])
def test_invalid_compute_inputs(episodes,budget):
    with pytest.raises(ValueError):compute_estimate([trace()],episodes,budget)


def test_missing_or_flag_only_gate_cannot_launch(tmp_path):
    gate=assess_readiness([trace()],2,{},episodes=100)
    assert not gate['passed'] and len(gate['reasons'])==3
    atomic_json(tmp_path/'fake.json',{'passed':True})
    with pytest.raises(ValueError):assess_readiness([trace()],2,{},tmp_path/'fake.json')


def test_no_action_evidence_is_not_a_positive_effect():
    assert not _positive_effect(trace(),{'windows':[]},2)


def test_necessary_physical_failure_is_retained(monkeypatch):
    t=trace();t.scenario.orbit=True
    monkeypatch.setattr('stars_rl.rl.readiness.preflight',lambda *args:{'passed':False})
    gate=assess_readiness([t],60,{})
    assert not gate['passed'] and 'necessary' in gate['reasons'][0]
