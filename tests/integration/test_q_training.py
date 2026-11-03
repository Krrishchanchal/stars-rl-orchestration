"""Controlled software transitions only: no solver-backed training pilot."""
from dataclasses import replace
from pathlib import Path
import pytest

from stars_rl.experiments.manifest import read_json
from stars_rl.optimization.result import StageResult
from stars_rl.rl.training import train
from stars_rl.rl.q_learning import LearningConfig
from stars_rl.simulation import WindowRecord
from stars_rl.topology.trace import build_trace


class ControlledEnvironment:
    def __init__(self,trace):self.trace=trace;self.records=[]
    def reset(self):self.index=0;self.records=[];return (1,3,0,0,0,0),{}
    def step(self,action):
        k=self.index;self.index+=1
        reward=0 if k==0 else (-1 if action==0 else -2) if k==1 else (0 if action==1 else -1)
        state=None if k==2 else (0,2-k,0,0,0,0 if k==0 else 1)
        record=WindowRecord(k,status='committed')
        for stage in ('stage1','stage2'):
            record.stages[stage]=StageResult(stage,'controlled','test',raw_status='controlled_test')
        self.records.append(record)
        return state,reward,k==2,False,dict(learning_eligible=k>0,failure=False)


def execute(trace,path,**kwargs):
    return train([trace],path,episodes=3,budget=2,config=LearningConfig(seed=41,epsilon_decay_steps=4),
                 _test_environment_factory=ControlledEnvironment,**kwargs)


def final_state(path):
    manifest=read_json(path/'manifest.json')
    return read_json(path/manifest['active_boundary'])


def test_three_episodes_initial_exclusion_and_complete_boundary(episode_trace,tmp_path):
    trace,_=episode_trace()
    result=execute(trace,tmp_path/'run')
    assert result['scope']=='controlled_test_adapter' and not result['pilot_is_scientific_evidence']
    assert result['learning_updates']==result['exploration_steps']==6
    assert sum(result['action_counts'])==6
    assert result['solver_calls']==result['accepted_solver_calls']==0
    assert result['stage_attempts']==18
    assert result['attempted_windows']==9
    data=final_state(tmp_path/'run')
    assert data['next_episode_index']==3 and data['active_deployment'] is None
    assert (tmp_path/'run/boundary-0000.json').is_file()


@pytest.mark.parametrize('event,episode,step',[
    ('before_episode',0,0),('after_step',0,0),('after_step',0,1),('after_step',1,1),
    ('before_boundary',0,3),('after_boundary_before_publish',0,3),('after_publish',0,3)])
def test_interruption_replays_whole_episode_exactly(episode_trace,tmp_path,event,episode,step):
    trace,_=episode_trace();baseline=tmp_path/'baseline';interrupted=tmp_path/'interrupted'
    execute(trace,baseline)
    def fault(actual,e,s):
        if (actual,e,s)==(event,episode,step):raise KeyboardInterrupt('controlled interruption')
    with pytest.raises(KeyboardInterrupt):execute(trace,interrupted,_fault=fault)
    result=execute(trace,interrupted,resume=True)
    assert final_state(baseline)==final_state(interrupted)
    assert result['accepted_solver_calls']==result['solver_calls']==0 and result['stage_attempts']>=18
    manifest=read_json(interrupted/'manifest.json')
    if event!='after_publish':
        assert any(a['status']=='abandoned' for a in manifest['attempts'])
    assert len(manifest['completed_episodes'])==3
    # Accepted action/reward/update logs match; partial logs remain abandoned.
    def transitions(path):
        m=read_json(path/'manifest.json')
        return [[(s['state'],s['action'],s['reward'],s['next_state']) for s in read_json(path/a['summary'])['steps']]
                for a in m['completed_episodes']]
    assert transitions(baseline)==transitions(interrupted)


def test_completed_resume_does_no_more_work(episode_trace,tmp_path):
    trace,_=episode_trace();path=tmp_path/'run'
    before=execute(trace,path)
    result=execute(trace,path,resume=True)
    assert result==before
    assert len(read_json(path/'manifest.json')['attempts'])==3


def test_corrupted_inputs_checkpoint_and_changed_config_refused(episode_trace,tmp_path):
    trace,_=episode_trace();path=tmp_path/'run';execute(trace,path)
    with pytest.raises(ValueError,match='incompatible'):
        train([trace],path,episodes=3,budget=2,config=LearningConfig(seed=99),resume=True,
              _test_environment_factory=ControlledEnvironment)
    (path/'trace-0000.json').write_text('{}')
    with pytest.raises(ValueError,match='hash mismatch'):execute(trace,path,resume=True)


def test_programming_error_aborts_without_checkpointing_partial_learning(episode_trace,tmp_path):
    trace,_=episode_trace();path=tmp_path/'run'
    def fault(event,e,s):
        if event=='after_step' and s==1:raise RuntimeError('controlled implementation failure')
    with pytest.raises(RuntimeError):execute(trace,path,_fault=fault)
    manifest=read_json(path/'manifest.json')
    assert manifest['status']=='aborted'
    assert final_state(path)['learner']['updates']==0
    with pytest.raises(ValueError,match='aborted'):execute(trace,path,resume=True)


def test_real_cli_style_launch_is_blocked_before_training(episode_trace,tmp_path):
    trace,_=episode_trace();path=tmp_path/'blocked'
    result=train([trace],path,episodes=3,budget=2)
    assert result['status']=='blocked'
    assert not list(path.glob('boundary-*.json'))
    assert not list(path.glob('attempt-*'))
    assert (path/'compute-estimate.json').is_file()


def test_trace_ordering_rng_and_duplicate_rejection(episode_trace,tmp_path):
    trace,_=episode_trace()
    other=build_trace(replace(trace.scenario,slices=tuple(replace(s,demand_mbps=3) for s in trace.scenario.slices)))
    train([trace,other],tmp_path/'ordered',episodes=4,budget=2,_test_environment_factory=ControlledEnvironment)
    data=final_state(tmp_path/'ordered')
    assert sorted(data['episode_order'][:2])==sorted([trace.content_hash,other.content_hash])
    assert len(data['episode_order'])==4
    with pytest.raises(ValueError,match='duplicate'):
        train([trace,trace],tmp_path/'duplicate',_test_environment_factory=ControlledEnvironment)


def test_terminal_failure_is_learned_and_score_keeps_episode_origin_discount(episode_trace,tmp_path):
    class Failure(ControlledEnvironment):
        def step(self,action):
            if self.index==1:
                self.records.append(WindowRecord(1,status='failed'))
                return None,-4*(1+.95),True,False,dict(learning_eligible=True,failure=True)
            return super().step(action)
    trace,_=episode_trace();path=tmp_path/'failure'
    result=train([trace],path,episodes=1,budget=2,_test_environment_factory=Failure)
    assert result['learning_updates']==1
    m=read_json(path/'manifest.json');summary=read_json(path/m['completed_episodes'][0]['summary'])
    assert summary['failure'] and summary['penalized_score']==pytest.approx(.95*4*(1+.95))
    assert summary['attempted_windows']==2


def test_checkpoint_and_accepted_step_corruption_rejected(episode_trace,tmp_path):
    trace,_=episode_trace()
    for kind in ('checkpoint','step'):
        path=tmp_path/kind;execute(trace,path)
        if kind=='checkpoint':
            manifest=read_json(path/'manifest.json');(path/manifest['active_boundary']).write_text('{}')
        else:(path/'attempt-0000/step-0000.json').write_text('{}')
        with pytest.raises(ValueError,match='hash mismatch'):execute(trace,path,resume=True)


def test_train_cli_records_blocked_plan_without_optimizer_training(episode_trace,tmp_path):
    import json
    import subprocess
    import sys
    from stars_rl.topology.trace import save_trace
    trace,_=episode_trace();source=tmp_path/'trace.json';save_trace(trace,source)
    result=subprocess.run([sys.executable,'-m','stars_rl.cli','train','--trace',str(source),
                           '--output',str(tmp_path/'cli'),'--episodes','1','--budget','2'],capture_output=True,text=True)
    assert result.returncode==1,result.stderr
    assert json.loads(result.stdout)['status']=='blocked'
    assert (tmp_path/'cli/compute-estimate.json').is_file()
    assert not list((tmp_path/'cli').glob('boundary-*.json'))
