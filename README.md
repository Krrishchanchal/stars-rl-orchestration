# STARS-RL Orchestration

An independent Python implementation of optimization-based STARS orchestration, followed by a reinforcement-learning extension that selects stability-weight ratios around the optimizer.

The project is being implemented incrementally. The current release provides the Python package, CLI, a verified SCIP backend, validated schemas, numeric physics, authored traces, and the discrete model. A C07 draft now adds continuous CPU, radio and end-to-end delay constraints. Its acceptance awaits C08's independent validator. The STARS workflow, simulations and RL remain pending.

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
The binary domain retains compatible instances on zero-CPU hosts; the C07 draft's
resource constraints reject their active use. Unreachable
link products are omitted together with explicit endpoint prohibition rows,
and every route-link class must sum to one. No nearest-host filtering is used.
All constraints/variables have deterministic source-family/entity names.

Both builders currently use a constant feasibility objective. The association
builder contains no placement/routing/CPU/radio/delay variables or constraints;
Stage I objectives and orchestration are still pending. Discrete-model solutions
do not certify CPU, radio throughput, delay or complete deployment feasibility.
The resource/delay additions below and independent validator are required for that
approval. CPU allocation is continuous.

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

## CPU, radio and end-to-end delay

`build_full_model(scenario, window)` extends the discrete model with C13–C16,
CPU gating, activation overhead, instance limits, occupancy-dependent radio and
the documented user-level throughput constraint. CPU remains a continuous
optimization decision. A tight-delay test requires 60 MIPS while throughput alone
requires 20; no minimum-CPU allocation shortcut is used.

Processing uses dimensionless variables `g=G/L`, `qhat=q/L` and `tau=t/(A/L)`.
The reciprocal equality is `tau*qhat=beta`, with `qhat=g+1-beta` and the conditional
bound `qhat <= (capacity/L)*beta +1-beta`. Its global upper bound is
`max(capacity/L,1)`, preserving inactive undersized and zero-capacity hosts.
The export restores CPU/q in MIPS and processing time in seconds for every
selected and unselected candidate.

Radio occupancy uses binary one-hot counts including zero and AND products for
each visible user/satellite/positive-occupancy combination. Service is summed
over the selected satellite once per user. Bandwidth/noise/rates come from the
physical radio inputs. Explicit authored coefficient tables are permitted only
for labeled analytical fixtures, whose original trusted tables must also be
supplied separately to the independent validator.

All five propagation classes, every candidate processing term and access
serialization enter C16. The builders retain a constant feasibility objective;
STARS method objectives and two-stage orchestration remain later work. No extra
ISL traffic constraints, scheduling policy or secondary CPU objective is added.

```powershell
.\.venv\Scripts\python.exe -c "from stars_rl.config import load_scenario; from stars_rl.topology.trace import build_trace; from stars_rl.optimization.monolithic import build_full_model; t = build_trace(load_scenario('configs/toy.yaml')); m, v = build_full_model(t.scenario, t.windows[0]); print(m.getNVars(), m.getNConss())"
.\.venv\Scripts\python.exe -m pytest tests/solver/test_cpu.py tests/solver/test_nonlinear_delay.py tests/solver/test_radio_occupancy.py -m solver -q
```

The first command prints `185 350` for toy window 0. Diagnostics provide build
time, generated counts, finite bounds, coefficient ranges and original-unit
scaling metadata before solving. More than 250000 estimated link variables is
blocked by default; larger builds require explicit opt-in plus a measured memory
forecast within the initial 2 GiB budget.

`export_solution(model, scenario, window, variables, result)` preserves the raw
solver result, decoded choices, all candidate reciprocal/CPU values, activations,
occupancies, rates and encoded delay components. No-incumbent outcomes retain
their status and have no candidate. Exported reports say `validation: not_run`.
An optimal solver status or a C04-helper consistency comparison does not approve
a deployment. The independent C08 validator checks full raw/decoded residuals
and corrupted exports; the joint C07/C08 acceptance gate passes. Stage I/II,
simulation and RL remain later work.

Analytical expectations and limits are in `tests/fixtures/resource_oracles.json`.

## Independent deployment validation

`validate_export(scenario, window, exported)` in `stars_rl.validation.deployment`
returns a separate report with status, reason, residual units, thresholds,
normalized violations and independently recomputed per-user delays. It consumes
plain exported data without a live solver, reconstructs shortest-path costs and
radio rates independently, checks raw algebra and decoded physical constraints,
and sums processing reconstruction errors across every candidate, including
inactive ones. No solver optimality status bypasses these checks.

```python
from stars_rl.validation.deployment import validate_export

validation = validate_export(scenario, window, exported)
if not validation.valid:
    print(validation.status, validation.errors)
    print([row for row in validation.residuals if not row.passed])
```

For analytical coefficient fixtures, pass the original trusted table separately
as `radio_coefficients=original_rates`; exported coefficients cannot certify
themselves. Unknown identities, malformed fields and nonfinite values are rejected.
No-incumbent reports preserve the solver cause and never approve a deployment.
Validation establishes feasibility within the registered original-unit tolerances,
not optimality. Redundant export fields use a small floating arithmetic roundoff
envelope; this does not relax any feasibility threshold.

The test suite includes 128 full-model extreme cases, all toy windows, literal
allocation oracles, each residual family's boundary, and adversarial processing,
CPU, routing, occupancy and throughput cases. Tests and public oracle metadata
are in `tests/unit/test_validator.py`, `tests/unit/test_residuals.py`,
`tests/solver/test_export_validation.py` and `tests/fixtures/validator_oracles.json`.

## Temporal repair and observed changes

`repair_previous(scenario, window, previous)` retains visible associations and
repairs missing access links by minimum propagation distance, with stable-ID
ties. Gateway repair retains the old visible pair, then tries another ground
station on the old satellite, then the globally nearest visible pair. Missing
alternatives produce explicit failure records. These are visibility references;
capacity collisions and disconnected routes can still make them infeasible.
The original committed deployment is immutable and remains separate.

```python
from stars_rl.optimization.repair import repair_previous, partial_start_values
from stars_rl.optimization.backend import submit_start

repair = repair_previous(scenario, window, previous)
if repair.status == "candidate":
    values = partial_start_values(scenario, window, repair)
    start = submit_start(model, values, kind="partial")
```

Use `include_placement=False` for an association-only model. Starts specify only
compatible alpha/xi/beta binaries; CPU, reciprocal, occupancy, routing and future
deviation auxiliaries remain unknown. A stored partial start is not a feasibility
certificate. Final results still require independent validation.

`change_metrics(scenario, original_previous, final_deployment,
previous_available=...)` compares with the last original committed deployment,
including choices that are no longer visible. It counts one switch once and
reports the corresponding two one-hot flips separately. Access, gateway pair,
function assignment, instance-ID, host and instance activation changes have
separate fields. Initial setup has zero changes; missing final deployments have
null change fields. Supply the immediately preceding window's availability
(`None` before the first window) to count outage/restoration events, while keeping
the last committed deployment across failed windows. These are window-level
events, not measurements of packet loss or migration downtime.

Stage I/II objectives and orchestration remain later milestones.

## Stage I association optimization

`build_stage1_model` builds a **binary linear** C1–C6 association model. The
first window minimizes the sum of access and egress propagation in seconds.
Later windows minimize `w_alpha*D_alpha + w_xi*D_xi`, with default weights of 1 and 1
and the visibility-repaired reference. `reference_mode="original"` selects the
documented diagnostic variant. Deviations use full logical domains, including
unavailable prior choices, and fixed `2*users` denominators. There are no CPU,
placement, radio-throughput or complete-route constraints in Stage I.

```python
import time
from stars_rl.optimization.stage1 import run_stage1

started_at = time.perf_counter()  # before any observation/inference/repair work
outcome = run_stage1(scenario, window, previous,
                     total_budget_seconds=10, started_at=started_at)
if outcome.status == "reference_ready":
    reference = outcome.stage1_reference
```

Stage I build, warm-start submission, solving, extraction and independent checking
must finish by 15% of the total window budget. Remaining solver allowance shrinks
with elapsed work. Late results are retained diagnostically and cannot become a
reference; build/check overruns are detected rather than forcibly interrupted.
A valid nonoptimal incumbent may become a soft reference, with its original
status/bounds/gaps preserved. No incumbent means `stage1_no_reference`, with its
underlying cause; repair is never silently substituted.

The independent checker validates raw rows and decoded C1–C6, and recomputes both
the encoded objective and actual association deviations. Epigraph auxiliaries
may be slack in nonoptimal or zero-weight solutions, so their values are never
reported as actual change metrics. Reference availability certifies association
feasibility only. Stage II/full deployment validation is still required.
Explicit `objective_mode="propagation"` supports later hierarchy-only windows;
these use no prior temporal state/start when called with `previous=None`.
No secondary tie-breaking objective is added. C11 Stage II is still pending.

## Scientific scope

The planned core uses SCIP through PySCIPOpt, retains continuous CPU allocation and hard feasibility constraints, and preserves temporal repair plus two-stage orchestration. The RL layer will select objective-weight ratios only after the fixed-weight optimizer has been independently validated. This project does not claim exact reproduction of unavailable author code or guaranteed RL superiority.

See [REFERENCES.md](REFERENCES.md) for the scientific reference and clean-room implementation note.

