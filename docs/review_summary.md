# Review summary and implementation safeguards

Retained scientific safeguards from the completed planning review. Model and execution/experiment contracts, roadmap and test matrix remain authoritative. C01-C20 software and fixture evidence now exist; [EVIDENCE.md](../EVIDENCE.md) distinguishes them from blocked physical/training/evaluation work. No new reviewer prompt or review cycle is required for this handoff.

## Earlier corrections to preserve

- Conditional reciprocal bounds must allow unused undersized and zero-capacity hosts (O-QBOUND). Radio throughput sums over selected satellite/occupancy choices (O-RADIOSELECT).
- Packet latency uses packet bits; processing coefficients have separate meanings. Endpoint and internal routing must include every segment and prohibit unreachable choices.
- Failure penalties cover the remaining discounted horizon; they must not reward early termination.
- Baseline objectives, initialization, temporal references, start policies and total decision budgets are explicit. Soft Stage II does not establish a smaller model or faster runtime.
- Test expectations must be independent of production builders. Numerical acceptance uses original units; C07/C08 are a joint gate.
- Training/evaluation splits use scenario lineage and content, resume restores episode-boundary state, and statistical comparisons respect seed/group dependence.
- Binary Stage I, partially observed RL and independently specified baselines remain deliberate choices. Exact author-code reproduction and MDP convergence are not claimed.

## Final review findings and acceptance gates

| Finding | Disposition and concrete change | Location / planned verification |
|---|---|---|
| R1-01 inactive reciprocal error | Accepted. Sum selected reconstruction discrepancies and every inactive exported delay; preserve raw checks and validated logical decoding. | execution_contract §8; O-INACTIVEPROC; T-INACTIVEPROC at C07/C08 |
| R1-02 incorrect rescue oracle | Accepted. T-ST2 now points to O-ST2-RESCUE: unique Stage I optimum, propagation lower-bound infeasibility if fixed, numerical feasible alternative requiring changed access. Kept separate from multistep RL. | oracle_catalog; test_matrix; C11 |
| R1-03 failure-tail discount | Accepted. Full episode-origin equation, gamma^f multiplier, lower-is-better convention, initialization time retained. Explicit successful/first/middle/last failure examples and reward identity. | experiment_contract §7; O-SCOREDISCOUNT; C15/C18 |
| R2-01 physical infeasibility | Accepted. Documented region/plane capacity bound; paper-inputs-v1 is a known-infeasible audit. development-physical-v1 changes only population/slice membership to four users/two slices of two; feasibility is not promised. Separate access/egress matching with certificates precedes model build. | experiment_contract §9; D09/D27; O-REGIONCAP/O-MATCHING; C13/C14 |
| R2-02 implicit generator inputs | Accepted. Table fixes separate egress capacity5, per-slice chain/demand/delay, discrete-uniform chain length, per-type overhead/coefficients, per-host CPU, persistence, units/provenance and named RNG streams. | experiment_contract §§2/9; O-DRAWSCOPE; C03/C14 |
| R2-03 Stage I scope | Accepted. Corrected C1–C6 plus objective/deviation rows only; occupancy/throughput belongs in full final-deployment models. D10 now definitively records throughput as source-model completion. | model_specification §7; execution_contract §§1/3; D10; O-ST1SCOPE; C10/C11 |
| R2-04 observable RL regimes | Accepted. Different geometries do not suffice: hand-computed observation tuples must differ for the learnable example; enumerate sequences and return margins. Separate aliased-state example required. Realization remains a C15 gate. | experiment_contract §4; O-OBSREGIME; T-OBSREGIME |
| R2-05 residual families | Accepted. Table fixes units, scaling, absolute/relative references, raw and decoded checks including throughput and occupancy. Thresholds are proposed calibration targets, not achieved accuracy. | execution_contract §8; O-RESIDUALFAMILY; C02/C07/C08 |

## Readiness and evidence

Save an initial checkpoint before episode0, distinguish meaningful decisions from equivalent representations, and use controlled ablations before attributing gains to warm starts alone.

All 98 software traceability rows have recorded fixture evidence; the C20 full suite passed 743 tests. Solver-backed authored simulations exist, but no actual solver-backed training or scientific held-out result exists. The 30-user reference is a known-infeasible audit; development seed 0 fails 13/14 necessary snapshots. Physical-scale runtime and representative action sensitivity remain open.

Full reviewer transcripts, superseded responses and reviewer prompts were removed during repository cleanup. Their actionable conclusions are retained here and in the implementation contracts; no obsolete reviewer prompts are needed to resume the project.
