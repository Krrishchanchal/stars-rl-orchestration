"""Strict JSON, atomic files, content identities and measured runtime metadata."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time


SCHEMA_VERSION=1


def utc_now():return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ValueError(f'duplicate JSON field: {k}')
            result[k]=v
        return result
    def invalid(value):raise ValueError(f'nonfinite JSON value: {value}')
    def number(value):
        parsed=float(value)
        if not math.isfinite(parsed):raise ValueError('nonfinite JSON number')
        return parsed
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=pairs,parse_constant=invalid,parse_float=number)


def atomic_json(path,value):
    path=Path(path)
    payload=json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n'
    fd,temp=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as stream:
            stream.write(payload);stream.flush();os.fsync(stream.fileno())
        # Windows scanners/indexers can briefly hold the destination without
        # delete sharing. Retry only those Windows errors; preserve atomicity,
        # the old file and the final exception on persistent access denial.
        for attempt in range(6):
            try:
                os.replace(temp,path)
                break
            except PermissionError as exc:
                if getattr(exc,'winerror',None) not in (5,32,33) or attempt==5:
                    raise
                time.sleep(.01*2**attempt)
    finally:
        if os.path.exists(temp):os.unlink(temp)


@contextmanager
def run_lock(directory):
    """OS lock releases even after a killed worker; a leftover file is harmless."""
    with (Path(directory)/'.lock').open('a+b') as stream:
        stream.seek(0,2)
        if stream.tell()==0:stream.write(b'0');stream.flush()
        stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:raise ValueError('run is locked by another worker') from exc
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def environment():
    from stars_rl.optimization.backend import create_model,versions,PARAMETERS
    package=Path(__file__).resolve().parents[1]
    repo=Path(__file__).resolve().parents[3]
    source={str(p.relative_to(package)).replace('\\','/'):file_hash(p) for p in sorted(package.rglob('*.py'))}
    for filename in ('pyproject.toml','requirements-lock.txt','requirements-build-lock.txt'):
        if (repo/filename).is_file():source['@repo/'+filename]=file_hash(repo/filename)
    def git(*args):
        try:return subprocess.check_output(['git',*args],cwd=repo,stderr=subprocess.DEVNULL).decode().strip()
        except (OSError,subprocess.CalledProcessError):return None
    revision=git('rev-parse','HEAD')
    git_state={'revision':revision,'status_porcelain':git('status','--porcelain'),
               'tracked_diff_sha256':None}
    try:git_state['tracked_diff_sha256']=hashlib.sha256(subprocess.check_output(['git','diff','HEAD','--binary'],cwd=repo,stderr=subprocess.DEVNULL)).hexdigest()
    except (OSError,subprocess.CalledProcessError):pass
    hardware={'platform':platform.platform(),'machine':platform.machine(),'processor':platform.processor(),
              'logical_cpus':os.cpu_count(),'total_physical_memory_bytes':None}
    if os.name=='nt':
        import ctypes
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),*[(n,ctypes.c_ulonglong) for n in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]]
        info=Memory();info.length=ctypes.sizeof(info)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):hardware['total_physical_memory_bytes']=info.total
    elif hasattr(os,'sysconf'):
        try:hardware['total_physical_memory_bytes']=os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')
        except (ValueError,OSError):pass
    dependencies={d.metadata['Name']:d.version for d in metadata.distributions() if d.metadata['Name']}
    return {'python':sys.version,'executable':sys.executable,'dependencies':dict(sorted(dependencies.items())),
            'backend':versions(create_model('manifest_probe')),'solver_parameters':dict(PARAMETERS),
            'hardware':hardware,'git':git_state,'source_files':source,'source_hash':digest(source)}


def compatibility_profile(env):
    return {k:env[k] for k in ('python','dependencies','backend','solver_parameters','hardware','source_hash')} | {'revision':env['git']['revision']}


def checked_path(directory,relative):
    root=Path(directory).resolve()
    if not isinstance(relative,str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('unsafe artifact path')
    path=(root/relative).resolve()
    if not path.is_relative_to(root):raise ValueError('artifact escapes run directory')
    return path


def diagnostic_json(value):
    """Only aborted reports use explicit tags for invalid raw numbers."""
    if isinstance(value,float) and not math.isfinite(value):return {'invalid_numeric':repr(value)}
    if isinstance(value,dict):return {k:diagnostic_json(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [diagnostic_json(v) for v in value]
    return value
