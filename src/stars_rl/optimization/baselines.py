"""Independent monolithic baseline objectives on the common full feasible set."""
from dataclasses import dataclass, field
import math
import time
from pyscipopt import quicksum

from stars_rl.config import deployment_from_dict
from stars_rl.validation.monolithic import validate_monolithic
from .backend import solve,submit_start
from .monolithic import build_full_model,export_solution
from .objectives import association_deviations,add_absolute_deviation
from .repair import repair_previous,partial_start_values
from .result import StageResult,StartResult
from .variables import name


@dataclass
class MonolithicVariables:
    full: object
    mode: str
    previous: object
    repair: object


def build_monolithic_method(scenario,window,method_id,previous=None,*,radio_coefficients=None,
                            deadline=None,clock=time.perf_counter):
    if method_id not in {'mono-delay','mono-temporal'}:raise ValueError('not a monolithic method')
    if method_id=='mono-temporal' and window.window_index>0 and previous is None:
        raise ValueError('later temporal method requires original committed state')
    mode='temporal' if method_id=='mono-temporal' and previous is not None else 'Q'
    repair=repair_previous(scenario,window,previous) if mode=='temporal' else None
    if deadline is not None and clock()>=deadline:raise TimeoutError('deadline_after_repair')
    model,full=build_full_model(scenario,window,radio_coefficients=radio_coefficients)
    base={'variables':model.getNVars(),'constraints':model.getNConss()}
    if mode=='Q':
        objective=quicksum(full.delay.total_seconds[u]/scenario.slice_for_user(u).delay_limit_seconds for u in window.user_ids)/len(window.user_ids)
    else:
        da,dx=association_deviations(model,scenario,window,full.discrete.association,previous)
        old={(a.user_id,a.stage_index,*a.instance.identity) for a in previous.allocations}
        db={k:add_absolute_deviation(model,b,int(k in old),variable_name=name('d_beta',*k)) for k,b in full.discrete.beta.items()}
        stages=sum(len(scenario.slice_for_user(u).chain) for u in window.user_ids)
        objective=(quicksum(da.values())+quicksum(dx.values()))/(2*len(window.user_ids))+quicksum(db.values())/(2*stages)
    model.setObjective(objective,'minimize')
    full.diagnostics.update(method_id=method_id,objective_mode=mode,base_full_model_size=base,
        generated_variables=model.getNVars(),generated_constraints=model.getNConss(),
        final_model_size={'variables':model.getNVars(),'constraints':model.getNConss()},
        coefficient_summary_scope='base full rows; temporal deviations add only +/-1 coefficients')
    return model,MonolithicVariables(full,mode,previous,repair)


@dataclass
class MonolithicOutcome:
    status: str
    reason: str
    stage_result: StageResult
    final_deployment: object=None
    export: dict | None=None
    validation: dict=field(default_factory=dict)
    start: object=None
    elapsed_seconds: float=0


def run_monolithic(scenario,window,method_id,previous=None,*,started_at,total_budget_seconds=10,
                    radio_coefficients=None,clock=time.perf_counter,solve_fn=solve):
    if type(total_budget_seconds) not in (int,float) or not math.isfinite(total_budget_seconds) or total_budget_seconds<=0:
        raise ValueError('positive finite window budget required')
    now=clock()
    if not math.isfinite(started_at) or started_at>now:raise ValueError('invalid shared start time')
    cutoff=started_at+.95*total_budget_seconds;deadline=started_at+total_budget_seconds
    mode='temporal' if method_id=='mono-temporal' and previous is not None else 'Q'
    out=MonolithicOutcome('monolithic_no_deployment','not_attempted',StageResult('monolithic',mode,'dimensionless'))
    def finish(reason,valid=False):
        out.elapsed_seconds=max(0,clock()-started_at);out.reason=reason
        out.stage_result.timings['window_elapsed_seconds']=out.elapsed_seconds
        if out.elapsed_seconds>total_budget_seconds:
            out.status='late';out.reason='window_deadline_exceeded';out.final_deployment=None
        elif valid:out.status='validated'
        return out
    build_start=clock()
    if build_start>=cutoff:return finish('deadline_before_build')
    try:model,v=build_monolithic_method(scenario,window,method_id,previous,radio_coefficients=radio_coefficients,deadline=cutoff,clock=clock)
    except TimeoutError as exc:return finish(str(exc))
    build_seconds=clock()-build_start
    if clock()>=cutoff:return finish('deadline_after_build')
    start_begin=clock()
    if start_begin>=cutoff:return finish('deadline_before_start')
    if v.repair is not None:
        if v.repair.status=='candidate':
            values=partial_start_values(scenario,window,v.repair)
            if clock()>=cutoff:return finish('deadline_before_start_submission')
            out.start=submit_start(model,values,kind='partial')
        else:
            out.start=StartResult('partial',0,'repair_failed',False,None,'not_submitted','no visible repair; no start, full model unchanged')
    start_seconds=clock()-start_begin;remaining=cutoff-clock()
    if remaining<=0:return finish('deadline_before_solve')
    result=solve_fn(model,stage='monolithic',objective_name=v.mode,objective_units='dimensionless',time_limit=remaining)
    out.stage_result=result;returned=clock()
    result.timings.update(build_repair_wall_seconds=build_seconds,start_wall_seconds=start_seconds,
        solver_return_window_seconds=returned-started_at,solver_cutoff_overrun_seconds=max(0,returned-cutoff))
    if returned>=deadline:return finish('deadline_before_export')
    if result.raw_status in {'unbounded','inforunbd','not_attempted'}:raise ValueError('invalid monolithic solver outcome')
    export_start=clock()
    if export_start>=deadline:return finish('deadline_before_export')
    out.export=export_solution(model,scenario,window,v.full,result)
    result.timings['export_wall_seconds']=clock()-export_start
    if clock()>=deadline:return finish('deadline_before_validation')
    out.validation=validate_monolithic(scenario,window,out.export,mode=v.mode,previous=previous,radio_coefficients=radio_coefficients)
    result.timings['validation_wall_seconds']=out.validation['elapsed_seconds']
    if out.validation['status'] in {'schema_error','input_error'}:raise ValueError(f"invalid monolithic data: {out.validation['errors']}")
    result.validation=out.validation['status']
    if not result.has_incumbent:return finish(result.raw_status)
    if not out.validation['valid']:return finish('deployment_validation_rejected')
    out.final_deployment=deployment_from_dict(out.export['candidate']['deployment'],scenario)
    result.first_valid_incumbent_time=clock()-started_at
    result.first_valid_incumbent_reason='first_independent_final_incumbent_validation_not_solver_event'
    return finish('validated_full_deployment',True)
