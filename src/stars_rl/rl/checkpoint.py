"""Strict atomic episode-boundary checkpoints; no active deployment or pickle."""
from dataclasses import asdict
import random

from stars_rl.experiments.manifest import atomic_json,digest,read_json
from .actions import RATIOS
from .q_learning import TabularQ
from .state import OBSERVATION_SCHEMA


def contract(horizons):
    if not horizons or any(type(h) is not int or h<1 for h in horizons):raise ValueError('positive horizons required')
    observation=dict(schema=OBSERVATION_SCHEMA,fields=['initial','remaining','demand','host_pressure','loss','previous_churn'],
        horizons=list(horizons),upper_inclusive_bins=[[.25,.75],[.5,.9],[0,.5],[0,1/3]],
        zero_cpu='global overload; empty individual host zero',geometry='current and next only',
        host_pressure='current minimum CPU plus previous active-instance overhead; no optimized CPU')
    actions=dict(ratios=list(RATIOS),unseen=1,initial_forced=1,tie_absolute_tolerance=1e-12,tie_preference=[1,0,2,3,4])
    reward=dict(discount=.95,success='-(D_alpha+D_xi+D_beta)',initial=0,
                failure='-4*sum(discount**j for j in range(remaining))',terminal_observation=None,truncated=False)
    return dict(observation=observation,actions=actions,reward=reward,
                hashes={k:digest(v) for k,v in [('observation',observation),('actions',actions),('reward',reward)]})


def save_boundary(path,learner,*,next_episode_index,episode_order,group_order,compatibility,order_rng_state):
    state=dict(schema_version=1,scope='completed_episode_boundary',active_deployment=None,
               next_episode_index=next_episode_index,episode_order=episode_order,group_order=group_order,
               compatibility=compatibility,learner=learner.state_dict(),order_rng_state=order_rng_state)
    # Validate the same JSON representation that will be read after a restart.
    import json
    payload=json.loads(json.dumps(state,allow_nan=False))
    _validate(payload,compatibility)
    atomic_json(path,payload|{'state_hash':digest(payload)})


def _validate(data,expected):
    fields={'schema_version','scope','active_deployment','next_episode_index','episode_order','group_order',
            'compatibility','learner','order_rng_state'}
    if type(data) is not dict or set(data)!=fields or data['schema_version']!=1 or data['scope']!='completed_episode_boundary':
        raise ValueError('invalid boundary schema')
    if data['active_deployment'] is not None:raise ValueError('mid-episode continuation unsupported')
    if data['compatibility']!=expected:raise ValueError('incompatible checkpoint configuration/schema/code/runtime')
    order=data['episode_order'];groups=data['group_order'];index=data['next_episode_index']
    if type(order) is not list or not order or type(groups) is not list or len(groups)!=len(order):
        raise ValueError('invalid trace/group ordering')
    if any(type(v) is not str or not v for v in order+groups):raise ValueError('invalid ordering identity')
    if type(index) is not int or not 0<=index<=len(order):raise ValueError('invalid episode boundary index')
    if order!=expected['episode_order'] or groups!=expected['group_order']:raise ValueError('ordering changed')
    learner=TabularQ.from_state_dict(data['learner'])
    if learner.updates!=learner.exploration_steps:raise ValueError('boundary contains unmatched action/update counters')
    if asdict(learner.config)!=expected['learning_config']:raise ValueError('learning configuration changed')
    allowed=set(expected['contract']['observation']['horizons'])
    if any(state[1]>=max(allowed) for state in learner.q):raise ValueError('Q horizon exceeds learnable episode states')
    def tuples(value):return tuple(tuples(v) for v in value) if isinstance(value,(list,tuple)) else value
    rng=random.Random()
    try:rng.setstate(tuples(data['order_rng_state']))
    except (TypeError,ValueError,OverflowError) as exc:raise ValueError('invalid ordering RNG state') from exc
    return learner,rng


def load_boundary(path,expected):
    data=read_json(path)
    if type(data) is not dict or 'state_hash' not in data:raise ValueError('missing boundary integrity hash')
    claimed=data.pop('state_hash')
    if claimed!=digest(data):raise ValueError('boundary integrity hash mismatch')
    learner,rng=_validate(data,expected)
    return data,learner,rng
