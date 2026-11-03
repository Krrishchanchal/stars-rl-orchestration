# STARS-RL Orchestration

An independent Python implementation of optimization-based STARS orchestration, followed by a reinforcement-learning extension that selects stability-weight ratios around the optimizer.

The project is being implemented incrementally. The current release provides the Python package, CLI, a verified SCIP backend capability check, validated schemas, direct numeric physics, immutable authored traces, and the discrete C1–C12 optimization layer. CPU/radio/delay constraints, the full STARS workflow, simulations, and RL functionality remain pending.

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
approval. Authored trace/path construction is available as described below.

## Numeric physics

`stars_rl.physics` provides explicit SI conversions, free-space received power,
thermal noise, SINR, equal-bandwidth Shannon rate and per-packet delay calculations.
Radio inputs come from the validated `Radio` record. Both shared bandwidth and
thermal noise are recomputed for each positive occupancy. `access_rate_table`
returns immutable link-budget records indexed by occupancy, with `None` at zero
occupancy because there is no active user rate there.

`end_to_end_delay` returns all five propagation classes: user-to-access,
access-to-first-host, consecutive host paths, last-host-to-egress and egress-to-GS.
It also retains each stage's processing delay and access serialization. Callers
must supply resolved path distances; the authored trace API below now constructs
them and checks connectivity. Zero path distance represents colocation; unavailable
paths (`None` or infinity) are rejected.

Latency uses one representative packet unchanged along the chain, not all traffic
generated in a window. Throughput CPU uses psi; packet processing uses omega.
The toy sets them equal as an explicit assumption, while the functions keep them
distinct. CPU remains an input to the direct calculation and a continuous decision
for the later optimizer; the throughput lower bound does not fix its allocation.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -c "from stars_rl.physics.delay import processing_seconds; print(processing_seconds(12000, 10, 100))"
.\.venv\Scripts\python.exe -m pytest tests/unit/test_units.py tests/unit/test_radio.py tests/unit/test_delay.py -q
```

The first command prints `0.0012` seconds. Tests use hand-derived examples and
an independent high-precision radio reference, documented in
`tests/fixtures/physics_oracles.json`. Comparing a solver export with these same
production helpers would provide consistency evidence only; it would not replace
the independent deployment validator planned for a later milestone.

## Authored traces and paths

`build_trace` materializes every authored window without sampling or solving.
Snapshots retain all satellites, explicit access/ground distance matrices (with
`None` for invisible pairs), visibility masks and all-pairs undirected ISL paths.
Shortest paths include identity paths of distance zero; disconnected pairs are
`None`. Unknown IDs are input errors. No host is pruned because of visibility or CPU.

Equal-cost paths use the lexicographically smallest complete ID sequence from
the smaller endpoint; reverse queries reverse that same path. Costs are compared
without an approximate tie tolerance. This is shortest-path computation, not a
placement heuristic.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -c "from stars_rl.config import load_scenario; from stars_rl.topology.trace import build_trace; t = build_trace(load_scenario('configs/toy.yaml')); print(len(t.windows), t.windows[0].paths.get('s0', 's2').distance_m)"
.\.venv\Scripts\python.exe -m pytest tests/unit/test_paths.py tests/unit/test_trace.py -q
```

The first command prints `3 200000.0`. Toy windows start at relative seconds
0, 60 and 120; u0 loses its s0 access edge in the second window. The last two
windows have unchanged connectivity.

`window.route_distances(user_id, access_id, host_ids, egress_id, ground_station_id)`
assembles all five propagation classes for the selected ordered host tuple.
Unavailable access, ground or ISL segments raise `RouteUnavailableError` carrying
the failed segment and endpoints. It checks connectivity only; resource, type,
throughput and SLA feasibility still need the later model/validator gates.

`save_trace` / `load_trace` round-trip versioned JSON, retaining the full scenario,
metadata and derived snapshots. Loading verifies checksums and reconstructs caches
from source inputs, rejecting stale/corrupt paths or matrices.

Two SHA-256 identifiers serve different purposes. `artifact_hash` includes full
provenance and cached paths. `content_hash` covers normalized exogenous inputs:
stable entity IDs, coordinates, link visibility/distances, relative window timing,
chains, demands, packets, resources and radio values. It excludes scenario/family
labels and generation/group/seed/absolute-time metadata, so relabeling identical
inputs does not evade content identity. Numeric equivalents such as 200 and 200.0
and different input insertion orders normalize identically. Stable entity IDs
remain semantic keys. The frozen toy content hash is recorded with independent
fixture derivations in `tests/fixtures/topology_oracles.json`.

This trace builder supports authored toy/analytical inputs. Physical trace generation,
matching audits, full optimization and episode simulation remain later milestones.

## Discrete optimization layer

`build_association_model(scenario, window)` creates binary associations and corrected
C1–C6 feasibility constraints. Each user selects exactly one access satellite and
exactly one `(satellite, ground station)` egress pair globally. Egress capacity
counts user flows across all ground-station choices once per satellite; access
capacity is a separate pool. Invisible access/gateway choices are absent from the
variable domain, representing the zero values required by C2/C5. No aggregate
ground-station capacity is added.

`build_discrete_model(scenario, window)` adds C7–C12, compatible instance choices,
activation equivalence, and all access/host/egress linkage classes. Instances keep
their `(type, instance_id, host)` identities. An instance activates exactly when
at least one eligible user-stage selects it; the activation upper bound counts
eligible user-stage occurrences, including users sharing a slice.

Reachable multi-hop hosts remain available regardless of direct user visibility.
The binary domain retains compatible instances on zero-CPU hosts; resource
constraints in the next milestone will reject their active use. Unreachable
link products are omitted together with explicit endpoint prohibition rows,
and every route-link class must sum to one. No nearest-host filtering is used.
All constraints/variables have deterministic source-family/entity names.

Both builders currently use a constant feasibility objective. The association
builder contains no placement/routing/CPU/radio/delay variables or constraints;
Stage I objectives and orchestration are still pending. Discrete-model solutions
do not certify CPU, radio throughput, delay or complete deployment feasibility.
The later full model and independent validator are required for that approval.
CPU allocation remains a continuous optimization decision for the next milestone.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -c "from stars_rl.config import load_scenario; from stars_rl.topology.trace import build_trace; from stars_rl.optimization.constraints import build_discrete_model; t = build_trace(load_scenario('configs/toy.yaml')); m, v = build_discrete_model(t.scenario, t.windows[0]); print(len(v.alpha), len(v.xi), len(v.beta))"
.\.venv\Scripts\python.exe -m pytest tests/solver/test_association.py tests/solver/test_placement.py tests/solver/test_activation.py tests/solver/test_linkage.py -m solver -q
```

The first command prints `4 4 24`. Solver checks include all 256 association-bit
patterns, all 16 tiny placement-bit patterns, AND truth tables, type/identity
checks and isolated disconnected-route fixtures. A hand-enumerated joint objective
checks the discrete model on connected/disconnected graphs; it is an algebraic
test objective, not a STARS objective. Exact fixture expectations and safe-domain
arguments are in `tests/fixtures/discrete_oracles.json`. Raw values remain in the
solver record; `decode_binary` rejects values outside the fixed integrality target
and does not substitute for constraint validation.

## Scientific scope

The planned core uses SCIP through PySCIPOpt, retains continuous CPU allocation and hard feasibility constraints, and preserves temporal repair plus two-stage orchestration. The RL layer will select objective-weight ratios only after the fixed-weight optimizer has been independently validated. This project does not claim exact reproduction of unavailable author code or guaranteed RL superiority.

See [REFERENCES.md](REFERENCES.md) for the scientific reference and clean-room implementation note.

