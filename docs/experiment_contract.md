# Fixed scenarios, RL semantics and statistical reproduction

Current scientific specification. This document freezes development choices; implementation assumptions are not recovered author inputs. Authored and frozen physical generation, audits and RL/evaluation/analysis software are implemented. The frozen reference fails necessary coverage conditions; development seed 0 fails 13/14 snapshots. No solver-backed training pilot or scientific held-out evaluation has run. See [EVIDENCE.md](../EVIDENCE.md).

## 1. Frozen development toy: `toy-v1`

Purpose: an authored, deterministic non-orbital trace for two-stage tests. Three satellites s0/s1/s2 with CPU 200/300/0 MIPS; access pools 2/2/0; egress pools 2/2/0; active-instance limits 4/4/0. Functions f0/f1 have psi=omega=10/20 instructions per bit and base overhead 5/10 MIPS. Each type has two stable instance IDs per satellite. Every user's ordered chain is [f0,f1]; repeated types rejected. Two users u0/u1, separate slices, demand 2/3 Mbps; packet 12000 bits; delay limit 50 ms; no traffic scaling through functions.

One ground station g0. Three 60-second windows. Initially both users see s0 and s1; at window 1 u0 sees only s1, u1 sees both; window 2 repeats window 1. s0 and s1 both see g0 throughout. User/access and egress/GS distances are 500000 m for allowed links. Undirected ISLs s0-s1 and s1-s2 are each 100000 m; s2 has no access/GS links and cannot host active instances. No additional random draws. This is a synthetic connectivity trace, not a physically generated orbit.

Radio defaults: carrier 14e9 Hz, transmit 0.1 W, gains 15/40 dBi, bandwidth 100e6 Hz per satellite, temperature 290 K, external interference 0 W, speed of light 299792458 m/s and Boltzmann constant 1.380649e-23 J/K. Separate pools follow the interpreted C3/C6; no GS aggregate limit. Supported numeric ranges are in execution_contract.md. Feasibility is an implementation test expectation, not a result already obtained.

Counterexample fixtures override individual values explicitly rather than mutating this shared config silently. The undersized-host case uses L=1500, hosts 1000/2000 MIPS and zero overhead; repeat first host at zero. Pure algebraic solver-smoke fixtures need not share the physical toy ranges and must identify themselves as backend tests.

## 2. Explicit physical reference assumptions: `paper-inputs-v1`

Source inputs retain the reported 60 satellites, four planes, 500 km altitude, 88-degree inclination, 30 users, six slices, two stated GS coordinates, 10-degree elevation, 14 windows of 60 seconds and parameter ranges in decisions.md.

Freeze previously missing conventions: spherical Earth radius 6371000 m; gravitational parameter 3.986004418e14 m^3/s^2; rotation rate 7.2921150e-5 rad/s; reference epoch 2026-01-01T00:00:00Z, ECI/ECEF longitude alignment defined as zero at this synthetic epoch (not claimed astronomical Greenwich orientation). Four Walker-star-style RAAN values 0,45,90,135 degrees; 15 equally spaced satellites per plane; initial anomaly 2*pi*j/15 + 2*pi*p/60 (phasing F=1). Record this convention rather than assuming the label Walker-star uniquely specifies it.

Static users: latitude uniform in sin(latitude) over 49–51 degrees N and longitude uniform over 80–69 degrees W, with minimum great-circle Earth-centered angular separation 0.5 degrees, rejection sampling in stable user order with 100000-attempt cap and explicit generation failure. Five users per slice. This region/distribution is our assumption. Seed streams independently draw layout, SFC types, demand, capacities and delay limits. Each slice draws its chain once: length discrete-uniform on {2,3,4}, then an ordered sample without replacement from the eight source types. Instance IDs: two per type/host; limit eight active instances/host. Base overhead sampled once per type uniformly 1–17 **MIPS**, an explicit unit interpretation. Demand drawn once per slice uniformly 2–20 Mbps, delay once per slice uniformly 35–150 ms, CPU once per satellite uniformly 1000–2000 MIPS; all remain constant across the episode and all exact draws are persisted. psi=omega drawn once per type uniformly 5–90 instructions/bit. Packet size 12000 bits; radio defaults as toy.

Undirected ISLs: potential two nearest same-plane neighbors and corresponding-index neighbors in the immediately adjacent planes, with no wrap between the two ends of the Walker-star plane sequence. Retain only Earth-unoccluded edges. This explicit seam policy gives degree at most four; do not invent edges to restore connectivity. ISL capacity values may be stored for provenance, but aggregate contention is not a reference constraint. External interference remains zero; no decision-dependent interference in the radio lookup.

These choices are SELECTED assumptions, not replication of author traces. This exact 30-user family is access-infeasible by the region bound below and is reserved for reference/infeasibility audits, never feasible-training screening. Audit before running optimizer. Retain uncovered users/windows and generation failures. A different plane layout, epoch, larger constellation, seam policy or region is a separately versioned scenario.

Independent visibility bound for this regular geometry: cap angle theta=acos((R/(R+h))*cos(e_min))-e_min. For R=6371 km,h=500 km,e=10 degrees theta is about 14 degrees. Each equally spaced plane's maximum visible arc is at most 2*theta, so at 24-degree spacing at most floor(2*theta/24 degrees)+1=2 satellites per plane, hence at most eight in four planes. Boundary rounding needs an explicit tolerance. This contradicts approximately fourteen visible satellites under this exact regular interpretation, not every imaginable constellation. Record the source figure as unresolved; never force generated visibility to match it. Numerically verify the formula independently at C14.

## 3. Exact observation definition

Observation is computed **before action**, using current trace, previous committed discrete deployment, known deterministic next-window geometry and prior measured actual churn. No optimized CPU allocation/slack is used, because those may differ among tied solutions.

State tuple: (initial_flag, R, global_demand_bin, host_pressure_bin, impending_loss_bin, previous_churn_bin), with R=T-t including the current window. Four three-way bins, R in 1..T and binary initial flag; at T=14 at most 2268 state combinations before excluding impossible ones. Persist exact schema and T with the policy.

- Global demand ratio = sum_(u,k) demand_Mbps[u]*psi[k] / sum_s CPU_s. If total CPU=0, use explicit overload sentinel; bin as high. This excludes overhead and is a lower-bound demand indicator, not feasibility proof. Bins: <=0.25, (0.25,0.75], >0.75.
- Host pressure = maximum per-host (current minimum CPU of stages assigned there in previous deployment + previous active-instance overhead) / CPU_s. Zero-capacity positive demand gives overload sentinel; empty zero-capacity host contributes 0. At initial setup use global demand ratio. Bins: <=0.5, (0.5,0.9], >0.9.
- Impending loss fraction = fraction of users whose previous access or egress pair is invalid now or at the next known snapshot. At last window inspect current validity only; at initialization value=0. Bins: 0, (0,0.5], >0.5. No future stochastic demand/resource failures are read.
- Previous churn = previous successful window's actual c/3, with initial value=0. Bins: 0, (0,1/3], >1/3.

No-valid-deployment ends the episode, so there is no observation pretending to continue from a missing placement. The state is explicitly partially observable: it omits topology and detailed placement. Do not claim tabular MDP convergence guarantees. All adaptive comparison policies receive the same observable fields.

Ratios ordered [0.25,0.5,1,2,4]. Unseen evaluation states choose rho=0.5. Among maximal Q values within absolute 1e-12, prefer rho=0.5 if tied, otherwise the smallest ratio. No exploration or updates during evaluation. First-window initialization forces rho=0.5 and is excluded from learning/action-frequency comparisons because no previous beta exists; the first learned state follows that deployment.

## 4. Failure reward and action-sensitivity evidence

Use model_specification.md's fixed successful churn cost and horizon-bounded failure penalty, not the old -10. Explicitly verify at R=14, gamma=0.95: worst successful tail is -3*sum gamma^j, and failure is -4*sum gamma^j. No early solver timeout can improve return relative to every fully successful tail solely by avoiding future costs. This does not guarantee a policy never fails; it defines the intended incentive.

Sanity comparator: if Stage I equals previous associations, H=(D_a+D_x)/2, so rho=0.5 makes H+rho*D_b half the immediate churn cost. Always evaluate this fixed ratio. Adaptive gains must come from sequential consequences, repaired-reference differences, partial-observation tradeoffs or runtime effects, not an artificially weak comparator.

Required two-regime fixture target: previous deployment has access a and host x. In the current window only complete deployments A=(access a,host y) and B=(access b,host x) meet the constructed delay/capacity conditions, with unchanged egress. Then A has (H,D_b)=(0,1), B=(0.5,0); rho=0.25 favors A and rho=1 favors B, both current churn=1. In next-window regime X only A persists; B must change access and host (churn=2). In regime Y only B persists; A pays 2. Different upcoming visibility alone does not establish distinguishability through the actual binned observation. The realized learnable fixture must report independently hand-computed pre-action tuples that differ between regimes, and enumerate short-horizon action sequences with positive return margins. Also retain an aliased-state example with identical tuples and different best actions to document partial observability. Construct actual independently validated topology/delay fixtures realizing the table before claiming this is a STARS result; an abstract table alone is not a solver oracle.

For small sensitivity fixtures require fully solved/certified optima and positive objective margins between meaningful decision classes (access/egress and host/type placement), allowing equivalent instance-ID permutations or CPU ties within a class. Check complete objective-optimal classes: an equivalent representation cannot be counted as a different action effect. Replay from identical serialized pre-action state with the same seeds and budget. Different tied incumbents are not evidence of a true weight effect. For larger bounded runs label differences as possibly solver-budget effects and record gaps/status. Measure action-distinctness on representative traces before training. If no useful effects appear, stop and diagnose; no constraint changes to manufacture improvement.

## 5. Grouped data split

Each trace stores scenario_group_id, underlying constellation/phasing/epoch interval, base user layout and demand-family lineage. All derivatives of one base scenario (load variants, neighboring/overlapping time windows, alternative seeds that only perturb the same root) stay in the same split. Build connected groups for overlapping intervals of the same constellation/layout family; apply a guard interval of at least one episode length between split intervals. Known repeated phase cycles belong to one group. Document that an interval gap alone does not prove statistical independence.

Maintain a normalized exogenous-content hash excluding arbitrary seed labels, file paths, run IDs and irrelevant timestamps; include actual geometry, visibility, demand and capacities. Duplicate hashes across splits are rejected, even under different seeds. Same root lineage is also rejected across splits even when perturbations change its hash. Freeze group lists before tuning. Report limitations of generalization when groups share the same global constellation design.

Feasible-training-scenario screening may use only exogenous coverage/resource necessary conditions and must be declared as conditioning the training distribution. Preserve rejected counts and separate unscreened stress evaluation. Do not select scenarios based on which algorithm wins or succeeds after optimization.

## 6. Episode-boundary resume only

Initial resume contract is at completed episode boundaries. Save a complete initial boundary checkpoint before episode 0 so interruption during the first episode follows the same replay rule. Checkpoint after each completed episode: Q table, all RNG states, next episode index, deterministic trace/group ordering, exploration counter/schedule, schema/action/bin/reward hashes, solver config and code revision. At a boundary no active deployment remains; next reset starts a fresh trace. Mid-episode resume is unsupported.

If interrupted during an episode, reload the preceding boundary checkpoint and discard/relabel all partial updates/logs from that episode as abandoned; replay the whole episode. Do not combine a partially updated Q table with a reset environment. A metadata-only checkpoint cannot claim exact continuation without RNG/order state. Different solver versions or hardware may still alter time-limited outcomes; distinguish exact controlled-fake continuation from practical solver reproducibility.

Simulation-only restart is also at episode boundary initially. More granular recovery can be a later isolated feature.

## 7. Fixed estimands and uncertainty

For failure at zero-based window f, primary score J = sum_(t=0..f-1) gamma^t*c_t + gamma^f*4*sum_(j=0..T-f-1) gamma^j. For complete success J = sum_(t=0..T-1) gamma^t*c_t. Lower J is better. Equivalently J=-sum over attempted transitions gamma^t*r_t, with the absorbing tail already included in the terminal reward. Use finite sums also for gamma=0 or 1, with gamma^0=1. Initial setup remains window 0 in discounting and failure accounting even though its learning update is skipped. At T=3,gamma=0.5,f=1,c_0=0, J=3, not 6. It is a **penalized episode score**, not fabricated observed traffic after stopping. Physical metrics for unattempted windows stay null. Separately report episode completion rate, failure cause, attempted windows, conditional delay/churn and unconditional penalized score.

For K trained policy seeds and M held-out scenario groups, evaluate every seed on every group. If a group has multiple episodes, average within group first with equal episode weights; groups then receive equal weight. Fixed baseline is paired on the identical episode/group. Delta = mean_(k,m) [J_policy(k,m)-J_fixed(m)]. No pooling of correlated windows as independent samples.

Use crossed bootstrap for exploratory 95% intervals: independently resample training-seed IDs and scenario-group IDs with replacement, preserve the Cartesian grid and matched fixed baseline, and recompute Delta for 2000 draws with a recorded bootstrap seed. This targets variation over both sampled training seeds and scenario groups under the stated grouping assumptions. Show per-seed and per-group results. With fewer than three training seeds or ten independent groups, label results descriptive/exploratory and do not present an interval as strong evidence. For fixed-method ablations, bootstrap paired scenario groups only.

Failure rates and penalized scores include every modeled failed episode. Infrastructure/numerical implementation errors invalidate the run and must be fixed or explicitly reported as missing/error outcomes, not silently dropped. Report both sample sizes and exclusions/reasons. The source paper's exact confidence-interval procedure is not claimed to be replicated.

## 8. Training budget gate

Measure B usage, stage times, memory and sensitivity overhead on a size ladder before setting episodes. Estimate E*T*(t_I+t_II+overhead), plus sensitivity, validation and evaluation solves; omit initial training-update count only from learning, not compute. No training launch without saved estimate and compatible budget. Global solver optimality, policy learning and deadline practicality are separate acceptance gates.

## 9. Physical family classification and generation table (R2-01/02)

`paper-inputs-v1`: deterministic access-infeasibility/reference audit. At most four satellites can be visible to the user population at any snapshot, so access capacity <=4*5=20<30. This conclusion is independent of random draws within the declared rectangle and of the optimizer.

Independent derivation: the rectangle lies within 6.5 degrees of (50 N,74.5 W), using a conservative latitude-plus-longitude path bound. Expanded cap radius is 14.056535+6.5=20.556535 degrees. With plane normal n=(sin(i)sin(RAAN),-sin(i)cos(RAAN),cos(i)) and unit centre vector r, plane distance is asin(|n dot r|). At the synthetic epoch the distances are approximately 40.22,35.86,11.44,16.83 degrees. During even the conservative 840-second interval, Earth rotation changes these by at most 3.51 degrees. The first two planes therefore cannot intersect the expanded cap. Each remaining plane's intersecting arc is at most 41.11307 degrees, admitting at most two satellites spaced 24 degrees apart. The proof uses a superset cap and does not depend on phasing. C14 implemented and independently tested this bound; saved audits are indexed in EVIDENCE.md. The written derivation alone is not execution evidence.

`development-physical-v1`: same geometry, radio, instance limits and distributions as paper-inputs-v1, but four users in two slices of two users each. This is an explicitly changed population, not paper-scale replication. It is a development candidate, not a promised feasible family: access/egress matching, resource necessary conditions, full independently validated solutions and runtime gates still apply. toy-v1 remains the initial deterministic development fixture. Do not silently move users/epochs, raise capacity, prune hosts or retry until an algorithm succeeds. If no usable physical traces exist, retain failures and propose a new version with explicit rationale; do not claim physical experiments completed.

| Parameter | Value/distribution; units | Scope and persistence | Provenance |
|---|---|---|---|
| Population | reference 30 users/6 slices/5 each; development 4/2/2 | Fixed per family; user-to-slice mapping stable across windows | Reference counts from paper; development reduction explicit |
| User coordinates | sin-latitude and longitude uniform on §2 region; rejection separation 0.5 degrees | Per user, static episode | Selected geographic sampling convention |
| Chain length and sequence | Uniform integer {2,3,4}; uniform ordered distinct sample of 8 types | Per slice, shared by all its users, static episode | Source range/slice semantics; selected probability law |
| Demand / delay limit | Continuous uniform [2,20] Mbps / [35,150] ms | Separate draws per slice, shared by its users, static episode | Source ranges and slice semantics; selected distribution |
| CPU capacity | Continuous uniform [1000,2000] MIPS | Per satellite, static episode | Source range; selected distribution |
| psi and omega | One uniform [5,90] instructions/bit draw; assign both fields this value | Per type, shared by all hosts/instances/slices, static episode | Source range; selected equality/distribution |
| Base overhead | Continuous uniform [1,17] MIPS | Per type, shared by all its host/instance copies, static episode; charged per activated instance | Source range; selected units/distribution |
| Access capacity | 5 users per satellite | Fixed every satellite/window | Source value |
| Egress capacity | 5 user flows per satellite, separate from access pool | Fixed every satellite/window; no aggregate GS cap | Explicit implementation assumption |
| Instances | 2 IDs per type/host; <=8 activated per host | Stable identities and caps across episode | Selected implementation assumptions |
| Packet / radio | 12000 bits; constants in §1 | Fixed globally across episode | Declared assumptions/source values as §1/decisions |
| Orbit / GS / ISLs | Deterministic §2 constants, coordinates and edge rule | Positions/visibility evolve each window; constants unchanged | Source inputs plus declared geometry conventions |

Use independently seeded named streams for layout, chain, demand, delay, CPU, coefficients and overhead; stable sorted IDs determine draw order. Persist RNG algorithm/library version, each named seed, actual draws, distribution/scope metadata and family version. Within-slice demand is each user's demand, not a total divided across slice members. Aggregate per-user processing and association loads accordingly.

Before expensive model building, for every snapshot perform separate necessary-condition audits: access user-to-visible-satellite capacitated matching; egress user-to-satellite matching with an edge only if that satellite sees at least one permitted GS. Each user needs one unit in each separate pool. Do not sum a satellite's egress capacity once per GS. Save flow value, unmatched users and a min-cut/bottleneck certificate. These checks do not prove joint routing/CPU/throughput feasibility. In audit mode retain known failures without a full solve; in simulation use a typed preflight-infeasible outcome, which is a modeled failure with the same reward accounting. RL training never uses the known-infeasible reference family. Report conditioning/rejection counts for any screened development distribution.
