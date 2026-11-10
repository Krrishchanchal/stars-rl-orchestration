# STARS + RL

This project implements STARS for placing security function chains in a changing satellite network. It selects the user's access satellite, function hosts, ground-station route and CPU allocation while checking throughput, capacity and delay requirements.

The implementation uses Python and SCIP. Stage I selects satellite associations; Stage II solves the complete placement problem. The RL extension selects the stability-weight ratio used by Stage II.

## 1. Requirements

- Python **3.11**
- Dependencies listed in `requirements-lock.txt`
- A compatible PySCIPOpt wheel, which bundles SCIP on the tested platform
- Matplotlib only if you want to generate figures

The recorded experiments ran on CPU. A GPU and Gurobi license are not required. Setup and demos were tested locally on Windows; hosted fast checks also passed on Windows and Ubuntu.

## 2. Installation

Open PowerShell in the repository folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-build-lock.txt
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
.\.venv\Scripts\python.exe -m pip check
```

No separate compilation step is needed. In the commands below, `$py` points to this environment:

```powershell
$py = ".\.venv\Scripts\python.exe"
& $py -m stars_rl.cli doctor --solver
```

The doctor checks the solver installation and prints its results. Keep using the same PowerShell window, or set `$py` again in a new one.

## 3. Run the handover demo

```powershell
& $py examples/demo.py --output runs/demo-01
Start-Process .\runs\demo-01\index.html
```

This runs three windows. When the user loses access to the first satellite, the optimizer moves the two functions to the new host. The browser page shows the route, CPU allocations, delay and change counts.

The output folder contains `index.html`, `summary.json` and `raw_result.json`. **Use a new output folder for every run.** This example uses authored connectivity and real solver calls.

## 4. Run the 16-user scenario

```powershell
& $py -m stars_rl.cli generate --scenario experiments/inputs/authored-16users-v1.yaml --output runs/trace-16.json
& $py -m stars_rl.cli simulate --trace runs/trace-16.json --output-root runs --run-id demo-16 --method stars-fixed --rho 0.5 --budget 10
& $py -m stars_rl.cli validate --run-dir runs/demo-16/stars-fixed
```

The scenario contains 16 users and four satellites across three windows. Four users change access after the first window. Both optimization stages run, followed by independent validation.

This command uses the fixed ratio `0.5`. Other supported comparison methods are `mono-delay`, `mono-temporal` and `hier-only`. The scenario's visibility is authored; it is separate from the orbital physical scenarios.

## 5. Run the tests

```powershell
& $py -m pytest
```

For the full verification profile, including the backend preflight:

```powershell
& $py scripts/ci_checks.py --suite full --output artifacts/check-01
```

The recorded full regression passed **743 tests**, including **183 solver tests**. The final experiment outputs were also independently checked again: all **100 committed deployments** passed. These counts describe recorded checks; a new run produces its own results.

## 6. Experiments and results

The experiments cover user load, satellite count, handovers, resource pressure, method comparisons and physical coverage.

- **32 users on eight satellites** completed three validated windows.
- **64 users on sixteen satellites** exceeded the first window's deadline.
- Repeated sixteen-user runs showed lower decision times for the hierarchical methods than the tested monolithic methods. Hierarchy-only performed similarly to STARS on those cases.
- The controlled RL experiment showed that the preferred weight can change with future connectivity. A trained-policy improvement has not been demonstrated; physical training remains blocked by readiness checks.

Read the [selected findings](experiments/SELECTED_FINDINGS.md) for interpretation, or the [complete tables and figures](experiments/report-evidence/SUMMARY.md) for all recorded cases. Successes, infeasible inputs and deadline failures are retained.

To rerun the main matrix:

```powershell
& $py experiments/run_final_matrix.py --output experiments/results/matrix-02
```

This may take several minutes. [Experiment instructions](experiments/README.md) describe the exact inputs, supplementary runs and output files.

## 7. Documentation

- [Detailed command reference and troubleshooting](docs/USAGE.md)
- [System model and formulation](docs/model_specification.md)
- [Implementation decisions](docs/decisions.md)
- [Execution rules and budgets](docs/execution_contract.md)
- [Scenario and RL definitions](docs/experiment_contract.md)
- [Test plan](docs/test_plan.md) and [test matrix](docs/test_matrix.csv)
- [Recorded verification evidence](EVIDENCE.md)
- [Plain-text instructions](README.txt)

The repository includes the final configurations, compact raw outputs, tables and figures. Environments, scratch files, machine logs and bulky legacy snapshots are excluded from Git; the complete legacy archive remains preserved locally.

## Reference

M. Mahyoub, W. Jaafar, S. Muhaidat and H. Yanikomeroglu, “STARS: Stability-Aware SFC Orchestration and Associations in LEO Satellite Networks,” *IEEE Transactions on Network and Service Management*, vol. 23, pp. 3326–3340, 2026. [DOI: 10.1109/TNSM.2026.3674391](https://doi.org/10.1109/TNSM.2026.3674391).

This is an independent implementation with documented interpretations and an RL extension. No author implementation code was copied. See [REFERENCES.md](REFERENCES.md) for attribution.
