"""Physical CLI dispatch/audit persistence plus real small ladder supervision."""
from pathlib import Path
import pytest

from stars_rl.cli import main
from stars_rl.experiments.manifest import read_json
from stars_rl.topology.benchmark import benchmark_ladder


def test_physical_generate_dispatch_and_audit(physical_traces,tmp_path,monkeypatch,capsys):
    import stars_rl.topology.physical as physical
    import stars_rl.topology.trace as trace_module
    trace,stats=physical_traces['development-physical-v1']
    config=Path(__file__).resolve().parents[2]/'configs/development-physical-v1.yaml'
    def cached(path):
        assert path==config
        return trace,stats
    monkeypatch.setattr(physical,'load_physical_config',cached)
    path=tmp_path/'physical.json'
    assert main(['generate','--physical-config',str(config),'--output',str(path)])==0
    sidecar=read_json(path.with_name(path.name+'.generation.json'))
    assert sidecar['sampling']==stats
    monkeypatch.setattr(trace_module,'load_trace',lambda path:trace)
    output=tmp_path/'audit.json'
    assert main(['audit','--trace',str(path),'--output',str(output)])==0
    audit=read_json(output)
    assert audit['user_count']==4 and not audit['all_windows_necessary_passed']
    assert audit['region_bound']['reference_access_capacity_bound']==20


def test_generation_failure_saved_without_fake_trace(tmp_path,monkeypatch):
    import stars_rl.topology.physical as physical
    def failure(path):raise physical.GenerationError('controlled layout cap',{'attempts':100000,'accepted_users':2,'requested_users':4})
    monkeypatch.setattr(physical,'load_physical_config',failure)
    config=tmp_path/'config.yaml';config.write_text('physical_schema_version: 1')
    output=tmp_path/'trace.json'
    assert main(['generate','--physical-config',str(config),'--output',str(output)])==2
    assert not output.exists()
    assert read_json(tmp_path/'trace.json.generation-failed.json')['status']=='generation_failed'


@pytest.mark.solver
def test_first_ladder_case_measured_and_validated(tmp_path):
    report=benchmark_ladder(tmp_path/'ladder',sizes=((2,1),),budget=10)
    row=report['records'][0]
    assert row['status']=='success' and row['variables']==row['estimated_variables']==82
    assert 0<row['peak_process_memory_bytes']<2*1024**3
    assert row['first_valid_incumbent_seconds'] is not None
    assert row['constraints']>0 and row['stage_times']['validation_wall_seconds']>=0
    assert not report['large_physical_experiments_authorized']


def test_ladder_does_not_skip_small_cases(tmp_path):
    with pytest.raises(ValueError,match='ordered prefix'):benchmark_ladder(tmp_path/'bad',sizes=((60,30),))
