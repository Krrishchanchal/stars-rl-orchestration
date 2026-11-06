# Verification, experiments and maintained evidence

Current verification contract. [Oracle catalog](oracle_catalog.md), [execution contract](execution_contract.md) and [experiment contract](experiment_contract.md) define independent acceptance semantics. The C20 full suite executed 743 tests on Windows; [test_matrix.csv](test_matrix.csv) has 98 software requirements with recorded fixture evidence. Scientific readiness is separate; see [EVIDENCE.md](../EVIDENCE.md).

## 1. Separate three questions

1. **Software correctness:** does code implement its declared behavior?
2. **Model correctness:** do constraints and equations encode the intended networking problem?
3. **Research performance:** does STARS or RL improve a metric under defined scenarios?

Passing automated tests establishes neither universal optimality nor RL superiority. Keep correctness test reports separate from experiment conclusions.

## 2. Test layers

| Layer | Purpose | Examples | When |
|---|---|---|---|
| Unit | Numeric/schema/metric correctness | Units, packet delay, normalization, IDs | Every relevant edit |
| Constraint | Correct feasible set per source rule | Fix violating choices and verify rejection | Constraint implementation/change |
| Solver smoke | Backend capabilities and exports | Assignment optimum, reciprocal resource model | Setup/version change |
| Tiny oracle | Independent answer | Enumerate discrete choices with analytically solvable continuous allocation | Optimization changes |
| Independent validator | Detect invalid returned deployment | Corrupt each constraint family separately | Every accepted solution and tests |
| Integration | Cross-window workflow | Forced handover, soft Stage II correction | Orchestration changes |
| RL semantics | Learning/environment correctness | Reward, terminal updates, action sensitivity | RL changes |
| Regression | Prevent previous bugs recurring | Minimal fixture for each fixed defect | Every relevant edit |
| Reproduction | External user can run artifacts | Fresh install, quickstart, plot-only | README/release changes |

No production test may require access to the author's code or supplied PDFs. All fixtures include a human-readable explanation of why the expected answer is correct.

## 3. Exact-oracle discipline

Enumerate tiny binary assignments independently from production constraint builders. For each assignment, use a closed-form continuous allocation case or another certified calculation. An independently written local NLP routine is not a global MINLP oracle. Compare feasible sets, optimal objectives and constraint residuals, not exact chosen assignments under ties.

For Stage I, exhaustively enumerate associations on tiny graphs. For nonlinear stages, start with one user and one/two known function hosts where CPU-delay tradeoffs have analytic optima. Expand only when the oracle remains trustworthy.

## 4. Constraint and negative cases

test_matrix.csv contains separate rows for C1–C26 and supporting requirements, with source/decision, fixture and independent-oracle IDs. For each constraint family:

- a satisfiable fixture;
- a boundary fixture;
- an invalid candidate that the validator rejects;
- where meaningful, a fixed-invalid solver fixture that makes the model infeasible.

Avoid negative tests that accidentally violate several unrelated constraints, because they do not prove the intended constraint is enforced. Name IDs in failures and include residuals.

Important combinations: shared instance overhead; CPU gating plus processing delay; rate reduction when a second user attaches; colocated functions; unreachable host pair; valid multi-hop host; no gateway visible; repair collisions; association changed by Stage II; zero objective coefficient with slack deviation auxiliary; topology pruning with an unavailable previous association.

## 5. Tolerances and numerical robustness

Freeze units, solver feasibility/integrality settings and validator tolerances together. Validate solver outputs at original scale, not only transformed variables. Keep raw float values for diagnosis. Near-zero comparisons use explicit absolute tolerances; capacities may use an additional relative tolerance. Record all tolerances in manifests.

Test cases just inside and outside each tolerance. A model that passes because checks are excessively loose is a failure. If transformed residuals are small but original-delay residuals are large, do not accept the deployment.

Tests do not assert that warm starts are always faster or that all solver runs choose identical tied assignments. Performance is measured separately on matched hardware and budgets.

## 6. Failure handling tests

Use backend adapter fakes for deterministic status mapping tests and real tiny cases for feasible/infeasible numerical behavior. Cover optimal, feasible time-limited incumbent, no incumbent, infeasible, unbounded/model error and invalid exported solution. Never expect an arbitrary tiny wall-time limit to reliably produce a specific status on every machine.

Integration tests verify no invalid result is committed and no missing window disappears from summaries. If an episode stops early, export a failure record and explicit not-attempted remaining windows. Report completion rate and conditional delay separately; early failure must not appear as excellent low average delay.

## 7. RL verification and experiments

Before training, run action replay on identical saved states and verify constraint/solver-budget invariance. Different action-dependent objective weights may produce identical solutions; measure this and require a justified non-degenerate experiment.

Verify Q updates with manually computed values, exploration RNG, reset state isolation, horizon/failure termination, frozen-policy evaluation and compatible checkpoint resume. Check no future stochastic data in observation and no test-seed overlap or test-fitted bins.

Research evaluation uses lineage/interval/content-hash grouped splits, tuned fixed ratios including rho=0.5, random actions and multiple policy seeds as budget permits. Apply the fixed crossed seed/group estimand in experiment_contract.md. Do not assert RL must outperform in unit tests. The failure-return bound and realizable multistep fixture are separate requirements from merely observing different actions.

## 8. Implemented test commands and reports

```text
python -m pytest tests/unit -q
python -m pytest tests/solver -q
python -m pytest tests/integration -q
python -m pytest tests -q --junitxml=artifacts/tests/<run-id>/junit.xml
```

Directory-selected CI profiles are implemented in scripts/ci_checks.py. The fast job runs selected unit and tiny solver/integration cases. Large benchmarks/training are opt-in; mark their absence as not run, not as passing. No blanket solver skip that hides broken SCIP installation.

Per-test evidence record: ID, source/decision links, fixture ID, independent oracle ID, expected result and derivation, command, observation, status, date, backend versions, code/tree state and artifact path. Generate indexes from JUnit where possible. A short note explains reasoning and visual review. Same-helper recomputation is consistency-only, not an independent oracle.

## 9. Maintaining tests as implementation evolves

- Every commit updates only affected test rows and preserves prior evidence references.
- Statuses: PLANNED, IMPLEMENTED_NOT_RUN, PASS, FAIL, BLOCKED, DEFERRED.
- PASS requires an actual run; a written test or code inspection is insufficient.
- A bug fix adds the smallest fixture that failed before the fix and passes after it.
- A model change updates source mapping, decision register, fixtures, expected results and affected experiment versions together.
- Code coverage is a supporting signal; no arbitrary percentage substitutes for requirement coverage.
- Review skipped tests and warnings before release. Record why each is skipped and what claim it prevents.

## 10. Completion gate

All in-scope source constraints, numerical utilities, failure modes, temporal/hierarchical behavior, RL semantics and reproduction paths have linked evidence. Physical scenario audits and performance experiments are reported separately. No claim that finite tests prove correctness for every possible network.

## Numerical and regression acceptance

Require the review regression fixtures in oracle_catalog.md. Validator must reject NaN/Infinity and unknown IDs before evaluating residuals. C07/C08 form a joint gate: solver-builder consistency checks alone cannot certify the mathematical model.

Test separate Stage I/II statuses, their distinct bounds and a shared window deadline; validate partial versus complete warm starts and API storage semantics. A numerical/programming error aborts training rather than becoming an ordinary reward transition.

Numerical tests derive original-unit errors from transformed residuals and sum them across the chain. Use analytic two-function CPU optima, lower-bound-active cases and zero-objective absolute gaps. Run supported-range sweeps before accepting physical instances.

The matrix has source_decisions, fixture_id and oracle_id columns. Expected proofs belong in oracle_catalog.md; JUnit and observed values are linked only after execution. Every new failure adds a regression without rewriting history. Minimal CI begins at C01; C20 hardens release gates.

## Cross-cutting acceptance gates

Follow the [commit roadmap](commit_roadmap.md#cross-cutting-acceptance-gates) and [test matrix](test_matrix.csv) for milestone-specific checks. Preserve fixtures, independent derivations, command transcripts, version/config hashes, outcomes and residuals in the [evidence index](../EVIDENCE.md). Documentation calculations do not mark a test PASS.
