# Experiments

The scripts use the existing optimizer and frozen physical families. Generated runs are written locally; measured tables and figures are in [results-summary](results-summary/README.md).

## Main matrix

From the repository root, after installing the package:

```powershell
.\.venv\Scripts\python.exe experiments/run_final_matrix.py --output experiments/results/new-matrix
```

Use a new output folder. The run may take several minutes. It writes each result as it finishes and creates `status.json` when the matrix is complete.

The matrix varies one factor at a time around a sixteen-user/four-satellite network:

| Factor | Tested values |
|---|---|
| User count | 4, 8, 16, 24, 32 |
| Satellite count | 2, 4, 8, 12, 20 |
| Users changing access | 0, 4, 8, 16 |
| CPU per satellite | 100, 200, 500, 1000 MIPS |
| Per-user demand | 2, 5, 10, 20 Mbps |
| Delay limit | 5, 10, 20, 50 ms |
| Physical scenarios | Both frozen families; seeds 0–4; fourteen snapshots each |

Each authored episode has three sixty-second windows and two functions per chain. Default satellite CPU is 1000 MIPS, with separate five-user access and egress pools. There are no ISLs in these controlled cases. Each user sees one satellite at a time. Four users change access after the initial window unless the handover intervention specifies otherwise.

All four methods are compared across handover intensities. Other stress cases use fixed-weight STARS with ratio 0.5 and a ten-second window budget. Identical baseline inputs can reuse a saved result and are labelled `reused_from`; these are not extra independent runs.

## Additional runs

```powershell
.\.venv\Scripts\python.exe experiments/physical_prefix.py --results experiments/results/new-matrix
.\.venv\Scripts\python.exe experiments/repeat_budget_case.py --input experiments/results/new-matrix/inputs/handover-4.json --output experiments/results/new-repetitions
.\.venv\Scripts\python.exe experiments/capacity_extension.py --results experiments/results/new-matrix
```

The physical-prefix command attempts seeds that pass initial coverage checks, with a 180-second worker limit. Its PID-only memory monitor is not a complete process-tree measurement on Windows. Runtime repetitions rotate method order and repeat the same trace three times. The capacity extension tests 20 users/4 satellites, 32/8 and 64/16 without increasing the five-user pools.

## Outputs and plots

Generated output includes exact input configurations, complete raw episode JSON compressed with gzip, physical audits, CSV/JSON summaries and failure reasons. Failed episodes terminate early. A zero move count before any committed deployment does not mean successful stability; missing physical metrics remain unavailable.

Use a plotting interpreter with Matplotlib to render saved results:

```powershell
python experiments/summarize_final.py --results experiments/results/new-matrix --output experiments/new-plots
```

These commands do not bypass training readiness. The constructed weight experiments and untrained checkpoint replay do not establish a learned-policy advantage.
