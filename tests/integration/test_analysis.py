"""Saved-only aggregation with complete paired domains and failure retention."""
from pathlib import Path
import json
import subprocess
import sys
import pytest

from test_evaluation import prepare,EvaluationFixture
from stars_rl.experiments.aggregate import analyze,load_evaluation,training_curve
from stars_rl.experiments.evaluate import evaluate
from stars_rl.experiments.manifest import atomic_json,file_hash,read_json


@pytest.fixture
def saved(tmp_path,episode_trace):
    split,runs=prepare(tmp_path,episode_trace,seeds=(7,8),rates=(.1,))
    folder=tmp_path/'evaluation'
    evaluate(split,runs,folder,budget=2,_test_environment_factory=EvaluationFixture)
    return folder,runs


def test_analysis_pairing_failures_nulls_training_and_tables(saved,tmp_path):
    folder,runs=saved
    result=analyze(tmp_path/'analysis',evaluation=folder,training=[runs[0]],bootstrap_seed=7)
    assert len(result['methods'])==4 and result['exclusions']==[]
    assert result['comparisons']['policy_minus_tuned_fixed']['training_seed_count']==2
    assert result['comparisons']['policy_minus_tuned_fixed']['scenario_group_count']==1
    assert all(m['episodes']==2 and m['failures']==1 and m['completion_rate']==.5 for m in result['methods'].values())
    assert all(m['delay_ms']==dict(n=0,mean=None,p95=None) for m in result['methods'].values())
    assert all(m['cpu_utilization']['mean'] is None for m in result['methods'].values())
    assert all(m['events']['access_switches'] is None for m in result['methods'].values())
    assert len(result['training'][0]['points'])==2 and sum(result['training'][0]['action_counts'])==4
    assert (tmp_path/'analysis/methods.csv').is_file() and (tmp_path/'analysis/episodes.csv').is_file()
    assert read_json(tmp_path/'analysis/analysis_manifest.json')['solver_calls']==0
    with pytest.raises(FileExistsError):analyze(tmp_path/'analysis',evaluation=folder)


def rewrite_row(folder,change):
    manifest=read_json(folder/'manifest.json')
    name=next(n for n in manifest['artifact_hashes'] if n.startswith('test-') and read_json(folder/n)['status']=='failed')
    row=read_json(folder/name);change(row);atomic_json(folder/name,row)
    manifest['artifact_hashes'][name]=file_hash(folder/name);atomic_json(folder/'manifest.json',manifest)


@pytest.mark.parametrize('kind',['score','null','method','error'])
def test_corrupt_or_error_episode_rejected_even_if_file_hash_rewritten(saved,kind):
    folder,_=saved
    def change(row):
        if kind=='score':row['penalized_score']=0
        elif kind=='null':row['windows'][2]['metrics']={}
        elif kind=='method':row['policy_id']='other'
        else:row['status']='infrastructure_error'
    rewrite_row(folder,change)
    with pytest.raises(ValueError):load_evaluation(folder)


def test_missing_method_episode_not_silently_excluded(saved):
    folder,_=saved;manifest=read_json(folder/'manifest.json')
    name=next(n for n in manifest['artifact_hashes'] if n.startswith('test-'))
    manifest['artifact_hashes'].pop(name);atomic_json(folder/'manifest.json',manifest)
    with pytest.raises(ValueError,match='grid'):load_evaluation(folder)


def test_wrong_manifest_version_and_training_step_tamper(saved):
    folder,runs=saved;manifest=read_json(folder/'manifest.json');manifest['schema_version']=2;atomic_json(folder/'manifest.json',manifest)
    with pytest.raises(ValueError,match='version'):load_evaluation(folder)
    path=runs[0]/'attempt-0000/step-0001.json';path.write_text('{}')
    with pytest.raises(ValueError,match='step checksum'):training_curve(runs[0])


def test_analysis_cli_imports_no_solver_or_learning_modules(saved,tmp_path):
    folder,_=saved
    script=tmp_path/'saved_only.py'
    script.write_text("""import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,name,*args):
        if name.startswith(('pyscipopt','stars_rl.optimization','stars_rl.rl','stars_rl.topology')):
            raise AssertionError('analysis attempted solver/environment import: '+name)
sys.meta_path.insert(0,Block())
from stars_rl.cli import main
raise SystemExit(main(sys.argv[1:]))
""")
    result=subprocess.run([sys.executable,str(script),'plot','--evaluation',str(folder),'--output',str(tmp_path/'cli'),
                           '--bootstrap-seed','7'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['solver_calls']==0
    assert not json.loads(result.stdout)['figures_rendered']


@pytest.mark.parametrize('failed',[False,True])
def test_saved_fixed_run_includes_real_approved_samples_or_failure_nulls(episode_trace,tmp_path,failed):
    from stars_rl.experiments.runner import run_experiment
    from stars_rl.topology.trace import save_trace
    trace,_=episode_trace(empty_window=0 if failed else None)
    source=tmp_path/'trace.json';save_trace(trace,source)
    run_experiment(source,tmp_path/'runs','fixed','stars-fixed',rho=.5,total_budget_seconds=3)
    folder=tmp_path/'runs/fixed/stars-fixed'
    result=analyze(tmp_path/'analysis',runs=[folder])
    data=result['methods']['stars-fixed-rho-0.5']
    if failed:
        assert data['failure_rate']==1 and data['delay_ms']['n']==0 and data['delay_ms']['mean'] is None
        assert data['unattempted_windows']==2
        assert data['mean_group_score']==pytest.approx(4*(1+.95+.95**2))
    else:
        assert data['completion_rate']==1 and data['delay_ms']['n']==3 and data['mean_group_score']==pytest.approx(2.85)
        assert data['events']['access_switches']==1 and data['events']['host_changes']==1
        assert data['cpu_utilization']['n']==3 and data['active_instances']['mean']==1
    with pytest.raises(ValueError,match='duplicate normalized'):analyze(tmp_path/'duplicate',runs=[folder,folder])
