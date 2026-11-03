"""Full Stage II model with soft hierarchy and temporal placement preferences."""
from dataclasses import dataclass, field
import math
import time

from pyscipopt import quicksum
from stars_rl.config import deployment_from_dict
from stars_rl.models import validate_deployment_structure
from stars_rl.validation.stage2 import validate_reference, validate_stage2
from .backend import solve, submit_start
from .monolithic import build_full_model, export_solution
from .objectives import association_deviations, add_absolute_deviation, weights_checked
from .result import StageResult
from .variables import name


@dataclass
class Stage2Variables:
    full: object
    h_alpha: dict
    h_xi: dict
    d_beta: dict
    stage1_reference: object
    original_previous: object
    weights: tuple


def build_stage2_model(scenario, window, reference, previous=None, *, weights=(1,1),
                       radio_coefficients=None, deadline=None, clock=time.perf_counter,
                       allow_large_model=False, measured_memory_forecast_bytes=None):
    weights = weights_checked(weights)
    validate_reference(scenario,window,reference)
    if previous is not None:
        validate_deployment_structure(previous,scenario)
        if previous.window_index >= window.window_index:
            raise ValueError('previous deployment must precede current window')
    elif window.window_index > 0 and weights[1] > 0:
        raise ValueError('temporal placement objective requires previous deployment')
    if deadline is not None and clock() >= deadline:
        raise TimeoutError('stage2_deadline_before_full_build')
    model, full = build_full_model(scenario,window,radio_coefficients=radio_coefficients,
        allow_large_model=allow_large_model,measured_memory_forecast_bytes=measured_memory_forecast_bytes)
    base_size = {'variables':model.getNVars(),'constraints':model.getNConss()}
    ha,hx = association_deviations(model,scenario,window,full.discrete.association,reference,prefixes=('h_alpha','h_xi'))
    db = {}
    if previous is not None:
        old = {(a.user_id,a.stage_index,*a.instance.identity) for a in previous.allocations}
        db = {k:add_absolute_deviation(model,b,int(k in old),variable_name=name('d_beta',*k))
              for k,b in full.discrete.beta.items()}
    users = len(scenario.users)
    stages = sum(len(scenario.slice_for_user(u.id).chain) for u in scenario.users)
    h = (quicksum(ha.values())+quicksum(hx.values()))/(4*users)
    beta = quicksum(db.values())/(2*stages)
    model.setObjective(weights[0]*h+weights[1]*beta,'minimize')
    full.diagnostics.update(base_full_model_size=base_size,
        stage2_model_size={'variables':model.getNVars(),'constraints':model.getNConss()},
        generated_variables=model.getNVars(),generated_constraints=model.getNConss(),
        coefficient_summary_scope='base_full_feasibility_rows; added deviation coefficients +/-1',
        stage2_objective={'weights':list(weights),'H_denominator':4*users,'D_beta_denominator':2*stages,
                          'initial_placement_zero':previous is None})
    return model,Stage2Variables(full,ha,hx,db,reference,previous,weights)


def partial_stage2_start(variables):
    """Current Stage I associations and compatible previous placements only."""
    ref = variables.stage1_reference
    a = {(x.user_id,x.satellite_id) for x in ref.access}
    x = {(c.user_id,c.satellite_id,c.ground_station_id) for c in ref.egress}
    v = variables.full.discrete
    values = {b.name:float(k in a) for k,b in v.alpha.items()}
    values.update({b.name:float(k in x) for k,b in v.xi.items()})
    if variables.original_previous is not None:
        old = {(c.user_id,c.stage_index,*c.instance.identity) for c in variables.original_previous.allocations}
        values.update({b.name:float(k in old) for k,b in v.beta.items()})
    return values


@dataclass
class Stage2Outcome:
    status: str
    reason: str
    stage_result: StageResult
    final_deployment: object = None
    export: dict | None = None
    validation: dict = field(default_factory=dict)
    start: object = None
    total_budget_seconds: float = 10
    solve_cutoff_seconds: float = 9.5
    elapsed_seconds: float = 0


def run_stage2(scenario, window, stage1_outcome, previous=None, *, started_at,
               total_budget_seconds=10, weights=(1,1), radio_coefficients=None,
               warm=True, start_values=None, start_kind='partial', clock=time.perf_counter, solve_fn=solve):
    """Use the shared window clock; solve until .95B, check until B.

    Returns a validated candidate; committing state belongs to C12 orchestration.
    Builds/checks are not preempted; any overrun withholds final_deployment.
    """
    if type(total_budget_seconds) not in (int,float) or not math.isfinite(total_budget_seconds) or total_budget_seconds <= 0:
        raise ValueError('positive finite window budget required')
    now = clock()
    if not math.isfinite(started_at) or started_at > now:
        raise ValueError('invalid shared window start time')
    cutoff = started_at+.95*total_budget_seconds
    deadline = started_at+total_budget_seconds
    out = Stage2Outcome('stage2_no_deployment','not_attempted',
        StageResult('stage2','hierarchy_and_placement','dimensionless'),
        total_budget_seconds=total_budget_seconds,solve_cutoff_seconds=.95*total_budget_seconds)
    def finish(reason,valid=False):
        out.elapsed_seconds = max(0,clock()-started_at)
        out.stage_result.timings['window_elapsed_seconds'] = out.elapsed_seconds
        out.reason = reason
        if out.elapsed_seconds > total_budget_seconds:
            out.status='late';out.reason='window_deadline_exceeded';out.final_deployment=None
        elif valid:out.status='validated'
        return out
    if (stage1_outcome.status != 'reference_ready' or stage1_outcome.stage1_reference is None
            or stage1_outcome.stage_result.validation != 'valid' or not stage1_outcome.validation.get('valid')):
        return finish('stage1_no_reference:'+stage1_outcome.reason)
    build_start = clock()
    if build_start >= cutoff:return finish('deadline_before_build')
    try:
        model,v = build_stage2_model(scenario,window,stage1_outcome.stage1_reference,previous,weights=weights,
                                     radio_coefficients=radio_coefficients,deadline=cutoff,clock=clock)
    except TimeoutError as exc:return finish(str(exc))
    build_seconds = clock()-build_start
    if clock() >= cutoff:return finish('deadline_after_build')
    start_begin=clock()
    if start_begin >= cutoff:return finish('deadline_before_start')
    if warm:
        values=partial_stage2_start(v) if start_values is None else start_values
        if start_kind == 'partial':
            compatible={b.name for domain in (v.full.discrete.alpha,v.full.discrete.xi,v.full.discrete.beta) for b in domain.values()}
            if not values.keys() <= compatible or any(type(x) not in (int,float) or x not in (0,1) for x in values.values()):
                raise ValueError('partial Stage II start requires compatible binaries only')
        if clock() >= cutoff:return finish('deadline_before_start_submission')
        out.start=submit_start(model,values,kind=start_kind)
    start_seconds=clock()-start_begin
    remaining=cutoff-clock()
    if remaining <= 0:return finish('deadline_before_solve')
    result=solve_fn(model,stage='stage2',objective_name='hierarchy_and_placement',objective_units='dimensionless',time_limit=remaining)
    out.stage_result=result
    result.timings.update(build_wall_seconds=build_seconds,start_wall_seconds=start_seconds)
    returned_at=clock()
    result.timings.update(solver_return_window_seconds=returned_at-started_at,
                          solver_cutoff_overrun_seconds=max(0,returned_at-cutoff))
    if returned_at >= deadline:return finish('deadline_before_export')
    if result.raw_status in {'unbounded','inforunbd','not_attempted'}:
        raise ValueError('invalid Stage II solver outcome')
    export_start=clock()
    if export_start >= deadline:return finish('deadline_before_export')
    out.export=export_solution(model,scenario,window,v.full,result)
    result.timings['export_wall_seconds']=clock()-export_start
    if clock() >= deadline:return finish('deadline_before_validation')
    out.validation=validate_stage2(scenario,window,out.export,v.stage1_reference,previous,
                                  weights=v.weights,radio_coefficients=radio_coefficients)
    result.timings['validation_wall_seconds']=out.validation['elapsed_seconds']
    if out.validation['status'] in {'schema_error','input_error'}:
        raise ValueError(f"invalid Stage II data: {out.validation['errors']}")
    result.validation=out.validation['status']
    if not result.has_incumbent:return finish(result.raw_status)
    if not out.validation['valid']:return finish('deployment_validation_rejected')
    out.final_deployment=deployment_from_dict(out.export['candidate']['deployment'],scenario)
    result.first_valid_incumbent_time=clock()-started_at
    result.first_valid_incumbent_reason='first_independent_final_incumbent_validation_not_solver_event'
    return finish('validated_full_deployment',True)
