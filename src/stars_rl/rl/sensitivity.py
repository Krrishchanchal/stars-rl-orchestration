"""Replay all ratios; classify meaningful decisions independently of CPU/ID ties."""
import hashlib
import json
from dataclasses import asdict

from stars_rl.config import deployment_to_dict
from .actions import RATIOS
from .environment import StarsEnvironment
from .state import observation


def decision_class(deployment):
    if deployment is None:
        return None
    return dict(access=sorted((a.user_id,a.satellite_id) for a in deployment.access),
                egress=sorted((a.user_id,a.satellite_id,a.ground_station_id) for a in deployment.egress),
                placement=sorted((a.user_id,a.stage_index,a.instance.function_type_id,a.instance.satellite_id)
                                 for a in deployment.allocations))


def replay_actions(environment):
    """Report solved status/gaps, without treating distinct incumbents as a gate."""
    previous = environment._previous
    source = dict(trace=environment.trace.content_hash,index=environment._index,
                  previous=None if previous is None else deployment_to_dict(previous),churn=environment._churn)
    fingerprint = hashlib.sha256(json.dumps(source,sort_keys=True,allow_nan=False).encode()).hexdigest()
    rows = []
    for action,rho in enumerate(RATIOS):
        branch = environment.fork()
        _,reward,terminated,_,info = branch.step(action)
        record = branch.records[-1]
        stages = {k:dict(status=v.raw_status,outcome=v.outcome,objective=v.objective,
                         absolute_gap=v.absolute_gap) for k,v in record.stages.items()}
        rows.append(dict(action=action,rho=rho,pre_action_fingerprint=fingerprint,reward=reward,
                         terminated=terminated,info=info,decision_class=decision_class(record.committed_deployment),stages=stages,
                         export=record.export,commit_validation=record.commit_validation,
                         metrics=None if record.metrics is None else asdict(record.metrics),
                         elapsed_seconds=record.elapsed_seconds,preflight=record.preflight))
    distinct = len({json.dumps(row['decision_class'],sort_keys=True) for row in rows if row['decision_class'] is not None})
    return dict(pre_action_state=source,observation=observation(environment.trace,environment._index,previous,environment._churn),
                actions=rows,distinct_successful_classes=distinct,
                budget_seconds=environment._options['total_budget_seconds'] or (60 if environment.trace.scenario.orbit else 10),
                solver_seed=0,runtime_adapter='standard' if environment._options['services'] is None else 'injected_test_adapter',
                interpretation='Differences require complete class enumeration and positive margins to certify a weight effect.')


def measure_trace(trace, **options):
    env = StarsEnvironment(trace,**options)
    env.reset()
    reports = []
    while not env._done:
        reports.append(replay_actions(env))
        env.step(1)
    return dict(schema_version=1,trace_content_hash=trace.content_hash,reference_policy_rho=.5,
                windows=reports,training_gate='OPEN: requires certified constructed classes and representative nondegeneracy',
                physical_training_ready=False)
