"""Literal TD targets, seeded exploration, initialization and frozen selection."""
from copy import deepcopy
import random
import pytest

from stars_rl.rl.q_learning import LearningConfig,TabularQ

S=(0,2,0,0,0,0)
NEXT=(0,1,0,0,0,1)


def test_hand_computed_update_and_terminal_no_bootstrap():
    learner=TabularQ()
    learner.q[S]=[2.,0,0,0,0]
    learner.q[NEXT]=[4.,1,0,0,0]
    # O-QUPDATE literal arithmetic oracle (independent of network reward range).
    assert learner.update(S,0,3,NEXT,False)==pytest.approx(2.48)
    learner.q[S][0]=2
    assert learner.update(S,0,3,None,True)==pytest.approx(2.1)


def test_terminal_initialization_and_invalid_horizon():
    learner=TabularQ()
    with pytest.raises(ValueError):learner.update((1,3,0,0,0,0),1,0,S,False)
    with pytest.raises(ValueError):learner.update(S,1,0,NEXT,True)
    with pytest.raises(ValueError):learner.update(S,1,0,S,False)
    with pytest.raises(ValueError):learner.update(S,1,float('nan'),None,True)


def test_frozen_greedy_evaluation_never_mutates_rng_q_or_counters():
    learner=TabularQ()
    before=deepcopy(learner.state_dict())
    assert learner.select(S)==1
    assert learner.state_dict()==before and learner.q=={}
    learner.q[S]=[3,0,3,0,0]
    before=deepcopy(learner.state_dict())
    assert learner.select(S)==0
    assert learner.state_dict()==before


def test_seeded_exploration_schedule_and_initial_exclusion():
    global_before=random.getstate()
    config=LearningConfig(seed=17,epsilon_decay_steps=2,epsilon_end=.2)
    a,b=TabularQ(config),TabularQ(config)
    before=a.state_dict()
    assert a.select((1,3,0,0,0,0),training=True)==1
    assert a.state_dict()==before
    assert a.epsilon==1
    x=a.select(S,training=True)
    assert a.epsilon==pytest.approx(.6)
    sequence=[x]+[a.select(S,training=True) for _ in range(40)]
    assert sequence==[b.select(S,training=True) for _ in range(41)]
    assert a.epsilon==pytest.approx(.2)
    assert sum(a.action_counts)==a.exploration_steps==41
    assert random.getstate()==global_before


@pytest.mark.parametrize('kwargs',[{'seed':True},{'epsilon_decay_steps':0},{'epsilon_start':.1,'epsilon_end':.2},
    {'learning_rate':0},{'discount':.9},{'epsilon_start':float('inf')},{'learning_rate':True}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):LearningConfig(**kwargs)


def test_rng_and_table_round_trip_and_invalid_rows():
    a=TabularQ();action=a.select(S,training=True);a.update(S,action,-1,NEXT,False)
    data=a.state_dict();b=TabularQ.from_state_dict(data)
    assert b.state_dict()==data
    assert [a.select(S,training=True) for _ in range(20)]==[b.select(S,training=True) for _ in range(20)]
    broken=deepcopy(data);broken['q'].append(broken['q'][0])
    with pytest.raises(ValueError):TabularQ.from_state_dict(broken)
    broken=deepcopy(data);broken['q'][0]['values'][0]=float('inf')
    with pytest.raises(ValueError):TabularQ.from_state_dict(broken)
