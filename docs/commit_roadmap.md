# Commit-by-commit implementation roadmap

Retained C00-C20 implementation requirements, not an outstanding task queue. Software milestones have been implemented through `5b6725f`; current executed evidence and unresolved scientific gates are in [EVIDENCE.md](../EVIDENCE.md). C07/C08 joint independent-validation acceptance was completed. Original milestone instructions below remain the acceptance contract; a checked software module is not a completed scientific experiment.

## Working procedure for every commit

1. Read its source equations and decision-register dependencies.
2. Write the smallest relevant fixture and its expected answer before implementing the behavior.
3. Implement only this commit's files/behavior; keep interfaces typed and deterministic.
4. Run targeted tests; investigate every failed/skipped test. Run the full implemented suite before closing the commit.
5. Save JUnit output and a short evidence note with environment and tested Git revision/tree state. Record dirty-tree status honestly. Test reports may reference the tested parent revision plus diff hash to avoid a self-referential commit hash.
6. Update test_matrix.csv, progress.md, relevant decisions and README commands.
7. Inspect `git diff`, then stage named files and commit with the proposed message. No credentials, private source PDFs or bulky artifacts.

If a design decision is unresolved, finish independent work but do not label dependent results reproducible. C07 is the explicit draft exception: implement C08 next to complete their joint acceptance gate, then proceed to C09. A successful import is not proof of solver correctness; a feasible solve is not proof of optimality.

## C00 — `docs: resolve reviewed model and experiment contracts`

**Read/freeze:** model_specification.md, execution_contract.md, experiment_contract.md, decisions.md and oracle_catalog.md. Archive the original review and finding-by-finding response. Correct the inactive-host q bound and satellite-summed throughput rule. Define complete endpoint routes, packet/psi/omega semantics, distinct antenna pools, stable instance identity and repeated-type rejection.

**Specify:** the exact toy and physical assumptions, complete baseline table, per-stage status and total budget, horizon-dominated failure penalty, observations, episode-boundary resume and grouped/crossed statistics. No solver result is claimed by this documentation commit.

**Gate:** documentation links and IDs resolve; review counterexamples are recorded; implementer can trace every selected formula to a decision/oracle. Planning review is complete; begin C01/C02 after checking documentation consistency. Backend and numerical/runtime gates are explicitly still pending.

## C01 — `build: scaffold Python package and test environment`

**Create:** pyproject.toml, src/stars_rl/__init__.py, cli.py, tests/unit/test_cli.py, base test configuration, initial runtime and build-toolchain lockfiles, REFERENCES.md, and minimal CI workflow. Update README with actual setup commands.

**Implement:** editable src-layout install, `python -m stars_rl.cli --help`, `--version`, CLI error exit codes, optional dependency groups if needed. Start with Python 3.11. Add only dependencies actually used; record exact working versions after installation, including the build backend. Use --no-build-isolation for the controlled editable install after pinned build tools are installed. Do not create a pretend solver module.

**Test:** new virtual environment installs package; help exits 0; invalid arguments exit nonzero; version is consistent with package metadata. Run `python -m pytest tests/unit/test_cli.py`.

**Gate:** clean environment imports the package without changing PYTHONPATH manually. Document PowerShell and POSIX commands; only claim platforms actually tested.

## C02 — `feat: verify SCIP backend and solver result contract`

**Create:** optimization/backend.py, result.py; tests/solver/test_backend.py; doctor CLI.

**Implement:** model creation, bounded solve, solution extraction, status mapping, objective/bound/gap capture, package/backend version logging. Test supported warm-start solution insertion. No full STARS model yet.

**Fixtures:** (a) two-user/two-satellite assignment with costs [[1,4],[3,1]], capacity one each: optimum cost 2; (b) minimize G subject to 1<=G<=10 and t*G=6, 0<=t<=2: optimum G=3; (c) activation-aware processing test at b=0 and b=1; (d) contradictory bounds/constraints for known infeasibility.

**Test:** independent numeric calculations agree within declared tolerances; no incumbent extraction on infeasibility; warm start is checked and its acceptance recorded. Deterministically test timeout status logic with a backend adapter fake, rather than relying on an unpredictable microsecond time limit. Also run one genuine bounded solve.

**Run:** `python -m stars_rl.cli doctor --solver` and `python -m pytest tests/solver/test_backend.py -m solver`.

**Gate:** no license prerequisite; actual Windows installation and SCIP nonlinear behavior work. If unsupported, log blocker and stop dependent commits. Do not install or substitute Gurobi.

**Required acceptance checks:** Add O-QBOUND undersized/zero-capacity inactive-host cases, O-ZEROGAP, stage-aware result records, partial starts and a complete deliberately invalid start. Capture feasibility diagnostics separately from stored/not-stored API returns. Test dimensionless reciprocal equations and the initial scaling targets, not only the unscaled example.


## C03 — `feat: define validated scenario and deployment schemas`

**Create:** config.py, models.py, configs/toy.yaml; schema/unit tests.

**Implement:** typed records for users/slices/chains/instances/satellites/GSs, scenario parameters, trace metadata, deployments and outcomes. Enforce unique stable IDs, valid coordinate ranges, positive demands/workloads/packet sizes, nonnegative capacities, valid chain references and supported repeated-type behavior. Separate immutable exogenous data from per-run deployment state. Config loading performs no hidden sampling.

**Test:** serialize/deserialize round trip; malformed IDs, units, missing fields and invalid bounds fail with helpful messages; copying an algorithm run cannot mutate shared trace data.

**Gate:** a third party can read toy.yaml and determine every input without reading implementation code.

**Required acceptance checks:** Freeze toy-v1 values before schema coding. Reject repeated function types within a chain, unsupported decision-dependent interference, NaN/Infinity and unknown IDs. Keep psi and omega as distinct fields and instance identities as (type,id,host). Activation bounds count eligible stage occurrences. These choices are already specified, not deferred to orbital work.


## C04 — `feat: implement units radio and delay calculations`

**Create:** physics/units.py, radio.py, delay.py; test_units.py, test_radio.py, test_delay.py.

**Implement:** direct numeric equations before solver expressions. SI conversions, free-space radio, equal bandwidth sharing, rate, five-segment propagation and processing/transmission delays. Return decomposed components, not only one total.

**Fixtures:** 300000 m propagation is 300000/c seconds; 20 dBm = 0.1 W; 12000 bits at 10 instructions/bit and 100 MIPS is 0.0012 seconds; 5 Mbps at 10 instructions/bit requires 50 MIPS; 12000 bits at 20 Mbps transmits in 0.0006 seconds.

**Test:** manually derived values, zero/negative input rejection, monotonicity of processing with CPU, empty occupancy handling, and consistency of any rate lookup with direct Shannon values. Do not assume a false radio monotonicity without checking the bandwidth/noise relationship.

**Gate:** units and packet/window-load distinction are unambiguous.

**Required acceptance checks:** Add independent O-PACKET and O-COEFF examples, and explain why using the same numeric routine in a solver export check is only consistency evidence. Packet Lambda semantics and psi=omega scenario assumption are explicit. Complete each unit conversion with a hand derivation independent of production helpers.


## C05 — `feat: add deterministic toy topology and path traces`

**Create:** topology/paths.py, trace.py; tests/fixtures with small connected/disconnected graphs; trace serialization tests.

**Implement:** explicit visibility matrices, shortest-path costs and paths, identity paths, deterministic tie ordering, immutable windows and trace hashes. Toy traces are authored test inputs, not orbital simulations.

**Fixtures:** one-hop chain, two-hop chain, colocated functions, disconnected egress, disappearing access link between two windows. Include a no-change trace and a jointly feasible route requiring different access and egress satellites.

**Test:** path distance and membership; disconnected graph yields an unavailable path rather than zero cost; same seed/config yields same serialized trace; hash changes when inputs change.

**Gate:** every fixture's expected connectivity can be drawn and checked manually.

**Required acceptance checks:** Add separate O-ENDACCESS, O-ENDINTERNAL and O-ENDEGRESS cases so each isolated disconnection is rejected. The graph is explicitly undirected in this version; symmetry assertions depend on that choice.


## C06 — `feat: build discrete assignment placement and activation constraints`

**Create:** optimization/variables.py, constraints.py; tests/solver/test_association.py, test_placement.py, test_activation.py, test_linkage.py.

**Implement:** C1-C12 with the D01/D02/D05/D07 decisions; exact-one stage assignment, capacities, activation linkage, logical host-pair constraints and stable constraint names. CPU/delay integration follows C07.

**Test:** separate fixtures for each constraint and combinations. Fix offending candidate variable values and establish infeasibility when appropriate. Exhaustively enumerate tiny binary assignment options for an independent oracle. Shared instances incur one activation, unused instances deactivate, unsupported paths cannot be selected.

**Gate:** no fractional deployment/rounding; corrected egress equation documented; variable filtering does not exclude a feasible multi-hop function host.

**Required acceptance checks:** Implement all access/host/egress linkage expressions, forbidding unreachable combinations rather than dropping their delay cost. Add type-domain and repeated-stage-rejection cases. Safe pruning needs a recorded proof; no nearest-candidate pruning. Test eligible-occurrence activation bound and stable identities.


## C07 — `feat: optimize CPU allocation and end-to-end delay`

**Create:** optimization/resources.py and delay expression builder; tests/solver/test_cpu.py, test_nonlinear_delay.py, test_radio_occupancy.py; monolithic.py feasibility path.

**Implement:** C13-C16, CPU gating, base overhead, instance limit, exact activated reciprocal reformulation, all propagation segments and association-dependent radio delay. Include explicitly documented throughput interpretation. CPU remains continuous and optimized.

**Test:** known minimal CPU examples; inactive terms exactly zero; CPU beyond minimum required to satisfy a tight delay; over-capacity and impossible-delay cases; sharing counts overhead once; occupancy lookup exactly agrees with direct formula. Export solution and recompute delays with C04 numeric routines.

**Gate:** C07 is not accepted until C08 independent validation and the new oracle checks pass; dimensional checks alone are insufficient. Tiny nonlinear optimum is analytically justified; do not use an unproven local nonlinear optimizer as a global oracle.

**Required acceptance checks:** Use the corrected conditional q upper bound and satellite-summed throughput expression. Add O-QBOUND, O-RADIOSELECT and O-ALLOC2 oracles. Record variable counts/build time and the first size-ladder pilot. This commit may contain a working draft, but its completion gate is jointly dependent on C08.


## C08 — `feat: independently validate solver deployments`

**Create:** validation/deployment.py, residuals.py; solver export tests and adversarial validator fixtures.

**Implement:** plain-data solution export and independent recomputation of every constraint family. Return residuals, IDs, severities and tolerances. Separate valid incumbent from proof of optimality. Record complete no-solution outcomes without trying to access missing values.

**Test:** mutate valid deployments to violate each family; boundary cases on either side of tolerance; nonintegral output, missing stage, wrong instance activation, insufficient CPU, fake path and wrong rate. A valid solver status with deliberately corrupted output must be rejected.

**Gate:** validator does not just read solver slack values or reuse expression-builder logic. It must independently detect injected defects.

**Required acceptance checks:** Reject nonfinite values and unknown IDs before numeric comparisons. Use O-ALLOC2 and lower-bound-active variants independently of C04 helpers. Apply per-user summed reciprocal/original-delay error budgets and extreme-range sweeps. C07/C08 acceptance is joint; no downstream Stage I/II claim before validation passes.


## C09 — `feat: implement temporal repair and stable change metrics`

**Create:** optimization/repair.py, metrics.py; test_repair.py and test_metrics.py.

**Implement:** visibility-aware retain/repair candidates, preserving original committed state. Choose nearest valid visible alternatives as paper repair suggests, but do not claim repaired candidates satisfy the whole model. Handle empty alternatives explicitly. Export warm-start candidates without deploying them.

**Test:** unchanged links; forced access/GS loss; capacity-colliding repairs; no alternative; original state remains unchanged. One switch counts once despite two flipped one-hot entries; initial setup is not a change. Assignment changes, host changes, instance activation, outage and restoration are separate fields.

**Gate:** forced changes remain counted against the committed prior deployment even when objective references use repaired values.

**Required acceptance checks:** Implement the full gateway-pair repair order from execution_contract.md, including replacement of egress satellite when it sees no GS. Rebuild complete-start auxiliaries or submit compatible binaries as a true partial start; do not copy stale occupancy/processing values. Metrics always use original committed state.


## C10 — `feat: solve Stage I association objectives`

**Create:** optimization/stage1.py, objectives.py; stage1 and normalization tests.

**Implement:** first-window propagation objective; later-window normalized deviations; correct auxiliary bounds and binary association constraints. Attach candidate warm starts where supported. Explicitly implement D04 reference choice.

**Test:** first-window known optimal assignment; later window prefers unchanged feasible association; forced changes remain valid; absolute-deviation truth tables; normalization invariant to filtered variable domain; zero-weight auxiliary values are not used as metrics.

**Gate:** objective is independently recomputed. Label the binary linear model accurately; do not claim a continuous LP without an integrality argument.

**Required acceptance checks:** Apply the exact reference, fixed ordering/seed and Stage I budget policy. A nonoptimal valid Stage I incumbent is a reference with its own status; no incumbent is not a reference. Preserve per-stage objective units and gap handling.


## C11 — `feat: solve Stage II with soft hierarchical consistency`

**Create:** optimization/stage2.py; hierarchical objective and integration tests.

**Implement:** common full model with alpha/xi still free; w_H*H + w_beta*D_beta; normalized C21-C26 deviation terms; t=0 placement convention; validated warm starts; complete final associations/resources in output.

**Fixtures:** Stage I selects a low-propagation association that cannot meet full CPU/delay conditions, but another association permits Stage II feasibility; conflicting preservation objectives; feasible and invalid warm-start candidates.

**Test:** soft preferences permit correction; hard constraints remain enforced; changing ratio can select a different known optimum; cold/warm solves have matching optimal objective on fully solved tiny cases, not necessarily identical tied assignments. Do not require warm starts to always improve runtime.

**Gate:** no hard fixing of Stage I; changes propagate correctly to metrics and next-window state.

**Required acceptance checks:** No secondary objective in version 1. Keep all final associations in export; test tied CPU allocations without assuming unique observations. Submit/rebuild starts per the partial/complete contract. Compare actual model size rather than assert dimension reduction.


## C12 — `feat: integrate STARS and documented mechanism ablations`

**Create:** simulation.py and baseline specifications/configs; multi-window integration tests.

**Implement:** solve/validate/commit cycle, first-window initialization, final state persistence, and D08's fully specified independent baseline variants. Exact author baseline objectives remain unknown; use descriptive method IDs from execution_contract.md instead of claiming recovered paper objectives.

**Test:** no-change, forced handover, SF relocation and feasibility correction episodes; state reset between algorithms; same trace not mutated; timeout with/without incumbent, proven infeasible and invalid output have distinct outcomes. Stop or continue only according to a documented failure policy.

**Gate:** fixed-weight STARS is useful without RL. Every window produces a structured record, including failures.

**Required acceptance checks:** Use the frozen descriptive baseline IDs and complete first/subsequent objectives in execution_contract.md. Add joint total-budget and staged-outcome tests, including not-attempted Stage II, timed-out Stage I with usable incumbent, and late validation. No hidden fallback or extra compute per stage.


## C13 — `feat: add reproducible experiment runner and manifests`

**Create:** experiments/runner.py, manifest.py; CLI generate/simulate/validate; output schema tests.

**Implement:** command-line configs, run IDs, input hashes, seeds, Git state, dependency/backend versions, hardware/settings, timings and artifact paths. Write decisions, metrics and validation reports transactionally; no successful summary for a partial crash. Resume only after compatible config/trace/state hashes are checked.

**Test:** same trace/settings reproduce analytical toy objectives; missing output/corrupt trace errors; failed windows retained; distinct algorithms cannot overwrite each other; identical trace used for paired comparisons. Test controlled recovery from an interrupted run.

**Gate:** reviewer can reconstruct a result from manifest and inputs without relying on an interactive notebook state.

**Required acceptance checks:** Manifest includes group lineage, normalized trace-content hash and separate stage records/bounds/objective units. Initial recovery is episode-boundary replay only; partial episodes are marked abandoned. Preserve failed versus not-attempted versus infrastructure-error records.


## C14 — `feat: generate and audit orbital scenarios`

**Create:** topology/geometry.py, orbits.py, visibility.py; physical configs; orbital tests and audit CLI.

**Implement:** circular orbits, declared plane distribution/phasing/epoch, Earth rotation, ECEF user/GS positions, elevation masks, Earth-occlusion checks and ISL policy. Sample geographic users/demands/capacities with independent seed streams. Precompute traces, not model outcomes.

**Test:** orbital radius and period formulas; overhead versus below-horizon cases; Earth rotation/time continuity; symmetric distances; maximum-degree/occlusion policy; no artificial visibility. Compare selected coordinates against a second independent analytic calculation. Inspect coverage and graph-connectivity plots.

**Gate:** D09 is frozen for each physical scenario; coverage gaps preserved and explained. Paper-scale inputs are not declared equivalent to author traces. Benchmark per-window runtime before scheduling large experiments.

**Required acceptance checks:** Use frozen paper-inputs-v1 conventions, 0.5-degree user separation and O-CAPBOUND independent geometry check. Start a size ladder before physical-scale experiments. Do not claim the approximately fourteen-satellite source visibility number is reproducible under the declared regular geometry.


## C15 — `feat: wrap STARS as an RL environment`

**Create:** rl/environment.py, state.py, actions.py, reward.py; RL environment tests; action-sensitivity CLI.

**Implement:** fixed five-ratio action space; well-defined observation bins and initial state; reset/step lifecycle; fixed reward; immutable trace access; terminal failure and horizon conventions. If Gymnasium is used, run its environment checker, in addition to semantic tests.

**Test:** all action IDs valid/invalid; constraints and solver budget unaffected by action; reward independently calculated from actual events; reset isolation; deterministic controlled rollout; no future demand leakage; horizon and failure semantics. Replay all actions on identical states to demonstrate meaningful effects.

**Gate:** action-sensitivity report passes on constructed trade-off cases and is measured on traces. If real actions are degenerate, diagnose before proceeding. Do not alter the core to force an apparent RL gain.

**Required acceptance checks:** Use exact pre-action observation formulas, remaining horizon, unseen-state/Q-tie policy and horizon-bounded failure reward. Verify O-FAILRETURN and O-RATIO. Instantiate the two-regime multistep fixture with actual validated topology; an abstract payoff table alone does not establish a solver result. Separate objective-margin effects from ties/timeouts.


## C16 — `feat: train and checkpoint tabular Q-learning`

**Create:** rl/q_learning.py, checkpoint.py; CLI train; learning-update tests.

**Implement:** epsilon-greedy action selection, seeded exploration, terminal-aware update, episode loops, checkpoint at each completed episode boundary, hyperparameter manifest and whole-episode replay after interruption. Checkpoint includes Q table, observation/action schema, bins, reward config, random-generator states, trace ordering, next episode index and exploration/training counters. First-window initialization is forced and excluded from learning updates.

**Test:** hand-computed update, no terminal bootstrap, greedy evaluation with no updates, checkpoint round trip, compatible resume reproduces a controlled continuation; incompatible reward/action/schema hashes rejected.

**Gate:** short training pilot records wall time and solve count. Choose larger budget using measured throughput; no convergence or improvement claim based on a learning curve alone.

**Required acceptance checks:** Permit training pilot only after scaling and action gates. Checkpoint each completed episode with RNG/order/schedule/schema state; restore and replay an interrupted episode from the preceding boundary. Estimate total compute including initialization, sensitivity, validation and evaluation solves.


## C17 — `feat: evaluate frozen policies on held-out scenarios`

**Create:** CLI evaluate; split manifests; fixed/random/rule policy adapters if included; evaluation leakage tests.

**Implement:** disjoint scenario seed groups, validation-only tuning, frozen policy selection, paired evaluation versus tuned fixed ratios. Log all solver budgets and statuses. Use multiple RL training seeds if runtime permits.

**Test:** train/test overlap rejected; evaluation cannot change Q values or exploration; normalization/bins not fit on test data; identical traces and solver budgets across policies; failed episodes included in failure summaries.

**Gate:** test results are generated once configurations are frozen; no claim of successful RL merely because it beats an untuned weak baseline.

**Required acceptance checks:** Split by underlying scenario lineage/orbital intervals and normalized content hashes, not seed uniqueness alone. Include rho=0.5 and validation-tuned fixed ratios. Freeze policy and fixed comparator before test evaluation; no test-tuned observation bins.


## C18 — `feat: generate reproducible analysis tables and figures`

**Create:** experiments/aggregate.py, plots.py; CLI plot; aggregation tests.

**Implement:** event counts, failure/timeout rates, delay mean/p95/CDF, CPU/instance metrics, solve/total runtime, training curves and selected-action frequencies. Pair differences by episode; bootstrap or other declared confidence intervals at independent-episode level. Treat training-seed and scenario variation explicitly.

**Test:** known synthetic result tables yield exact expected aggregates; missing/failure records are not silently dropped; wrong schema/version rejected; plot generation reads saved results only. Check units and axes visually. Do not use image pixel identity as a scientific correctness test.

**Gate:** every figure identifies input runs, method, scenario and aggregation rule. Published percentages are shown only as clearly labeled reference values, never inserted as our measurements.

**Required acceptance checks:** Implement the exact paired group-level score and crossed training-seed/scenario bootstrap. Use O-CROSS synthetic tables, duplicated-trace cases and early-failure/unattempted-window records. Never replace unobserved physical metrics with zeros.


## C19 — `docs: verify clean-room reproduction and demo`

**Create/update:** final README, tested setup instructions, notebooks/demo.ipynb, tiny example results, troubleshooting and benchmark timings.

**Implement:** quickstart from a fresh checkout/environment; saved-policy evaluation; plot-only path; optional full training path. Notebook calls the package and does not duplicate optimization logic.

**Test:** a fresh environment executes README commands in order without untracked local files; new result directory; a fresh notebook kernel runs top-to-bottom; no Gurobi, GPU, hidden data, credentials or author PDFs required for toy quickstart.

**Gate:** save command transcript and expected outputs/tolerances. Record actual platform; Linux/Colab support is a claim only after testing there. Full training exact bitwise reproduction is not promised.

**Required acceptance checks:** Test build-toolchain locks and --no-build-isolation in a clean environment, saved-policy evaluation and plot-only workflow. The notebook is optional and may be deferred without blocking the CLI reproduction gate; do not duplicate logic.


## C20 — `ci: enforce regression gates and prepare reproducible release`

**Create/update:** harden the CI workflow started at C01; release checklist, CHANGELOG, status/evidence indexes, optional CITATION.cff and project license after owner choice.

**Implement:** fast unit and tiny solver/integration tests on changes; larger experiments manual/scheduled rather than blocking every commit. A SCIP install failure must be visible, not converted into an all-green solver suite through blanket skipping.

**Test:** CI-equivalent clean run; artifact redaction/no credentials; schema/version compatibility; release quickstart; confirm the selected policy and figures point to the correct config/run IDs.

**Gate:** no unreviewed model decisions; all relevant matrix rows PASS with evidence or explicitly deferred scope; tests and experiment claims separated; known limitations documented. Tag a release only after these checks.

**Required acceptance checks:** CI already starts at C01. This commit hardens release gates and automatically generates evidence indexes where practical. Keep actual backend, numerical and statistical limitations visible; documentation edits do not count as execution evidence.


## Scope control

DQN, larger constellations, additional RL actions, packet simulation and alternative exact reformulations require later separately scoped commits. Do not add them while the preceding acceptance gates are unresolved.

## Cross-cutting acceptance gates

These requirements apply alongside the coding steps and tests in each named commit.

| Commit | Additional required work/evidence |
|---|---|
| C02 | Calibrate every residual family in execution_contract §8; record proposed versus achieved thresholds |
| C03 | Encode family IDs, per-slice/per-type draw scopes, separate egress capacity and persisted generation metadata |
| C07/C08 | Execute T-INACTIVEPROC and T-RESIDUALFAMILY; full candidate sums and raw/decoded independent validation |
| C10/C11 | Explicit Stage I row families; T-ST1SCOPE; T-ST2 uses O-ST2-RESCUE, never O-MULTISTEP |
| C13/C14 | Preflight typed access/egress matching failures before model construction; retain certificates and failed traces; implement family classification and T-REGIONCAP/T-MATCHING/T-DRAWSCOPE |
| C15 | T-SCOREDISCOUNT and T-OBSREGIME; actual distinct observation tuples, sequence enumeration and separate alias case before RL |
| C16 | Initial pre-episode0 checkpoint and T-INITIALCHECKPOINT |
| C18 | Same episode-origin score as training; package comparisons and controlled-mechanism claims separated |
| C19 | Document reference-audit versus development commands, expected preflight infeasibility, all test evidence and fresh-user reproduction |

New tests start as PLANNED; current rows in test_matrix.csv have executed evidence, with their stated fixture scopes. Preserve fixtures, independent derivations, command transcripts, version/config hashes, status and residuals in the existing evidence ledger. A documentation calculation cannot mark a test PASS.
