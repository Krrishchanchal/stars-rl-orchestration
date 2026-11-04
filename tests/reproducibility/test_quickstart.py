"""Executable public examples: saved inference is explicitly untrained."""
import json
from pathlib import Path
import subprocess
import sys
import pytest

from stars_rl.config import load_scenario
from stars_rl.experiments.manifest import file_hash
from stars_rl.topology.trace import build_trace,save_trace

ROOT=Path(__file__).resolve().parents[2]
pytestmark=pytest.mark.solver


def execute(*args):
    return subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,capture_output=True,text=True)


def test_expected_quickstart_trace_is_tracked_and_exact():
    expected=json.loads((ROOT/'examples/expected_quickstart.json').read_text())
    trace=build_trace(load_scenario(ROOT/'configs/toy.yaml'))
    assert trace.content_hash==expected['toy']['trace_content_hash']
    assert (len(trace.scenario.users),len(trace.windows))==(expected['toy']['users'],expected['toy']['windows'])


def test_saved_policy_fresh_process_roundtrip_and_readonly_inference(tmp_path):
    trace=build_trace(load_scenario(ROOT/'configs/toy.yaml'));source=tmp_path/'trace.json';save_trace(trace,source)
    script=ROOT/'examples/saved_policy_demo.py';first=tmp_path/'first';second=tmp_path/'second'
    created=execute(script,'--trace',source,'--output',first)
    assert created.returncode==0,created.stderr
    original=file_hash(first/'policy.json')
    replay=execute(script,'--trace',source,'--policy-dir',first,'--output',second)
    assert replay.returncode==0,replay.stderr
    for folder in (first,second):
        summary=json.loads((folder/'summary.json').read_text())
        assert summary['committed_windows']==3 and summary['solver_calls']==6
        assert summary['updates']==summary['exploration_steps']==0 and summary['policy_unchanged']
        assert summary['penalized_score']==pytest.approx(.475,abs=1e-8)
        assert 'Untrained' in summary['scope']
    assert file_hash(first/'policy.json')==original
    repeat=execute(script,'--trace',source,'--policy-dir',first,'--output',second)
    assert repeat.returncode!=0 and file_hash(first/'policy.json')==original
    incompatible=execute(script,'--trace',source,'--policy-dir',first,'--output',tmp_path/'different-budget','--budget','11')
    assert incompatible.returncode!=0 and 'differs' in incompatible.stderr


def test_handover_demo_is_validated_and_refuses_overwrite(tmp_path):
    output=tmp_path/'handover';script=ROOT/'examples/demo.py'
    result=execute(script,'--output',output)
    assert result.returncode==0,result.stderr
    summary=json.loads((output/'summary.json').read_text())
    assert len(summary)==3 and all(r['validated'] for r in summary)
    assert [r['access_switches'] for r in summary]==[0,1,0]
    assert [r['host_changes'] for r in summary]==[0,2,0]
    assert all(r['delay_ms']<=r['sla_ms']+1e-4 for r in summary)
    original=file_hash(output/'raw_result.json')
    repeat=execute(script,'--output',output)
    assert repeat.returncode!=0 and file_hash(output/'raw_result.json')==original
