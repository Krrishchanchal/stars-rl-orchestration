"""Fail-closed CI, artifact privacy and explicit release blockers."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import pytest
import yaml

from stars_rl.experiments.manifest import atomic_json
from stars_rl.experiments.release import analysis_binding,junit_summary,redact,release_audit,source_audit,source_hash
from stars_rl.experiments.manifest import file_hash

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture
def repo(tmp_path):
    subprocess.run(['git','init',str(tmp_path)],check=True,capture_output=True)
    (tmp_path/'source.py').write_text('value=1\n')
    atomic_json(tmp_path/'release_status.json',dict(schema_version=1,license='undecided_by_owner',
        release_tag='not_created',gates={'trained_policy':'not_run'}))
    subprocess.run(['git','add','.'],cwd=tmp_path,check=True,capture_output=True)
    return tmp_path


def junit(path,*,kind=None,solver=True):
    child='' if kind is None else '<'+kind+'/>'
    name='tests.solver.fixture' if solver else 'tests.unit.fixture'
    path.write_text(f'<testsuites><testsuite><testcase classname="{name}" name="one">{child}</testcase></testsuite></testsuites>')


@pytest.mark.parametrize('kind',[None,'failure','error','skipped'])
def test_junit_fails_for_any_failure_error_or_skip(tmp_path,kind):
    path=tmp_path/'junit.xml';junit(path,kind=kind)
    assert junit_summary(path)['passed']==(kind is None)


def test_empty_or_solver_free_suite_cannot_be_green(tmp_path):
    path=tmp_path/'junit.xml';junit(path,solver=False)
    assert not junit_summary(path)['passed']
    path.write_text('<testsuites/>')
    assert not junit_summary(path)['passed']


def test_source_hygiene_and_redaction_never_echo_credentials(repo):
    token='gh'+'p_'+'a'*35
    (repo/'source.py').write_text('token="'+token+'"\n')
    result=source_audit(repo)
    assert not result['passed'] and token not in json.dumps(result)
    auth=''.join(['https',':','//','account',':','password','@example.test/path'])
    sanitized=redact(token+' at C:\\Users\\Person\\secret.txt\n'+auth)
    assert token not in sanitized and 'Person' not in sanitized and 'password' not in sanitized


def test_generated_or_private_files_cannot_be_tracked(repo):
    (repo/'private.pdf').write_bytes(b'private fixture')
    subprocess.run(['git','add','private.pdf'],cwd=repo,check=True,capture_output=True)
    assert not source_audit(repo)['passed']


def test_owner_license_choice_and_scientific_blocks_survive_passing_ci(repo,tmp_path):
    report=tmp_path/'ci.json';atomic_json(report,dict(schema_version=1,source_hash=source_hash(repo),status='passed',suite='full',
        tests=dict(tests=1,failures=0,errors=0,skipped=0,solver_tests=1),backend_versions={'scip':'fixture'}))
    result=release_audit(repo,report)
    assert result['software_checks_passed'] and not result['release_ready']
    assert result['license']=='undecided_by_owner' and len(result['release_blockers'])>=3
    (repo/'source.py').write_text('value=2\n')
    with pytest.raises(ValueError,match='match this source'):release_audit(repo,report)


def test_ci_workflow_read_only_profiles_and_summary_upload():
    workflow=yaml.load((ROOT/'.github/workflows/tests.yml').read_text(),Loader=yaml.BaseLoader)
    assert workflow['permissions']=={'contents':'read'}
    assert set(workflow['on'])=={'push','pull_request','workflow_dispatch'}
    job=workflow['jobs']['regression'];steps=job['steps']
    assert set(job['strategy']['matrix']['os'])=={'ubuntu-latest','windows-latest'}
    assert all('continue-on-error' not in s for s in steps)
    upload=next(s for s in steps if s.get('uses','').startswith('actions/upload-artifact'))
    assert upload['if']=='always()' and upload['with']['path']=='artifacts/ci/public/'
    command=next(s['run'] for s in steps if 'scripts/ci_checks.py' in s.get('run',''))
    assert '"$CI_SUITE"' in command


def runner():
    spec=importlib.util.spec_from_file_location('ci_runner_fixture',ROOT/'scripts/ci_checks.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_missing_backend_is_visible_and_pytest_not_substituted(tmp_path,monkeypatch):
    module=runner();calls=[]
    def run(command,**kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1,stdout='',stderr='missing backend')
    monkeypatch.setattr(module.subprocess,'run',run)
    monkeypatch.setattr(module,'source_hash',lambda root:'fixture')
    # The audit is isolated from Git to keep this a backend-failure oracle.
    monkeypatch.setattr(module,'release_audit',lambda *args:dict(source_hygiene={'passed':True},release_ready=False,software_checks_passed=False))
    output=tmp_path/'ci'
    assert module.main(['--output',str(output)])==1
    assert len(calls)==1 and 'doctor' in calls[0]
    report=json.loads((output/'public/ci-report.json').read_text())
    assert report['status']=='failed' and report['tests'] is None
    assert not (output/'public/doctor.stderr.txt').exists()


def test_license_remains_undecided_in_source():
    status=json.loads((ROOT/'release_status.json').read_text())
    assert status['license']=='undecided_by_owner'
    assert not list(ROOT.glob('LICENSE*'))
    assert status['claims']['rl_superiority_demonstrated'] is False


def test_passing_label_cannot_hide_skips_or_license_contradiction(repo):
    path=repo/'ci.json';atomic_json(path,dict(schema_version=1,source_hash=source_hash(repo),status='passed',suite='full',
        tests=dict(tests=1,solver_tests=1,failures=0,errors=0,skipped=1),backend_versions={'scip':'fixture'}))
    assert not release_audit(repo,path)['software_checks_passed']
    (repo/'LICENSE').write_text('Unapproved license fixture')
    with pytest.raises(ValueError,match='contradicts'):release_audit(repo)


def test_figure_method_scenario_and_source_bindings(tmp_path):
    data=dict(schema_version=1,status='completed',source={'kind':'C13 fixed-method diagnostics','scope':'diagnostic'},
              methods={'fixed':{}},episodes=[{'trace_hash':'trace'}])
    atomic_json(tmp_path/'analysis.json',data);sha=file_hash(tmp_path/'analysis.json')
    atomic_json(tmp_path/'analysis_manifest.json',dict(schema_version=1,analysis_sha256=sha))
    figures=tmp_path/'figures';figures.mkdir();(figures/'sample.png').write_bytes(b'figure fixture')
    meta=dict(schema_version=1,analysis_sha256=sha,source=data['source'],figures={'sample.png':dict(
        sha256=file_hash(figures/'sample.png'),analysis_sha256=sha,methods=['fixed'],scenarios=['trace'])})
    atomic_json(figures/'plot_manifest.json',meta)
    assert analysis_binding(tmp_path)['passed']
    meta['figures']['sample.png']['methods']=['wrong-policy'];atomic_json(figures/'plot_manifest.json',meta)
    with pytest.raises(ValueError,match='method/scenario'):analysis_binding(tmp_path)


def test_claims_cannot_be_changed_to_rl_success_without_review(repo):
    path=repo/'release_status.json';data=json.loads(path.read_text());data['claims']={'rl_superiority_demonstrated':True};atomic_json(path,data)
    with pytest.raises(ValueError,match='unsupported'):release_audit(repo)
