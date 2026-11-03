"""Hand-computed fixed observation/action/reward contract."""
from dataclasses import replace
from types import SimpleNamespace
import math
import pytest

from stars_rl.rl.actions import RATIOS, ratio, greedy_action
from stars_rl.rl.reward import failure_reward, success_reward
from stars_rl.rl.state import observation, _bin
from stars_rl.topology.trace import build_trace


@pytest.mark.parametrize('action,expected',enumerate((.25,.5,1,2,4)))
def test_action_grid(action,expected):
    assert ratio(action)==expected


@pytest.mark.parametrize('action',[-1,5,True,False,.5,'1',None])
def test_invalid_actions(action):
    with pytest.raises(ValueError):ratio(action)


def test_unseen_and_tie_policy():
    assert greedy_action() == greedy_action([0]*5) == 1
    assert greedy_action([1,0,1,0,0])==0
    assert greedy_action([0,1-5e-13,1,0,0])==1
    assert greedy_action([0,1-2e-12,1,0,0])==2
    with pytest.raises(ValueError):greedy_action([math.nan]*5)


@pytest.mark.parametrize('remaining',[1,2,14])
@pytest.mark.parametrize('discount',[0,.95,1])
def test_failure_return_strictly_worse_than_every_successful_tail(remaining,discount):
    tail=sum(discount**j for j in range(remaining))
    assert failure_reward(remaining,discount)==pytest.approx(-4*tail)
    assert failure_reward(remaining,discount)<-3*tail


def test_fixed_actual_event_reward():
    assert success_reward(SimpleNamespace(d_alpha=.5,d_xi=1,d_beta=.25))==-1.75
    assert success_reward(SimpleNamespace(d_alpha=0,d_xi=0,d_beta=0))==0
    with pytest.raises(ValueError):success_reward(SimpleNamespace(d_alpha=None,d_xi=None,d_beta=None))


@pytest.mark.parametrize('low,high',[(.25,.75),(.5,.9),(0,.5),(0,1/3)])
def test_closed_bin_edges(low,high):
    assert [_bin(v,low,high) for v in (low,math.nextafter(low,math.inf),high,math.nextafter(high,math.inf))]==[0,1,1,2]


def test_observation_literal_demand_overhead_and_cpu_independence(temporal_case):
    s,_,previous=temporal_case
    trace=build_trace(s)
    # Demand: 2*(10+20)+3*(10+20)=150; global 150/500=.3.
    # Old host s0: 150 + shared f0/f1 overhead 15 =165/200=.825.
    state=observation(trace,1,previous,1)
    assert state[:4]==(0,2,1,1)
    assert state[5]==1
    changed=replace(previous,allocations=tuple(replace(a,cpu_mips=199) for a in previous.allocations))
    assert observation(trace,1,changed,1)==state
    assert observation(trace,0)==(1,3,1,0,0,0)
    assert observation(trace,2,previous,3)[1:2]==(1,)
    assert observation(trace,1,previous,3)[5]==2


def test_zero_cpu_sentinels(temporal_case):
    s,_,previous=temporal_case
    s=replace(s,satellites=tuple(replace(n,cpu_capacity_mips=0) for n in s.satellites))
    trace=build_trace(s)
    assert observation(trace,0)[2:4]==(2,2)
    assert observation(trace,1,previous)[3]==2


def test_empty_zero_cpu_host_is_not_overload(temporal_case):
    s,_,previous=temporal_case
    assert observation(build_trace(s),1,previous)[3]==1
