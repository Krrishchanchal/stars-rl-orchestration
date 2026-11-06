# Independent oracle and fixture catalog

Current independent constructions and expected derivations. Executed fixture evidence is indexed by [test_matrix.csv](test_matrix.csv) and [EVIDENCE.md](../EVIDENCE.md); a construction written here alone is not a test result. Same-helper comparisons establish consistency only. Constructed action regimes do not establish representative physical usefulness.

## O-CONSTRAINT / F-C01 through F-C26

Each constraint gets a satisfiable case, boundary case and candidate violating that rule while others have slack. Fix offending choices in negative solver tests so the optimizer cannot evade the intended case. Store expected residuals by hand. C17–C26 use the four binary input combinations and explicit absolute differences. Zero-weight epigraphs cannot be assumed tight.

| Fixture | Independent condition |
|---|---|
| F-C01 | Association count exactly 1; 0 and 2 invalid |
| F-C02 | Selected invisible edge invalid; unselected invisible edge harmless |
| F-C03 | Access count at capacity valid; capacity+1 invalid |
| F-C04 | One egress pair over all satellites/GSs; literal per-satellite counterexample |
| F-C05 | Selected egress pair visible |
| F-C06 | Egress count within its separate pool |
| F-C07 | One compatible instance per chain stage |
| F-C08 | Positive assignment count requires activation |
| F-C09 | Unused instance inactive |
| F-C10/F-C11 | Linkage bounded by each endpoint |
| F-C12 | Both endpoints imply linkage |
| F-C13 | Allocated MIPS >= demand*psi |
| F-C14 | CPU plus overhead paid once per instance <= capacity |
| F-C15 | Active-instance count within limit |
| F-C16 | All propagation/processing/serialization terms within delay |
| F-C17/F-C18 | Positive/negative access temporal deviations |
| F-C19/F-C20 | Positive/negative gateway temporal deviations |
| F-C21/F-C22 | Positive/negative Stage I access deviations |
| F-C23/F-C24 | Gateway hierarchical deviations with correct xi indices |
| F-C25/F-C26 | Placement temporal deviations |

Discrete oracle enumerates tiny assignments without production builders; AND oracle is its four-row truth table. A local nonlinear solve is not a global oracle.

## O-QBOUND / F-UNDERSIZED and F-ZEROHOST

L=1500 MIPS, C1=1000,C2=2000, zero overhead. Select host 2: inactive host1 has b1=0,G1=0,q1=1500. Conditional upper q1<=C1*b1+L*(1-b1)=1500 holds; unconditional q1<=1000 falsely fails. Repeat C1=0. Selecting host1 actively must fail. Test scaled and unscaled forms. A>0 is fixed independently.

## O-RADIOSELECT / F-TWOCANDIDATES

One user, two visible hosts, each with enough fixed lookup rate. Select host1; all y on host2 are zero. User-level sum_(s,n) yR meets demand, while an ungated per-host demand rule would falsely reject host2. Repeat host2 selected and both rates insufficient. Enumerate occupancy 0..A; alpha=1 must exclude n=0. Physical rates are separately checked against hand-evaluated Shannon calculations. Decision-dependent interference configs must be rejected.

## O-PACKET and O-COEFF

2 Mbps * 60 s=120000000 bits; at 20 Mbps serialization is 6 s. A 12000-bit packet serializes in 0.0006 s. This distinguishes semantics, not merely units.

Demand 2 Mbps, psi=10 gives 20 MIPS. With omega=20 and 12000 bits, processing at 20 MIPS is 12000*20/(20e6)=0.012 s. This catches conflating psi and omega. Also test the selected equal-coefficient scenario.

## O-ENDACCESS, O-ENDINTERNAL, O-ENDEGRESS

Three isolated disconnections: (1) fixed visible access in component A, first host and all later elements in B; (2) access/first host in A, next host/egress in B; (3) access/all hosts in A, fixed visible egress/GS in B. Only the named ISL segment is invalid. Each must be rejected inside the optimizer. Positive variants add one bridge with hand-summed distance. Colocation is valid with zero internal propagation.

## O-ALLOC2 / F-TWOCPU and F-LOWERBOUND

For fixed active stages minimize A1/G1+A2/G2 with G1+G2<=C and positive G. With inactive lower bounds, convexity and Cauchy-Schwarz give G_i=C*sqrt(A_i)/(sqrt(A1)+sqrt(A2)), optimum (sqrt(A1)+sqrt(A2))^2/C.

A1=1,A2=4,C=9 yields G=(3,6), objective 1. With G1>=4,G2>=1, optimum is (4,5), value 1/4+4/5=1.05. Sum of lower bounds>C is infeasible. These are declared algebraic backend fixtures, not physical samples. Do not apply the inactive-bound formula when a bound is active.

## O-FAILRETURN

Successful per-step cost in [0,3], R>=1 remaining windows, gamma in [0,1]. Let S_R=sum_(j=0..R-1) gamma^j. Worst successful tail reward is -3*S_R; selected failure reward -4*S_R is strictly smaller. Test R=1,2,14 and gamma=0,0.95,1, and terminal no-bootstrap updates. Keep a regression showing why the former fixed -10 fails for long horizons. This verifies incentive design, not learned success.

## O-RATIO and O-MULTISTEP

If Stage I associations equal the previous committed ones, H=(D_a+D_x)/2 and rho=0.5 yields c/2. Verify exact binary examples. The two-regime target table in experiment_contract.md must be realized through actual validated topology/delay/resources: a payoff table alone is not a STARS solver oracle. Require positive objective margins under low/high rho, and differing future costs. Tied returned incumbents do not establish action sensitivity.

## O-CAPBOUND

Theta=acos(R/(R+h)*cos(e))-e. Regular plane spacing is 2*pi/15; maximum visible arc <=2*theta. Count bound floor(2*theta/(2*pi/15))+1, with boundary tolerance. R=6371 km,h=500 km,e=10 degrees gives two per plane and eight across four. Also test e=90 (zero cap) and e=0 (tangent cap). This is conditional on the regular geometry, not a universal constellation bound. Add independent orbital radius/period and Earth-occlusion examples.

## O-SCALE and O-ZEROGAP

Generate known residuals using the exact error identity in execution_contract.md. Sweep supported demands, psi/omega, packets, CPU and 1–4 stages. Include small individual errors whose aggregate exceeds C16 allowance. Check original A/G independently. Zero objective with primal=dual=0 has absolute gap zero; undefined relative gap is not replaced with a fabricated number. Add near-zero objectives and bounds with different signs.

## O-STAGES, O-START and O-GWPAIR

Backend fakes deterministically cover stage statuses/deadlines. Real tiny solves cover numerical feasible/infeasible behavior. Valid nonoptimal Stage I can proceed; no incumbent cannot; late Stage II cannot deploy on time. Bounds remain per objective.

Change visibility/occupancy to make copied y/q/t stale. Complete starts rebuild; partial starts keep unknown fields unknown. A valid start not stored is not necessarily infeasible. Gateway cases cover retaining pair, replacing only GS, replacing satellite and GS, and no visible pair. Repair candidates need not satisfy capacity.

## O-SPLIT, O-BOUNDARY and O-CROSS

Identical exogenous traces under different seed labels must fail cross-split content checks. Overlapping intervals and perturbed derivatives of one root must also fail lineage-group checks, even with different hashes.

Interrupt a training episode, restore the prior boundary Q/RNG/order/schedule state and replay; partial updates/logs are abandoned. Controlled fake transitions must reproduce continuation; no cross-machine time-limited solver exactness claim.

Crossed-statistic toy: K=2,M=2 paired differences [[1,3],[5,7]], equal-weight mean Delta=4. Multiple episodes within a group are averaged before equal weighting across groups. Bootstrap row and column IDs independently, preserving their Cartesian grid and baseline column pairing. Test degenerate counts and early-failure score accounting. Small fixtures verify arithmetic, not inferential strength.

## O-DATA and O-REPRO

Reject NaN/Infinity before comparisons, unknown/duplicate IDs, missing stages, incompatible types, repeated types in version 1, invalid activation bounds and instance identity collisions. Mutate one property of an otherwise valid fixture at a time.

Fresh installation uses pinned build/runtime toolchains, wheel-only dependencies and editable install with --no-build-isolation. Preserve transcript, versions and source-tree hash; no untracked modules or stale notebook state. These are tests to run later, not evidence already obtained.

## O-UNITS, O-TRACE, O-METRIC and O-OBJECTIVE

O-UNITS: derive 20 dBm=10^((20-30)/10)=0.1 W and 300000 m/c seconds directly; compare typed constants and dimensions without importing conversion helpers. Other packet/CPU cases use O-PACKET/O-COEFF.

O-TRACE: fixed toy-v1 has no sampling; compare serialized exogenous arrays against the declared values. Seeded cases use independently saved expected input tables. Hash rules exclude arbitrary labels but include actual physical inputs. These tests verify deterministic generation, not physical realism.

O-METRIC: manually change one of two users' one-hot access choices; L1=2, normalized D_a=2/(2*2)=0.5 and event count=1. Initial setup has zero changes. Two stage assignments changing host give two events; a same-host instance-ID change contributes beta change but not host migration. Missing/unattempted outcomes remain null.

O-OBJECTIVE: enumerate tiny feasible deployments, compute H,D_a,D_x,D_b,Q directly from hand-labeled arrays and delays, and compare each method's objective/initialization policy with execution_contract.md. Do not call production objective builders. Positive scaling preserves optima but adding secondary terms may not; tied optimal variable arrays need not be identical.

## O-QUPDATE, O-OBS and O-COUNT

O-QUPDATE: Q=2,lr=0.1,r=3,gamma=0.95,next_max=4 gives target 6.8 and updated Q=2.48; terminal update gives Q=2.1. Evaluation must preserve Q and disable exploration. Unseen-state and tie selection follow the declared rho=0.5 preference.

O-OBS: compute each state feature from a saved pre-action topology and discrete deployment using the formulas in experiment_contract.md. Change only allocated CPU among otherwise identical feasible optima: state must remain unchanged. Change R alone: state must change. Test initialization, next-window visibility and no future-demand access, plus exact bin boundaries and zero-capacity sentinel.

O-COUNT: for fully reachable S satellites, U users, K stages, internal links U*(K-1)*S^2 and endpoint links 2*U*S^2 before safe filtering. Hand-check counts at S=2,U=1,K=2; inspect exported builder counts and count only actually instantiated variables. Model-size equality is not a performance claim; measure peak memory/runtime separately.

Fixture naming convention: rows without a special case name use F- followed by the test suffix and instantiate the oracle's explicit cases. A fixture metadata file will record exact inputs and independent expected values when that test is implemented. No row is PASS on the strength of this naming convention.

## Additional independent oracles

**O-INACTIVEPROC** (R1-01): 476 inactive terms, each tau=1e-9 and A/L=0.108 seconds, contribute 5.1408e-8 seconds even if every selected term is exact. The half-budget check must reject. Also test zero inactive terms, many smaller terms below budget, and mixed active/inactive contributions individually below but jointly above budget. Preserve raw binary/product checks; do not obtain expected delay by calling the production reconstruction helper.

**O-ST2-RESCUE** (R1-02): hand-authored algebraic trace, not an orbital realization. One user, one function, visible access a/b, sole egress satellite x, sole CPU host x. User access propagation a=1 ms,b=2 ms; egress propagation=1 ms; shortest ISL paths a-x=20 ms,b-x=1 ms. Stage I propagation uniquely selects a. Any deployment fixing a has propagation alone >=22 ms, violating D=10 ms. Host x capacity100 MIPS, zero overhead, demand2 Mbps, psi=omega10, packet12000 bits: choose G=100, L=20, processing=1.2 ms. Both access rate coefficients are 12 Mbps (serialization1 ms), with capacity1 pools and one instance. Access b gives 2+1+1+1.2+1=6.2 ms and a valid solution. a/b have zero CPU. This weighted connectivity/radio coefficient fixture tests the optimization model; it makes no Euclidean/orbital claim. Independently enumerate the two access choices. Fixed-a full model must be infeasible; soft Stage II must change to b and validate. This oracle is separate from O-MULTISTEP.

**O-ST1SCOPE** (R2-03): a separate authored coefficient fixture has unique low-propagation access a, demand2 Mbps, occupancy-one rates a=1 Mbps and b=12 Mbps; generous complete delay/resource limits permit b. Stage I must still select a, and full Stage II must select b. Verify Stage I row/variable families contain corrected C1–C6 and objective/deviation rows only, no radio occupancy/throughput constraints. Rates are declared synthetic inputs for this algebraic test, not outputs of the physical radio generator.

**O-SCOREDISCOUNT** (R1-03): T=3,gamma=0.5,c=[0,1,2] gives successful J=1. Failure at f=0 gives7; f=1 with c0=0 gives3; f=2 with c0=0,c1=1 gives1.5. Verify J equals negative discounted transition rewards, including the initial window, and gamma=0/1 endpoints. Derive expected constants manually.

**O-REGIONCAP / O-MATCHING** (R2-01): independently calculate plane-normal distances and conservative cap bound in experiment_contract §9. Matching fixtures enumerate assignments directly, not via the production max-flow helper: three users all see only s0 with capacity2, while invisible s1 has capacity2; total capacity4>=3 yet only2 served. Also all-served, zero-edge and two-GS-one-satellite cases (capacity is counted once), for both independent pools. A successful matching is necessary, never sufficient for full deployment.

**O-DRAWSCOPE** (R2-02): hand-author two slices with two users each and different chain/demand/delay triples; assert shared values within each slice, no forced equality between slices, and unchanged values across windows. Two hosts and instance IDs of a type share its coefficient/overhead draw; charging remains per active instance. Explicitly test separate access5/egress5 pools and per-user demand accounting. Later save a generated trace with independently checked exact inputs and RNG metadata.

**O-OBSREGIME** (R2-04): for realized O-MULTISTEP fixtures hand-compute every field of both pre-action observation tuples. Require different tuples for the learnable-regime claim, positive short-horizon return margins by exhaustive sequence enumeration, and a separate same-tuple/different-best-action counterexample. Do not claim these fixtures are already realizable or solved. If realization fails, block C15 sensitivity acceptance and revise transparently; no invented RL benefit.

**O-RESIDUALFAMILY** (R2-05): independently inject 0.5x/2x each execution_contract §8 threshold; check original units and normalized violations. Include throughput deficits, raw near-binary values, inconsistent occupancy/product records, aggregate inactive delay, zero-capacity gates, and nonfinite values. Expected acceptance requires all families simultaneously; an inside-threshold row may not excuse a different violated row.

**O-INITIALCHECKPOINT**: interrupt a deterministic fake training environment during episode0; restore the pre-episode0 checkpoint and replay. Compare Q, RNG, ordering, counters and logs against uninterrupted execution. This checks restart logic, not reproducibility of time-limited solver incumbents across machines.
