"""C07 draft full-feasible-set builder and lossless plain-data candidate export.

No deployment is approved here. C08 independent validation is mandatory.
"""
from dataclasses import dataclass, asdict
import time

from pyscipopt import Model

from stars_rl.config import deployment_to_dict
from stars_rl.models import Scenario, Deployment, AccessChoice, EgressChoice, StageAllocation, InstanceKey, validate_deployment_structure
from stars_rl.physics.units import _finite
from stars_rl.topology.trace import NetworkWindow
from .constraints import build_discrete_model
from .variables import DiscreteVariables, check_inputs, decode_binary
from .resources import ResourceVariables, add_resource_constraints
from .radio import RadioVariables, add_radio_constraints
from .delay import DelayExpressions, add_delay_constraints
from .result import StageResult


LINK_VARIABLE_LIMIT=250000
MEMORY_BUDGET_BYTES=2*1024**3


class ModelSizeLimitError(ValueError):
    pass


def check_model_size(estimated_links: int, *, allow_large_model: bool=False,
                      measured_memory_forecast_bytes: int | None=None) -> None:
    if type(estimated_links) is not int or estimated_links<0:
        raise ValueError("estimated link count must be a nonnegative integer")
    if type(allow_large_model) is not bool:
        raise ValueError("allow_large_model must be boolean")
    if measured_memory_forecast_bytes is not None:
        if type(measured_memory_forecast_bytes) is not int or measured_memory_forecast_bytes<=0:
            raise ValueError("memory forecast must be positive integer bytes")
        if measured_memory_forecast_bytes>MEMORY_BUDGET_BYTES:
            raise ModelSizeLimitError("measured memory forecast exceeds the initial 2 GiB budget")
    if estimated_links>LINK_VARIABLE_LIMIT and not (allow_large_model and measured_memory_forecast_bytes is not None):
        raise ModelSizeLimitError("large model requires explicit opt-in and a measured memory forecast")


@dataclass
class FullVariables:
    discrete: DiscreteVariables
    resources: ResourceVariables
    radio: RadioVariables
    delay: DelayExpressions
    diagnostics: dict


def _diagnostics(model,resources,estimated_links,started):
    coefficients=[];linear_rows=0
    for row in model.getConss():
        if row.getConshdlrName()=="linear":
            linear_rows+=1
            coefficients.extend(x for x in model.getValsLinear(row).values() if x!=0)
    # Only nonlinear rows are the dimensionless tau*qhat-beta equalities;
    # both the bilinear and linear monomial coefficients have magnitude1.
    coefficients.extend([1,-1]*len(resources.terms))
    bounds=[(v.getLbOriginal(),v.getUbOriginal()) for v in model.getVars()]
    return {"build_wall_seconds":time.perf_counter()-started,
        "estimated_link_variables":estimated_links,"generated_variables":model.getNVars(),
        "generated_constraints":model.getNConss(),"linear_rows":linear_rows,
        "nonlinear_reciprocal_rows":len(resources.terms),
        "coefficient_summary":{"minimum_nonzero_magnitude":min(abs(x) for x in coefficients),
            "maximum_magnitude":max(abs(x) for x in coefficients),"signed_minimum":min(coefficients),"signed_maximum":max(coefficients)},
        "bound_summary":{"minimum_lower":min(a for a,b in bounds),"maximum_upper":max(b for a,b in bounds)},
        "minimum_cpu_row_scale_mips":resources.minimum_row_scale_mips,
        "cpu_row_scales_mips":resources.cpu_row_scales_mips,
        "processing_scales":[{"key":list(key),"required_mips":t.required_mips,"amplitude":t.amplitude,
            "time_scale_seconds":t.time_scale_seconds,"capacity_mips":t.capacity_mips,
            "g_upper":t.capacity_mips/t.required_mips,"qhat_upper":max(t.capacity_mips/t.required_mips,1),"tau_upper":1}
            for key,t in resources.terms.items()]}


def build_full_model(scenario: Scenario, window: NetworkWindow, *, radio_coefficients: dict | None=None,
                       allow_large_model: bool=False, measured_memory_forecast_bytes: int | None=None) -> tuple[Model,FullVariables]:
    """Constant feasibility objective; later method objectives attach to this set."""
    started=time.perf_counter();check_inputs(scenario,window)
    reachable=sum(p is not None for p in window.paths.entries)
    estimate=reachable*sum(len(scenario.slice_for_user(u).chain)+1 for u in window.user_ids)
    check_model_size(estimate,allow_large_model=allow_large_model,measured_memory_forecast_bytes=measured_memory_forecast_bytes)
    model,discrete=build_discrete_model(scenario,window)
    resources=add_resource_constraints(model,scenario,window,discrete)
    radio=add_radio_constraints(model,scenario,window,discrete,radio_coefficients=radio_coefficients)
    delay=add_delay_constraints(model,scenario,window,discrete,resources,radio)
    diagnostics=_diagnostics(model,resources,estimate,started)
    diagnostics.update(rate_provenance=radio.rate_provenance,large_model_opt_in=allow_large_model,
                       measured_memory_forecast_bytes=measured_memory_forecast_bytes)
    return model,FullVariables(discrete,resources,radio,delay,diagnostics)


def export_solution(model: Model, scenario: Scenario, window: NetworkWindow,
                      variables: FullVariables, result: StageResult) -> dict:
    """Preserve raw plus decoded/original-unit values; no feasibility certificate."""
    out={"export_schema_version":1,"scenario_id":scenario.scenario_id,"window_index":window.window_index,
         "validation":"not_run","solver_result":asdict(result),"diagnostics":variables.diagnostics,"candidate":None}
    if not result.has_incumbent:
        return out
    raw=result.values
    for key,value in raw.items():_finite(value,key)
    sol=model.getBestSol()
    if sol is None:
        raise ValueError("result claims an incumbent but model has no stored solution")
    registered={variable.name:variable for variable in model.getVars()}
    if raw.keys()!=registered.keys():
        raise ValueError("raw result variable domain differs from model snapshot")
    if any(raw[key]!=model.getSolVal(sol,variable) for key,variable in registered.items()):
        raise ValueError("raw result differs from the stored model solution snapshot")
    def value(variable):
        if variable.name not in raw:raise ValueError(f"missing exported raw variable: {variable.name}")
        return raw[variable.name]
    def evaluated(expression):return _finite(model.getSolVal(sol,expression),"encoded expression")
    assignments=[];allocations=[]
    for key,term in variables.resources.terms.items():
        u,k,f,i,s=key;b=value(variables.discrete.beta[key]);bit=decode_binary(b)
        g=value(term.g);q=value(term.qhat);tau=value(term.tau)
        cpu=_finite(g*term.required_mips,"cpu_mips")
        assignment={"user_id":u,"stage_index":k,"function_type_id":f,"instance_id":i,"satellite_id":s,
            "beta_raw":b,"beta_decoded":bit,"g":g,"qhat":q,"tau":tau,"cpu_mips":cpu,
            "q_mips":_finite(q*term.required_mips,"q_mips"),
            "processing_seconds":_finite(tau*term.time_scale_seconds,"processing_seconds"),
            "required_mips":term.required_mips,"amplitude":term.amplitude,"time_scale_seconds":term.time_scale_seconds}
        assignments.append(assignment)
        if bit:allocations.append(StageAllocation(u,k,InstanceKey(f,i,s),cpu))
    access=tuple(AccessChoice(u,s) for (u,s),x in variables.discrete.alpha.items() if decode_binary(value(x)))
    egress=tuple(EgressChoice(u,s,g) for (u,s,g),x in variables.discrete.xi.items() if decode_binary(value(x)))
    deployment=Deployment(window.window_index,access,egress,tuple(allocations))
    validate_deployment_structure(deployment,scenario)
    users={u:{"propagation_components":{k:evaluated(x) for k,x in variables.delay.propagation_components[u].items()},
               "processing_seconds":evaluated(variables.delay.processing_seconds[u]),
               "access_transmission_seconds":evaluated(variables.radio.transmission_seconds[u]),
               "total_delay_seconds":evaluated(variables.delay.total_seconds[u]),
               "achieved_rate_bps":evaluated(variables.radio.achieved_rate_bps[u])} for u in window.user_ids}
    out["candidate"]={"deployment":deployment_to_dict(deployment),"assignments":assignments,"users":users,
        "activations":[{"function_type_id":f,"instance_id":i,"satellite_id":s,"raw":value(x),"decoded":decode_binary(value(x))}
                       for (f,i,s),x in variables.discrete.active.items()],
        "occupancy":[{"satellite_id":s,"occupancy":n,"raw":value(x),"decoded":decode_binary(value(x))}
                     for (s,n),x in variables.radio.z.items()],
        "radio_products":[{"user_id":u,"satellite_id":s,"occupancy":n,"raw":value(x),"decoded":decode_binary(value(x)),
                           "rate_coefficient_bps":variables.radio.rates[(u,s,n)]} for (u,s,n),x in variables.radio.y.items()]}
    return out
