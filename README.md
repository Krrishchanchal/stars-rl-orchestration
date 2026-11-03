# STARS-RL Orchestration

An independent Python implementation of optimization-based STARS orchestration, followed by a reinforcement-learning extension that selects stability-weight ratios around the optimizer.

The project is being implemented incrementally. The current release provides the Python package, CLI, a verified SCIP backend capability check, and validated scenario/deployment schemas with an explicit toy configuration. The STARS network model, simulations, and RL functionality are not implemented yet.

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
.\.venv\Scripts\python.exe -m stars_rl.cli doctor --solver
.\.venv\Scripts\python.exe -m pytest
```

Invalid CLI options return a nonzero exit status. There are no runnable optimization, simulation, or training commands yet.

The doctor prints JSON containing analytical assignment and nonlinear reciprocal checks,
raw statuses, stage-local bounds/gaps, versions and warm-start diagnostics. Its exit status
is nonzero on a failed check. It is a backend smoke check, not a validated STARS deployment.
Solver tests additionally cover inactive undersized/zero-capacity hosts, algebraic CPU
allocation, physical scaling extremes and original-unit residual calibration. The full
independent deployment validator is still pending. No solver test is silently skipped.

Verified on Windows with CPython 3.11.4, PySCIPOpt 6.3.0 and bundled SCIP 10.0.2.
The pinned Windows wheel installs without a separate SCIP installation or solver license.
Linux CI is configured; its remote execution has not been verified here.

## Scenario inputs

`configs/toy.yaml` freezes `toy-v1`: two users, three satellites (one with zero CPU),
two function types and three 60-second windows. It includes every instance identity,
resource pool, radio constant, access window, ground link and undirected ISL distance.
It is synthetic connectivity, not an orbital scenario. Feasibility is not yet established.

After installing the current lock files, inspect its schema from the repository root:

```powershell
.\.venv\Scripts\python.exe -c "from stars_rl.config import load_scenario; s = load_scenario('configs/toy.yaml'); print(s.scenario_id, len(s.users), s.window_count)"
.\.venv\Scripts\python.exe -m pytest tests/unit/test_config.py -q
```

The first command prints `toy-v1 2 3`. Loading performs no sampling or solving.
Inputs are immutable typed records; unknown/missing fields, incorrect units/types,
duplicate identities, nonfinite numbers and repeated function types are rejected.
The numeric domain currently follows the backend calibration: demand 2–20 Mbps,
psi/omega 5–90 instructions/bit, packet size 512–12000 bits, 1–4 stages and CPU
0–2000 MIPS. Other positive physical constants and nonnegative overhead are explicit.

Demand, chain and SLA belong to each slice and apply to each of its users;
psi, omega and overhead belong to each function type. Access and egress pools are
separate. Instances use `(function_type_id, instance_id, satellite_id)` identities.
Generation metadata preserves family/lineage, named seeds and scoped original draws;
no physical scenario generator exists yet.

`scenario_to_dict` / `scenario_from_dict` and `dump_scenario` / `load_scenario`
provide round-trips. Deployment/outcome serializers and
`validate_deployment_structure` check IDs, completeness and type compatibility.
They do not certify CPU, radio, routing, visibility or delay feasibility; that needs
the later independent deployment validator. A candidate outcome is not a deployment
approval. Toy trace/path construction remains a later milestone.

## Scientific scope

The planned core uses SCIP through PySCIPOpt, retains continuous CPU allocation and hard feasibility constraints, and preserves temporal repair plus two-stage orchestration. The RL layer will select objective-weight ratios only after the fixed-weight optimizer has been independently validated. This project does not claim exact reproduction of unavailable author code or guaranteed RL superiority.

See [REFERENCES.md](REFERENCES.md) for the scientific reference and clean-room implementation note.

