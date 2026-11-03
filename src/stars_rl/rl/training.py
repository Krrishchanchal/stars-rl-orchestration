"""Episode-boundary training transactions with whole-episode replay only."""
from dataclasses import asdict
from pathlib import Path
import inspect
import random
import shutil
import time

from stars_rl.experiments.manifest import (atomic_json,checked_path,compatibility_profile,digest,
    environment,file_hash,read_json,run_lock)
from stars_rl.topology.trace import trace_to_dict
from .checkpoint import contract,load_boundary,save_boundary
from .environment import StarsEnvironment
from .q_learning import LearningConfig,TabularQ
from .readiness import assess_readiness,compute_estimate


def train(traces,output,*,episodes=3,budget=60,config=None,resume=False,evidence_path=None,
          _test_environment_factory=None,_fault=None):
    """Real launches require measured gates. Test adapters cannot be CLI-selected.

    Test runs are explicitly labeled controlled_test_adapter and cannot resume
    as standard solver training. Only the owned learner and ordering RNG are used;
    exogenous traces are immutable and the core's solver seed remains zero.
    """
    run_started=time.perf_counter()
    traces=tuple(traces)
    estimate=compute_estimate(traces,episodes,budget)
    config=LearningConfig() if config is None else config
    if not isinstance(config,LearningConfig):raise ValueError('LearningConfig required')
    hashes=[t.content_hash for t in traces]
    if len(set(hashes))!=len(hashes):raise ValueError('duplicate normalized training traces')
    adapter='standard' if _test_environment_factory is None else 'controlled_test_adapter'
    adapter_source=None if _test_environment_factory is None else dict(
        module=_test_environment_factory.__module__,name=_test_environment_factory.__qualname__,
        source=inspect.getsource(_test_environment_factory))
    envinfo=environment();profile=compatibility_profile(envinfo)
    gate=(assess_readiness(traces,budget,profile,evidence_path,episodes) if adapter=='standard'
          else dict(passed=True,reasons=[],scope='controlled software test only; no scientific training gate clearance'))
    folder=Path(output).resolve()
    if not resume:folder.mkdir(parents=True,exist_ok=False)
    elif not folder.is_dir():raise ValueError('no training run to resume')
    with run_lock(folder):
        order_rng=random.Random(int(digest({'seed':config.seed,'stream':'training_trace_order'}),16))
        order=[]
        while len(order)<episodes:
            cycle=list(range(len(traces)));order_rng.shuffle(cycle)
            order.extend(cycle)
        order=order[:episodes]
        episode_order=[hashes[i] for i in order]
        group_order=[traces[i].scenario.metadata.scenario_group_id for i in order]
        expected=dict(contract=contract([len(t.windows) for t in traces]),learning_config=asdict(config),
                      episode_order=episode_order,group_order=group_order,budget=budget,solver_seed=0,
                      runtime_adapter=adapter,runtime_profile=profile,readiness=gate,
                      controlled_adapter=adapter_source,
                      trace_artifact_hashes=[t.artifact_hash for t in traces])
        if resume:
            manifest=read_json(folder/'manifest.json')
            if manifest['compatibility']!=expected:raise ValueError('incompatible training resume settings/code/runtime/gates')
            if manifest['status'] in ('aborted','blocked'):raise ValueError('aborted/blocked training requires diagnosis and a new run')
            for name,value in manifest['input_hashes'].items():
                if file_hash(checked_path(folder,name))!=value:raise ValueError('training input/source hash mismatch: '+name)
            boundary_name=manifest['active_boundary']
            if file_hash(checked_path(folder,boundary_name))!=manifest['active_boundary_file_hash']:
                raise ValueError('active checkpoint file hash mismatch')
            boundary,learner,order_rng=load_boundary(checked_path(folder,boundary_name),expected)
            start=boundary['next_episode_index']
            for accepted in manifest['completed_episodes']:
                path=checked_path(folder,accepted['summary'])
                if file_hash(path)!=accepted['sha256']:raise ValueError('accepted episode summary hash mismatch')
                for step in read_json(path)['steps']:
                    if file_hash(checked_path(path.parent,step['artifact']))!=step['artifact_hash']:
                        raise ValueError('accepted step artifact hash mismatch')
            if len(manifest['completed_episodes'])!=start:raise ValueError('checkpoint/accepted episode count mismatch')
            if manifest['status']=='completed':
                if start!=episodes or manifest.get('active_attempt') is not None:
                    raise ValueError('completed run has inconsistent boundary')
                if file_hash(folder/'summary.json')!=manifest['summary_hash']:
                    raise ValueError('training summary hash mismatch')
                return read_json(folder/'summary.json')
            if manifest.get('active_attempt') is not None:
                attempt=manifest['attempts'][manifest['active_attempt']]
                attempt['status']='abandoned';attempt['reason']='whole-episode replay from preceding published boundary'
                manifest['active_attempt']=None
        else:
            atomic_json(folder/'compute-estimate.json',estimate)
            atomic_json(folder/'readiness.json',gate)
            manifest=dict(schema_version=1,status='ready' if gate['passed'] else 'blocked',compatibility=expected,
                          environment=envinfo,scope=adapter,active_boundary='boundary-0000.json',
                          active_attempt=None,attempts=[],completed_episodes=[],input_hashes={})
            if not gate['passed']:
                atomic_json(folder/'manifest.json',manifest)
                return dict(status='blocked',readiness=gate,compute_estimate=estimate)
            # Keep complete code/input snapshots even for dirty source trees.
            package=Path(__file__).resolve().parents[1];repo=Path(__file__).resolve().parents[3]
            for name,value in envinfo['source_files'].items():
                origin=repo/name.removeprefix('@repo/') if name.startswith('@repo/') else package/name
                relative='source/'+name.removeprefix('@repo/') if name.startswith('@repo/') else 'source/src/stars_rl/'+name
                destination=checked_path(folder,relative);destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(origin,destination)
                if file_hash(destination)!=value:raise ValueError('source changed during snapshot')
                manifest['input_hashes'][relative]=value
            for i,trace in enumerate(traces):
                name=f'trace-{i:04d}.json';atomic_json(folder/name,trace_to_dict(trace))
                manifest['input_hashes'][name]=file_hash(folder/name)
            for name in ('compute-estimate.json','readiness.json'):
                manifest['input_hashes'][name]=file_hash(folder/name)
            learner=TabularQ(config);start=0
            save_boundary(folder/'boundary-0000.json',learner,next_episode_index=0,episode_order=episode_order,
                          group_order=group_order,compatibility=expected,order_rng_state=order_rng.getstate())
            manifest['active_boundary_file_hash']=file_hash(folder/'boundary-0000.json')
        manifest['status']='running';atomic_json(folder/'manifest.json',manifest)
        manifest.setdefault('invocations',[]).append(dict(resume=resume,setup_wall_seconds=time.perf_counter()-run_started))
        atomic_json(folder/'manifest.json',manifest)
        fault=_fault or (lambda event,episode,step:None)
        for episode in range(start,episodes):
            attempt_index=len(manifest['attempts']);name=f'attempt-{attempt_index:04d}'
            attempt_folder=folder/name;attempt_folder.mkdir()
            manifest['attempts'].append(dict(episode_index=episode,status='running',folder=name))
            manifest['active_attempt']=attempt_index;atomic_json(folder/'manifest.json',manifest)
            steps=[];started=time.perf_counter();solves=0
            try:
                fault('before_episode',episode,0)
                trace=traces[order[episode]]
                env=StarsEnvironment(trace,total_budget_seconds=budget) if _test_environment_factory is None else _test_environment_factory(trace)
                state,_=env.reset();step_index=0
                while True:
                    action=learner.select(state,training=True)
                    next_state,reward,terminated,truncated,info=env.step(action)
                    if truncated:raise ValueError('finite-horizon contract forbids truncation')
                    eligible=not bool(state[0])
                    if info['learning_eligible']!=eligible:raise ValueError('initialization eligibility differs from observation')
                    if eligible:learner.update(state,action,reward,next_state,terminated)
                    record=env.records[-1]
                    solves+=sum(v.raw_status!='not_attempted' for v in record.stages.values())
                    artifact=f'step-{step_index:04d}.json'
                    atomic_json(attempt_folder/artifact,dict(state=state,action=action,reward=reward,next_state=next_state,
                                terminated=terminated,info=info,record=asdict(record)))
                    steps.append(dict(state=state,action=action,reward=reward,next_state=next_state,
                                      terminated=terminated,learning_eligible=eligible,artifact=artifact,
                                      artifact_hash=file_hash(attempt_folder/artifact)))
                    atomic_json(attempt_folder/'progress.json',dict(status='partial_not_resumable',steps=steps))
                    fault('after_step',episode,step_index)
                    step_index+=1
                    if terminated:break
                    state=next_state
                elapsed=time.perf_counter()-started
                summary=dict(episode_index=episode,trace_hash=trace.content_hash,steps=steps,
                             solver_calls=solves,wall_seconds=elapsed,
                             attempted_windows=len(steps),initialization_windows=sum(not s['learning_eligible'] for s in steps),
                             penalized_score=-sum(config.discount**i*s['reward'] for i,s in enumerate(steps)),
                             status='completed',failure=info['failure'],learning_updates=sum(s['learning_eligible'] for s in steps))
                atomic_json(attempt_folder/'summary.json',summary)
                fault('before_boundary',episode,step_index)
                boundary_name=f'boundary-{episode+1:04d}.json'
                save_boundary(folder/boundary_name,learner,next_episode_index=episode+1,episode_order=episode_order,
                              group_order=group_order,compatibility=expected,order_rng_state=order_rng.getstate())
                fault('after_boundary_before_publish',episode,step_index)
                manifest['attempts'][attempt_index]['status']='completed'
                manifest['attempts'][attempt_index].update(solver_calls=solves,wall_seconds=time.perf_counter()-started)
                manifest['completed_episodes'].append(dict(summary=name+'/summary.json',sha256=file_hash(attempt_folder/'summary.json')))
                manifest['active_boundary']=boundary_name;manifest['active_boundary_file_hash']=file_hash(folder/boundary_name)
                manifest['active_attempt']=None
                atomic_json(folder/'manifest.json',manifest)
                fault('after_publish',episode,step_index)
            except BaseException as exc:
                manifest['status']='interrupted' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'aborted'
                manifest['attempts'][attempt_index].update(solver_calls=solves,wall_seconds=time.perf_counter()-started)
                manifest['error']={'type':type(exc).__name__,'message':str(exc)}
                atomic_json(folder/'manifest.json',manifest)
                raise
        summaries=[read_json(folder/a['summary']) for a in manifest['completed_episodes']]
        totals=dict(status='completed',scope=adapter,episodes=len(summaries),
                    stage_attempts=sum(a.get('solver_calls',0) for a in manifest['attempts']),
                    solver_calls=sum(a.get('solver_calls',0) for a in manifest['attempts']) if adapter=='standard' else 0,
                    accepted_solver_calls=sum(s['solver_calls'] for s in summaries) if adapter=='standard' else 0,
                    episode_wall_seconds=sum(a.get('wall_seconds',0) for a in manifest['attempts']),
                    accepted_episode_wall_seconds=sum(s['wall_seconds'] for s in summaries),
                    attempted_windows=sum(s['attempted_windows'] for s in summaries),
                    learning_updates=learner.updates,exploration_steps=learner.exploration_steps,
                    action_counts=learner.action_counts,final_epsilon=learner.epsilon,
                    pilot_is_scientific_evidence=adapter=='standard',
                    setup_wall_seconds=sum(i['setup_wall_seconds'] for i in manifest['invocations']),
                    limitation='Controlled adapters prove software replay only; solver timing can vary across runs/hardware.')
        atomic_json(folder/'summary.json',totals)
        manifest['summary_hash']=file_hash(folder/'summary.json')
        manifest['status']='completed';atomic_json(folder/'manifest.json',manifest)
        return totals
