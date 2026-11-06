# Status and evidence index

The C01–C20 implementation roadmap ends with an academic software prototype.
Scientific readiness remains incomplete; see [release_status.json](release_status.json),
[CHANGELOG.md](CHANGELOG.md), and [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

| Scope | Executable evidence | Meaning |
|---|---|---|
| Backend and hard constraints | `tests/solver/`, backend doctor | CPU solver and numerical/model regression checks |
| Independent validation | `tests/unit/test_validator.py`, `test_residuals.py`, solver export checks | Raw and decoded physical feasibility checks |
| Episodes and artifacts | `tests/integration/test_simulation.py`, `test_failures.py`, experiment runner/CLI tests | Commit boundaries, failed outcomes and source/input integrity |
| Frozen physical inputs | Orbit/generation/audit tests | Synthetic geometry and necessary coverage checks; no feasible-family promise |
| RL control and resume | Environment, Q-update, checkpoint and controlled-replay tests | Software semantics; controlled fixtures do not establish a learned gain |
| Splits/evaluation | Split, frozen-policy and evaluation tests | Lineage/domain checks and frozen selection; no eligible scientific trained result yet |
| Analysis/plots | Aggregate, saved-plot and saved-analysis tests | Exact scores/units/paired bootstrap; recorded diagnostic data only |
| Clean quickstart | `tests/reproducibility/test_quickstart.py`, `examples/quickstart_sample.json` | C19 fresh Windows run: 729 tests passed; saved policy is explicitly untrained |
| CI/release hygiene | `tests/reproducibility/test_release.py`, `scripts/ci_checks.py` | Required backend, non-skipping tests, summary evidence, source audit |

Each CI invocation generates `public/ci-report.json` and
`public/evidence-index.json` under its output directory. These contain actual
counts, versions and source hashes; they do not copy raw logs or private paths.
The fast profile explicitly excludes the heavier physical-generation/split
checks and multi-episode training/evaluation/analysis integration fixtures. The
manual full profile executes the entire implemented test suite. Neither profile
launches a scientific training experiment.

Local detailed transcripts and research notes remain outside the public source
tree. This index does not turn deferred or failed scientific gates into passes.
Licensing is undecided, the optional notebook is deferred, and no release tag
is authorized. Verified hosted fast-profile evidence is distinguished below.

## C20 local verification (2026-11-05)

A fresh Windows checkout and isolated Python 3.11 environment using the existing
locked wheel files passed the fast profile (510 tests, 74 solver tests) and full
profile (743 tests, 183 solver tests), with zero failures, errors or skips. The
quickstart, untrained saved-policy replay and saved-figure provenance checks also
passed. CI reports bind to a canonical source hash. Hosted execution was not
verified during C20 implementation; the subsequent read-only check is below.

The initial full run had 5 failures and 8 setup errors from Windows path-length
limits; the runner now uses a unique short temporary fixture directory. Earlier
check failures remain in local evidence. Passing software checks leaves licensing
undecided and scientific release gates open; no tag or publication was performed.

## Verification by profile and platform

Checked against existing records on 2026-11-06; no tests or experiments were
launched to obtain the following results. All refer to software at `5b6725f`,
not to a new full regression on the documentation handoff commit.

| Platform | Profile | Executed outcome | Evidence |
|---|---|---|---|
| Local Windows, fresh Python 3.11.4 venv | Full | 743 tests, including 183 solver tests; zero failures/errors/skips | Local C20 reports below |
| Local Windows, same fresh venv | Fast | 510 tests, including 74 solver tests; zero failures/errors/skips | Local C20 reports below |
| Hosted `windows-latest` | Fast, push event | 510 tests, including 74 solver tests; zero failures/errors/skips | [Job 127042314136](https://github.com/Krrishchanchal/stars-rl-orchestration/actions/runs/41965773833/job/127042314136) |
| Hosted `ubuntu-latest` | Fast, push event | 510 tests, including 74 solver tests; zero failures/errors/skips | [Job 127042314546](https://github.com/Krrishchanchal/stars-rl-orchestration/actions/runs/41965773833/job/127042314546) |
| Hosted Windows / Ubuntu | C20 full, manual dispatch | Not observed; dispatch query returned zero runs | [Run history](https://github.com/Krrishchanchal/stars-rl-orchestration/actions) |

The actual job-log JSON reports, backend steps and commit were inspected, not
just the green run badge. Both hosted jobs used PySCIPOpt 6.3.0 / SCIP 10.0.2.
Their canonical source hash matches the local C20 reports:
`bd097ecb0e33778304320b8620e879c0d0a74db5d4726e86b2c70c6a8b15a941`.
The `remote_ci` readiness gate remains unresolved for full hosted regression;
its fast-profile observation is recorded separately in `release_status.json`.
Older workflow runs have different definitions and are not relabeled C20 full.
Colab, optional notebook and a complete Linux quickstart remain unverified.

The handoff updates status metadata in `release_status.json`, which participates
in the canonical source hash. Historical reports therefore must retain their
original hash; they are not matching full-suite evidence for the handoff tree.
No optimizer, tests, constraints, scenario configuration or lockfiles changed.

For the documentation handoff, 17 lightweight release/CLI checks passed with
zero failures/errors/skips. Seventy local Markdown links, 38 listed artifact
paths and all 98 traceability rows' test-file paths were checked; tracked-source
hygiene passed. Scientific gates, claims and licensing were compared with the
base commit and remain unchanged. Results are retained in the local C20
`documentation.xml` and `summary.json` documentation-handoff entry. No expensive
regression, simulation, sensitivity probe, training or evaluation was rerun.

## Experimental state from existing evidence

- **Frozen reference:** the declared geometry admits at most four visible
  satellites over the region during the conservative 0–840 s interval. With
  five access slots each, capacity is at most 20 for 30 required users. Seed-0
  snapshots 0–13 (times 0–780 s, every 60 s) all fail both access and egress
  matching; flows are 5–10 instead of 30. Aggregate CPU necessary checks pass,
  which does not overcome these failures or prove complete feasibility.
- **Development seed 0:** four users, same geometry. Access matching fails at
  windows 0–10 and 12–13; only window 11 at 660 s passes the necessary checks.
  Covered-user/access-flow counts are `[2,2,1,1,3,3,2,1,1,1,3,4,3,1]`.
  Initially `u02` and `u03` have no visible access satellite. Egress matching
  reaches four and the aggregate CPU bound passes in every window. Even window
  11 is only a necessary-condition pass, not a validated physical deployment.
- **Physical episodes:** both recorded default-60-second simulations terminate
  at window 0 preflight, with zero optimizer calls and zero approved windows;
  windows 1–13 remain unattempted. Artifact validation can pass for these failed
  runs. No frozen physical scenario is recorded as completing a fully validated
  episode. Other seeds were not screened; their outcomes are unknown.
- **Scaling/runtime:** the accepted authored-v2 single-window ladder measured
  satellite:user sizes 2:1, 4:2 and 8:4. Variables/constraints were 82/147,
  336/654 and 1648/3612; decision times were about 0.044, 0.204 and 1.398 seconds;
  process peaks were 58,142,720, 66,781,184 and 113,696,768 bytes. These are
  independently validated tiny authored cases, not cropped physical traces or
  a 60:30 runtime estimate. Earlier variable-port probes remain separate.
- **Action effects:** C15 constructed regimes pass observable multistep and
  alias tests, with recorded return margins 1.9. The authored toy has one
  equivalent decision class at each measured state; it does not supply useful
  representative weight trade-offs. All five development initial-action
  replays fail preflight. Representative physical sensitivity remains open.
- **Training/evaluation:** no actual solver-backed training pilot or scientific
  held-out evaluation occurred. C16 checkpoint/resume and C17 selection/leakage
  runs use controlled adapters with zero actual solver calls. C17's 18 native
  authored stage solves compare fixed ratios and an **untrained** Q policy;
  they are diagnostic inference, not training. C19/C20 empty-Q replay likewise
  has zero learning/exploration updates. No eligible trained policy exists.
- **Compute estimate:** C16 records a conservative upper bound of 653 stage
  calls / 14,930 decision-budget seconds including readiness work. This is not
  a measured pilot throughput estimate or authorization for a larger launch.

The [physical-family proposal](docs/physical_family_proposal.md) is **UNAPPROVED**:
it suggests investigating constellation/plane/region alternatives but selects
no replacement geometry, capacity, epoch or population. Preserve the v1 failures;
do not seed-screen or manufacture feasibility. The next scientific action is an
owner decision on whether to retain an infeasibility-focused study or authorize
a separately versioned physical-family investigation, before any training.

## Local evidence map

All paths here are relative to the repository root. These pre-existing local
artifacts are intentionally **not included in a clone**. The incoming agent
needs the same workspace or an owner-provided private archive. `CONTEXT.md`
records the absolute repository/environment paths. Do not replace or delete
failed evidence, consumed test claims, abandoned attempts or source snapshots.

| Read for | Exact local location |
|---|---|
| Frozen geometry, per-window failures and min-cut/unmatched-user certificates | `docs/evidence/c14/paper-audit.json`, `docs/evidence/c14/development-audit.json` |
| Inputs and bound/scaling summary | `docs/evidence/c14/paper-trace.json`, `docs/evidence/c14/development-trace.json`, `docs/evidence/c14/summary.json` |
| Failed physical episodes, source snapshots and validation | `docs/evidence/c14/physical-runs/paper-default60/stars-fixed/`, `docs/evidence/c14/physical-runs/development-default60/stars-fixed/` |
| Accepted authored ladder / earlier unsuccessful probes | `docs/evidence/c14/ladder-v2/`, `docs/evidence/c14/preliminary-variable-port-ladder/` |
| Constructed, degenerate toy and failed development sensitivity | `docs/evidence/c15/constructed-final.json`, `docs/evidence/c15/toy-final.json`, `docs/evidence/c15/development-sensitivity.json` |
| Controlled resume and blocked native pilot | `docs/evidence/c16/summary.json`, `docs/evidence/c16/software-uninterrupted/`, `docs/evidence/c16/software-interrupted/`, `docs/evidence/c16/development-blocked/` |
| Controlled policies/selection and blocked scientific evaluation | `docs/evidence/c17/summary.json`, `docs/evidence/c17/controlled-policy-0.1-7/`, `docs/evidence/c17/controlled-evaluation/`, `docs/evidence/c17/native-blocked/` |
| Saved diagnostic plots, including physical-failure nulls | `docs/evidence/c18/native-final/`, `docs/evidence/c18/controlled-final/`, `docs/evidence/c18/physical-failure-final/` |
| Clean setup, wheel hashes, quickstart and initial failed installs | `docs/evidence/c19/clean-reproduction.json`, `docs/evidence/c19/transcript.json`, `docs/evidence/c19/summary.json` |
| Latest local CI evidence and earlier failures | `docs/evidence/c20/clean-validation.json`, `docs/evidence/c20/clean-transcript.json`, `docs/evidence/c20/clean-first-transcript.json`, `docs/evidence/c20/summary.json` |
| Read-only hosted verification captured during handoff | `docs/evidence/c20/hosted-ci.json` |
| Actual fast/full JUnit and CI reports | `.tmp/c20-clean/artifacts/fast-final/private/junit.xml`, `.tmp/c20-clean/artifacts/full-final/private/junit.xml`, `.tmp/c20-clean/artifacts/full-final/public/ci-report.json` |
| C20 native fixed episode, untrained checkpoint/replay and analysis | `.tmp/c20-clean/runs/quickstart/fixed/stars-fixed/`, `.tmp/c20-clean/runs/quickstart/policy/policy.json`, `.tmp/c20-clean/runs/quickstart/replay/`, `.tmp/c20-clean/runs/quickstart/analysis/` |

Older milestone summaries contain historical `remaining_uncommitted` and pending
notes. The demo was intentionally committed at C19; those old notes are not the
current Git status. Original equations/interpretations are in the tracked
[scientific specifications](docs/model_specification.md) and
[decision register](docs/decisions.md), with [98 software traceability rows](docs/test_matrix.csv).
