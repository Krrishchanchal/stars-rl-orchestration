# STARS-RL Orchestration

An independent Python implementation of optimization-based STARS orchestration, followed by a reinforcement-learning extension that selects stability-weight ratios around the optimizer.

The current implementation provides validated scenario inputs, authored traces, continuous-CPU optimization, independent deployment checks, temporal repair, both STARS stages, and episode simulation with three independent baselines. The experiment runner records reproducible inputs and artifacts. Frozen circular-orbit generation, coverage audits, tabular Q-learning with boundary recovery, and grouped frozen-policy evaluation are implemented. The solver-backed training pilot and scientific held-out evaluation remain blocked by readiness gates.

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

Invalid CLI options return a nonzero exit status. Optimization and episode simulation are available through the Python APIs and CLI below. Training remains later work.

The doctor prints JSON containing analytical assignment and nonlinear reciprocal checks,
raw statuses, stage-local bounds/gaps, versions and warm-start diagnostics. Its exit status
is nonzero on a failed check. It is a backend smoke check, not a validated STARS deployment.
Solver tests additionally cover inactive undersized/zero-capacity hosts, algebraic CPU
allocation, physical scaling extremes and original-unit residual calibration. The independent deployment validator checks complete exported candidates. No solver test is silently skipped.

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
the independent deployment validator described below.

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

Authored toy/analytical traces retain their original format and hashes. Physical
traces add frozen orbit metadata and derive access, ground-station, ISL and path
data separately for every window. Episode simulation audits physical snapshots
before expensive model construction.

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
The binary domain retains compatible instances on zero-CPU hosts; the full model's
resource constraints reject their active use. Unreachable
link products are omitted together with explicit endpoint prohibition rows,
and every route-link class must sum to one. No nearest-host filtering is used.
All constraints/variables have deterministic source-family/entity names.

Both builders currently use a constant feasibility objective. The association
builder contains no placement/routing/CPU/radio/delay variables or constraints;
Stage I adds objectives separately. Discrete-model solutions
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

Stage I/II objectives and episode orchestration are described below.

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
No secondary tie-breaking objective is added.

## Stage II full deployment optimization

`build_stage2_model` extends the common full feasible set with the objective
`w_H*H + w_beta*D_beta`. Access and gateway binaries remain free: Stage I is a
soft preference, so Stage II can correct associations that fail radio, CPU,
route or delay requirements. `H` divides combined access/gateway one-hot L1 by
`4*users`; placement L1 uses `2*user_stages` against the original committed
deployment. Initial setup has `D_beta=0`. No secondary CPU objective is added.

```python
from stars_rl.optimization.stage2 import run_stage2

second = run_stage2(scenario, window, outcome, previous,
                    started_at=started_at, total_budget_seconds=10,
                    weights=(1, 0.5))
if second.status == "validated":
    candidate = second.final_deployment
```

Pass the same start time and budget used by Stage I. Stage II solves until 95%
of that shared budget and checks the result until 100%; elapsed Stage I work is
not reset. Late output retains diagnostics but has no final deployment. A valid
nonoptimal incumbent may be accepted with its own status/bounds/gaps. Missing
Stage I reference means Stage II is not attempted.

Default starts are true partial solutions: current Stage I association binaries
and compatible prior placements, with resource/routing/occupancy/deviation
auxiliaries unknown. Explicit complete starts require every variable and are
checked before submission; known-invalid complete starts are withheld. Neither
start policy changes the feasible set or fixes Stage I decisions.

`validate_stage2` independently checks C21–C26, recomputes actual `H`/`D_beta`
and the encoded objective, and invokes the independent full-deployment validator
on the base decisions. The original export retains all raw auxiliaries and final
associations/resources. Actual model counts include added deviation variables;
no dimension reduction or warm-start speed advantage is claimed.
Accumulated auxiliary errors cannot underreport the actual discrete objective
by more than the fixed `1e-8` objective target. Positive epigraph slack in a
nonoptimal result is retained separately from actual change metrics.

The result is a validated deployment candidate. The episode runner below checks
and commits final choices for the following window.

## Episode simulation and independent baselines

```python
from stars_rl.config import load_scenario
from stars_rl.topology.trace import build_trace
from stars_rl.simulation import simulate

trace = build_trace(load_scenario("configs/toy.yaml"))  # offline common input
result = simulate(trace, "stars-fixed", rho=0.5, total_budget_seconds=10)
for window in result.windows:
    print(window.window_index, window.status, window.reason)
```

Each call owns fresh state. A final deployment becomes the next window's
committed prior only after independent validation at the state boundary and an
on-time decision. The raw export, separate stage statuses/bounds/gaps, start
reports, residuals, actual metrics, original prior and final commit are retained.
The extra commit-boundary check consumes the same shared budget; no extra solve
or secondary objective is introduced.

| Method | Initial objective | Later objective | Prior-window start |
|---|---|---|---|
| `mono-delay` | Mean E2E/SLA, `Q` | `Q` | None |
| `mono-temporal` | `Q` | `D_alpha+D_xi+D_beta`, original prior | Repaired associations and compatible placements |
| `hier-only` | Propagation then `H` | Propagation then `H` | None; Stage II can start from current Stage I associations |
| `stars-fixed` | Propagation then `H` | Repaired association deviations then `H+rho*D_beta` | Repair/previous partial starts |

The first three are independently specified baselines, not recovered author
MINLP methods. Definitions/defaults are in `configs/baselines.yaml`. Default
`rho=1` is diagnostic, not a validation-tuned comparator; always report `rho=0.5`
separately. Initial STARS setup records the forced irrelevant ratio 0.5 because
there is no prior placement. `stars-random`/`stars-q` policy selection is not
implemented at C12 and is rejected rather than simulated as a fixed policy.

The failure policy is **terminate at the first failed decision**. Proven
infeasibility, timeout/no incumbent, missing Stage I reference and late decisions
remain distinguishable. Remaining windows are explicitly `not_attempted`, never
fabricated successes or zero-cost outcomes. The last committed state is retained.
Numerical rejection and infrastructure/corrupted-data errors abort separately,
with `transition_valid=False`; they are not ordinary network failures. No reward
or training policy is implemented here.

Passing a saved **base full-model** window 0 export as `initial_export=...` runs a
separate `common_initial_state` study: the seed is independently checked within
the window budget and native initial objectives are skipped. Ordinary calls are
labeled `native_initialization`. Results from these studies must not be merged.
Synthetic analytical rates require original trusted tables supplied as
`radio_coefficients_by_window={window_index: table}`.

`simulate` commits in memory and returns dataclass records. The experiment runner
below publishes transactional files and manifests. `services` injection is for
controlled runtime tests and labels results as test adapters.
These tiny tests are not physical-scale or RL performance evidence.

## Reproducible experiment CLI

From the repository root, using the Python environment where this package is installed:

```powershell
.\.venv-c03\Scripts\python.exe -m stars_rl.cli generate --scenario configs/toy.yaml --output runs/toy-trace.json
.\.venv-c03\Scripts\python.exe -m stars_rl.cli simulate --trace runs/toy-trace.json --run-id demo-c13 --method stars-fixed --rho 0.5 --budget 10
.\.venv-c03\Scripts\python.exe -m stars_rl.cli validate --run-dir runs/demo-c13/stars-fixed
```

`generate --scenario` materializes authored scenarios; `--physical-config` creates
the frozen physical families below. Offline preparation cost is recorded in a
sidecar. `validate --trace PATH`
checks cached paths and hashes against the original scenario. The normalized
trace-content hash excludes arbitrary provenance labels; its separate artifact
hash retains the exact trace identity and group/lineage metadata.

Runs live under `OUTPUT_ROOT/RUN_ID/METHOD/`, defaulting to `runs/`. Different
methods can share a run ID and the same saved trace for paired comparisons;
an existing method run cannot be overwritten. `--config FILE` reads JSON/YAML
keys `method_id`, `rho`, `window_budget_seconds`, `solver_seed`; explicit CLI flags
override them. `configs/fixed_experiment.yaml` is a ready-to-run example.
Solver seed 0 and one thread remain frozen. Default budgets are 10s for authored
traces and 60s for physical traces; explicit settings override them. `--initial-export` selects
the separately labeled common-initial-state study. Analytical fixture coefficients
use `--radio-coefficients FILE`, a list of original records with `window_index`,
`user_id`, `satellite_id`, `occupancy`, `rate_bps`; empty visibility windows retain
empty tables. Missing coefficients for visible choices remain input errors.

A run saves the resolved settings, trace, original coefficient/initial-state
inputs, group lineage, generation seeds/draws, code/Git state, installed versions,
SCIP parameters, hardware, per-window decision times, post-decision serialization
and audit times, and a computational source/lockfile snapshot.
The source snapshot permits inspection of dirty-tree runs without relying on a
notebook. Source lives under `source/` with its original `pyproject.toml` and
`src/` layout. Decisions, metrics, raw stage-local results, independent validation
and summary projections have recorded SHA-256 hashes.

An attempt is published only when its complete file transaction passes independent
verification and `manifest.json` atomically marks it completed (or aborted).
Pending folders and standalone summary files do not establish a successful run.
`validate --run-dir` checks hashes, schemas, committed state chains, actual metrics,
Stage I references, full deployments and objectives again. It checks feasibility
and artifact integrity, not historical solver optimality or a timing guarantee.

Recovery uses **whole-episode replay from the initial boundary**, including an
interruption in episode 0:

```powershell
.\.venv-c03\Scripts\python.exe -m stars_rl.cli simulate --run-id demo-c13 --method stars-fixed --resume
```

The runner first checks saved config, exact trace identity, boundary-state hash,
code revision/source, dependency/backend versions and hardware compatibility.
Partial attempts are retained as `abandoned-NNNN`; a fresh attempt resets all
active deployment state. Completed compatible runs are verified and returned
without solving again. Locks release after worker exit; concurrent workers cannot
publish the same run. A code/environment change requires a new run ID.

These are single fixed-method episode checkpoints, with no policy RNG or Q-table
state. They do not implement the later RL training checkpoint contract or
mid-episode continuation. Modeled failure completes an episode and retains failed
and `not_attempted` windows. Numerical/infrastructure failures publish diagnostic
aborted runs, never advance the boundary, and require diagnosis rather than auto
replay. Invalid raw numbers in aborted diagnostics have explicit `invalid_numeric`
tags; they never become valid numeric decisions.

CLI exit codes are 0 for a successful simulation or valid usable artifacts,
1 for a modeled failed episode or aborted diagnostic, and 2 for invalid inputs
or incompatible recovery.
Known network failure artifacts can still pass artifact validation. `runs/` is
ignored by Git; keep generated results and any private inputs out of public commits.

## Physical generation, audits and initial scaling

```powershell
.\.venv-c03\Scripts\python.exe -m stars_rl.cli generate --physical-config configs/development-physical-v1.yaml --output runs/development-trace.json
.\.venv-c03\Scripts\python.exe -m stars_rl.cli audit --trace runs/development-trace.json --output runs/development-audit.json
.\.venv-c03\Scripts\python.exe -m stars_rl.cli benchmark --output runs/size-ladder
```

`configs/paper-inputs-v1.yaml` selects the separate 30-user reference audit.
The development family has 4 users in 2 slices; the reference has 30 in 6 slices.
Both use the same frozen spherical two-body conventions:

| Input | Frozen value |
|---|---|
| Earth radius / altitude | 6371000 m / 500000 m |
| Gravitational parameter | 3.986004418e14 m³/s² |
| Orbit layout | 4 planes, 15 satellites/plane, 88° inclination |
| RAAN / phasing | 0°,45°,90°,135°; anomaly `2*pi*j/15 + 2*pi*p/60` |
| Earth rotation | 7.2921150e-5 rad/s |
| Epoch | 2026-01-01 UTC; declared synthetic ECI/ECEF alignment 0 |
| Elevation mask / snapshots | 10°; 14 windows of 60s |
| Users | Static 49–51°N,80–69°W; uniform sin(latitude)/longitude; minimum .5° separation |
| Sampling | Independent SHA-256-derived named MT19937 streams; 100000 layout proposal cap |
| Pools / instances | Access 5 and separate egress 5; 2 instances/type/host; maximum 8 active/host |

Ground stations are at (49.93,-79.53) and (49.93,-69.53) degrees. The epoch
alignment is synthetic, not astronomical Greenwich orientation. Each slice draws
its chain/demand/SLA once; type coefficients/overhead and satellite CPU are also
sampled once. Exact seeds, accepted draws and layout rejection counts are saved.
No layout is retried for network feasibility. A sampling-cap failure produces an
explicit generation-failed record.

ISLs connect the two same-plane neighbors and corresponding-index neighbors in
adjacent planes, without an end-plane wrap. Earth-occluded edges are removed.
Geometry is never altered to restore coverage/connectivity. The full validator
independently recomputes physical coordinates/visibility/edge policy before
checking resources and delay. Alternate coordinate evaluations have a 128-ulp
orbital-radius comparison envelope in metres; existing CPU, integrality,
throughput and delay residual targets remain unchanged.

`audit` records separate access and egress matching flows, unmatched users and
residual min-cut certificates, a global minimum-CPU necessary condition, coverage,
ISL degree and connected components. Multiple GS choices do not multiply a
satellite's egress capacity. Passing these checks does not prove full
routing/CPU/radio/SLA feasibility. A failed physical preflight returns a typed
`preflight_infeasible` episode before either optimizer stage is built.

The independent region calculation gives a 14.056535° elevation cap. Only two
planes can intersect the expanded user rectangle over the frozen 840s interval,
and each can contribute at most two satellites: access capacity is at most
`4*5=20 < 30`. The reference family is therefore an infeasibility audit under
these assumptions. Development seed 0 also has coverage gaps: only 1 of 14
snapshots passes necessary checks. Neither seed 0 trace is claimed to support a
successful physical episode. A different geometry requires a separately versioned
approved family; no new family is introduced to turn these failures into success.
Artifact validation can approve a correctly recorded failed episode; it does not
certify a physical deployment or training readiness.

Plot saved data with an interpreter that has Matplotlib installed:

```powershell
python examples/plot_coverage.py runs/development-audit.json --output runs/development-plots
```

Plotting is separate from the solver environment. The script records Python,
Matplotlib and input/code hashes, and writes coverage/connectivity PNGs. Dateline
crossing edges are omitted from the drawing only, not from the network data.

The supervised ladder measures `(S,U)=(2,1),(4,2),(8,4)` on separately labeled
authored diagnostics, not cropped physical inputs. Its v2 fixes chain length 2,
2 instances/type/host, 2000 MIPS and both pools 5 across sizes. Actual Stage II
variable counts are 82,336,1648. Generated/presolved sizes, coefficient ranges,
build/solve/validation times, bounds/progress, first independently checked
incumbent and peak process memory are retained. Memory includes the interpreter,
imports and SCIP. A measured proportional forecast, 2 GiB ceiling and 250000-link
guard block unsupported growth. These measurements do not establish a speed
advantage, dimension reduction, physical-scale solve or training readiness.

## Objective-weight environment and action checks

`StarsEnvironment` provides a plain Python `reset()` / `step(action)` API;
Gymnasium is not required. Action IDs `0..4` select ratios `[0.25,0.5,1,2,4]`.
Actions change Stage II objective weights only. The first window forces ratio
`0.5` and reports `learning_eligible=False`. Every later successful step commits
through the same independent validation and shared window budget as simulation.

The pre-action observation is `(initial_flag, remaining_windows, demand_bin,
host_pressure_bin, impending_loss_bin, previous_churn_bin)`. Demand excludes
instance overhead; host pressure includes previous active-instance overhead and
current minimum demand, without using optimized CPU allocations. Only current
and next known geometry enter impending loss. This compact observation is
partially observable. Unseen evaluation states choose action 1; Q ties within
absolute `1e-12` prefer action 1, then the smallest ratio.

Successful reward is minus actual normalized access, egress and assignment
changes, independent of the chosen ratio. Failure terminates with
`-4*sum(0.95**j for j in range(remaining_windows))`. Horizon completion also
terminates (`truncated=False`); terminal observations are `None`. Infrastructure
and numerical errors raise `TransitionError` without a learnable reward.

```python
from stars_rl.rl import StarsEnvironment
from stars_rl.topology.trace import load_trace

env = StarsEnvironment(load_trace("runs/toy-trace.json"))
state, info = env.reset()
while True:
    state, reward, terminated, truncated, info = env.step(1)
    if terminated:
        break
```

```powershell
stars-rl action-sensitivity --constructed --output runs/constructed-actions.json
stars-rl action-sensitivity --trace runs/toy-trace.json --output runs/toy-actions.json
```

Output paths must be new. Sensitivity replays every ratio from identical
committed state and records raw exports, independent checks, statuses and gaps.
Meaningful decision classes ignore CPU ties and equivalent instance IDs.
The constructed analytical topology certifies all access/host classes, realizes
two different next-window regimes and an aliased observation, and enumerates all
25 two-action sequences per regime. Low/high ratios have positive objective
margins; ratio `0.5` is an explicit tie. The return margin is `1.9` at discount
`0.95`. These are constructed solver results, with no learned policy involved.

The original toy trace has one successful decision class per window across
ratios. Development physical seed 0 fails initial necessary coverage checks.
Representative useful action effects and feasible physical episodes remain an
open training gate. No geometry, capacities or constraints were changed to
manufacture a gain; the analytical fixture is separately labeled.

## Tabular Q-learning and training checkpoints

`rl.q_learning.TabularQ` uses a private seeded Python RNG and linear epsilon
decay per learnable decision. Defaults are learning rate `0.1`, discount `0.95`,
epsilon `1.0` to `0.05` over 1000 decisions. These are recorded starting settings,
with no claim that they are tuned. Initialization does not draw exploration,
decay epsilon, update Q, or increment action frequencies. Terminal transitions
never bootstrap. `select(state, training=False)` is greedy and preserves the
Q table, RNG and counters, including for unseen states.

```powershell
stars-rl train --trace runs/development-trace.json --output runs/q-pilot --episodes 3 --budget 60 --seed 0
```

With current evidence this command exits with a blocked status and saves a
compute estimate, readiness reasons and manifest. It performs no training
episodes. The default pilot limit is three episodes; a larger launch requires
a reviewed measured pilot. The estimate includes initialization, five-action
sensitivity replay, validation, six evaluation passes (five fixed ratios and one
policy), and constructed sensitivity solves. It is a conservative decision-budget
bound; generation, artifact I/O and other offline work still need measured time.

A future pilot also requires `--readiness PATH`, a JSON map with `constructed`
and `scaling` report paths plus ordered `successful_runs` and `sensitivity`
path lists, one per input trace. Paths stay within the evidence directory.
Readiness checks compatible code/runtime, physical necessary conditions,
independently validated complete episodes, a size/budget-compatible measured
ladder authorizing physical experiments, and positive cross-weight objective
margins on representative traces. Sensitivity commands now save runtime profiles
and Stage I references for independent rechecks. Current reference/development
coverage failures, toy degeneracy and the small authored ladder leave these
gates open. There is no CLI override to bypass them.

For an eligible run, a complete atomic checkpoint is saved before episode 0 and
after every completed episode. It stores Q values, both owned RNG states,
trace/group ordering, next episode, epsilon schedule/counters, action frequencies,
schemas/bins/reward hashes, solver settings, source hashes and code revision.
Trace inputs and the actual source tree are snapshotted, including dirty sources.
No active deployment is stored at a boundary. Restart with the same inputs and
arguments plus `--resume`; configuration, source, runtime or schema changes are
rejected. A completed compatible resume performs no additional episodes.

Interrupted episodes restart from the preceding published boundary: partial
updates are discarded and partial logs remain labeled abandoned. This includes
interruption during episode 0 and between checkpoint writing and publication.
Accepted raw records and summary hashes are verified on resume. Infrastructure
or numerical exceptions abort the run and require diagnosis rather than becoming
network rewards. Persistent file errors still raise; transient Windows atomic
replacement denials have six attempts with waits of 10/20/40/80/160 milliseconds.

Controlled deterministic tests compare final Q/RNG/checkpoint contents and
accepted transitions with uninterrupted execution. Their artifacts are explicitly
labeled `controlled_test_adapter`, record zero actual solver calls, and cannot
resume as standard training. They establish software recovery, without a
solver-backed pilot, convergence, speed or policy-improvement claim.

## Grouped splits and frozen-policy evaluation

Freeze the supplied trace groups before validation tuning:

```powershell
stars-rl split --train runs/train-a.json --validation runs/validation-a.json --test runs/test-a.json --output runs/split-v1
stars-rl evaluate --split runs/split-v1 --policy-run runs/q-seed0 runs/q-seed1 --output runs/evaluation-v1 --budget 60
```

These commands require actual eligible inputs. Current physical coverage and
training gates remain open, so no scientific held-out policy results are claimed.
Controlled C16 test checkpoints are rejected by the public evaluation command;
it records a blocked manifest without evaluating the test set. There is no CLI
flag to relabel controlled software fixtures as trained scientific policies.

Split manifests bind normalized exogenous-content hashes, exact trace artifacts,
root lineage, declared groups, constellation/layout identity, time intervals and
connected components. Relabeled duplicates and load variants of a shared root
cannot cross partitions. The guard is at least the longest episode duration.
Overlapping intervals and known repeated phase cycles join components transitively.
Repeated constellation/layout families are conservatively grouped even across
large gaps; identical physical base geometry also survives metadata relabeling.
Optional `--phase-groups PATH` supplies known cycle IDs keyed by content hash.
No input screening occurs here: supplied failures remain in the split. Declare
upstream lineage and selection honestly; shared constellation design may still
correlate distinct groups, and temporal separation alone proves no independence.

Evaluation loads completed boundary checkpoints and checks their input/source
integrity, training-partition provenance, solver budget/runtime, optimizer code,
frozen observation/action/reward schema and horizon. It permits new evaluation
code while comparing the actual optimizer/environment source to training. A
checkpoint's recorded training artifact cannot be relabeled after fitting to
hide a lineage overlap. Its entire declared input pool belongs in the training
partition, even if a short pilot visits only a subset. Q values, exploration RNG, counters and schemas remain
unchanged throughout validation and test rollouts; unseen states use ratio `0.5`.

All five fixed ratios run on the same validation traces and budget. The comparator
minimizes mean penalized score, averaging episodes within each connected group
before weighting groups equally; ties prefer `0.5`, then the smallest ratio.
Policy configurations are selected using validation scores only, retaining all
training seeds of the winning configuration. Candidate configurations require
the same complete seed grid. No best-seed selection or test-time bin fitting is
performed.

The selected policies, checkpoint hashes, comparator and input/source hashes are
saved in `frozen-selection.json` before any test reward is read. A one-shot
`test-consumed.json` claim is written into the split directory before testing;
repeat evaluation is refused, including after interruption. Evaluation resume is
unsupported. Treat an interrupted test as consumed and document any new study;
do not reset the claim to tune repeatedly against the same held-out outcomes.

Test comparisons always include fixed `0.5` and the validation-tuned ratio, paired
with every selected policy seed on identical episodes and budgets. Modeled
failures retain their horizon-bounded penalized score, failure cause, raw solver
statuses and attempted windows. Physical metrics for unattempted windows remain
null. Infrastructure/numerical errors abort evaluation instead of being dropped
or turned into network rewards. Saved records include source/input snapshots,
completion rates and per-group paired differences. They are descriptive; crossed
uncertainty estimates and publication figures remain C18 work.

## Scientific scope

The core uses SCIP through PySCIPOpt, retains continuous CPU allocation and hard feasibility constraints, and preserves temporal repair plus two-stage orchestration. The environment selects objective-weight ratios around the independently validated optimizer. This project does not claim exact reproduction of unavailable author code or guaranteed RL superiority.

See [REFERENCES.md](REFERENCES.md) for the scientific reference and clean-room implementation note.

