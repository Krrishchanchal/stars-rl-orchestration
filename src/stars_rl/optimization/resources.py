"""Continuous CPU and dimensionless activation-aware processing (C07 draft)."""
from dataclasses import dataclass

from pyscipopt import Model, Variable, Expr, quicksum

from stars_rl.models import Scenario
from stars_rl.physics.units import _positive, _nonnegative
from stars_rl.topology.trace import NetworkWindow
from .variables import DiscreteVariables, name


@dataclass
class ProcessingTerm:
    required_mips: float
    amplitude: float  # packet_bits*omega/1e6, seconds*MIPS
    capacity_mips: float
    g: Variable
    qhat: Variable
    tau: Variable

    @property
    def time_scale_seconds(self) -> float:
        return self.amplitude/self.required_mips

    @property
    def cpu_mips(self) -> Expr:
        return self.required_mips*self.g

    @property
    def processing_seconds(self) -> Expr:
        return self.time_scale_seconds*self.tau


def add_processing_term(model: Model, beta: Variable, required_mips: float, amplitude: float,
                         capacity_mips: float, key: tuple) -> ProcessingTerm:
    """Exact scaled formulation; also used by explicitly algebraic oracle fixtures."""
    required=_positive(required_mips,"required_mips")
    a=_positive(amplitude,"amplitude")
    capacity=_nonnegative(capacity_mips,"capacity_mips")
    ratio=capacity/required
    _nonnegative(ratio,"capacity_ratio")
    _positive(a/required,"processing_time_scale")
    g=model.addVar(name("g",*key),lb=0,ub=ratio,vtype="C")
    qhat=model.addVar(name("qhat",*key),lb=1,ub=max(ratio,1),vtype="C")
    tau=model.addVar(name("tau",*key),lb=0,ub=1,vtype="C")
    # CPU row scaled by max(C_s,1 MIPS), including the zero-capacity case.
    divisor=max(capacity,1)
    model.addCons(required/divisor*g<=capacity/divisor*beta,name=name("CPU_gate",*key))
    model.addCons(qhat==g+1-beta,name=name("Q_definition",*key))
    # Never use the host ratio as an unconditional qhat upper bound.
    model.addCons(qhat<=ratio*beta+1-beta,name=name("Q_conditional_bound",*key))
    model.addCons(tau*qhat==beta,name=name("PROC_reciprocal",*key))
    return ProcessingTerm(required,a,capacity,g,qhat,tau)


@dataclass
class ResourceVariables:
    terms: dict[tuple,ProcessingTerm]
    cpu_mips: dict[tuple,Expr]
    processing_seconds: dict[tuple,Expr]
    cpu_row_scales_mips: dict[str,float]
    minimum_row_scale_mips: float


def add_resource_constraints(model: Model, scenario: Scenario, window: NetworkWindow,
                              discrete: DiscreteVariables) -> ResourceVariables:
    functions={f.id:f for f in scenario.function_types}
    capacities={s.id:s.cpu_capacity_mips for s in scenario.satellites}
    terms={}
    for key,beta in discrete.beta.items():
        u,k,f,i,s=key
        request=scenario.slice_for_user(u)
        required=request.demand_mbps*functions[f].psi_instructions_per_bit
        amplitude=request.packet_bits*functions[f].omega_instructions_per_bit/1e6
        terms[key]=add_processing_term(model,beta,required,amplitude,capacities[s],key)
    cpu={key:t.cpu_mips for key,t in terms.items()}
    delay={key:t.processing_seconds for key,t in terms.items()}
    # C13 spans hosts; use the largest host scale. Individual gates/C14 use
    # their own max(C_s,1) scale. Original-unit residuals remain a C08 check.
    minimum_scale=max(1,*capacities.values())
    for u in window.user_ids:
        for k,f in enumerate(scenario.slice_for_user(u).chain):
            required=scenario.slice_for_user(u).demand_mbps*functions[f].psi_instructions_per_bit
            model.addCons(quicksum(x/minimum_scale for (user,stage,ft,i,s),x in cpu.items()
                                   if (user,stage)==(u,k))>=required/minimum_scale,
                          name=name("C13_minimum_cpu",u,k))
    scales={s:max(c,1) for s,c in capacities.items()}
    for sat in sorted(scenario.satellites,key=lambda x:x.id):
        allocation=quicksum(x for (u,k,f,i,s),x in cpu.items() if s==sat.id)
        overhead=quicksum(functions[f].base_overhead_mips*x for (f,i,s),x in discrete.active.items() if s==sat.id)
        model.addCons((allocation+overhead)/scales[sat.id]<=sat.cpu_capacity_mips/scales[sat.id],
                      name=name("C14_cpu_capacity",sat.id))
        model.addCons(quicksum(x for (f,i,s),x in discrete.active.items() if s==sat.id)<=sat.max_active_instances,
                      name=name("C15_active_instance_limit",sat.id))
    return ResourceVariables(terms,cpu,delay,scales,minimum_scale)
