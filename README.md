# STARS-RL Orchestration

An independent Python implementation of optimization-based STARS orchestration, followed by a reinforcement-learning extension that selects stability-weight ratios around the optimizer.

The project is being implemented incrementally. The current release provides the Python package and command-line scaffold; the optimization model, simulations, and RL functionality are not implemented yet.

## Requirements

- Python 3.11
- Windows PowerShell or a POSIX-compatible shell

Only Windows PowerShell has been verified locally so far. The CI workflow checks the same package and tests on Ubuntu.

## Setup

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build-lock.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
```

### POSIX shells

These are the corresponding commands; local POSIX execution has not yet been verified:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-build-lock.txt
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
```

## Current commands

```powershell
.\.venv\Scripts\python.exe -m stars_rl.cli --help
.\.venv\Scripts\python.exe -m stars_rl.cli --version
.\.venv\Scripts\python.exe -m pytest tests/unit/test_cli.py
```

Invalid CLI options return a nonzero exit status. There are no runnable optimization, simulation, or training commands yet.

## Scientific scope

The planned core uses SCIP through PySCIPOpt, retains continuous CPU allocation and hard feasibility constraints, and preserves temporal repair plus two-stage orchestration. The RL layer will select objective-weight ratios only after the fixed-weight optimizer has been independently validated. This project does not claim exact reproduction of unavailable author code or guaranteed RL superiority.

See [REFERENCES.md](REFERENCES.md) for the scientific reference and clean-room implementation note.

