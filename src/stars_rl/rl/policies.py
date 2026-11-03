"""Evaluation-only adapters: fixed ratios and immutable checkpoint Q policies."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from stars_rl.experiments.manifest import checked_path,digest,file_hash,read_json
from stars_rl.topology.trace import load_trace
from .actions import DEFAULT_ACTION,RATIOS
from .checkpoint import contract,load_boundary


class PolicyUnavailable(ValueError):
    """No compatible completed scientific training checkpoint is available."""


class FixedRatio:
    def __init__(self,rho):
        if type(rho) not in (int,float) or rho not in RATIOS:raise ValueError('frozen ratio required')
        self.rho=rho;self.policy_id='fixed-'+str(float(rho))
    def select(self,state):return DEFAULT_ACTION if state[0] else RATIOS.index(self.rho)
    def assert_frozen(self):pass


class FrozenQPolicy:
    def __init__(self,learner,policy_id):
        self._learner=deepcopy(learner);self.policy_id=policy_id
        self._fingerprint=digest(self._learner.state_dict())
    def select(self,state):
        self.assert_frozen()
        result=self._learner.select(state,training=False)
        self.assert_frozen()
        return result
    def assert_frozen(self):
        if digest(self._learner.state_dict())!=self._fingerprint:raise ValueError('evaluation mutated frozen policy/Q/RNG/counters')


def load_policy(run,split,profile,budget,*,controlled=False):
    folder=Path(run).resolve();manifest=read_json(folder/'manifest.json')
    if manifest.get('status')!='completed':raise PolicyUnavailable('policy training run is not completed')
    expected=manifest['compatibility'];adapter=expected['runtime_adapter']
    if adapter!='standard' and not controlled:raise PolicyUnavailable('controlled test checkpoints are not scientific trained policies')
    if controlled and adapter!='controlled_test_adapter':raise PolicyUnavailable('controlled diagnostics cannot relabel a standard policy')
    if not controlled and not expected['readiness'].get('passed'):raise PolicyUnavailable('training readiness was not passed')
    if expected['budget']!=budget:raise PolicyUnavailable('training/evaluation solver budgets differ')
    for name,value in manifest['input_hashes'].items():
        if file_hash(checked_path(folder,name))!=value:raise ValueError('policy source/input integrity mismatch: '+name)
    name=manifest['active_boundary'];path=checked_path(folder,name)
    if file_hash(path)!=manifest['active_boundary_file_hash']:raise ValueError('policy checkpoint file hash mismatch')
    boundary,learner,_=load_boundary(path,expected)
    if boundary['next_episode_index']!=len(boundary['episode_order']):raise PolicyUnavailable('policy is not at its final planned episode boundary')
    if len(manifest['completed_episodes'])!=boundary['next_episode_index']:raise ValueError('policy completion count differs')
    if file_hash(folder/'summary.json')!=manifest['summary_hash']:raise ValueError('policy training summary integrity mismatch')
    for accepted in manifest['completed_episodes']:
        summary_path=checked_path(folder,accepted['summary'])
        if file_hash(summary_path)!=accepted['sha256']:raise ValueError('policy accepted episode integrity mismatch')
        for step in read_json(summary_path)['steps']:
            if file_hash(checked_path(summary_path.parent,step['artifact']))!=step['artifact_hash']:
                raise ValueError('policy accepted step integrity mismatch')
    if not set(expected['episode_order']).issubset(split['partitions']['train']):
        raise PolicyUnavailable('checkpoint training inputs do not match the frozen training partition')
    for key,group in zip(boundary['episode_order'],boundary['group_order']):
        if split['traces'][key]['group_id']!=group:raise ValueError('checkpoint training group lineage differs')
    training_traces=[]
    for relative in manifest['input_hashes']:
        if relative.startswith('trace-') and relative.endswith('.json'):
            training_traces.append(load_trace(checked_path(folder,relative)))
    pool={t.content_hash for t in training_traces}
    if pool!=set(split['partitions']['train']):raise PolicyUnavailable('declared training input pool differs from the frozen training partition')
    if not set(expected['episode_order']).issubset(pool):raise ValueError('checkpoint trace snapshots differ')
    if any(t.artifact_hash!=split['traces'][t.content_hash]['artifact_hash'] for t in training_traces):
        raise PolicyUnavailable('training provenance/lineage artifact was relabeled after fitting')
    if sorted(t.artifact_hash for t in training_traces)!=sorted(expected['trace_artifact_hashes']):
        raise ValueError('checkpoint training artifact identities differ')
    frozen_contract=expected['contract']
    if contract(frozen_contract['observation']['horizons'])!=frozen_contract:raise PolicyUnavailable('policy observation/action/reward schema is incompatible')
    horizons=set(frozen_contract['observation']['horizons'])
    if any(row['horizon'] not in horizons for row in split['traces'].values()):
        raise PolicyUnavailable('evaluation horizon differs from frozen policy schema')
    # C17 evaluation code is new. Compare the actual optimizer/environment code,
    # rather than demanding the whole evaluation source hash equal C16's hash.
    previous=expected['runtime_profile']
    for key in ('python','dependencies','backend','solver_parameters'):
        if previous[key]!=profile[key]:raise PolicyUnavailable('policy runtime/solver configuration mismatch: '+key)
    core=lambda n:n.startswith(('optimization/','validation/','physics/','topology/')) or n in (
        'models.py','config.py','metrics.py','simulation.py','baselines.py','rl/environment.py','rl/state.py',
        'rl/actions.py','rl/reward.py','rl/q_learning.py')
    old=manifest['environment']['source_files'];new=profile['source_files']
    if {k:v for k,v in old.items() if core(k)}!={k:v for k,v in new.items() if core(k)}:
        raise PolicyUnavailable('optimizer/environment source changed since policy training')
    config=asdict(learner.config);seed=config.pop('seed')
    configuration_id=digest(dict(learning=config,training_episode_count=boundary['next_episode_index']))
    policy_id='q-'+configuration_id[:12]+'-seed-'+str(seed)
    policy=FrozenQPolicy(learner,policy_id)
    metadata=dict(policy_id=policy_id,configuration_id=configuration_id,learning_config=config,seed=seed,
                  training_episode_count=boundary['next_episode_index'],
                  checkpoint_hash=file_hash(path),checkpoint=read_json(path),training_manifest=manifest,
                  training_manifest_hash=file_hash(folder/'manifest.json'),scope=adapter)
    return policy,metadata
