"""Plot reader enforces saved schema/provenance before optional dependencies."""
import hashlib
import json
from pathlib import Path
import pytest

from stars_rl.experiments.plots import render


def test_renderer_rejects_wrong_version_without_importing_solver(tmp_path):
    source=tmp_path/'analysis.json';source.write_text(json.dumps(dict(schema_version=2,status='completed')))
    with pytest.raises(ValueError,match='unsupported'):render(source,tmp_path/'figures')
    assert not (tmp_path/'figures').exists()


def test_renderer_rejects_tampered_saved_analysis(tmp_path):
    source=tmp_path/'analysis.json';source.write_text(json.dumps(dict(schema_version=1,status='completed')))
    (tmp_path/'analysis_manifest.json').write_text(json.dumps(dict(schema_version=1,analysis_sha256='wrong')))
    with pytest.raises(ValueError,match='checksum'):render(source,tmp_path/'figures')
    assert not (tmp_path/'figures').exists()


def test_renderer_rejects_nonfinite_json(tmp_path):
    source=tmp_path/'analysis.json';source.write_text('{"schema_version":1,"status":"completed","x":NaN}')
    with pytest.raises(ValueError,match='nonfinite'):render(source,tmp_path/'figures')
