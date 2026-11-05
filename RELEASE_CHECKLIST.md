# Release and academic handoff checklist

This checklist separates working software from scientific readiness. Passing CI
does not authorize a release tag. The current project is an academic prototype;
licensing remains undecided by its owner. Repository visibility is owner-managed.

## Executable software checks

- [ ] Install the pinned build/runtime wheel locks in a clean Python 3.11 venv;
  install the package using `--no-build-isolation --no-deps`; run `pip check`.
- [ ] Run `python scripts/ci_checks.py --suite fast --output artifacts/fast`.
- [ ] Run `python scripts/ci_checks.py --suite full --output artifacts/full`.
- [ ] Confirm the backend doctor passed and JUnit contains real solver tests,
  no failed/error/skipped tests and a nonzero test count.
- [ ] Execute the README quickstart in a new output directory. Confirm the
  expected trace hash, three approved windows and the authored scalar checks.
- [ ] Check the saved **untrained** policy replay preserves its hash and zero
  learning/exploration counters. Do not relabel it as trained-policy evidence.
- [ ] Render saved analysis with its checksum manifest; confirm zero solver
  calls and method/scenario/run/aggregation provenance on every figure.
- [ ] Check all source, analysis and policy schema versions and paired domains.
- [ ] Run the source hygiene/evidence audit below and review its summary.

```powershell
python -m stars_rl.experiments.release --ci-report artifacts/full/public/ci-report.json --output artifacts/release-review.json
```

CI uploads only `artifacts/ci/public/`: test counts, backend versions, hashes and
gate status. Raw stdout/stderr, JUnit and generated experiment sources stay in
the private subdirectory and are not selected for upload. Pattern scanning and
redaction are useful checks, not guarantees against every possible secret format.
Never upload private traces, credentials, source PDFs or arbitrary run folders.
Pytest fixture directories use a unique system temporary directory to avoid
Windows path-length limits in deep checkouts. Its location is recorded privately
in `pytest-temp.txt` and retained for diagnosis. If the local sandbox's default
temporary directory denies writes, set `TEMP` and `TMP` to a short writable
directory in that shell before running the checks, as in the README setup notes.

## Scientific and owner decisions — currently open

- [ ] Resolve frozen reference/development coverage limitations without silently
  changing capacities, users, geometry or seed selection. Any new family needs
  a separate reviewed version and declared conditioning.
- [ ] Establish physical-scale runtime and representative positive-margin action
  effects before a native training pilot; preserve failed cases.
- [ ] Produce eligible trained checkpoints and frozen disjoint held-out results,
  paired with `rho=0.5` and validation-tuned fixed ratios.
- [ ] Keep failed episodes and null unattempted physical metrics in analysis;
  report seed/group sample sizes and uncertainty limitations.
- [ ] Review model decisions and every requirement: executed evidence or explicit
  deferred/blocked scope, never a documentation-only numerical PASS.
- [ ] Obtain the owner's licensing decision if preparing a distributable release.
  Do not infer a license from public visibility. Citation metadata is optional
  and awaits confirmed owner/authorship information.
- [ ] Verify hosted Windows/Linux CI results. Local Windows execution does not
  establish remote CI, Linux, Colab or notebook compatibility.
- [ ] Review and explicitly authorize a tag/publication only after these checks.

`release_status.json` is the machine-readable scope ledger. The audit command's
`--require-release` option fails while release blockers remain. It never creates
tags, changes visibility, trains a model or publishes files.
