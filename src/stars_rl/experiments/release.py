"""Release evidence and source hygiene; standard library, no solver imports."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

from .manifest import atomic_json,digest,file_hash,read_json

SECRET=re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
AUTH_URL=re.compile(r'https?://[^/\s:@]+:[^/\s@]+@')


def redact(text):
    text=SECRET.sub('[REDACTED_CREDENTIAL]',str(text))
    text=AUTH_URL.sub('https://[REDACTED_AUTH]@',text)
    text=re.sub(r'[A-Za-z]:[\\/][^\r\n\"\']+','[LOCAL_PATH]',text)
    return re.sub(r'/home/[^/\s]+','/home/[USER]',text)


def tracked_files(root):
    root=Path(root).resolve()
    names=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode('utf-8').split('\0')
    paths=[]
    for name in filter(None,names):
        path=(root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file():raise ValueError('tracked path missing or outside source root: '+name)
        paths.append((name,path))
    return paths


def source_hash(root):
    # Runtime/config/tests, not generated evidence tables or Markdown edits.
    return digest({name:hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
        for name,path in tracked_files(root) if path.suffix in ('.py','.json','.yaml','.yml','.toml') or name.startswith('requirements-')})


def source_audit(root):
    issues=[];inventory={}
    for name,path in tracked_files(root):
        parts=Path(name).parts
        if any(p in ('.venv','.tmp','runs','checkpoints','artifacts','__pycache__') for p in parts) or path.suffix.lower() in ('.pdf','.pem','.key') or (path.name.startswith('.env') and path.name!='.env.example'):
            issues.append(dict(path=name,reason='private/generated file is tracked'))
        data=path.read_bytes();inventory[name]=hashlib.sha256(data).hexdigest()
        text=data.decode('utf-8',errors='replace')
        if SECRET.search(text) or AUTH_URL.search(text):issues.append(dict(path=name,reason='credential-like content; value withheld'))
    return dict(passed=not issues,issues=issues,tracked_file_count=len(inventory),inventory_sha256=digest(inventory),
                scope='Pattern and tracked-path audit, not a guarantee against every possible secret format')


def junit_summary(path):
    root=ET.parse(path).getroot();cases=list(root.iter('testcase'))
    result=dict(tests=len(cases),failures=sum(c.find('failure') is not None for c in cases),
        errors=sum(c.find('error') is not None for c in cases),skipped=sum(c.find('skipped') is not None for c in cases),
        solver_tests=sum('.solver.' in c.attrib.get('classname','') for c in cases))
    result['passed']=bool(cases) and result['solver_tests']>0 and not any(result[k] for k in ('failures','errors','skipped'))
    return result


def release_audit(root,ci_report=None):
    root=Path(root).resolve();status=read_json(root/'release_status.json')
    if type(status.get('schema_version')) is not int or status['schema_version']!=1:raise ValueError('unsupported release status schema')
    hygiene=source_audit(root);blockers=[]
    if status['license']=='undecided_by_owner' and list(root.glob('LICENSE*')):
        raise ValueError('license file contradicts the owner\'s undecided status')
    if any(status.get('claims',{}).get(key) for key in ('rl_superiority_demonstrated','physical_training_ready','author_code_recovered')):
        raise ValueError('unsupported release claim requires separate reviewed scientific evidence')
    if status['license']=='undecided_by_owner':blockers.append('Owner has left licensing undecided')
    for name,state in status['gates'].items():
        if state not in ('passed','deferred') :blockers.append(name+': '+state)
    if status['release_tag']=='not_created':blockers.append('Release tag has not been reviewed or authorized')
    tests=None
    if ci_report is not None:
        tests=read_json(ci_report)
        if tests.get('schema_version')!=1 or tests.get('source_hash')!=source_hash(root):raise ValueError('CI evidence does not match this source')
    counts={} if tests is None else tests.get('tests') or {}
    executed=counts.get('tests',0)>0 and counts.get('solver_tests',0)>0 and all(counts.get(k)==0 for k in ('failures','errors','skipped'))
    software_ready=hygiene['passed'] and tests is not None and tests.get('status')=='passed' and executed
    if tests is None or tests.get('suite')!='full':blockers.append('Matching full-profile CI evidence required for release review')
    return dict(schema_version=1,software_checks_passed=software_ready,release_ready=software_ready and not blockers,
        release_blockers=blockers,source_hygiene=hygiene,source_hash=source_hash(root),license=status['license'],
        ci=None if tests is None else {k:tests[k] for k in ('suite','status','tests','backend_versions')},
        scientific_gates=status['gates'],scope='Review evidence only; this command never tags, publishes, trains or changes repository visibility')


def analysis_binding(folder):
    """Verify saved figures and chosen-policy pointers without importing a solver."""
    folder=Path(folder).resolve();data=read_json(folder/'analysis.json');meta=read_json(folder/'analysis_manifest.json')
    if data.get('schema_version')!=1 or meta.get('schema_version')!=1:raise ValueError('unsupported analysis schema')
    sha=file_hash(folder/'analysis.json')
    if meta['analysis_sha256']!=sha:raise ValueError('analysis checksum mismatch')
    figure_manifest=read_json(folder/'figures/plot_manifest.json')
    if figure_manifest.get('schema_version')!=1 or figure_manifest['analysis_sha256']!=sha:raise ValueError('figure source analysis differs')
    if figure_manifest['source']!=data['source']:raise ValueError('figure run/config source differs')
    from .manifest import checked_path
    methods=list(data['methods']);scenarios=sorted({r['trace_hash'] for r in data['episodes']})
    for name,figure in figure_manifest['figures'].items():
        if file_hash(checked_path(folder/'figures',name))!=figure['sha256']:raise ValueError('figure checksum mismatch')
        if figure['analysis_sha256']!=sha or figure['methods']!=methods or figure['scenarios']!=scenarios:
            raise ValueError('figure method/scenario binding differs')
    if data['source']['kind']=='C17 frozen evaluation':
        source=Path(data['source']['directory']);frozen=read_json(source/'frozen-selection.json')
        if file_hash(source/'frozen-selection.json')!=data['source']['freeze_sha256']:raise ValueError('selected policy freeze differs')
        policies=[p['policy_id'] for p in frozen['policies']]
        expected=set(policies)|{'fixed-0.5','fixed-'+str(float(frozen['comparator_rho']))}
        if set(methods)!=expected:raise ValueError('figure method set differs from selected policies/comparators')
        if data['comparisons']['policy_minus_tuned_fixed']['method_order']!=policies:
            raise ValueError('plotted policies do not match frozen configuration/seed grid')
    return dict(passed=True,analysis_sha256=sha,figures=len(figure_manifest['figures']),methods=methods,scenario_count=len(scenarios),
                scope=data['source']['scope'],claim='Artifact binding only; diagnostic sources do not establish policy superiority')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.cwd());parser.add_argument('--ci-report',type=Path)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--require-release',action='store_true')
    parser.add_argument('--analysis',nargs='*',type=Path,default=[])
    args=parser.parse_args(argv);report=release_audit(args.root,args.ci_report)
    report['analysis_bindings']=[analysis_binding(folder) for folder in args.analysis]
    args.output.parent.mkdir(parents=True,exist_ok=True);atomic_json(args.output,report)
    print(json.dumps(report,allow_nan=False))
    ok=report['source_hygiene']['passed'] and (args.ci_report is None or report['software_checks_passed'])
    return 0 if (report['release_ready'] if args.require_release else ok) else 1


if __name__=='__main__':raise SystemExit(main())
