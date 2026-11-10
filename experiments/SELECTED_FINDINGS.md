# Findings selected for the project report

This is an evidence guide for the team, not a finished academic report. All other cases remain in the archive and full tables.

## 1. A meaningful multiuser demonstration

Use the 16-user/four-satellite forced handover as the primary live example. Four users change access and eight function stages change hosts; the next unchanged window retains those choices. Both optimization stages run, continuous CPU remains optimized, and final deployments pass independent checks. The controlled visibility is authored, not generated orbital coverage.

Use the 32-user/eight-satellite result as the scaling example: three committed windows, four access switches and eight function-host moves, 9.931 seconds summed over the three decision windows in this single run. It is not a 9.931-second per-window measurement or a measured maximum population of the software.

Retain the unsuccessful 64-user/16-satellite result in the same table: no committed window, first decision rejected for exceeding the ten-second budget, measured decision wall time 34.642 seconds. Model construction/extraction can overrun a requested budget; the runtime detects lateness and withholds deployment rather than guaranteeing immediate interruption at ten seconds.

## 2. Where STARS helps computationally

Use the three rotated-order repetitions of the same sixteen-user/four-handover input:

| Method | Successful episodes / attempts | Sum of decision times per attempted episode |
|---|---|---|
| stars-fixed | 3/3 | 1.089, 1.350, 1.917 seconds |
| mono-temporal | 3/3 | 9.882, 10.955, 10.349 seconds |
| hier-only | 3/3 | 1.867, 1.540, 1.114 seconds |
| mono-delay | 0/3 | 19.265, 19.121, 19.007 seconds; each stops after one committed window |

Each method gets ten seconds per window. These observations support a computational advantage for the hierarchical methods over the tested monolithic methods on this trace. They do not isolate the contribution of hierarchy, objectives or starts, do not prove universal speedup, and do not establish STARS superiority over hierarchy-only. Failed episode timings describe fewer completed windows. These repetitions are not independent network samples.

Also show the four handover intensities (0,4,8,16 users). The method-completion figure retains all successes and failures, including cases where monolithic delay completes. Do not omit these favorable baseline outcomes.

## 3. Feasibility boundaries with clear explanations

- Four satellites with five access slots each support the tested twenty-user case. Twenty-four and thirty-two users on those same four satellites are association-infeasible. Adding satellites enabled the separately tested thirty-two-user case.
- At sixteen users, two satellites are capacity-infeasible; four, eight and twelve complete; twenty misses the computational budget. More available satellites can enlarge the optimization model.
- CPU per satellite 100 and 200 MIPS: infeasible. 500 and 1000 MIPS: complete. Requests and overhead remain included.
- Uniform user demand 2 and 5 Mbps: complete. 10 and 20 Mbps: infeasible at the fixed capacities. This is a resource-feasibility result, not a network throughput benchmark.
- Delay limit 5 ms: infeasible. 10,20,50 ms: complete. CPU allocations and delays at tied stability optima may change; do not interpret lower observed delay under higher demand as a systematic improvement.

Use one or two representative boundary figures in the report. Keep the full grid in the appendix/archive.

## 4. Why Stage II association freedom matters

The previously executed rescue fixture has a Stage I access rate of 0.5 Mbps against a 2 Mbps demand. Fixing this association makes the full model infeasible. Soft Stage II changes access, obtaining 12 Mbps and approximately 6.31 ms validated delay. This is a direct functionality demonstration, not a statistical performance claim.

## 5. What adaptive weights can add, and what remains unestablished

The saved constructed X/Y solver experiments show equal immediate churn but different future consequences: ratio 0.25 gives remaining return -1 in X and -2.9 in Y; ratio 2 reverses these outcomes. The 1.9 return gap corresponds to two additional changes discounted by 0.95. Include the aliased-state case: identical observations can conceal different best choices.

The all-five-ratio experiments on the eight/sixteen-user forced handovers have identical mandatory migrations. They show that adaptive weights do not help when the network leaves no alternative.

Together these explain the opportunity and limitation for RL. They are not a learned-policy improvement. No native trained-policy pilot or scientific held-out evaluation passed readiness. Do not create an RL learning curve or label the untrained checkpoint replay as training. Controlled learning/checkpoint/evaluation tests establish software semantics only.

## 6. Physical experiments: keep the failures informative

Both physical families were audited at all fourteen snapshots for seeds 0–4: ten traces and 140 snapshots, with every seed retained. The reference family has zero passing snapshots for each seed. Development passing snapshots are 1,10,1,2,1 across the five seeds; none is a fully passing episode.

Development seeds 1 and 2 initially pass coverage/resource necessary checks and were therefore attempted through the actual optimizer. Seed 1 reaches the solver time limit at the first window without a deployment; seed 2 is infeasible in the full model. Neither produces a committed physical window. This establishes why access matching alone cannot approve a deployment. The frozen reference's regional access upper bound 20<30 is specific to that reconstructed geometry.

Physical satellite counts/plane geometry are frozen by the existing generator and schema. Arbitrary physical constellation sweeps were not executable without changing the implementation; they are explicitly outside this code-frozen experiment program. Varying authored satellite counts does not substitute for orbital experiments.

## Coverage and verification

The final matrix has 38 records from 34 unique authored simulations; four baseline configurations reuse identical content hashes and are labelled. Supplementary work adds three larger-capacity episodes, twelve runtime repetitions and two physical optimizer attempts: 51 new simulation invocations plus ten physical trace audits. The archive also includes all 24 earlier native/shared-start/weight-comparison runs and the prior fresh regression evidence.

Saved authored outputs were independently revalidated again: 49 episode records inspected, 100 committed deployments passed full objective/deployment checks, zero new solver calls for this revalidation. Two initial verification-script calls used an inappropriate validator entry point/weight for Stage II; the script was corrected to use the existing method-specific validator without changing any measured data or implementation.

The previous full regression passed 743 tests/183 solver tests. It was not rerun merely because experimental configurations and scripts were added. No optimization, validation, RL or physical-generation implementation was modified. Raw outputs, configurations, command records and errors/failures are retained. No remote push or publication has been performed.
