"""Public CLI generation/provenance, fixed-method settings and saved validation."""
import json
from pathlib import Path
import subprocess
import sys
import yaml

from stars_rl.config import dump_scenario
from stars_rl.experiments.manifest import read_json


def cli(*args):
    return subprocess.run([sys.executable,'-m','stars_rl.cli',*map(str,args)],capture_output=True,text=True)


def prepare(tmp_path,episode_trace):
    trace,rates=episode_trace();scenario=tmp_path/'scenario.yaml';dump_scenario(trace.scenario,scenario)
    path=tmp_path/'trace.json'
    generated=cli('generate','--scenario',scenario,'--output',path)
    assert generated.returncode==0,generated.stderr
    radio=tmp_path/'rates.json';radio.write_text(json.dumps([{'window_index':w,'user_id':u,'satellite_id':s,'occupancy':n,'rate_bps':r}
        for w,table in rates.items() for (u,s,n),r in table.items()]))
    return path,radio


def test_cli_generate_simulate_validate_resume(tmp_path,episode_trace):
    path,radio=prepare(tmp_path,episode_trace)
    config=tmp_path/'settings.yaml';config.write_text(yaml.safe_dump({'method_id':'mono-temporal','rho':.5,'window_budget_seconds':2,'solver_seed':0}))
    root=tmp_path/'runs'
    result=cli('simulate','--trace',path,'--output-root',root,'--run-id','cli','--config',config,'--radio-coefficients',radio)
    assert result.returncode==0,result.stderr
    folder=root/'cli/mono-temporal';manifest=read_json(folder/'manifest.json')
    assert manifest['generation_timing']['seconds']>=0 and (folder/'generation.json').exists()
    assert cli('validate','--trace',path).returncode==0
    verified=cli('validate','--run-dir',folder)
    assert verified.returncode==0 and json.loads(verified.stdout)['approved_windows']==3
    resumed=cli('simulate','--output-root',root,'--run-id','cli','--method','mono-temporal','--resume')
    assert resumed.returncode==0,resumed.stderr
    assert len(read_json(folder/'manifest.json')['attempts'])==1
    collision=cli('simulate','--trace',path,'--output-root',root,'--run-id','cli','--method','mono-temporal')
    assert collision.returncode==2
    assert cli('generate','--scenario',tmp_path/'scenario.yaml','--output',path).returncode==2


def test_cli_bad_inputs_and_corrupt_trace_fail_clearly(tmp_path,episode_trace):
    path,radio=prepare(tmp_path,episode_trace)
    payload=read_json(path);payload['scenario']['satellites'][0]['cpu_capacity_mips']+=1
    path.write_text(json.dumps(payload))
    invalid=cli('validate','--trace',path)
    assert invalid.returncode==2 and 'checksum' in invalid.stderr
    missing=cli('validate','--run-dir',tmp_path/'missing')
    assert missing.returncode==2
    bad=cli('simulate','--trace',path,'--output-root',tmp_path/'runs','--run-id','invalid','--seed','1')
    assert bad.returncode==2 and 'frozen' in bad.stderr
    assert not (tmp_path/'runs/invalid/stars-fixed/manifest.json').exists()


def test_cli_failed_episode_keeps_artifacts_and_nonzero_exit(tmp_path,episode_trace):
    # Empty access is modeled episode failure, not malformed input.
    trace,_=episode_trace(empty_window=1);scenario=tmp_path/'scenario.yaml';dump_scenario(trace.scenario,scenario)
    path=tmp_path/'trace.json'
    assert cli('generate','--scenario',scenario,'--output',path).returncode==0
    result=cli('simulate','--trace',path,'--output-root',tmp_path/'runs','--run-id','failure','--budget','2')
    assert result.returncode==1,result.stderr
    folder=tmp_path/'runs/failure/stars-fixed';manifest=read_json(folder/'manifest.json')
    assert manifest['status']=='completed' and manifest['episode_status']=='failed'
    assert cli('validate','--run-dir',folder).returncode==0
