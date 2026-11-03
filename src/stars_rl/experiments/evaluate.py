"""Validation-only selection, then immutable paired held-out evaluation.

No learning, fitted normalization, exploration, test-time tuning or bootstrap.
Full uncertainty/plots belong to C18. Modeled failed episodes remain observations.
"""
from dataclasses import asdict
from pathlib import Path
import inspect
import math
import shutil
import time

from .manifest import atomic_json,checked_path,compatibility_profile,digest,environment,file_hash,read_json,run_lock
from .splits import load_split
from stars_rl.rl.actions import RATIOS
from stars_rl.rl.environment import StarsEnvironment
from stars_rl.rl.policies import FixedRatio,PolicyUnavailable,load_policy
from stars_rl.rl.reward import DISCOUNT
from stars_rl.simulation import WindowRecord
from stars_rl.topology.trace import trace_to_dict


def rollout(trace,policy,budget,*,environment_factory=None):
    """One complete attempted episode, retaining null unattempted records."""
    policy.assert_frozen();started=time.perf_counter()
    env=StarsEnvironment(trace,total_budget_seconds=budget) if environment_factory is None else environment_factory(trace,budget)
    state,_=env.reset();transitions=[];done=False
    for index in range(len(trace.windows)):
        action=policy.select(state)
        next_state,reward,done,truncated,info=env.step(action)
        if truncated or type(done) is not bool or not math.isfinite(reward):raise ValueError('invalid evaluation transition')
        if (done and next_state is not None) or (not done and next_state is None):raise ValueError('invalid terminal observation')
        if bool(info['learning_eligible'])!=bool(index):raise ValueError('initialization exclusion differs')
        transitions.append(dict(window_index=index,state=state,action=action,reward=reward,next_state=next_state,
                                terminated=done,info=info))
        policy.assert_frozen()
        if done:break
        state=next_state
    if not done:raise ValueError('episode did not terminate at the frozen horizon')
    records=list(env.records)
    if len(records)!=len(transitions) or [r.window_index for r in records]!=list(range(len(records))):
        raise ValueError('evaluation record/transition domains differ')
    failed=bool(transitions[-1]['info']['failure'])
    if not failed and len(transitions)!=len(trace.windows):raise ValueError('successful episode ended before horizon')
    attempts=sum(v.raw_status!='not_attempted' for r in records for v in r.stages.values())
    for index in range(len(records),len(trace.windows)):
        records.append(WindowRecord(index,reason='episode_terminated_before_window'))
    result=dict(trace_content_hash=trace.content_hash,policy_id=policy.policy_id,budget_seconds=budget,
                solver_seed=0,scope='standard' if environment_factory is None else 'controlled_test_adapter',
                status='failed' if failed else 'success',attempted_windows=len(transitions),
                failure_window=len(transitions)-1 if failed else None,
                failure_cause=transitions[-1]['info'].get('reason') if failed else None,
                penalized_score=-sum(DISCOUNT**i*t['reward'] for i,t in enumerate(transitions)),
                solver_calls=attempts if environment_factory is None else 0,stage_attempts=attempts,
                wall_seconds=time.perf_counter()-started,transitions=transitions,windows=[asdict(r) for r in records])
    policy.assert_frozen()
    return result


def grouped_score(rows):
    if not rows:raise ValueError('empty evaluation cannot be scored')
    groups={}
    for row in rows:
        if row['status'] not in ('success','failed'):raise ValueError('infrastructure/numerical errors cannot be scored as network outcomes')
        value=row['penalized_score']
        if not math.isfinite(value):raise ValueError('invalid evaluation score')
        groups.setdefault(row['component_id'],[]).append(value)
    means={key:sum(values)/len(values) for key,values in sorted(groups.items())}
    return dict(mean=sum(means.values())/len(means),groups=means,episodes=len(rows),
                failures=sum(r['status']=='failed' for r in rows),
                completion_rate=sum(r['status']=='success' for r in rows)/len(rows))


def select_fixed(scores):
    if set(scores)!=set(RATIOS):raise ValueError('all five validation ratios required')
    best=min(scores.values());ties=[rho for rho in RATIOS if abs(scores[rho]-best)<=1e-12]
    return .5 if .5 in ties else min(ties)


def claim_test_set(split_folder,freeze_hash,scope):
    """A killed/interrupted test remains consumed; no silent repeated tuning."""
    folder=Path(split_folder).resolve()
    with run_lock(folder):
        path=folder/'test-consumed.json'
        if path.exists():raise ValueError('held-out split already claimed; repeated test evaluation is refused')
        atomic_json(path,dict(schema_version=1,status='claimed_before_test',freeze_hash=freeze_hash,scope=scope))


def evaluate(split_folder,policy_runs,output,*,budget=60,_test_environment_factory=None,_fault=None):
    if type(budget) not in (int,float) or not math.isfinite(budget) or budget<=0:raise ValueError('positive finite evaluation budget required')
    split,partitions=load_split(split_folder)
    if (Path(split_folder)/'test-consumed.json').exists():
        raise ValueError('held-out split already claimed; repeated test evaluation is refused')
    if not policy_runs:raise ValueError('at least one completed policy run required')
    folder=Path(output).resolve();folder.mkdir(parents=True,exist_ok=False)
    scope='standard' if _test_environment_factory is None else 'controlled_test_adapter'
    info=environment();profile=compatibility_profile(info)|{'source_files':info['source_files']}
    manifest=dict(schema_version=1,status='preparing',scope=scope,split_hash=split['split_hash'],
        environment=info,budget_seconds=budget,solver_seed=0,artifact_hashes={},
        controlled_adapter=None if _test_environment_factory is None else dict(module=_test_environment_factory.__module__,
            name=_test_environment_factory.__qualname__,source=inspect.getsource(_test_environment_factory)),
        limitation='No scientific evaluation from controlled checkpoints; no superiority or confidence-interval claim.')
    atomic_json(folder/'manifest.json',manifest)
    policies=[];metadata=[]
    try:
        for run in policy_runs:
            policy,meta=load_policy(run,split,profile,budget,controlled=_test_environment_factory is not None)
            if any(meta['policy_id']==m['policy_id'] for m in metadata):raise ValueError('duplicate policy configuration/training seed')
            policies.append(policy);metadata.append(meta)
    except PolicyUnavailable as exc:
        manifest.update(status='blocked',reason=str(exc));atomic_json(folder/'manifest.json',manifest)
        return dict(status='blocked',reason=str(exc),scientific_evaluation_performed=False)
    except Exception as exc:
        manifest.update(status='aborted',error=dict(type=type(exc).__name__,message=str(exc)))
        atomic_json(folder/'manifest.json',manifest);raise
    configurations={}
    for policy,meta in zip(policies,metadata):configurations.setdefault(meta['configuration_id'],[]).append((policy,meta))
    seed_sets=[{m['seed'] for _,m in group} for group in configurations.values()]
    if any(seeds!=seed_sets[0] for seeds in seed_sets):
        manifest.update(status='aborted',error=dict(type='ValueError',message='candidate configurations must use the identical training-seed grid'))
        atomic_json(folder/'manifest.json',manifest)
        raise ValueError('candidate configurations must use the identical training-seed grid')
    # Snapshot all inputs, including test geometry for split auditing. Only
    # validation rewards are consulted before the selection is frozen.
    atomic_json(folder/'split.json',split)
    manifest['artifact_hashes']['split.json']=file_hash(folder/'split.json')
    for traces in partitions.values():
        for trace in traces:
            name='input-'+trace.content_hash+'.json';atomic_json(folder/name,trace_to_dict(trace))
            manifest['artifact_hashes'][name]=file_hash(folder/name)
    for meta in metadata:
        name=meta['policy_id']+'-input.json';atomic_json(folder/name,meta)
        manifest['artifact_hashes'][name]=file_hash(folder/name)
    package=Path(__file__).resolve().parents[1];repo=Path(__file__).resolve().parents[3]
    for name,value in info['source_files'].items():
        origin=repo/name.removeprefix('@repo/') if name.startswith('@repo/') else package/name
        relative='source/'+name.removeprefix('@repo/') if name.startswith('@repo/') else 'source/src/stars_rl/'+name
        destination=checked_path(folder,relative);destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(origin,destination)
        if file_hash(destination)!=value:raise ValueError('evaluation source changed during snapshot')
        manifest['artifact_hashes'][relative]=value
    atomic_json(folder/'manifest.json',manifest)
    fault=_fault or (lambda event:None)
    results=[]
    def run_partition(partition,adapters):
        rows=[]
        for trace in partitions[partition]:
            for policy in adapters:
                row=rollout(trace,policy,budget,environment_factory=_test_environment_factory)
                row['component_id']=split['traces'][trace.content_hash]['component_id'];row['partition']=partition
                name=f'{partition}-{trace.content_hash}-{policy.policy_id}.json'
                atomic_json(folder/name,row);manifest['artifact_hashes'][name]=file_hash(folder/name)
                rows.append(row);results.append(row)
        return rows
    try:
        manifest['status']='validation';atomic_json(folder/'manifest.json',manifest)
        fixed=[FixedRatio(rho) for rho in RATIOS]
        validation=run_partition('validation',fixed+policies)
        scores={p.policy_id:grouped_score([r for r in validation if r['policy_id']==p.policy_id]) for p in fixed+policies}
        rho=select_fixed({p.rho:scores[p.policy_id]['mean'] for p in fixed})
        config_scores={key:sum(scores[p.policy_id]['mean'] for p,_ in group)/len(group) for key,group in configurations.items()}
        best=min(config_scores.values());chosen=min(key for key,value in config_scores.items() if abs(value-best)<=1e-12)
        selected=configurations[chosen]
        frozen=dict(schema_version=1,split_hash=split['split_hash'],budget_seconds=budget,discount=DISCOUNT,
            comparator_rho=rho,always_include_rho=.5,selected_configuration=chosen,
            policies=[dict(policy_id=m['policy_id'],checkpoint_hash=m['checkpoint_hash'],seed=m['seed']) for _,m in selected],
            candidate_validation_scores=scores,configuration_validation_scores=config_scores,
            selection='Equal weight per connected group, then per training seed; validation rewards only. Deterministic ties.',
            all_input_hashes=dict(manifest['artifact_hashes']),scope=scope)
        atomic_json(folder/'frozen-selection.json',frozen);freeze_hash=file_hash(folder/'frozen-selection.json')
        manifest.update(status='frozen',freeze_hash=freeze_hash);atomic_json(folder/'manifest.json',manifest)
        fault('after_freeze')
        if file_hash(folder/'frozen-selection.json')!=freeze_hash:raise ValueError('frozen selection changed before test')
        for name,value in frozen['all_input_hashes'].items():
            if file_hash(checked_path(folder,name))!=value:raise ValueError('frozen input/source changed before test')
        claim_test_set(split_folder,freeze_hash,scope)
        manifest['status']='test';atomic_json(folder/'manifest.json',manifest)
        fault('before_test')
        comparators=[FixedRatio(.5)]+([] if rho==.5 else [FixedRatio(rho)])
        test=run_partition('test',comparators+[p for p,_ in selected])
        if file_hash(folder/'frozen-selection.json')!=freeze_hash:raise ValueError('frozen selection changed during test')
        for name,value in frozen['all_input_hashes'].items():
            if file_hash(checked_path(folder,name))!=value:raise ValueError('frozen input/source changed during test')
        for policy in policies:policy.assert_frozen()
        test_scores={p.policy_id:grouped_score([r for r in test if r['policy_id']==p.policy_id])
                     for p in comparators+[p for p,_ in selected]}
        baseline=test_scores[FixedRatio(rho).policy_id]
        paired={p.policy_id:{g:test_scores[p.policy_id]['groups'][g]-baseline['groups'][g] for g in baseline['groups']}
                for p,_ in selected}
        summary=dict(status='completed',scope=scope,scientific_evaluation_performed=scope=='standard',
            freeze_hash=freeze_hash,selected_configuration=chosen,comparator_rho=rho,test_scores=test_scores,
            paired_policy_minus_tuned_fixed=paired,training_seed_count=len(selected),test_group_count=len(baseline['groups']),
            solver_calls=sum(r['solver_calls'] for r in results),stage_attempts=sum(r['stage_attempts'] for r in results),
            evaluated_episodes=len(results),modeled_failed_episodes=sum(r['status']=='failed' for r in results),
            interpretation='Descriptive paired evaluation only; C18 uncertainty remains pending. No RL superiority claim.')
        atomic_json(folder/'summary.json',summary);manifest['artifact_hashes']['summary.json']=file_hash(folder/'summary.json')
        manifest['artifact_hashes']['frozen-selection.json']=freeze_hash
        manifest['status']='completed';atomic_json(folder/'manifest.json',manifest)
        return summary
    except BaseException as exc:
        manifest.update(status='aborted',error=dict(type=type(exc).__name__,message=str(exc)))
        atomic_json(folder/'manifest.json',manifest);raise
