"""Frozen adapters, group weighting and validation-only deterministic ties."""
from copy import deepcopy
import pytest

from stars_rl.experiments.evaluate import grouped_score,select_fixed,claim_test_set
from stars_rl.rl.actions import RATIOS
from stars_rl.rl.policies import FixedRatio,FrozenQPolicy
from stars_rl.rl.q_learning import TabularQ


@pytest.mark.parametrize('rho',RATIOS)
def test_fixed_ratio_initial_force_and_grid(rho):
    p=FixedRatio(rho)
    assert p.select((1,3,0,0,0,0))==1
    assert p.select((0,2,0,0,0,0))==RATIOS.index(rho)


def test_q_adapter_copies_and_preserves_all_learner_state():
    learner=TabularQ();s=(0,2,0,0,0,0);learner.q[s]=[1,0,1,0,0]
    before=deepcopy(learner.state_dict());policy=FrozenQPolicy(learner,'frozen')
    assert policy.select(s)==0 and policy.select((0,1,2,2,2,2))==1
    assert learner.state_dict()==before
    learner.q[s][0]=99
    assert policy.select(s)==0
    policy._learner.exploration_steps+=1
    with pytest.raises(ValueError,match='mutated'):policy.select(s)


def test_equal_weight_per_group_includes_failed_episodes():
    rows=[dict(component_id=g,penalized_score=score,status=status) for g,score,status in
          [('a',1,'success'),('a',3,'failed'),('b',10,'failed')]]
    result=grouped_score(rows)
    assert result['mean']==6 and result['groups']=={'a':2,'b':10}
    assert result['failures']==2 and result['completion_rate']==pytest.approx(1/3)
    with pytest.raises(ValueError,match='cannot be scored'):
        grouped_score([dict(component_id='a',penalized_score=0,status='infrastructure_error')])


def test_all_five_validation_ratios_and_tie_preference():
    assert select_fixed({r:0 for r in RATIOS})==.5
    assert select_fixed({r:0 if r in (.25,1) else 1 for r in RATIOS})==.25
    assert select_fixed({r:0 if r==2 else 1 for r in RATIOS})==2
    with pytest.raises(ValueError):select_fixed({.5:0})


def test_one_shot_test_claim(tmp_path):
    claim_test_set(tmp_path,'frozen','controlled_test_adapter')
    with pytest.raises(ValueError,match='already claimed'):claim_test_set(tmp_path,'new','controlled_test_adapter')
