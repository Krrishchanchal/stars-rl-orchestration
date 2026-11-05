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
or remote CI success is claimed.

## C20 local verification (2026-11-05)

A fresh Windows checkout and isolated Python 3.11 environment using the existing
locked wheel files passed the fast profile (510 tests, 74 solver tests) and full
profile (743 tests, 183 solver tests), with zero failures, errors or skips. The
quickstart, untrained saved-policy replay and saved-figure provenance checks also
passed. CI reports bind to a canonical source hash. Hosted Windows/Linux runs
remain unverified.

The initial full run had 5 failures and 8 setup errors from Windows path-length
limits; the runner now uses a unique short temporary fixture directory. Earlier
check failures remain in local evidence. Passing software checks leaves licensing
undecided and scientific release gates open; no tag or publication was performed.
