# Solver execution, baselines, budgets and numerical contract

Current specification. These are selected implementation rules, not measured capabilities. Read with model_specification.md. No dimension/speed advantage is assumed from decomposition alone.

## 1. Complete baseline definitions

Define Q=(1/U)*sum_u E2E_u/D_u; D_a, D_x and D_b are normalized actual deviations against the previous committed deployment; H is normalized deviation from current Stage I. All final-deployment models (monolithic and Stage II) use the same completed feasible set (including the documented throughput addition and reachable-path interpretation).

| Method ID / label | First window | Subsequent windows | Temporal start policy | Stage II freedom |
|---|---|---|---|---|
| `mono-delay` / independent monolithic delay reference | Minimize Q | Minimize Q | Cold; no previous start | All decisions joint; no stages |
| `mono-temporal` / independent temporal monolithic variant | Minimize Q | Minimize D_a+D_x+D_b | Repaired-association partial start plus compatible previous placements | All decisions joint |
| `hier-only` / independent hierarchy-only variant | Stage I: propagation; Stage II: H | Same as first window | No prior-window start; Stage II may receive current Stage I association partial start | Associations free; no temporal beta penalty |
| `stars-fixed` / documented STARS reimplementation | Stage I: propagation; Stage II: H | Stage I: D_a(repaired)+D_x(repaired); Stage II: H+rho*D_b | Repair/previous partial starts | Associations free |
| `stars-random` | Same as stars-fixed | Same; seeded random rho | Same as stars-fixed | Same |
| `stars-q` | Same as stars-fixed; rho irrelevant when D_b=0 | Same; learned rho | Same as stars-fixed | Same |

Stage I propagation means sum of user-access and egress-GS propagation in seconds, as the selected source interpretation. All variants have no secondary optimization objective. Stable IDs, insertion order, solver seed and one thread are fixed. Tied choices remain solver dependent; no claim of unique CPU allocation or cross-platform bitwise identity. Numeric perturbations are not used as hidden tie-breaking costs.

The first three labels are **independently specified baselines**, not recovered author MINLP/MINLP-TD/MINLP-HD implementations. The missing source objectives cannot be repaired by claiming knowledge we do not have. `mono-temporal` initial Q versus STARS initial H is a declared initialization difference: run both native-initialization results and a diagnostic starting from the same externally saved feasible initial deployment (if independently validated). Label the latter common-initial-state study; never merge them. Cold/warm-start timing effects can also be ablated separately; objective and start policy are not the same mechanism.

Default diagnostic rho=1. Final fixed-ratio comparator is tuned only on validation scenarios over the same five ratios; rho=0.5 is always explicitly reported. Hierarchy-only H is a spatial consistency term, not temporal regularization. Hard-fixing Stage I is excluded because it changes feasibility. At t=0 beta deviation is zero, all RL ratios tie; skip the meaningless learning action/update for that initial setup or store it as a forced action with no policy-selection credit (selected: force rho=0.5 and exclude this step from action-frequency/learning updates).

## 2. Total per-window budget

Choose a single B for each experiment family and apply it to all methods. Toy default B=10 seconds, pilot physical default B=60 seconds; these are budgets, not promised runtimes. Different budgets produce separately labeled experiments.

The clock starts before observation/inference, repair and model building. It includes both stages, starting-solution processing, all solver calls, solution extraction and validation. Immutable trace generation/precomputation is offline and separately timed for every method's common input. Result serialization/plotting occurs after the decision and is separately reported.

Reserve the last 5% of B for extraction and independent validation. A single-stage model may solve until t0+0.95B. Two-stage Stage I must finish its build/solve/check by t0+0.15B, and Stage II may use the remaining time until t0+0.95B. Unused Stage I time transfers to Stage II; it never creates extra total budget. Actual model-building time reduces the next solver call's remaining allowance. Deadline checks happen before each expensive operation. A supervisor may enforce the worker deadline in implementation; if validation finishes after t0+B, mark `late` and do not call the deployment on-time. Preserve the late incumbent for diagnostic analysis only.

No secondary optimization passes in version 1. If later introduced, they must consume this same budget. Report B, actual per-stage times, total elapsed time and any overrun, not just solver-internal time. Benchmarks with relaxed deadlines must be separate from this real-time-budget experiment.

## 3. Staged outcome state machine

Stage I contains corrected C1–C6 plus only its objective/deviation constraints. Occupancy, achievable throughput, CPU, placement, routing and complete delay constraints enter Stage II/full monolithic models, not Stage I. Stage I validation checks this association feasible set, not the complete SFC constraints. A validated nonoptimal Stage I incumbent is usable as a soft reference; record its stage-specific bound/gap and continue. Without a valid Stage I incumbent, stop with `stage1_no_reference` and the underlying cause; do not silently solve monolithic or use repair as the reference. Proven Stage I infeasibility and Stage I timeout are different causes.

Stage II is independently checked against the full model. A valid nonoptimal incumbent can deploy before the deadline; absent/invalid/late output cannot. Stage II optimality is conditional on its chosen reference/objective, not proof that the sequential algorithm globally optimizes the monolithic objective.

Keep StageResult records for every attempted stage and `not_attempted` for others. Each includes raw status, objective name/units, primal/dual bound, absolute gap, relative-gap value or explicit undefined reason, model counts, first-valid-incumbent time, progress log, timings and validation. WindowResult records combined deployability and failure reason. Never combine bounds belonging to different objectives.

Infrastructure errors, exceptions, NaN/Infinity or corrupted data abort the run and invalidate the training transition. A well-formed timeout/no-incumbent or proven infeasible network yields a recorded failed episode. A numerical tolerance rejection is retained with raw residuals and requires diagnosis; it is not hidden as ordinary network infeasibility or fed into training as if the environment behaved correctly.

## 4. Warm-start contract

Keep `original_previous`, `repair_candidate`, `stage1_reference` and `final_deployment` distinct.

Gateway repair: retain the previous (s,g) if currently visible; otherwise retain s and choose its minimum-propagation visible g if any; otherwise choose the globally minimum-propagation visible pair (s,g). Break equal distance ties by stable IDs. No visible pair yields an explicit repair failure. Access repair uses minimum-propagation visible access with stable-ID ties. These are start/reference repairs, not final feasible deployments; capacities and complete routes can still conflict.

Default warm start is **partial**: compatible binary decisions only; unknown dependent variables remain unknown. Do not default unspecified auxiliaries to zero. Before submitting a complete start, rebuild activation, occupancy, y, endpoint/internal links, cpu gates, q/t and deviation variables from current inputs and verify every constraint. A prior cpu/radio auxiliary is never copied blindly after occupancy/visibility changes.

Record separately: candidate kind (partial/complete), specified-variable count, prevalidation result, submission attempted, API return meaning, stored/not-stored, and solver diagnostic. `addSol` returning false means not stored, not necessarily infeasible. Verify installed-version behavior of createPartialSol, check/trySol and insertion methods in C02; do not pretend partial solutions can be completely feasibility checked while unknowns remain. Complete known-invalid starts are not submitted as valid; solver receives partial information or no start according to the policy. This never changes the final feasible set.

## 5. Scaling and error budgets

Initial supported test domain: positive demand 2–20 Mbps, psi/omega each 5–90 instructions/bit, packet size 512–12000 bits, chain length 1–4, CPU 0–2000 MIPS (zero-capacity hosts allowed but cannot process), finite nonnegative overhead. Larger ranges require a scaling re-audit. Toy one-stage fixtures are allowed even though paper scenarios use 2–4 stages. Negative/nonfinite physical inputs fail early.

For each assignment define g=G/L, qhat=q/L and tau=t/(A/L). Then qhat=g+1-b, tau*qhat=b, qhat>=1, 0<=tau<=1, and qhat<= (C_s/L)*b+1-b. Global bound max(C_s/L,1) preserves unused undersized hosts. CPU rows are divided by max(C_s,1 MIPS); C16 is divided by D_u. Retain units and invert scaling on export. Bound/coefficient summaries are emitted before solve; no unbounded big-M constants.

For exact active b=1, g>0, let e=tau*qhat-1 and delta=qhat-g. Original delay error is exactly (A/L)*(e-tau*delta)/g. For an accepted near-integral active b, include |b-1| in the numerator bound. Thus per-term bound is (A/L)*(|tau*qhat-b|+|b-1|+|tau|*|qhat-g|)/g. Use actual positive g in this bound, not an assumed g>=1 before capacity/throughput validation. Recompute original A/G regardless; the bound explains scaling but does not replace the independent check.

Independent per-user delay budget tolerance: 1e-7 seconds initially. Allocate at most half to total reciprocal reconstruction error (sum over all selected and unselected candidate assignments, as defined below), one quarter to remaining numeric reconstruction, and one quarter to positive C16 slack residual. Reject if the sum or independently recomputed E2E excess exceeds the total. Capacity tolerance initially max(1e-6 MIPS, 1e-8*C_s); raw integrality target 1e-8; check logical choices and raw gating residuals separately. Reject nonfinite values before comparison.

Start C02 calibration with solver feasibility target 1e-9 if the installed backend supports it, but never assume this implies the physical thresholds. Sweep all supported extremes and near-boundary cases. If independent checks fail, revise scaling/tolerances with recorded evidence before C07 acceptance; do not loosen scientific constraints to hide the issue.

For normalized stability and Q objectives, initial certificate absolute-gap target 1e-8, relative-gap target zero (no positive relative early-stop allowance); Stage I propagation-seconds objective uses absolute gap 1e-10 seconds. Record raw solver termination. `gaplimit` with certificate is not mislabeled an exact proof. Zero primary objectives require absolute bounds/gaps; store relative gap as undefined if necessary. Fully certified tiny oracle cases must meet the specific analytical tolerance. Performance experiments may time out and keep nonoptimal outcomes.

## 6. Scaling gate before large runs or training

Soft association preferences do not remove association variables. Reachable-pair routing may create approximately U*(K+1)*S^2 endpoint-plus-internal links; internal links alone are U*(K-1)*S^2. At U=30, K=4, S=60 the latter is 324000 and the total is about 540000, before other variables. We do not inherit a reduced-MINLP variable count or speedup from the paper.

Use a size ladder: (S,U)=(2,1),(4,2),(8,4),(12,6),(20,10), then (60,30) only if affordable. Use fixed chain counts/instance counts recorded for each case. Log generated and presolved variable/constraint counts, coefficient ranges, build time, peak process memory, time to first valid incumbent, primal/dual progress, validation time and total time. Compare variants with identical safe visibility/reachability filtering.

Default preflight guard: more than 250000 estimated link variables requires an explicit experiment-config opt-in and a measured memory forecast, not automatic execution. Run one window before a full episode, then an episode before RL. Initial memory budget is 2 GiB unless explicitly configured otherwise; exceedance is recorded and blocks that scale, never triggers pruning or dropped constraints.

Any pruning must prove it removes no feasible assignment (e.g. no visibility for an access variable, unreachable pair, or CPU capacity below required allocation). Candidate ranking/nearest-host pruning is not permitted in this optimization scope. Exceeding the gate means smaller scenarios or more time/resources, not a heuristic replacement.

## 7. Official capability references

- https://pyscipopt.readthedocs.io/en/stable/tutorials/expressions.html — nonlinear constraint expressions; linear objective requirement.
- https://pyscipopt.readthedocs.io/en/stable/api/model.html — partial solutions, checked insertion and storage results.
- https://www.scipopt.org/doc/html/PARAMETERS.php — feasibility and relative/absolute-gap settings.

These establish API/modeling direction, not measured correctness or runtime for this project. Installed-version checks remain mandatory.

## 8. Complete residual acceptance contract (R1-01, R2-05)

These initial thresholds are selected calibration targets, not verified solver capabilities. C02 measures them; C07/C08 cannot pass until original-unit checks pass. Any revised threshold needs a recorded numerical justification and rerun of affected fixtures.

Decode a binary only when its raw value is within 1e-8 of exactly 0 or 1; otherwise reject. Retain raw values. Check decoded logical cardinalities, occupancy, products, reachability and activation exactly; also check all raw rows. Decoding is validation, never a repair of an invalid candidate. Reject nonfinite values first.

For each user define E_proc = sum over decoded-selected assignments |t_j-A_j/G_j| + sum over decoded-unselected assignments |t_j|, using raw exported t and G. Selected G must be positive and pass CPU/minimum-allocation checks. Include every instance/host/stage candidate, not merely one delay per stage. Require E_proc <= 5e-8 seconds within the total 1e-7-second per-user budget in §5. The active-branch identity does not bound inactive terms with G=0. Preserve raw gating/product checks before reconstructing physical delay from decoded choices. The remaining reconstruction and C16 excess allocations remain 2.5e-8 seconds each; all checks and independent total E2E excess must pass.

For a row, violation means absolute equality residual or positive inequality excess. Threshold is max(abs_tol, rel_tol*reference) with the reference explicitly given below; relative tolerance is never applied to a near-zero residual itself. Report physical residual, threshold and residual/threshold (zero threshold uses exact logical pass/fail).

| Family | Solver row scaling | Independent units; abs_tol; rel_tol and reference | Additional logical check |
|---|---|---|---|
| Binary domains | None | dimensionless; 1e-8; 0 | Decode only as above |
| Association, occupancy, activation, endpoint/internal products, deviation equalities/inequalities and bounds | Unit coefficients; do not divide counts to hide excess | dimensionless/counts; 1e-8; 0 | Exact decoded sums, ANDs, capacities and forbidden combinations |
| CPU allocation, minimum allocation, activation overhead and gates | Divide by max(host capacity,1 MIPS) | MIPS; 1e-6; 1e-8 times host capacity | Selected G>0; inactive allocation raw gate also checked |
| Achievable throughput >= demand | Divide by positive demand in bits/s | bits/s; 1e-3; 1e-9 times requested bits/s | Recompute occupancy and rate from original radio inputs, not exported y alone |
| qhat definition/bounds and tau*qhat=b | Dimensionless definitions in §5 | dimensionless; 1e-8; 0 | Conditional bounds and full E_proc budget both required |
| End-to-end delay / C16 | Divide by positive D seconds | seconds; 1e-7; 0 for reconstructed E2E; raw positive C16 excess <=2.5e-8 seconds | All five route segments, serialization and physical processing reconstructed |
| Other delay reconstruction (radio/linkage/propagation) | Original units after undoing scaling | seconds; aggregate absolute discrepancy <=2.5e-8 per user; 0 | Compare raw encoded nonprocessing total with physical recomputation |

Rows not belonging to a registered family are schema errors, not checked with a generic tolerance. Objective certificates follow §5 separately from feasibility. Boundary tests inject 0.5 and 2 times each threshold, test near-integral decoding on both sides, and corrupt occupancy while leaving exported rates plausible.

Cross-method results compare specified method packages. A claim about warm starts alone requires matching objective, initialization, data, budget and all other policies in a separate ablation.
