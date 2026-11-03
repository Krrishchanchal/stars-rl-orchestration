"""Published schemas, strict compatibility and complete episode replay."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import pytest

from stars_rl.experiments.manifest import atomic_json,read_json
from stars_rl.experiments.runner import run_experiment,validate_run
from stars_rl.simulation import simulate
from stars_rl.topology.trace import save_trace

pytestmark=pytest.mark.solver


def inputs(tmp_path,episode_trace,**kwargs):
    trace,rates=episode_trace(**kwargs)
    path=tmp_path/'trace.json';save_trace(trace,path)
    records=[{'window_index':w,'user_id':u,'satellite_id':s,'occupancy':n,'rate_bps':v} for w,table in rates.items() for (u,s,n),v in table.items()]
    radio=tmp_path/'rates.json';atomic_json(radio,records)
    return trace,rates,path,radio


def run(tmp_path,path,radio,run_id='case',method='stars-fixed',**kwargs):
    return run_experiment(path,tmp_path/'runs',run_id,method,rho=.5,total_budget_seconds=2,radio_coefficients_path=radio,**kwargs)


def test_manifest_and_all_output_schemas(tmp_path,episode_trace):
    trace,rates,path,radio=inputs(tmp_path,episode_trace)
    manifest=run(tmp_path,path,radio);folder=tmp_path/'runs/case/stars-fixed'
    check=validate_run(folder)
    assert check['valid'] and check['approved_windows']==3
    assert manifest['trace_content_hash']==trace.content_hash
    assert manifest['lineage']['root_lineage_id']==trace.scenario.metadata.root_lineage_id
    assert manifest['environment']['backend']['scip'] and manifest['environment']['dependencies']['PySCIPOpt']=='6.3.0'
    assert manifest['environment']['hardware']['logical_cpus']>0
    assert manifest['timings']['post_decision_serialization_and_hashing_seconds']>=0
    assert manifest['timings']['offline_artifact_audit_seconds']>=0
    assert (folder/'source/src/stars_rl/simulation.py').exists()
    assert (folder/'source/pyproject.toml').exists()
    episode=read_json(folder/'attempt-0000/episode.json')
    assert set(episode['windows'][0]['stages'])=={'stage1','stage2','monolithic'}
    assert episode['windows'][0]['stages']['stage1']['objective_units']=='seconds'
    assert episode['windows'][0]['stages']['stage2']['objective_units']=='dimensionless'
    assert episode['windows'][0]['stages']['monolithic']['raw_status']=='not_attempted'
    boundary=read_json(folder/'boundary-0000.json');end=read_json(folder/'attempt-0000/boundary_end.json')
    assert boundary['next_episode_index']==0 and end['next_episode_index']==1
    assert boundary['active_deployment'] is end['active_deployment'] is None
    before=(folder/'manifest.json').read_bytes()
    run(tmp_path,None,None,resume=True)
    assert (folder/'manifest.json').read_bytes()==before


@pytest.mark.parametrize('event',['before_episode','after_decisions','before_publish','after_directory_publish','before_manifest_publish'])
def test_interrupt_archive_and_full_episode_replay(tmp_path,episode_trace,event):
    trace,rates,path,radio=inputs(tmp_path,episode_trace)
    def crash(point):
        if point==event:raise RuntimeError('controlled interruption at '+event)
    with pytest.raises(RuntimeError,match='controlled interruption'):
        run(tmp_path,path,radio,_fault=crash)
    folder=tmp_path/'runs/case/stars-fixed';boundary=(folder/'boundary-0000.json').read_bytes()
    assert read_json(folder/'manifest.json')['status']=='interrupted'
    with pytest.raises(ValueError,match='published'):validate_run(folder)
    manifest=run(tmp_path,path,radio,resume=True)
    assert [a['status'] for a in manifest['attempts']]==['abandoned','completed']
    assert (folder/'abandoned-0000').is_dir() and (folder/'attempt-0001').is_dir()
    assert (folder/'boundary-0000.json').read_bytes()==boundary
    assert validate_run(folder)['approved_windows']==3
    assert read_json(folder/'attempt-0001/episode.json')['windows'][0]['previous_committed'] is None


def test_controlled_continuation_exact_episode_replay(tmp_path,episode_trace):
    trace,rates,path,radio=inputs(tmp_path,episode_trace)
    frozen=simulate(trace,rho=.5,total_budget_seconds=2,radio_coefficients_by_window=rates)
    def controlled(*args,**kwargs):return deepcopy(frozen)
    run(tmp_path,path,radio,run_id='control',_simulate_fn=controlled)
    def crash(point):
        if point=='after_decisions':raise RuntimeError('controlled interruption')
    with pytest.raises(RuntimeError):run(tmp_path,path,radio,_simulate_fn=controlled,_fault=crash)
    run(tmp_path,path,radio,resume=True,_simulate_fn=controlled)
    a=read_json(tmp_path/'runs/control/stars-fixed/attempt-0000/episode.json')
    b=read_json(tmp_path/'runs/case/stars-fixed/attempt-0001/episode.json')
    assert a==b and b['runtime_adapter']=='injected_test_adapter'


def test_paired_methods_cannot_overwrite_each_other(tmp_path,episode_trace):
    trace,rates,path,radio=inputs(tmp_path,episode_trace)
    a=run(tmp_path,path,radio,method='stars-fixed');b=run(tmp_path,path,radio,method='hier-only')
    assert a['trace_content_hash']==b['trace_content_hash']==trace.content_hash
    before=(tmp_path/'runs/case/stars-fixed/manifest.json').read_bytes()
    with pytest.raises(FileExistsError):run(tmp_path,path,radio)
    assert (tmp_path/'runs/case/stars-fixed/manifest.json').read_bytes()==before


def test_failed_episode_retains_failure_and_not_attempted_records(tmp_path,episode_trace):
    trace,rates,path,radio=inputs(tmp_path,episode_trace,empty_window=1)
    manifest=run(tmp_path,path,radio)
    assert manifest['status']=='completed' and manifest['episode_status']=='failed'
    folder=tmp_path/'runs/case/stars-fixed';report=validate_run(folder)
    assert report['usable_episode'] and report['approved_windows']==1
    e=read_json(folder/'attempt-0000/episode.json')
    assert [w['status'] for w in e['windows']]==['committed','failed','not_attempted']


@pytest.mark.parametrize('target',['attempt-0000/metrics.json','trace.json','boundary-0000.json','source/src/stars_rl/simulation.py'])
def test_missing_or_corrupted_artifacts_reject(tmp_path,episode_trace,target):
    trace,rates,path,radio=inputs(tmp_path,episode_trace);run(tmp_path,path,radio)
    folder=tmp_path/'runs/case/stars-fixed';(folder/target).write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match='hash'):validate_run(folder)


def test_missing_output_rejects(tmp_path,episode_trace):
    trace,rates,path,radio=inputs(tmp_path,episode_trace);run(tmp_path,path,radio)
    folder=tmp_path/'runs/case/stars-fixed';(folder/'attempt-0000/metrics.json').unlink()
    with pytest.raises(FileNotFoundError):validate_run(folder)


def test_resume_rejects_settings_trace_and_environment_changes(tmp_path,episode_trace,monkeypatch):
    import stars_rl.experiments.runner as runner
    trace,rates,path,radio=inputs(tmp_path,episode_trace)
    def crash(point):raise RuntimeError('stop before episode')
    with pytest.raises(RuntimeError):run(tmp_path,path,radio,_fault=crash)
    with pytest.raises(ValueError,match='config'):
        run_experiment(path,tmp_path/'runs','case',rho=.5,total_budget_seconds=3,radio_coefficients_path=radio,resume=True)
    from stars_rl.topology.trace import build_trace
    altered=build_trace(replace(trace.scenario,scenario_id='new-label'))
    other=tmp_path/'other.json';save_trace(altered,other)
    assert altered.content_hash==trace.content_hash  # relabeling is not new data
    with pytest.raises(ValueError,match='trace'):run(tmp_path,other,radio,resume=True)
    original=runner.environment
    def changed():
        env=original();env['backend']['scip']='different-version';return env
    monkeypatch.setattr(runner,'environment',changed)
    with pytest.raises(ValueError,match='code, dependencies'):run(tmp_path,path,radio,resume=True)
    assert read_json(tmp_path/'runs/case/stars-fixed/manifest.json')['attempts'][0]['status']=='interrupted'


def test_aborted_infrastructure_data_retained_without_boundary_advance(tmp_path,episode_trace):
    from stars_rl.simulation import RuntimeServices
    trace,rates,path,radio=inputs(tmp_path,episode_trace)
    def broken(*args,**kwargs):raise RuntimeError('controlled infrastructure error')
    frozen=simulate(trace,services=RuntimeServices(stage1=broken),radio_coefficients_by_window=rates)
    frozen.windows[0].stages['stage1'].values['invalid_raw']=float('nan')
    def controlled(*args,**kwargs):return deepcopy(frozen)
    manifest=run(tmp_path,path,radio,_simulate_fn=controlled)
    folder=tmp_path/'runs/case/stars-fixed'
    assert manifest['status']=='aborted' and manifest['active_boundary']=='boundary-0000.json'
    assert read_json(folder/'attempt-0000/boundary_end.json')['next_episode_index']==0
    episode=read_json(folder/'attempt-0000/episode.json')
    assert episode['windows'][0]['stages']['stage1']['values']['invalid_raw']=={'invalid_numeric':'nan'}
    assert not validate_run(folder)['usable_episode']
    with pytest.raises(ValueError,match='diagnosis'):run(tmp_path,path,radio,resume=True,_simulate_fn=controlled)


def test_rehashed_wrong_metrics_still_fail_independent_recomputation(tmp_path,episode_trace):
    from stars_rl.experiments.manifest import file_hash
    trace,rates,path,radio=inputs(tmp_path,episode_trace);run(tmp_path,path,radio)
    folder=tmp_path/'runs/case/stars-fixed';attempt=folder/'attempt-0000'
    episode=read_json(attempt/'episode.json');episode['windows'][1]['metrics']['access_switches']=0
    atomic_json(attempt/'episode.json',episode)
    metrics=read_json(attempt/'metrics.json');metrics[1]['metrics']['access_switches']=0;atomic_json(attempt/'metrics.json',metrics)
    transaction=read_json(attempt/'transaction.json')
    for name in ('episode.json','metrics.json'):transaction['files'][name]=file_hash(attempt/name)
    atomic_json(attempt/'transaction.json',transaction)
    manifest=read_json(folder/'manifest.json')
    for name in ('episode.json','metrics.json','transaction.json'):manifest['artifact_hashes']['attempt-0000/'+name]=file_hash(attempt/name)
    atomic_json(folder/'manifest.json',manifest)
    with pytest.raises(ValueError,match='change metrics'):validate_run(folder)


def test_resume_rejects_boundary_state_corruption(tmp_path,episode_trace):
    from stars_rl.experiments.manifest import digest,file_hash
    trace,rates,path,radio=inputs(tmp_path,episode_trace)
    def crash(point):raise RuntimeError('before episode0')
    with pytest.raises(RuntimeError):run(tmp_path,path,radio,_fault=crash)
    folder=tmp_path/'runs/case/stars-fixed';state=read_json(folder/'boundary-0000.json')
    state['next_episode_index']=1;state['state_hash']=digest({k:v for k,v in state.items() if k!='state_hash'})
    atomic_json(folder/'boundary-0000.json',state)
    manifest=read_json(folder/'manifest.json');manifest['input_hashes']['boundary-0000.json']=file_hash(folder/'boundary-0000.json')
    atomic_json(folder/'manifest.json',manifest)
    with pytest.raises(ValueError,match='boundary state'):run(tmp_path,path,radio,resume=True)


def test_identical_real_trace_settings_reproduce_literal_objectives(tmp_path,episode_trace):
    trace,rates,path,radio=inputs(tmp_path,episode_trace)
    a=run(tmp_path,path,radio,run_id='repeat-a');b=run(tmp_path,path,radio,run_id='repeat-b')
    assert a['settings_hash']==b['settings_hash'] and a['trace_content_hash']==b['trace_content_hash']
    for run_id in ('repeat-a','repeat-b'):
        episode=read_json(tmp_path/f'runs/{run_id}/stars-fixed/attempt-0000/episode.json')
        objectives=[w['stages']['stage2']['objective'] for w in episode['windows']]
        assert objectives==pytest.approx([0,1,0],rel=0,abs=1e-8)
        assert episode['windows'][0]['stages']['stage1']['objective']==pytest.approx(800000/299792458,rel=0,abs=1e-10)
