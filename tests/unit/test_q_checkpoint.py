"""Atomic strict checkpoint compatibility and semantic corruption checks."""
from copy import deepcopy
from dataclasses import asdict
import random
import pytest

from stars_rl.experiments.manifest import atomic_json,digest,read_json
from stars_rl.rl.checkpoint import contract,load_boundary,save_boundary
from stars_rl.rl.q_learning import TabularQ


@pytest.fixture
def checkpoint(tmp_path):
    learner=TabularQ();state=(0,2,0,0,0,0)
    action=learner.select(state,training=True);learner.update(state,action,-1,None,True)
    expected=dict(contract=contract([3]),learning_config=asdict(learner.config),episode_order=['trace'],group_order=['group'])
    path=tmp_path/'boundary.json'
    save_boundary(path,learner,next_episode_index=1,episode_order=['trace'],group_order=['group'],
                  compatibility=expected,order_rng_state=random.Random(23).getstate())
    return path,learner,expected


def test_round_trip_all_state(checkpoint):
    path,learner,expected=checkpoint
    state,loaded,rng=load_boundary(path,expected)
    assert loaded.state_dict()==learner.state_dict()
    assert state['next_episode_index']==1 and state['active_deployment'] is None
    assert rng.random()==random.Random(23).random()


@pytest.mark.parametrize('field',['reward','actions','observation'])
def test_incompatible_contract_hash(checkpoint,field):
    path,_,expected=checkpoint
    changed=deepcopy(expected);changed['contract']['hashes'][field]='different'
    with pytest.raises(ValueError,match='incompatible'):load_boundary(path,changed)


@pytest.mark.parametrize('field,value',[('active_deployment',{}),('next_episode_index',2),('order_rng_state',[0]),
    ('episode_order',['other']),('group_order',['other'])])
def test_semantic_corruption_rejected_even_with_recomputed_hash(checkpoint,field,value):
    path,_,expected=checkpoint
    data=read_json(path);data.pop('state_hash');data[field]=value
    atomic_json(path,data|{'state_hash':digest(data)})
    with pytest.raises(ValueError):load_boundary(path,expected)


def test_hash_and_nonfinite_json_rejected(checkpoint):
    path,_,expected=checkpoint
    data=read_json(path);data['learner']['q'][0]['values'][0]=99
    atomic_json(path,data)
    with pytest.raises(ValueError,match='integrity'):load_boundary(path,expected)
    path.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError,match='duplicate'):load_boundary(path,expected)
    path.write_text('{"x":NaN}')
    with pytest.raises(ValueError,match='nonfinite'):load_boundary(path,expected)
