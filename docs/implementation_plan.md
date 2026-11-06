# STARS + RL: implementation master plan

Current master plan, originally reviewed 25 October 2026. C01-C20 software modules are implemented; scientific completion remains blocked. [EVIDENCE.md](../EVIDENCE.md) is the current status index; [test_matrix.csv](test_matrix.csv) records executed software oracles. This plan preserves the scientific requirements and supersedes earlier heuristic proposals.

## 1. Agreed objective

Independently implement the optimization-based STARS workflow described in the supplied presentation and paper, in Python with SCIP/PySCIPOpt, then add an RL controller that selects stability weights. Preserve the mathematical decision problem where it is specified. Record and test interpretations where the source is ambiguous.

Implementation proceeded in verified local milestones. Writing this plan created no executable evidence; current software evidence and remaining research gates are indexed in EVIDENCE.md.

Do not replace optimization with greedy placement, beam search, GA, ACO or a neural placement policy. Do not fix CPU at its minimum requirement. Reduce initial scenario size instead. A solver's own internal search heuristics are normal solver behavior and are not a replacement of the optimization formulation.

No Gurobi license is available. Implemented backend: SCIP through PySCIPOpt, whose documented capabilities include mixed-integer nonlinear optimization. This changes implementation and potentially runtime, not automatically the mathematical model. C02 capability checks passed on the tested backend; a future backend change requires renewed checks. If it fails, stop and document the exact unsupported behavior before proposing another formulation/backend.

Do not claim exact reproduction of unavailable source code or published percentage improvements. Use the description **independent optimization-based STARS implementation with documented model interpretations and an RL extension**.

## 2. How to use this specification

Read in this order:

1. This master plan: scope, architecture and completion criteria.
2. [Model specification](model_specification.md): variables, formulas, constraints and numerical handling.
3. [Decision register](decisions.md): every resolved interpretation and unresolved parameter.
4. [Commit roadmap](commit_roadmap.md): exact coding order, files, tests and gates.
5. [Test plan](test_plan.md) and [test matrix](test_matrix.csv): coverage and evidence requirements.
6. [Reproduction contract](reproducibility.md): current CLI, artifacts and third-person workflow.
7. [Execution contract](execution_contract.md): exact baselines, stage budgets, warm starts, scaling and numerical error budgets.
8. [Experiment contract](experiment_contract.md): frozen toy/physical assumptions, RL state/reward, grouped splits and statistics.
9. [Oracle catalog](oracle_catalog.md): independent fixture derivations and counterexamples.
10. [Review summary](review_summary.md): context and safeguards from the completed reviews.
11. [Evidence index](../EVIDENCE.md): current status and test evidence links.

Use the tested README entry point and current CLI help for executable commands. The roadmap records implementation requirements, not a claim that scientific experiments have completed.

## 3. Source mapping and boundaries

Primary sources: user-provided ACN_PPT.pdf and DOC-20260917-WA0014.pdf. Paper: M. Mahyoub et al., “STARS: Stability-Aware SFC Orchestration and Associations in LEO Satellite Networks,” IEEE TNSM, vol. 23, pp. 3326–3340, 2026; DOI 10.1109/TNSM.2026.3674391.

| Requirement | PPT slides | Paper locator | Implementation |
|---|---|---|---|
| Users, slices, instances, resources | 3–4, 9–10 | III, Table II | models/config |
| Orbital topology and visibility | 5, 9, 14 | III-A/B | topology |
| Associations and placement | 9 | C1–C12 | optimization/constraints |
| CPU allocation and instance limits | 9 | C13–C15, gating bounds | optimization/resources |
| Radio and E2E delay | 11 | equations 1–6, C16 | radio/delay |
| Normalized stability | 12 | equations 7–10 | optimization/objectives |
| Repair and Stage I | 13–16 | Algorithms 1–2, equations 11–12, C17–C20 | repair/stage1 |
| Stage II | 15–16 | Algorithm 3, equations 13–14, C21–C26 | stage2 |
| Control cycle | 18–19 | IV-E | simulation |
| Scenarios and mechanism ablations | 21–25 | V–VI | experiments |
| Adaptive stability weights | Additional RL component | IV-C, VII | rl |

The control cycle is simulated. Real firewall/IDS execution, SDN/OpenFlow/NETCONF deployment, packet-level ns-3/OMNeT++, migration state transfer, MPC and mega-constellation optimization are out of scope for the first implementation.

The linked author repository contained only README.md when inspected. No author implementation has been reused. Keep source attribution and future code-reuse attribution separate. Do not commit supplied IEEE PDFs by default.

## 4. Architecture

Data flow:

`scenario config -> immutable network trace -> previous deployment -> repair -> Stage I -> Stage II -> independent validation -> committed deployment -> metrics -> next window`.

RL inserts weight selection before the two-stage solve. It cannot alter constraints, telemetry, evaluation reward coefficients or solver time limits.

Key rules:

- Common constraint builders serve monolithic and two-stage models.
- The validator recomputes constraints from exported values without relying on model-builder expressions.
- Keep original previous deployment, repaired candidate and final deployment distinct.
- Stage II can revise Stage I associations.
- Previous state is private to each algorithm run; traces are shared and immutable.
- Every outcome carries solver status, incumbent presence, bounds/gap and validation status.
- Never silently drop users, relax SLA, fabricate visibility, deploy a repair candidate or substitute a heuristic after failure.

## 5. Proposed repository contents

```text
stars-rl-orchestration/
  README.md
  pyproject.toml                 # created at C01
  requirements-lock.txt          # tested resolved versions, created at C01/C02
  requirements-build-lock.txt    # pinned pip/build backend/toolchain
  .gitignore
  REFERENCES.md
  CHANGELOG.md
  configs/
    toy.yaml
    small_orbital.yaml
    paper_scale.yaml
    experiments/{smoke,baseline,rl_train,rl_eval}.yaml
  docs/
    implementation_plan.md
    model_specification.md
    decisions.md
    execution_contract.md
    experiment_contract.md
    oracle_catalog.md
    commit_roadmap.md
    test_plan.md
    test_matrix.csv
    reproducibility.md
    progress.md
    review_summary.md
  src/stars_rl/
    __init__.py
    cli.py
    config.py
    models.py
    topology/{geometry,orbits,visibility,paths,trace}.py
    physics/{units,radio,delay}.py
    optimization/{backend,variables,constraints,resources,objectives,
                  monolithic,repair,stage1,stage2,result}.py
    validation/{deployment,residuals}.py
    metrics.py
    simulation.py
    experiments/{runner,manifest,aggregate,plots}.py
    rl/{environment,state,actions,reward,q_learning,checkpoint}.py
  tests/
    unit/
    solver/
    integration/
    regression/
    review_regressions/
    reproducibility/
    fixtures/
  examples/                     # small redistributable trace/result examples
  notebooks/demo.ipynb           # thin wrapper, no separate algorithm implementation
  .github/workflows/tests.yml
  artifacts/                    # ignored; generated per-run outputs
```

This is a target tree, not a request to generate empty files now. Create a module when its commit needs it. Package internals use plain dataclasses/typed records and pure calculations where practical; no web service or dashboard is required.

## 6. Stack and solver gate

Pin build-toolchain dependencies separately and use the controlled no-build-isolation install in reproducibility.md. Start minimal CI at C01. The tested core uses Python 3.11, NumPy, PyYAML, pytest and PySCIPOpt, pinned in the lockfiles. Matplotlib is optional in a separate plotting interpreter; NetworkX, pandas and Gymnasium were not needed. Q-learning is tabular. DQN is optional future work, not an initial dependency.

Pin versions only after a successful clean installation. Record Python, PySCIPOpt and SCIP versions separately. Use a virtual environment. A supported wheel should include SCIP; verify rather than assume the user's platform is supported. No Gurobi credentials, GPU or cloud account is a prerequisite.

C02 must verify linear assignment, nonlinear reciprocal resource allocation, solution export, status/bounds and warm-start insertion. No large model work before it passes.

## 7. Simulation and RL strategy

Develop on hand-authored tiny fixtures, then small physically generated scenarios, then the paper-sized inputs if coverage and solver runtime allow. Toy fixtures verify correctness, not orbital realism. Never combine toy and physical results under one unlabeled curve.

Base experiments have fixed demand within an episode, as a paper-style setting. Variable-demand stress experiments are explicitly additional scenarios. All algorithms receive the same trace and information.

Train RL only after fixed-weight STARS and the matched baseline runner pass. Initial actions choose the Stage II ratio `w_beta / w_H` from `{0.25, 0.5, 1, 2, 4}`, with `w_H=1`. Stage I weights stay fixed. Test action sensitivity before training: not all weight changes affect the optimum.

Use a tabular agent first, with the precise allocation-independent observation and remaining-horizon field in experiment_contract.md. State aggregation is an approximation to the full sequential state and must be disclosed. Reward coefficients remain fixed and distinct from selected optimizer weights. Future deterministic visibility may be an observation; future stochastic demands may not.

Train/tune/test on grouped scenario families with overlap and content-hash rejection, not just disjoint seed numbers. Resume only at episode boundaries. Store scenario seeds independently from training/exploration and solver seeds. Report inference plus optimization time separately from training. Solver runtime is likely more important than neural-network compute; a GPU cannot eliminate solver calls.

## 8. Milestone groups

| Gate | Commits | Deliverable |
|---|---|---|
| A | C00–C04 | Environment, solver capability, validated data/physics |
| B | C05–C08 | Trace fixtures, common optimization and independent validator |
| C | C09–C12 | Temporal/hierarchical STARS and documented ablations |
| D | C13–C14 | Reproducible runner and orbital scenario audit |
| E | C15–C18 | RL environment, training, evaluation and plots |
| F | C19–C20 | Clean-room reproduction, CI, submission release |

There are 21 planned commits including documentation-only C00. C07 may land as a draft model commit so C08 can implement independent validation; C07/C08 are accepted together, and C09 onward is blocked until that joint gate passes. Other dependent work waits for its prerequisite gate. If progress is slower than hoped, extend the schedule or reduce experiment scale; do not weaken the model or hide failures. The prior 27 October target is flexible and not a runtime promise.

## 9. Definition of done

- Source equations, choices, code and tests are traceable.
- All accepted deployments pass an independent check within declared tolerances.
- Tiny analytic cases confirm model correctness; no false claim of global optimality from a local oracle.
- Full fixed-weight STARS runs over multiple windows.
- RL has non-degenerate actions and is evaluated against tuned fixed policies under matched budgets.
- All failures, timeouts and non-optimal incumbents are retained in results.
- A fresh environment can run the documented quickstart and regenerate plots from saved measurements.
- Larger-run costs, model differences and reproducibility limits are documented.
- No claim of RL superiority or published percentage reproduction is required for completion.

## 10. Current status

C01-C20 software is implemented through `5b6725f`. Fresh local Windows full regression: 743 passed, zero failures/errors/skips. Hosted C20 fast profile: 510 passed on Windows and Ubuntu; no C20 hosted full run is recorded. These are software checks, controlled fixtures and authored diagnostics. Frozen physical seed-0 episodes stop at initial necessary-condition failures; physical runtime, representative action sensitivity, solver-backed training and scientific held-out evaluation remain blocked. See EVIDENCE.md and release_status.json. No new experiment or publication is authorized by this handoff.

## Implementation safeguards

Read [the review summary](review_summary.md) for all eight accepted findings and dependent gates. paper-inputs-v1 is a known access-infeasible reference audit; development-physical-v1 explicitly reduces population to four users/two slices; seed 0 fails 13/14 necessary checks, including window 0. Full optimization and RL scope remain intact. Updated execution/experiment contracts, oracle catalog and commit gates are normative; current software test evidence is in EVIDENCE.md.
