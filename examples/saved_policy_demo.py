"""Saved untrained-policy round trip and native SCIP inference; no learning.

This diagnostic is deliberately separate from the gated C17 scientific evaluator.
An initial empty Q table is not a completed trained policy or held-out evidence.
"""
import argparse
from dataclasses import asdict
from pathlib import Path
import random

from stars_rl.experiments.evaluate import rollout
from stars_rl.experiments.manifest import atomic_json,file_hash,read_json
from stars_rl.rl.checkpoint import contract,load_boundary,save_boundary
from stars_rl.rl.policies import FrozenQPolicy
from stars_rl.rl.q_learning import LearningConfig,TabularQ
from stars_rl.topology.trace import load_trace

SCOPE='Untrained frozen-policy diagnostic; no training, held-out result or RL gain claim'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--policy-dir',type=Path,help='Replay a previously saved diagnostic in a fresh process')
    parser.add_argument('--budget',type=float,default=10)
    args=parser.parse_args(argv)
    trace=load_trace(args.trace)
    args.output.mkdir(parents=True,exist_ok=False)
    order=[trace.content_hash];groups=[trace.scenario.metadata.scenario_group_id]
    expected=dict(contract=contract([len(trace.windows)]),learning_config=asdict(LearningConfig()),
        episode_order=order,group_order=groups,trace_artifact_hash=trace.artifact_hash,budget_seconds=args.budget,scope=SCOPE)
    policy_dir=args.output if args.policy_dir is None else args.policy_dir
    if args.policy_dir is None:
        learner=TabularQ()
        save_boundary(policy_dir/'policy.json',learner,next_episode_index=0,episode_order=order,group_order=groups,
                      compatibility=expected,order_rng_state=random.Random(0).getstate())
        atomic_json(policy_dir/'policy-contract.json',expected)
    elif read_json(policy_dir/'policy-contract.json')!=expected:
        raise ValueError('saved diagnostic trace/schema/budget/configuration differs')
    before=file_hash(policy_dir/'policy.json')
    boundary,learner,_=load_boundary(policy_dir/'policy.json',expected)
    if learner.q or learner.updates or learner.exploration_steps or boundary['next_episode_index']:
        raise ValueError('only the initial untrained diagnostic is accepted')
    policy=FrozenQPolicy(learner,'saved-untrained-diagnostic')
    result=rollout(trace,policy,args.budget)
    policy.assert_frozen()
    if file_hash(policy_dir/'policy.json')!=before:raise ValueError('saved policy was modified during inference')
    atomic_json(args.output/'episode.json',result)
    summary=dict(scope=SCOPE,status=result['status'],committed_windows=sum(w['status']=='committed' for w in result['windows']),
        attempted_windows=result['attempted_windows'],solver_calls=result['solver_calls'],penalized_score=result['penalized_score'],
        policy_sha256=before,policy_unchanged=True,updates=learner.updates,exploration_steps=learner.exploration_steps,
        trace_content_hash=trace.content_hash,window_budget_seconds=args.budget,initial_boundary=True)
    atomic_json(args.output/'summary.json',summary)
    import json
    print(json.dumps(summary,allow_nan=False))
    return 0 if result['status']=='success' else 1


if __name__=='__main__':raise SystemExit(main())
