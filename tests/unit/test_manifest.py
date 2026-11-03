"""Atomic file replacement and strict bounded artifact paths/JSON."""
import pytest
from stars_rl.experiments.manifest import atomic_json,read_json,checked_path,run_lock
from stars_rl.experiments.runner import run_directory


def test_invalid_write_preserves_previous_file(tmp_path):
    path=tmp_path/'data.json';atomic_json(path,{'value':1});before=path.read_bytes()
    with pytest.raises(ValueError):atomic_json(path,{'value':float('nan')})
    assert path.read_bytes()==before and read_json(path)=={'value':1}


@pytest.mark.parametrize('payload',['{"a":1,"a":2}','{"a":NaN}','{"a":1e999}'])
def test_invalid_json_rejects(tmp_path,payload):
    path=tmp_path/'bad.json';path.write_text(payload)
    with pytest.raises(ValueError):read_json(path)


@pytest.mark.parametrize('name',['../escape','..','CON','a.','bad/name'])
def test_run_ids_cannot_alias_or_escape(tmp_path,name):
    with pytest.raises(ValueError):run_directory(tmp_path,name,'stars-fixed')


def test_artifact_path_cannot_escape(tmp_path):
    with pytest.raises(ValueError):checked_path(tmp_path,'../escape.json')


def test_exclusive_lock_and_release(tmp_path):
    with run_lock(tmp_path):
        with pytest.raises(ValueError,match='locked'):
            with run_lock(tmp_path):pass
    with run_lock(tmp_path):pass
