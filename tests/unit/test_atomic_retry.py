"""Reproduce the observed Windows replace denial without weakening errors."""
import os
import pytest

from stars_rl.experiments.manifest import atomic_json,read_json


@pytest.mark.parametrize('failures',[2,6])
def test_transient_and_persistent_windows_replace_denial(tmp_path,monkeypatch,failures):
    path=tmp_path/'state.json';atomic_json(path,{'old':True})
    original=os.replace;calls=[];waits=[]
    def replace(source,target):
        calls.append((source,target))
        if len(calls)<=failures:
            error=PermissionError('controlled Windows access denial');error.winerror=5
            raise error
        return original(source,target)
    monkeypatch.setattr('stars_rl.experiments.manifest.os.replace',replace)
    monkeypatch.setattr('stars_rl.experiments.manifest.time.sleep',waits.append)
    if failures==6:
        with pytest.raises(PermissionError):atomic_json(path,{'new':True})
        assert read_json(path)=={'old':True} and len(calls)==6
    else:
        atomic_json(path,{'new':True})
        assert read_json(path)=={'new':True} and len(calls)==3
    assert waits==[.01,.02,.04,.08,.16][:min(failures,5)]
    assert not list(tmp_path.glob('.state.json-*'))


def test_non_windows_permission_error_is_not_retried(tmp_path,monkeypatch):
    calls=[]
    def replace(*args):calls.append(args);raise PermissionError('permanent ordinary permission failure')
    monkeypatch.setattr('stars_rl.experiments.manifest.os.replace',replace)
    with pytest.raises(PermissionError):atomic_json(tmp_path/'state.json',{})
    assert len(calls)==1
