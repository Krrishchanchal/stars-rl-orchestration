# Third-person reproduction contract

Current reproduction contract. Software interfaces exist; use the tested [README quickstart](../README.md#tested-windows-quickstart) and [EVIDENCE.md](../EVIDENCE.md) for executed scope. Actual solver-backed training, scientific held-out evaluation and physical-scale performance remain blocked. Local Windows full and hosted Windows/Ubuntu fast profiles are distinct.

## 1. What another person should be able to do

There are four distinct workflows:

1. **Quick verification:** install, test SCIP, run automated tests, simulate a tiny scenario and inspect a figure.
2. **Reproduce baseline experiments:** generate the declared physical traces and run fixed STARS and documented ablations.
3. **Evaluate released RL policy:** load policy and metadata and evaluate held-out scenarios without training.
4. **Retrain:** regenerate training/validation traces, train with specified settings, freeze the policy, and evaluate.

Also provide **plot-only reproduction** from saved results. This should not require solver calls, training or the source PDFs.

## 2. Setup and verified profiles

Repository visibility is owner-managed. If access becomes private, an incoming agent needs authorized access or an owner-provided source archive; never copy credentials into instructions.

PowerShell setup uses the same `.venv` path as README, from repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-build-lock.txt
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m stars_rl.cli doctor --solver
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/ci_checks.py --suite full --output artifacts/full
```

Using the environment executable directly avoids PowerShell activation-policy changes. If the `py` launcher is absent, document the tested Python executable alternative. The build lock pins the actual working pip/build-backend/setuptools/wheel dependencies; the runtime lock pins runtime and test dependencies. Their exact contents were tested in fresh C19/C20 environments. Wheel-only installation fails explicitly on unsupported platforms instead of resolving unpinned source-build tools.

POSIX equivalent: hosted Ubuntu fast CI passed at `5b6725f`; this does not establish the complete quickstart or full suite on Linux.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r requirements-build-lock.txt
.venv/bin/python -m pip install --only-binary=:all: -r requirements-lock.txt
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m stars_rl.cli doctor --solver
.venv/bin/python -m pip check
.venv/bin/python scripts/ci_checks.py --suite fast --output artifacts/fast
```

PySCIPOpt installation is expected through supported binary wheels. Record actual supported Python/platform combinations and diagnose wheel/library loading errors. No Gurobi license or GPU is part of this workflow. Never instruct a user to disable security protections to make installation succeed.

## 3. Implemented CLI contract

All commands run from repository root and use the active virtual-environment Python. Each command validates input/config/schema versions and returns nonzero on command failure. A modeled infeasible scenario is an experiment outcome with an explicit status, not a Python exception disguised as a successful deployment.

| Command arguments after `python -m stars_rl.cli` | Purpose | Scope |
|---|---|---|
| `doctor --solver` | Backend capability checks | Implemented and executed |
| `generate --scenario CONFIG --output TRACE` | Authored trace | Quickstart verified |
| `generate --physical-config CONFIG --output TRACE` | Frozen physical family | Audited failures retained |
| `audit --trace TRACE --output JSON` | Coverage/matching/resource audit | Necessary conditions only |
| `simulate --trace TRACE --run-id ID --method stars-fixed --output-root runs` | Fixed-method episode | Four fixed methods; see README |
| `validate --run-dir RUN` | Independent stored-artifact validation | A valid failed-run artifact is not a feasible episode |
| `action-sensitivity --trace TRACE --output JSON` | Same-state ratio replay | Representative usefulness remains open |
| `train --trace TRACE --output DIR` | Gate-checked Q pilot | Implemented; actual pilot blocked |
| `split --train A --validation B --test C --output DIR` | Frozen group split | Controlled fixture verification |
| `evaluate --split DIR --policy-run RUN --output DIR` | Frozen policy/baseline comparison | No eligible trained scientific policy |
| `plot --run RUN --output DIR` or `plot --evaluation DIR --output DIR` | Saved-only analysis | Optional separate renderer; zero solves |

Use `python -m stars_rl.cli COMMAND --help` for complete flags. Names above are placeholders, not authorization to run experiments.

Fixed `simulate --method` values are mono-delay, mono-temporal, hier-only and stars-fixed. The RL layer implements random/frozen-Q policies separately; they are not additional simulate choices. `stars-fixed` is the documented two-stage method. The first three are explicitly independent baseline definitions, not recovered author implementations.

## 4. Verified quickstart

Follow the single maintained [Windows quickstart](../README.md#tested-windows-quickstart). Expected authored outcome: three approved windows, six stage solves and penalized score `0.475` within the existing absolute `1e-8` check. [Expected fields](../examples/expected_quickstart.json) and [one measured sample](../examples/quickstart_sample.json) are tracked. Tied CPU allocations/delays and wall times can vary.

The saved-policy demo creates and replays an initial empty-Q policy with zero learning/exploration updates. It is **UNTRAINED**, not a released learned policy. Saved analysis and standalone Matplotlib rendering work without new solver calls. The optional notebook is deferred.

## 5. Baseline experiment procedure

1. Freeze decision register, code revision, configs and solver budgets.
2. Generate trace sets once; keep actual sampled inputs and hashes.
3. Audit coverage, connectivity and resource feasibility indicators. Distinguish necessary checks from a proof of complete SFC feasibility.
4. Execute all methods on those same traces, resetting internal deployment state for each run.
5. Independently validate every stored incumbent; retain solver logs and failures.
6. Aggregate paired episode differences, timing, status and network metrics.
7. Generate figures from saved results; record plot version/config and source runs.

Reference-scale config starts from 60 satellites/30 users/6 slices/2 GSs/14 windows. The frozen reference fails the access-capacity bound; development seed 0 fails initial coverage and 13/14 necessary snapshots. No fully validated physical episode is recorded. A smaller or revised physical family is not approved by this document. Never change the data secretly to obtain continuous coverage or match the published gains.

## 6. Training and evaluation procedure

Training inputs/settings and the frozen split bind lineage/interval/content-hash group lists, episode budget, solver settings, action ratios, bins, fixed reward coefficients, learning parameters, episode-boundary checkpoints and seed streams. Resume mid-episode is unsupported; restore the prior complete boundary and replay the interrupted episode. Test scenario groups live in a separate evaluation config and are not consulted during tuning. Different seed labels do not establish independent traces; apply experiment_contract.md grouping and duplicate rejection.

Current gated commands and settings are documented in the [README training](../README.md#tabular-q-learning-and-training-checkpoints) and [evaluation](../README.md#grouped-splits-and-frozen-policy-evaluation) sections. No native training or scientific evaluation was launched during handoff. C16/C17 controlled adapters report zero actual solver calls; authored frozen-Q inference is untrained.

The toy sensitivity run is a correctness demonstration; train on many independent valid episodes. Pin final policy metadata before test evaluation. Evaluate tuned fixed ratios and random ratios using the same traces, observability and solver budgets. Record RL training-seed variation separately from test-scenario variation.

Release a small saved policy only after real training exists. Its metadata must bind it to action ordering, observation bins, reward definition, optimizer semantics, training split and code/config versions. Never load an incompatible checkpoint without an explicit migration.

## 7. Run artifact layout

```text
runs/<run-id>/<method>/
  manifest.json
  settings.json
  trace.json
  generation.json
  boundary-0000.json
  source/
  attempt-0000/
    episode.json
    summary.json
    validation.json
    decisions.json
    metrics.json
    progress.json
    transaction.json
    boundary_end.json
```

Partial/abandoned attempts remain alongside accepted attempts. Training uses its own manifest, `readiness.json`, `compute-estimate.json`, complete `boundary-NNNN.json` checkpoints and per-episode attempts. Evaluation records frozen selection/test claim and paired results; analysis records `analysis.json`, checksum manifest and CSV tables, plus optional figure/plot manifests. The examples are the actual C13-C20 layout; no `final.npz` policy format is implied.

The manifest includes schema version, method, trace/config/decision-register hashes, code commit and dirty status, Python/library/SCIP versions, OS/CPU/RAM, seed streams, scenario-group lineage and normalized exogenous-content hash, total window deadline and stage allocation, solver time/gap/feasibility limits, thread settings, all objective weights, normalization and failure policy, and timestamps.

Saved episode metrics include episode/window/time, solve status, incumbent/validation flags, per-stage objective IDs/units and separate bounds/gaps when defined, build/repair/solve/validation/total seconds, model size, handovers, egress changes, beta assignment changes, host changes, active instances, CPU utilization and delay summaries. Undefined fields use explicit nulls, not zero. Store per-user delay and detailed allocation records separately for CDF/per-slice checks.

The manifest marks completion only when the runner finishes its declared workflow. An interrupted run remains identifiable. A failed modeled episode can be a completed experiment with failure status; distinguish it from a process crash.

## 8. Statistical and reproducibility limits

- Identical seeds do not guarantee identical solver decisions across versions or tied optima. Different seeds also do not guarantee independent data; check lineage, overlapping intervals and normalized trace content.
- Compare objective, feasibility and invariants within declared tolerances for fully solved cases.
- Time-limited incumbent differences are expected; record bounds/gaps and hardware.
- Report runtime distributions, not universal speed claims.
- Primary estimand and crossed training-seed/scenario-group bootstrap follow experiment_contract.md. Group correlated variants before aggregation; do not treat adjacent windows or seed labels as independent samples.
- Include failed-window and completed-episode rates alongside delay/churn. Conditional success metrics cannot stand alone.
- Report failure categories and attempted/unattempted windows; no silent removal.
- Retrained RL may differ; release the actual evaluated policy and full metadata. Episode-boundary checkpoints contain Q/RNG/order/exploration state; partial episode logs/updates are abandoned on replay.
- Paper percentages are external reference results, not expected test assertions.

## 9. Git and artifact maintenance

Commit source, docs, lockfile, configs, tiny fixtures, example summaries and a small selected policy if appropriate. Ignore bulk traces, full solver logs, virtual environments, credentials and transient training artifacts. Archive complete result bundles outside Git or in a release attachment with checksums and access instructions.

Every figure must identify its input run IDs. Every report claim must point to a table/figure or test evidence. `REFERENCES.md` cites paper, author repository, SCIP/PySCIPOpt and other substantive dependencies. Code reuse, if it later occurs, gets separate attribution/license review.

## 10. Troubleshooting the final README must include

- PySCIPOpt import/wheel/backend load failure.
- Infeasible scenario versus solver timeout without incumbent.
- Independent validator disagrees with solver: inspect scaling, tolerances and original nonlinear residuals; never ignore.
- Excessive model size/runtime: smaller scenario or longer budget, with no hidden model simplification.
- No variation across RL actions: inspect trade-off and state cases before training.
- Invalid or incompatible checkpoint/config/trace hash.
- Missing private-repository permissions or missing release artifact.
- Fresh notebook versus stale interactive state.

## 11. Release acceptance

A person with no prior session context follows README in a fresh environment, runs tiny tests and simulation, validates the output and regenerates at least one plot. Save the command transcript, environment and checks. Separately test policy evaluation and plot-only paths. Claim additional OS/Colab support only after actual execution there. Record measured quickstart and larger-experiment runtimes before publication.

## Reproduction acceptance

Before release, execute counterexample tests for inactive undersized hosts, user-level radio indexing, all three route segment classes, packet/load semantics, horizon failure dominance, numerical aggregation, stage budgets/starts, duplicate traces and crossed statistics. Independent CPU allocation oracle and complete outcome metadata are mandatory. Full paper-scale coverage and solver speed remain unverified, and are never inferred from a smoke test.

## Cross-cutting acceptance gates

Follow the [commit roadmap](commit_roadmap.md#cross-cutting-acceptance-gates) and [test matrix](test_matrix.csv) for milestone-specific checks. Preserve fixtures, independent derivations, command transcripts, version/config hashes, outcomes and residuals in the [evidence index](../EVIDENCE.md). Documentation calculations do not mark a test PASS.
