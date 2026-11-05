"""Same runner for local and hosted CI; no training or release side effects."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from stars_rl.experiments.manifest import atomic_json,file_hash
from stars_rl.experiments.release import junit_summary,redact,release_audit,source_hash

FAST_TESTS=['tests/unit','tests/solver/test_backend.py','tests/solver/test_stage1.py','tests/solver/test_stage2.py',
    'tests/integration/test_simulation.py','tests/integration/test_failures.py','tests/reproducibility/test_release.py']
FAST_IGNORES=['tests/unit/test_physical_generation.py','tests/unit/test_orbits.py','tests/unit/test_splits.py']


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--suite',choices=('fast','full'),default='fast')
    parser.add_argument('--output',type=Path,default=Path('artifacts/ci'));args=parser.parse_args(argv)
    root=Path(__file__).resolve().parents[1];output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    private=output/'private';public=output/'public';private.mkdir();public.mkdir()
    report=dict(schema_version=1,suite=args.suite,status='failed',source_hash=source_hash(root),tests=None,backend_versions=None)
    started=time.perf_counter()
    def run(label,command,timeout):
        result=subprocess.run(command,cwd=root,capture_output=True,text=True,errors='replace',timeout=timeout)
        (private/(label+'.stdout.txt')).write_text(result.stdout,encoding='utf-8')
        (private/(label+'.stderr.txt')).write_text(result.stderr,encoding='utf-8')
        if result.returncode:print(redact(result.stdout+'\n'+result.stderr))
        return result
    audit=None
    try:
        doctor=run('doctor',[sys.executable,'-m','stars_rl.cli','doctor','--solver'],120)
        if doctor.returncode:raise ValueError('required backend preflight failed; tests were not substituted or skipped')
        capability=json.loads(doctor.stdout)
        if capability.get('passed') is not True:raise ValueError('backend preflight did not pass')
        report['backend_versions']=capability['assignment']['backend_versions']
        # Keep fixture filenames below Windows path limits even in deep checkouts.
        # Retain the unique directory for diagnostics; publish only the summaries.
        temporary=Path(tempfile.mkdtemp(prefix='srl-ci-'))
        (private/'pytest-temp.txt').write_text(str(temporary),encoding='utf-8')
        junit=private/'junit.xml';command=[sys.executable,'-m','pytest','-q','--junitxml',str(junit),'--basetemp',str(temporary/'p')]
        if args.suite=='fast':
            command+=FAST_TESTS
            for name in FAST_IGNORES:command+=['--ignore',name]
        result=run('pytest',command,2100)
        report['tests']=junit_summary(junit)
        if result.returncode or not report['tests']['passed']:raise ValueError('regression failed, empty, or skipped required tests')
        if source_hash(root)!=report['source_hash']:raise ValueError('source changed during CI execution')
        report['status']='passed'
    except Exception as exc:
        report['error']=redact(type(exc).__name__+': '+str(exc))
    report['wall_seconds']=time.perf_counter()-started
    atomic_json(public/'ci-report.json',report)
    try:
        audit=release_audit(root,public/'ci-report.json')
        if not audit['source_hygiene']['passed']:report['status']='failed';report['error']='tracked source hygiene check failed'
    except Exception as exc:
        report['status']='failed';report['error']=redact(str(exc))
    atomic_json(public/'ci-report.json',report)
    if audit is not None:
        audit['ci']={k:report[k] for k in ('suite','status','tests','backend_versions')}
        audit['software_checks_passed']=audit['software_checks_passed'] and report['status']=='passed'
        audit['release_ready']=audit['release_ready'] and report['status']=='passed'
        audit['ci_report_sha256']=file_hash(public/'ci-report.json')
        atomic_json(public/'evidence-index.json',audit)
    print(json.dumps(report,allow_nan=False))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
