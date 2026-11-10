STARS + RL — setup and usage

1. Requirements
Python 3.11; PySCIPOpt/SCIP and other exact versions in requirements-lock.txt.
CPU execution is supported; no Gurobi license or GPU is required for these runs.
Matplotlib is optional and used only by the figure-generation interpreter.

2. Install from the repository root (PowerShell)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-build-lock.txt
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
.\.venv\Scripts\python.exe -m pip check
No separate compilation step is required when compatible binary wheels exist.

3. Verify and demonstrate
.\.venv\Scripts\python.exe -m stars_rl.cli doctor --solver
.\.venv\Scripts\python.exe examples/demo.py --output runs/new-handover
.\.venv\Scripts\python.exe -m pytest
Use a new output path for each run. The demo writes index.html, summary.json and
raw_result.json. Open index.html in a browser after successful execution.

4. Sixteen-user demonstration
.\.venv\Scripts\python.exe -m stars_rl.cli generate --scenario experiments/inputs/authored-16users-v1.yaml --output runs/new-16-trace.json
.\.venv\Scripts\python.exe -m stars_rl.cli simulate --trace runs/new-16-trace.json --output-root runs --run-id new-16 --method stars-fixed --rho 0.5 --budget 10
.\.venv\Scripts\python.exe -m stars_rl.cli validate --run-dir runs/new-16/stars-fixed
This is authored connectivity, not orbital coverage. Stage I and Stage II both
run. rho is fixed in this command; no learned controller is claimed.

5. Reproduce experiments
Read experiments/README.md before launching. It lists every intervention,
physical seed, output schema, failed-case handling and supplementary command.
Run the final matrix with:
.\.venv\Scripts\python.exe experiments/run_final_matrix.py --output experiments/results/new-matrix
This takes several minutes and writes generated results locally.
Published tables and figures are in experiments/results-summary/.

6. Readiness and claims
The tested core retains continuous CPU allocation and hard feasibility checks.
Tests/demonstrations are distinct from scientific generalization. Both frozen
physical families fail full-episode necessary checks across the tested seeds.
Two initially passing development traces were also attempted through the solver:
one timed out and one was infeasible. Native training/held-out evaluation remains
blocked. Constructed action-sensitivity and an untrained checkpoint replay are
not trained-policy improvements.

7. Complete technical documentation
README.md: readable setup and demonstration guide.
docs/USAGE.md: detailed supported commands and usage.
REFERENCES.md: research paper and clean-room implementation attribution.
