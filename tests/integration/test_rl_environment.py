"""Real commits, isolation, terminal semantics and constructed solver gate."""
from copy import deepcopy
from dataclasses import replace
import pytest

from stars_rl.simulation import simulate, RuntimeServices, advance_window
from stars_rl.rl.environment import StarsEnvironment, TransitionError
from stars_rl.rl.fixtures import constructed_report, tradeoff_fixture
from stars_rl.rl.state import observation
from stars_rl.topology.trace import build_trace

pytestmark=pytest.mark.solver


def test_rollout_matches_existing_pipeline_and_real_event_reward(episode_trace):
    trace,rates=episode_trace()
    before=trace.artifact_hash,deepcopy(rates)
    env=StarsEnvironment(trace,total_budget_seconds=3,radio_coefficients_by_window=rates)
    state,_=env.reset()
    assert state==(1,3,0,0,0,0)
    rewards=[]
    for action in (4,2,0):
        state,reward,terminated,truncated,info=env.step(action)
        rewards.append(reward)
        assert not truncated
    assert rewards==[0,-3,0] and terminated and state is None
    assert env.records[0].rho==.5
    assert info['learning_eligible']
    assert (trace.artifact_hash,rates)==before
    reference=simulate(trace,rho=1,total_budget_seconds=3,radio_coefficients_by_window=rates)
    assert [r.metrics for r in env.records]==[r.metrics for r in reference.windows]
    with pytest.raises(RuntimeError):env.step(1)
    assert env.reset()[0]==(1,3,0,0,0,0)
    assert env.records==()
    env.step(1)
    assert env.records[0].metrics.initial_setup


@pytest.mark.parametrize('failed_window',[0,1,2])
def test_modeled_failure_terminal_tail(episode_trace,failed_window):
    trace,rates=episode_trace(empty_window=failed_window)
    env=StarsEnvironment(trace,total_budget_seconds=3,radio_coefficients_by_window=rates)
    env.reset()
    for k in range(failed_window+1):
        state,reward,done,truncated,info=env.step(1)
    assert done and not truncated and state is None and info['failure']
    assert reward==pytest.approx(-4*sum(.95**j for j in range(3-failed_window)))
    assert len(env.records)==failed_window+1


def test_exception_has_no_learnable_reward(episode_trace):
    trace,rates=episode_trace()
    def broken(*args,**kwargs):raise RuntimeError('injected unavailable solver')
    env=StarsEnvironment(trace,radio_coefficients_by_window=rates,services=RuntimeServices(stage1=broken))
    env.reset()
    with pytest.raises(TransitionError):env.step(1)
    with pytest.raises(RuntimeError):env.step(1)


def test_invalid_action_does_not_advance_or_solve(episode_trace):
    trace,rates=episode_trace()
    env=StarsEnvironment(trace,radio_coefficients_by_window=rates)
    env.reset()
    with pytest.raises(ValueError):env.step(True)
    assert env.records==()
    with pytest.raises(ValueError):advance_window(trace,1)


def test_controlled_rollout_is_deterministic_and_budget_invariant(episode_trace):
    trace,rates=episode_trace()
    frozen=simulate(trace,rho=1,total_budget_seconds=3,radio_coefficients_by_window=rates)
    calls=[]
    def first(s,w,previous,**kw):
        calls.append(('first',w.window_index,kw['total_budget_seconds']))
        return deepcopy(frozen.windows[w.window_index].stage1_outcome)
    def second(s,w,reference,previous,**kw):
        calls.append(('second',w.window_index,kw['total_budget_seconds'],kw['weights']))
        return deepcopy(frozen.windows[w.window_index].final_outcome)
    env=StarsEnvironment(trace,total_budget_seconds=3,radio_coefficients_by_window=rates,
                         services=RuntimeServices(stage1=first,stage2=second,clock=lambda:0))
    rollouts=[]
    for _ in range(2):
        env.reset()
        rollouts.append([env.step(a) for a in (4,2,2)])
    assert rollouts[0]==rollouts[1]
    assert all(c[2]==3 for c in calls)
    assert [c[3] for c in calls if c[0]=='second']==[(1,.5),(1,1),(1,1)]*2


def test_timeout_failure_keeps_cause_and_has_tail_reward(episode_trace):
    from stars_rl.optimization.result import StageResult
    from stars_rl.optimization.stage1 import run_stage1
    trace,rates=episode_trace()
    def absent(model,**kw):
        return StageResult('stage1',kw['objective_name'],kw['objective_units'],raw_status='timelimit')
    def first(*args,**kw):return run_stage1(*args,**kw,solve_fn=absent)
    env=StarsEnvironment(trace,radio_coefficients_by_window=rates,
                         services=RuntimeServices(stage1=first,clock=lambda:0))
    env.reset()
    state,reward,done,_,info=env.step(0)
    assert state is None and done
    assert reward==pytest.approx(-4*(1+.95+.95**2))
    assert info['reason']=='stage1_no_reference:timelimit'
    assert env.records[0].stages['stage2'].raw_status=='not_attempted'


def test_no_future_non_geometry_reads(episode_trace):
    trace,_=episode_trace()
    # Poison next-window non-geometry metadata through a restricted geometry view.
    class GeometryOnly:
        def __init__(self,w):self._w=w
        def access_distance(self,*args):return self._w.access_distance(*args)
        def ground_distance(self,*args):return self._w.ground_distance(*args)
        def __getattr__(self,name):raise AssertionError('future non-geometry read: '+name)
    class View:
        scenario=trace.scenario
        windows=tuple(GeometryOnly(w) for w in trace.windows)
    from stars_rl.models import Deployment,AccessChoice,EgressChoice,StageAllocation,InstanceKey
    prior=Deployment(0,(AccessChoice('u0','s0'),),(EgressChoice('u0','s0','g0'),),
                     (StageAllocation('u0',0,InstanceKey('f0','i0','s0'),20),))
    assert observation(View(),1,prior)==observation(trace,1,prior)


@pytest.fixture(scope='module')
def gate():return constructed_report(10)


def test_real_constructed_gate_observability_alias_and_multistep(gate):
    assert gate['constructed_gate_passed']
    x,y,alias=gate['regimes']
    assert x['observation']==alias['observation']==[0,2,0,0,0,0]
    assert y['observation']==[0,2,0,0,2,0]
    for report in gate['regimes']:
        assert report['return_margin']==pytest.approx(1.9)
        assert len(report['sequences'])==25
        assert all(r['terminated'] and r['rewards'][0]==-1 for r in report['sequences'])
        for rows in report['classes'].values():
            assert all(r['status'] in ('optimal','infeasible') for r in rows)
            assert all(r['validation']['valid'] for r in rows if r['valid'])
        actions=report['sensitivity']['actions']
        assert len({r['pre_action_fingerprint'] for r in actions})==1
        for row in actions:
            assert row['stages']['stage2']['status']=='optimal'
            assert row['stages']['stage2']['absolute_gap']<=1e-8
            assert row['stages']['stage2']['objective']==pytest.approx(min(row['rho'],.5),abs=1e-8)
        assert report['objective_margins']['0.5']==0 # explicitly a tie, never evidence of an effect
    assert 0 in x['best_first_actions'] and 2 not in x['best_first_actions']
    assert 2 in y['best_first_actions'] and 0 not in y['best_first_actions']


def test_action_changes_only_objective_and_not_budget_or_core_rows(tmp_path):
    from stars_rl.optimization.stage1 import run_stage1
    from stars_rl.optimization.stage2 import build_stage2_model
    from stars_rl.config import deployment_from_dict
    from stars_rl.rl.actions import RATIOS
    trace,rates,initial=tradeoff_fixture()
    previous=deployment_from_dict(initial['candidate']['deployment'],trace.scenario)
    first=run_stage1(trace.scenario,trace.windows[1],previous,total_budget_seconds=10)
    signatures=[]
    for rho in RATIOS:
        model,_=build_stage2_model(trace.scenario,trace.windows[1],first.stage1_reference,previous,
                                  weights=(1,rho),radio_coefficients=rates[1])
        path=tmp_path/f'ratio-{rho}.cip'
        model.writeProblem(str(path))
        rows=path.read_text().split('CONSTRAINTS',1)[1]
        signatures.append((model.getNVars(),model.getNConss(),rows))
    assert all(s==signatures[0] for s in signatures)
