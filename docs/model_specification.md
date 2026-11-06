# Mathematical and implementation specification

Current scientific specification. Read with [decisions](decisions.md), [execution contract](execution_contract.md) and [experiment contract](experiment_contract.md). C01-C20 software, including C08 independent validation, is implemented; tests and experimental limits are indexed in [EVIDENCE.md](../EVIDENCE.md). Source interpretations are explicit, not claims about unavailable author code. Physical feasibility, representative action effects, training and scientific held-out evaluation are not established.

## 1. Entities and stable identifiers

Use stable IDs for user, slice, satellite, ground station, function type and function instance. Stage position is distinct from function type. Version 1 explicitly rejects repeated function types within one chain; it does not merge them. beta[u,k,i,s] is created only for i in the instance set of the type at stage k. Instance identity is the tuple (type, instance_id, satellite_id); the same numeric instance_id at another host is a different instance.

Each satellite has CPU MIPS, separate access and egress-flow capacity pools, maximum active instances, and valid ISL edges. Separate pools follow the two source constraints; a shared physical antenna pool is not assumed. No aggregate GS capacity is added. Base overhead is paid once per active instance and per-user processing is charged separately. Instance IDs remain stable across windows. Define host[u,k,s]=sum_i beta[u,k,i,s]. For activation use assignment_count<=M_f*active and active<=assignment_count, with M_f equal to the total number of eligible user-stage occurrences of type f (not an unexplained constant). This remains a valid bound if repeated types are supported in a later version.

## 2. Decision variables

| Variable | Domain | Meaning |
|---|---|---|
| alpha[u,s] | binary | user u attaches to access satellite s |
| xi[u,s,g] | binary | user u exits via satellite s and ground station g |
| beta[u,k,i,s] | binary | chain stage k of user u uses instance i on s |
| active[f,i,s] | binary | instance is active |
| cpu[u,k,i,s] | continuous nonnegative | processing MIPS for that assignment |
| host[u,k,s] | binary or exact sum | stage host, aggregated over instances |
| chi[u,k,s,t] | binary | consecutive stages k and k+1 hosted on s and t |
| deviation variables | continuous nonnegative | absolute-difference epigraphs |

Do not create impossible access/gateway variables, but missing variables evaluate to zero when comparing previous deployments. Do not prune reachable SF hosts merely because they are not directly visible to a user. Unreachable host pairs must be forbidden, not omitted from delay sums while remaining selectable.

## 3. Feasibility constraints

Implement named constraints with stable prefixes and entity IDs. Test each constraint independently and together.

| Source | Requirement |
|---|---|
| C1 | sum_s alpha[u,s] = 1 |
| C2 | alpha allowed only on currently visible access edges |
| C3 | sum_u alpha[u,s] <= access antenna capacity |
| C4 interpretation | sum_(s,g) xi[u,s,g] = 1; see D01 |
| C5 | xi allowed only for visible satellite/GS pairs |
| C6 | gateway flow count per satellite <= configured gateway limit |
| C7 | sum_(i,s) beta[u,k,i,s] = 1 for each chain stage |
| C8–C9 | activation equivalent to at least one assignment; overhead counted once |
| C10–C12 | chi = AND(host current, host next), for valid host pairs |
| C13 | sum_(i,s) cpu[u,k,i,s] >= required processing MIPS |
| gating bounds | 0 <= cpu[u,k,i,s] <= satellite_cpu[s] * beta[u,k,i,s] |
| C14 | sum active overhead + sum user CPU <= satellite CPU |
| C15 | number of active instances <= satellite limit |
| C16 | full E2E delay for every user <= slice delay budget |

For binary AND z=x*y use z<=x, z<=y, z>=x+y-1. Colocated consecutive functions have zero propagation delay and remain valid. For unreachable pairs enforce host_current + host_next <= 1. Whether the domain is direct-neighbor or graph-reachable is explicitly resolved in D07.

The printed C1–C16 do not explicitly enforce achievable access rate >= requested throughput. Our implementation enforces it in Stage II and monolithic models as a documented source-model completion (D10). Aggregate ISL bandwidth sharing is not silently added to the reference model; it is a separate possible extension after the source audit.

## 4. Units and radio

Use meters, seconds, bits, watts and hertz for physics. Convert configuration ms/Mbps/MIPS at boundaries using named functions. Store units in field names where a mixed-unit interface remains necessary.

- watts = 10 ** ((dBm - 30) / 10).
- linear antenna gain = 10 ** (dBi / 10).
- propagation seconds = path distance / c.
- minimum MIPS = demand_Mbps * instructions_per_bit.
- processing seconds = packet_bits * instructions_per_bit / (cpu_MIPS * 1e6).
- shared bandwidth = satellite_bandwidth / associated_user_count for positive count.
- received power uses paper equation 3, free-space distance loss and linear gains.
- noise = Boltzmann constant * temperature_K * shared_bandwidth_Hz.
- SINR = received_power / (noise + interference_power).
- rate_bps = bandwidth_Hz * log2(1 + SINR).
- access transmission seconds = packet_bits / rate_bps.

Selected per-packet interpretation: paper Lambda in serialization is interpreted as the same representative packet_bits used in processing, not bits generated during the window. Packets do not expand/shrink across functions in version 1; packet size is deterministic per slice, not a random distribution. Define distinct config fields psi_instructions_per_bit (throughput CPU) and omega_instructions_per_bit (packet processing); set psi=omega in the initial scenarios as an explicit assumption, not a recovered source identity. With different values, use psi for L and omega for A. At 2 Mbps over 60 seconds the generated load is 120 Mbit and takes 6 seconds at 20 Mbps; a 12000-bit packet takes 0.0006 seconds. Preserve this counterexample in the tests and report the per-packet interpretation.

Received power and interference are fixed snapshot inputs. Initial interference is zero. Decision-dependent interference is rejected by the config schema for the occupancy formulation; it requires a different model. Every active denominator is positive by declared bounds; invalid configurations fail early.

Selected exact occupancy formulation, with all indices specified:

- For every s, z[s,n] is binary for n=0..A_s; sum_n z[s,n]=1 and sum_n n*z[s,n]=sum_u alpha[u,s].
- For n>=1, precompute R[u,s,n] from the direct radio equation and fixed snapshot power/interference.
- For every visible (u,s) and n>=1, y[u,s,n]=AND(alpha[u,s],z[s,n]). Impose sum_(n>=1) y[u,s,n]=alpha[u,s] explicitly, so an assigned user cannot use zero occupancy.
- For every user u, **sum_(s,n>=1) y[u,s,n]*R[u,s,n] >= demand_bps[u]**.
- Access transmission delay for u is **sum_(s,n>=1) y[u,s,n]*packet_bits[u]/R[u,s,n]**.

Do not apply the ungated demand inequality separately to each candidate satellite. Unselected satellites provide zero service and impose no per-satellite demand obligation. Test a user with two visible candidates, positive/insufficient rates, n=0 and all valid occupancy values. Exactness depends on the stated exogenous radio inputs.

## 5. Exact processing-delay reformulation candidate

For one assignment let b=beta, G=cpu in MIPS, L=demand_Mbps*psi > 0, and A=packet_bits*omega/1e6. Given exact-one assignment and gating, an active assignment has G>=L.

Introduce q=G+L*(1-b), q>=L, t>=0 and t*q=A*b. If b=0, G=0, q=L and t=0. If b=1, q=G and t=A/G. Bound 0<=G<=C_s*b, 0<=t<=A/L, and **q<=C_s*b+L*(1-b)**; the global q upper bound is **max(C_s,L)**. Never use q<=C_s unconditionally. If C_s<L, the assignment can remain inactive with q=L while active use is impossible. The same holds for an unused zero-capacity satellite.

Required counterexample: C1=1000, L=1500, C2=2000 MIPS with zero overhead in this fixture; choosing host 2 must remain feasible despite inactive host 1. Repeat with C1=0. Overhead is enforced separately; any tighter candidate bound must have an explicit safe proof.

Verify this bilinear equality formulation with the SCIP backend smoke test and independent direct calculations. It is implemented and tested with tiny independent oracles and raw/decoded validation; this does not establish physical-scale runtime. Zero-demand requests require separate semantics and are initially rejected by config validation. Nonlinear objectives, if needed, are represented by an auxiliary objective variable and an appropriate constraint because solver interfaces can restrict objective types.

## 6. End-to-end delay

Version 1 ISLs are undirected, with reciprocal propagation costs; d[s,t]=d[t,s] applies only under this choice. Define reachable pairs R including (s,s), d[s,s]=0. Do not store infinity as a coefficient in solver expressions.

Let h[u,k,s]=host[u,k,s], E[u,t]=sum_g xi[u,t,g], K_u=number of stages. E is binary by the exact-one egress pair rule. Introduce:

- a[u,s,t]=AND(alpha[u,s],h[u,1,t]) for reachable access-to-first-host pairs;
- chi[u,k,s,t]=AND(h[u,k,s],h[u,k+1,t]) for internal pairs;
- e[u,s,t]=AND(h[u,K_u,s],E[u,t]) for last-host-to-egress pairs.

For each unreachable pair enforce respectively alpha[u,s]+h[u,1,t]<=1, h[u,k,s]+h[u,k+1,t]<=1, or h[u,K_u,s]+E[u,t]<=1. These constraints are required even though no linkage variable/delay coefficient is created for that pair. Add sum_(s,t in R) a=1, sum chi=1 per internal stage, and sum e=1 as explicit consistency constraints.

The full per-user propagation expression is:

`P_u = sum_s alpha[u,s]*d_user[u,s]`

`    + sum_(s,t in R) a[u,s,t]*d[s,t]`

`    + sum_(k=1..K_u-1,s,t in R) chi[u,k,s,t]*d[s,t]`

`    + sum_(s,t in R) e[u,s,t]*d[s,t]`

`    + sum_(s,g) xi[u,s,g]*d_ground[s,g]`.

E2E = P_u + sum_(k,i,s) t[u,k,i,s] + access_transmission[u]. Add separate negative fixtures for each of the three ISL-segment classes, plus legal multihop and colocation. Validator reconstructs these segments independently from chosen IDs. ISL/GS serialization, queueing, packet loss and physical state-transfer delay are not modeled. This reachable-pair interpretation is broader than a literal direct-neighbor interpretation and does not inherit the paper's complexity reduction claim.

## 7. Stability and objective definitions

Keep the previous committed deployment W_prev and visibility-repaired candidate W_repair separately. Metrics compare W_final with W_prev. Objective reference choice is recorded in D04.

Raw deviations are L1 differences of one-hot alpha, xi and beta arrays. Normalize by a fixed maximum: 2*number_of_users for alpha/xi and 2*number_of_user_chain_stages for beta, assuming exact-one assignments. Use the full logical domain including prior choices now unavailable. Do not let pruning change the denominator.

Hierarchical deviation H is the L1 difference between final alpha/xi and Stage I alpha_star/xi_star. Normalize the combined quantity by 4*number_of_users. Record this explicit interpretation since alternative component-wise normalization changes weight meaning.

Absolute epigraphs d>=x-ref and d>=ref-x are tight under a positive objective coefficient. If the coefficient is zero, do not report arbitrary auxiliary values as actual deviations; recompute differences directly. Apply this rule to all ablations.

Stage I contains corrected C1–C6 plus only objective/deviation constraints; occupancy and achievable-throughput constraints enter Stage II/full monolithic models. Stage I: at t=0 minimize access-plus-egress propagation. At later t minimize w_alpha*D_alpha + w_xi*D_xi using the documented temporal reference. Binary associations are retained unless an integral LP-equivalent formulation is proved.

Stage II: minimize w_H*H + w_beta*D_beta with all core constraints and associations still variable. First window has no previous placement; define D_beta=0. Full method/initialization/warm-start definitions are frozen in execution_contract.md. Independent no-stability baselines are descriptively labeled, never presented as recovered author objectives.

No secondary allocation objective is added in version 1. Use fixed model ordering, solver seed and one thread; retain the solver-selected tied optimum. This improves repeatability but is not a proof of unique allocation or cross-version determinism. RL observations therefore do not use arbitrary optimized CPU or slack. Action-sensitivity claims must separate true objective trade-offs from ties and budget effects.

## 8. Solver outcomes and independent validation

WindowResult contains separate StageResult records for Stage I and Stage II (or monolithic), including objective identifier, status, incumbent, primal/dual bounds, absolute and relative gaps, timings, model counts, parameters and validation. Preserve joint window deadline and start-submission diagnostics. Never combine bounds from different stage objectives into one gap. See execution_contract.md for the budget/state machine.

Classify: proven optimal within solver tolerances, feasible non-optimal incumbent, proven infeasible, unbounded/model error, stopped without incumbent, numerical/validation failure. Never access solution values when no incumbent exists. Never convert time limit into infeasibility. Never round fractional/nonintegral output silently into feasibility.

Validator inputs are plain exported records, config and trace. Recompute sums, activation, capacities, links, delays and deviation components independently; return residuals with IDs and tolerance-normalized violations. Preserve raw values. Display units and tolerances in reports.

Reject NaN/Infinity and unknown/missing IDs before comparisons; NaN must not escape validation through false comparisons. Numerical scaling, reciprocal error propagation, summed delay acceptance, resource tolerances and zero-objective gaps are specified in execution_contract.md. These remain the acceptance thresholds. Tiny backend calibration and independent validation fixtures have executed; physical-scale capability is not inferred from them.

## 9. RL contract

Action chooses rho=w_beta/w_H from five configured values, w_H=1. It does not set the evaluation reward. Observation formulas, timing, horizon, bins, unseen-state and Q-tie policy are specified in experiment_contract.md. Observations use allocation-independent resource-demand bounds rather than optimized CPU/slack from a non-unique solution.

For success, reward=-c_t where c_t=D_alpha(actual)+D_xi(actual)+D_beta(actual) in [0,3]; first-window setup has c=0. If a deployable solution is unavailable with R>=1 windows remaining including this window, terminate with **reward=-4*sum_(j=0..R-1) discount^j**. For discount=1 use -4R. This represents an absorbing discounted failure tail and is strictly worse than any fully successful tail bounded below by -3 times the same sum. Remove the previous fixed -10 penalty. Test R=1,2,14 and discount=0,0.95,1. Runtime timeout and proven infeasibility are different recorded failure causes. A programming exception, corrupted/nonfinite output or infrastructure error aborts the training run as an error; it is not learned from as a valid network transition.

An episode is a sequence of immutable topology snapshots. A successful step commits the validated deployment. No-valid-deployment is an explicit terminal failure in the initial training mode. Finite 14-window episodes are terminal at horizon unless a separate continuing-process truncation mode is configured; test bootstrapping accordingly. Underlying model guarantees only accepted-deployment feasibility, not that every episode can succeed.

Q-learning update: Q(s,a) += lr*(r + discount*max Q(next) - Q(s,a)); omit next-state term on termination. Freeze exploration and updates during evaluation. Hyperparameter starting points lr=0.1, discount=0.95, epsilon 1.0 to 0.05 are proposals to tune on validation data. Model selection never reads test rewards.

Acceptance and scoring details: execution_contract.md §8 governs raw/decoded validation and all-candidate processing error; experiment_contract.md §7 defines episode-origin discounting. These are required parts of the model implementation contract.
