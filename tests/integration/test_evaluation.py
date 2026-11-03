"""Controlled selection/leakage tests; native optimizer smoke has no training."""
from dataclasses import replace
import json
import subprocess
import sys
import pytest

from stars_rl.experiments.evaluate import evaluate,rollout
from stars_rl.experiments.manifest import atomic_json,file_hash,read_json
from stars_rl.experiments.splits import create_split
from stars_rl.optimization.result import StageResult
from stars_rl.rl.policies import FixedRatio,FrozenQPolicy
from stars_rl.rl.q_learning import LearningConfig,TabularQ
from stars_rl.rl.training import train
from stars_rl.simulation import WindowRecord
from stars_rl.topology.trace import build_trace,save_trace


class TrainingFixture:
    def __init__(self,trace):self.trace=trace
    def reset(self):self.index=0;self.records=[];return (1,3,0,0,0,0),{}
    def step(self,action):
        k=self.index;self.index+=1
        record=WindowRecord(k,status='committed')
        for stage in ('stage1','stage2'):record.stages[stage]=StageResult(stage,'fixture','test',raw_status='controlled_test')
        self.records.append(record)
        return (None if k==2 else (0,2-k,0,0,0,0)),(0 if k==0 else -1),k==2,False,dict(learning_eligible=k>0,failure=False)


class EvaluationFixture(TrainingFixture):
    def __init__(self,trace,budget):super().__init__(trace);self.budget=budget
    def step(self,action):
        k=self.index
        state,reward,done,truncated,info=super().step(action)
        if k==1:
            if self.trace.scenario.scenario_id=='test-fail':
                info.update(failure=True,reason='controlled_infeasible');self.records[-1].status='failed'
                return None,-4*(1+.95),True,False,info
            target=3 if self.trace.scenario.scenario_id=='validation' else 0
            reward=-abs(action-target)/3
        elif k==2:reward=0
        return state,reward,done,truncated,info


def independent(trace,label,demand,*,root=None):
    s=trace.scenario;m=replace(s.metadata,root_lineage_id=root or label,scenario_group_id=root or label,
                             constellation_id=label,layout_id=label)
    return build_trace(replace(s,scenario_id=label,metadata=m,slices=tuple(replace(sl,demand_mbps=demand) for sl in s.slices)))


def prepare(tmp_path,episode_trace,*,seeds=(7,8),rates=(.1,.2)):
    original,_=episode_trace()
    training=independent(original,'train',2)
    validation=independent(original,'validation',3)
    test=independent(original,'test-ok',4)
    failure=independent(original,'test-fail',5,root='test-ok')
    split=tmp_path/'split';create_split(dict(train=[training],validation=[validation],test=[test,failure]),split)
    runs=[]
    for rate in rates:
        for seed in seeds:
            path=tmp_path/f'policy-{rate}-{seed}'
            train([training],path,episodes=2,budget=2,config=LearningConfig(seed=seed,learning_rate=rate),
                  _test_environment_factory=TrainingFixture)
            runs.append(path)
    return split,runs


def test_validation_freeze_paired_grid_failures_and_no_policy_mutation(episode_trace,tmp_path):
    split,runs=prepare(tmp_path,episode_trace);before={str(p):file_hash(p/'boundary-0002.json') for p in runs}
    output=tmp_path/'evaluation'
    def fault(event):
        if event=='after_freeze':
            frozen=read_json(output/'frozen-selection.json')
            assert frozen['comparator_rho']==2
            assert not list(output.glob('test-*.json'))
            assert not (split/'test-consumed.json').exists()
    result=evaluate(split,runs,output,budget=2,_test_environment_factory=EvaluationFixture,_fault=fault)
    assert result['status']=='completed' and not result['scientific_evaluation_performed']
    assert result['scope']=='controlled_test_adapter' and result['solver_calls']==0
    assert result['training_seed_count']==2 and result['test_group_count']==1
    assert result['comparator_rho']==2
    assert {'fixed-0.5','fixed-2.0'}.issubset(result['test_scores'])
    assert all(s['episodes']==2 and s['failures']==1 for s in result['test_scores'].values())
    assert result['modeled_failed_episodes']==4
    assert all(file_hash(p/'boundary-0002.json')==before[str(p)] for p in runs)
    rows=[read_json(p) for p in output.glob('test-*.json')]
    assert len(rows)==8 and all(r['budget_seconds']==2 for r in rows)
    for row in rows:
        if row['status']=='failed':
            assert row['penalized_score']==pytest.approx(.95*4*(1+.95))
            assert row['windows'][2]['status']=='not_attempted' and row['windows'][2]['metrics'] is None
    frozen=read_json(output/'frozen-selection.json')
    selected=min(frozen['configuration_validation_scores'],key=lambda k:(frozen['configuration_validation_scores'][k],k))
    assert result['selected_configuration']==selected
    for source in output.glob('q-*-input.json'):
        saved=read_json(source)
        assert saved['checkpoint']['compatibility']['contract']==saved['training_manifest']['compatibility']['contract']
    with pytest.raises(ValueError,match='already claimed'):evaluate(split,runs,output,budget=2,_test_environment_factory=EvaluationFixture)
    with pytest.raises(ValueError,match='already claimed'):
        evaluate(split,runs,tmp_path/'repeat',budget=2,_test_environment_factory=EvaluationFixture)


def test_freeze_tamper_stops_before_any_test_reward(episode_trace,tmp_path):
    split,runs=prepare(tmp_path,episode_trace,seeds=(7,),rates=(.1,));output=tmp_path/'evaluation'
    def fault(event):
        if event=='after_freeze':
            path=output/'frozen-selection.json';value=read_json(path);value['comparator_rho']=4;atomic_json(path,value)
    with pytest.raises(ValueError,match='selection changed'):
        evaluate(split,runs,output,budget=2,_test_environment_factory=EvaluationFixture,_fault=fault)
    assert not list(output.glob('test-*.json')) and not (split/'test-consumed.json').exists()
    assert read_json(output/'manifest.json')['status']=='aborted'


def test_controlled_checkpoint_cannot_be_scientific_cli_evaluation(episode_trace,tmp_path):
    split,runs=prepare(tmp_path,episode_trace,seeds=(7,),rates=(.1,))
    result=subprocess.run([sys.executable,'-m','stars_rl.cli','evaluate','--split',str(split),'--policy-run',str(runs[0]),
                           '--output',str(tmp_path/'native'),'--budget','2'],capture_output=True,text=True)
    assert result.returncode==1,result.stderr
    assert json.loads(result.stdout)['status']=='blocked'
    assert not (split/'test-consumed.json').exists()


def test_training_partition_and_budget_mismatch_blocked(episode_trace,tmp_path):
    split,runs=prepare(tmp_path,episode_trace,seeds=(7,),rates=(.1,))
    result=evaluate(split,runs,tmp_path/'budget',budget=3,_test_environment_factory=EvaluationFixture)
    assert result['status']=='blocked' and 'budgets differ' in result['reason']
    original,_=episode_trace();wrong=independent(original,'different-train',6)
    other=tmp_path/'wrong-split';create_split(dict(train=[wrong],validation=[independent(original,'v',7)],
                                                test=[independent(original,'t',8)]),other)
    result=evaluate(other,runs,tmp_path/'wrong',budget=2,_test_environment_factory=EvaluationFixture)
    assert result['status']=='blocked' and 'training inputs' in result['reason']


def test_infrastructure_exception_aborts_instead_of_becoming_a_failure_score(episode_trace,tmp_path):
    class Broken(EvaluationFixture):
        def step(self,action):raise RuntimeError('controlled backend exception')
    split,runs=prepare(tmp_path,episode_trace,seeds=(7,),rates=(.1,));output=tmp_path/'evaluation'
    with pytest.raises(RuntimeError):evaluate(split,runs,output,budget=2,_test_environment_factory=Broken)
    assert read_json(output/'manifest.json')['status']=='aborted'
    assert not (output/'summary.json').exists()


def test_native_identical_trace_budget_and_greedy_no_learning(episode_trace):
    trace,_=episode_trace();before=trace.artifact_hash
    learner=TabularQ();policy=FrozenQPolicy(learner,'untrained-diagnostic')
    records=[rollout(trace,p,3) for p in [FixedRatio(.5),FixedRatio(2),policy]]
    assert all(r['trace_content_hash']==trace.content_hash and r['budget_seconds']==3 for r in records)
    assert all(r['status']=='success' for r in records)
    assert all(r['penalized_score']==pytest.approx(.95*3) for r in records)
    assert all(r['solver_calls']==6 for r in records)
    assert learner.q=={} and learner.updates==learner.exploration_steps==0
    assert trace.artifact_hash==before


def test_test_rewards_are_not_read_before_freezing_and_cannot_select_ratio(episode_trace,tmp_path):
    class Guard(EvaluationFixture):
        frozen=False
        def __init__(self,trace,budget):
            if trace.scenario.scenario_id.startswith('test'):assert self.frozen
            super().__init__(trace,budget)
        def step(self,action):
            result=super().step(action)
            if self.trace.scenario.scenario_id=='test-ok' and self.index==2:
                state,_,done,truncated,info=result
                return state,-abs(action-4)/3,done,truncated,info
            return result
    split,runs=prepare(tmp_path,episode_trace,seeds=(7,),rates=(.1,.2));output=tmp_path/'eval'
    def fault(event):
        if event=='after_freeze':
            assert read_json(output/'frozen-selection.json')['comparator_rho']==2
            Guard.frozen=True
    result=evaluate(split,runs,output,budget=2,_test_environment_factory=Guard,_fault=fault)
    assert result['comparator_rho']==2 # despite test's deliberately opposite optimum


def test_incompatible_horizon_cannot_fit_observation_bins_to_test(episode_trace,tmp_path):
    from stars_rl.models import AccessWindow
    split,runs=prepare(tmp_path,episode_trace,seeds=(7,),rates=(.1,))
    original,_=episode_trace();t=independent(original,'long-test',8);s=t.scenario
    longer=build_trace(replace(s,window_count=4,metadata=replace(s.metadata,interval_end_seconds=240),
                               access_schedule=s.access_schedule+(AccessWindow(3,s.access_schedule[-1].links),)))
    from stars_rl.experiments.splits import load_split
    _,p=load_split(split);p['test']=[longer];other=tmp_path/'long-split';create_split(p,other)
    result=evaluate(other,runs,tmp_path/'long',budget=2,_test_environment_factory=EvaluationFixture)
    assert result['status']=='blocked' and 'horizon' in result['reason']
    assert not (other/'test-consumed.json').exists()


def test_configurations_need_a_complete_common_training_seed_grid(episode_trace,tmp_path):
    split,runs=prepare(tmp_path,episode_trace,seeds=(7,8),rates=(.1,.2));output=tmp_path/'unpaired'
    with pytest.raises(ValueError,match='training-seed grid'):
        evaluate(split,runs[:-1],output,budget=2,_test_environment_factory=EvaluationFixture)
    assert read_json(output/'manifest.json')['status']=='aborted'
    assert not (split/'test-consumed.json').exists()


def test_test_claim_is_retained_after_interruption(episode_trace,tmp_path):
    split,runs=prepare(tmp_path,episode_trace,seeds=(7,),rates=(.1,));output=tmp_path/'interrupted'
    def fault(event):
        if event=='before_test':raise KeyboardInterrupt('controlled test interruption')
    with pytest.raises(KeyboardInterrupt):
        evaluate(split,runs,output,budget=2,_test_environment_factory=EvaluationFixture,_fault=fault)
    assert (split/'test-consumed.json').exists()
    assert read_json(output/'manifest.json')['status']=='aborted'
    with pytest.raises(ValueError,match='already claimed'):
        evaluate(split,runs,tmp_path/'retry',budget=2,_test_environment_factory=EvaluationFixture)


def test_cli_split_freezes_before_tuning_and_rejects_relabelled_duplicate(episode_trace,tmp_path):
    original,_=episode_trace();traces=[independent(original,label,demand) for label,demand in [('train',2),('validation',3),('test',4)]]
    paths=[]
    for i,trace in enumerate(traces):
        path=tmp_path/f'trace-{i}.json';save_trace(trace,path);paths.append(path)
    def cli(test_path,output):
        return subprocess.run([sys.executable,'-m','stars_rl.cli','split','--train',str(paths[0]),'--validation',str(paths[1]),
                               '--test',str(test_path),'--output',str(output)],capture_output=True,text=True)
    result=cli(paths[2],tmp_path/'cli-split')
    assert result.returncode==0,result.stderr
    assert (tmp_path/'cli-split/manifest.json').is_file()
    duplicate=tmp_path/'renamed.json';save_trace(independent(original,'other-seed',2),duplicate)
    result=cli(duplicate,tmp_path/'invalid')
    assert result.returncode==2 and 'duplicate normalized' in result.stderr
    assert not (tmp_path/'invalid').exists()


def test_recorded_training_lineage_cannot_be_relabeled_to_hide_overlap(episode_trace,tmp_path):
    from stars_rl.experiments.splits import load_split
    split,runs=prepare(tmp_path,episode_trace,seeds=(7,),rates=(.1,));_,p=load_split(split)
    training=p['train'][0]
    p['train']=[build_trace(replace(training.scenario,metadata=replace(training.scenario.metadata,
                                root_lineage_id='pretend-independent-root')))]
    original,_=episode_trace();heldout=independent(original,'heldout',8)
    p['test']=[build_trace(replace(heldout.scenario,metadata=replace(heldout.scenario.metadata,root_lineage_id='train')))]
    renamed=tmp_path/'renamed';create_split(p,renamed)
    result=evaluate(renamed,runs,tmp_path/'eval-renamed',budget=2,_test_environment_factory=EvaluationFixture)
    assert result['status']=='blocked' and 'relabeled' in result['reason']
    assert not (renamed/'test-consumed.json').exists()


def test_entire_declared_training_pool_is_bound_even_when_pilot_visits_only_subset(episode_trace,tmp_path):
    original,_=episode_trace()
    a=independent(original,'train-a',2,root='train-root')
    b=independent(original,'train-b',3,root='train-root')
    validation=independent(original,'validation',4)
    test=independent(original,'test-ok',5)
    split=tmp_path/'pool-split';create_split(dict(train=[a,b],validation=[validation],test=[test]),split)
    run=tmp_path/'short-pilot'
    train([a,b],run,episodes=1,budget=2,config=LearningConfig(seed=7),_test_environment_factory=TrainingFixture)
    manifest=read_json(run/'manifest.json')
    assert len(manifest['compatibility']['episode_order'])==1
    assert len(manifest['compatibility']['trace_artifact_hashes'])==2
    result=evaluate(split,[run],tmp_path/'eval-pool',budget=2,_test_environment_factory=EvaluationFixture)
    assert result['status']=='completed'
