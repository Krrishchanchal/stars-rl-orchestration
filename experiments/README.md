# Final experiment archive

These scripts run the existing implementation. They do not change its optimization equations, RL learning rules, observation, tolerances or physical family definitions.

## Run the matrix

From the repository root, using the installed Python 3.11 project environment:

```powershell
.\.venv-c03\Scripts\python.exe experiments/run_final_matrix.py --output experiments/results/new-matrix
```

Use `.venv` instead of `.venv-c03` after following the normal README setup. A new output path is required. Generation and simulation can take several minutes. The script writes each completed case immediately and retains errors and failed episodes. `status.json` appears only when the entire batch completes.

## Protocol

- Load: 4, 8, 16, 24, 32 users on four satellites.
- Satellite count: 2, 4, 8, 12, 20 satellites for sixteen users.
- Handover: 0, 4, 8, 16 users change access; all four methods are compared with native initialization.
- CPU capacity: 100, 200, 500, 1000 MIPS per satellite.
- Demand: 2, 5, 10, 20 Mbps per user.
- Delay limit: 5, 10, 20, 50 milliseconds.
- Physical families: both frozen families, seeds 0,1,2,3,4. Keep every outcome. Full simulation is attempted only if all physical snapshots pass necessary checks.

All authored cases have three 60-second windows, two functions per chain, four access/egress choices in the default network, fixed five-user pools per satellite, one eligible instance per type/host and no ISLs. Each user sees one satellite at a time. The first four user IDs move to the next satellite after window zero, except for the explicit handover intervention. Default CPU is 1000 MIPS. Slice requirements otherwise originate from the existing toy configuration. The exact serialized inputs and protocol.json are authoritative.

These deliberately controlled connectivity cases do not model orbital motion. They are good tests of feasibility, forced changes and computational scaling, but provide limited decision freedom. Distinguish them from physical traces.

## Records

- `protocol.json`: configured cases, budgets and code revision.
- `inputs/`: all authored input configurations, including duplicate baselines used to anchor one-factor comparisons.
- `authored-results.json/csv`: every case/method outcome. A repeated identical content hash can reuse an already executed result; `reused_from` identifies it. Reuse is not an independent replication.
- `episodes/*.json.gz`: full raw simulation records, residual checks, stage outcomes and decisions. Read with Python's standard `gzip` and `json` modules.
- `physical/*-trace.json.gz` and `*-audit.json`: every generated physical input and complete audit, including failures.
- `physical-results.json/csv`: coverage summaries and full simulation outcomes where eligible.
- `errors/`: unexpected implementation errors, if any; these must not be interpreted as modeled infeasibility.

`J` is discounted normalized churn plus the declared failure tail. Switch/move totals and maximum delays concern committed windows only. A failure before any deployment has no measured physical delay. Comparisons are deterministic case studies, not population-level confidence intervals.

## Earlier completed experiments

The final interpretation also uses the frozen native/shared-start method comparisons and all-five-ratio comparisons for 8/16 users, plus the saved constructed X/Y and aliased-state study. Compact earlier comparison tables and the action-return figure are tracked; their full originals are retained in the local archive. An untrained-policy inference and controlled training-unit tests do not establish a native trained-policy gain. Native training/evaluation remains gated; no experiment script bypasses readiness.

`archive/previous-complete-evidence.zip` retains all 3,129 files from the earlier systematic comparisons, multiuser demos and fresh test/report runs, including failed runs and command records. It is a local, Git-ignored evidence archive; it is preserved without adding duplicate historical snapshots to GitHub.

## Supplementary experiments

`physical_prefix.py --results <matrix directory>` attempts each physical seed whose first snapshot passed the matching/resource checks. Its 180-second worker deadline limits the whole attempt. The PID memory monitor may observe the Windows virtual-environment launcher rather than its child interpreter: its recorded PID measurement must not be treated as a complete process-tree memory certificate. Retain raw outputs and the actual failure reason.

`repeat_budget_case.py --input <matrix>/inputs/handover-4.json --output <new folder>` runs three repetitions per method, serially and in rotated order. These characterize timing/deadline variation on one input; they are not independent scenario samples.

`capacity_extension.py --results <matrix directory>` tests 20 users/4 satellites, 32/8 and 64/16 under the same capacities, two-function chains and ten-second window budget. The 24/32-user failures on four satellites do not establish that the software has a sixteen-user limit.

## Regenerate figures and interpretation

Use an existing plotting interpreter with Matplotlib:

```powershell
python experiments/summarize_final.py --results experiments/results/final-matrix --output experiments/report-evidence
```

This reads saved measurements only. It writes full CSV tables, captioned figures, a source-file hash manifest and a research summary with report-selection guidance. The summary is supporting evidence; the team should write the final academic report in its own words.
