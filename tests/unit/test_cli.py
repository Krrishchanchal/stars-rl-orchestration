from __future__ import annotations

import subprocess
import sys
from importlib.metadata import version


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "stars_rl.cli", *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_help_exits_successfully() -> None:
    result = run_cli("--help")
    assert result.returncode == 0
    assert "usage: stars-rl" in result.stdout
    assert result.stderr == ""


def test_invalid_argument_exits_nonzero() -> None:
    result = run_cli("--not-a-real-option")
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_version_matches_installed_metadata() -> None:
    result = run_cli("--version")
    assert result.returncode == 0
    assert result.stdout.strip() == f"stars-rl {version('stars-rl')}"
    assert result.stderr == ""

