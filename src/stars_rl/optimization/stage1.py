"""Stage I binary linear association model, soft reference only; never deploys."""
from dataclasses import dataclass, field
import math
import time

from pyscipopt import quicksum
from stars_rl.models import AccessChoice, EgressChoice
from stars_rl.validation.association import validate_association
from .backend import solve, submit_start
from .constraints import build_association_model
from .objectives import association_deviations, temporal_expression, weights_checked
from .repair import repair_previous, partial_start_values
from .result import StageResult


@dataclass(frozen=True, slots=True)
class AssociationReference:
    window_index: int
    access: tuple[AccessChoice, ...]
    egress: tuple[EgressChoice, ...]


class RepairUnavailable(ValueError):
    pass


class Stage1Deadline(RuntimeError):
    pass


@dataclass
class Stage1Variables:
    association: object
    d_alpha: dict
    d_xi: dict
    objective_mode: str
    objective_reference: object
    reference_mode: str
    weights: tuple
    repair: object


def build_stage1_model(scenario, window, previous=None, *, reference_mode="repaired",
                       objective_mode=None, weights=(1, 1), deadline=None, clock=time.perf_counter):
    weights = weights_checked(weights)
    if reference_mode not in {"repaired", "original"}:
        raise ValueError("unknown reference mode")
    mode = objective_mode or ("propagation" if window.window_index == 0 else "temporal")
    if mode not in {"propagation", "temporal"}:
        raise ValueError("unknown objective mode")
    repaired = repair_previous(scenario, window, previous)
    reference = None
    if mode == "temporal":
        if previous is None:
            raise ValueError("temporal objective requires original committed state")
        if repaired.status == "failed":
            raise RepairUnavailable("no_visible_repair_reference")
        reference = repaired.repair_candidate if reference_mode == "repaired" else previous
    if deadline is not None and clock() >= deadline:
        raise Stage1Deadline("deadline_after_repair")
    model, association = build_association_model(scenario, window)
    da, dx = {}, {}
    if mode == "propagation":
        model.setParam("limits/absgap", 1e-10)
        c = scenario.radio.speed_of_light_mps
        objective = quicksum(v*window.access_distance(u,s)/c for (u,s),v in association.alpha.items())
        objective += quicksum(v*window.ground_distance(s,g)/c for (u,s,g),v in association.xi.items())
    else:
        da, dx = association_deviations(model, scenario, window, association, reference)
        objective = temporal_expression(da, dx, len(scenario.users), weights)
    model.setObjective(objective, "minimize")
    return model, Stage1Variables(association, da, dx, mode, reference, reference_mode, weights, repaired)


@dataclass
class Stage1Outcome:
    status: str
    reason: str
    stage_result: StageResult
    stage1_reference: AssociationReference | None = None
    validation: dict = field(default_factory=dict)
    start: object = None
    original_previous: object = None
    repair_candidate: object = None
    objective_reference_mode: str = "repaired"
    total_budget_seconds: float = 10
    stage1_deadline_seconds: float = 1.5
    elapsed_seconds: float = 0


def run_stage1(scenario, window, previous=None, *, total_budget_seconds=10,
               started_at=None, clock=time.perf_counter, solve_fn=solve,
               reference_mode="repaired", objective_mode=None, weights=(1, 1), warm=True):
    """Build/solve/extract/check within t0+0.15B, including prior elapsed work.

    Caller starts t0 before observation/inference/repair. No Stage II fallback.
    A late result is retained for diagnostics but cannot become a reference.
    Solver calls are bounded; build/check overruns are detected after completion.
    """
    if type(total_budget_seconds) not in (int, float) or not math.isfinite(total_budget_seconds) or total_budget_seconds <= 0:
        raise ValueError("positive finite total window budget required")
    now = clock()
    t0 = now if started_at is None else started_at
    if not math.isfinite(t0) or t0 > now:
        raise ValueError("invalid window start time")
    deadline = t0 + .15*total_budget_seconds
    mode = objective_mode or ("propagation" if window.window_index == 0 else "temporal")
    result = StageResult("stage1", "propagation" if mode == "propagation" else "normalized_association_deviation",
                         "seconds" if mode == "propagation" else "dimensionless")
    out = Stage1Outcome("stage1_no_reference", "deadline_before_build", result,
                        original_previous=previous, objective_reference_mode=reference_mode,
                        total_budget_seconds=total_budget_seconds, stage1_deadline_seconds=.15*total_budget_seconds)
    def finish(reason, validated=False):
        out.elapsed_seconds = max(0, clock()-t0)
        out.stage_result.timings["stage1_total_wall_seconds"] = out.elapsed_seconds
        if out.elapsed_seconds > .15*total_budget_seconds:
            out.reason = "stage1_deadline_exceeded"
            out.stage1_reference = None
        else:
            out.reason = reason
            if validated: out.status = "reference_ready"
        return out
    if now >= deadline: return finish("deadline_before_build")
    build_start = clock()
    if build_start >= deadline: return finish("deadline_before_repair")
    try:
        model, variables = build_stage1_model(scenario, window, previous, reference_mode=reference_mode,
                                             objective_mode=objective_mode, weights=weights, deadline=deadline, clock=clock)
    except (RepairUnavailable, Stage1Deadline) as exc:
        return finish(str(exc))
    build_seconds = clock()-build_start
    out.repair_candidate = variables.repair.repair_candidate
    if clock() >= deadline: return finish("deadline_after_build")
    start_begin = clock()
    if start_begin >= deadline: return finish("deadline_before_start")
    if warm and variables.repair.status == "candidate":
        values = partial_start_values(scenario, window, variables.repair, include_placement=False)
        if clock() >= deadline: return finish("deadline_before_start_submission")
        out.start = submit_start(model, values, kind="partial")
    start_seconds = clock()-start_begin
    remaining = deadline-clock()
    if remaining <= 0: return finish("deadline_before_solve")
    result = solve_fn(model, stage="stage1", objective_name=result.objective_name,
                      objective_units=result.objective_units, time_limit=remaining)
    out.stage_result = result
    result.timings.update(build_repair_wall_seconds=build_seconds, start_wall_seconds=start_seconds)
    if clock() >= deadline: return finish("deadline_after_solve")
    if result.raw_status in {"unbounded", "inforunbd", "not_attempted"}:
        raise ValueError("invalid Stage I solver outcome")
    if not result.has_incumbent:
        return finish(result.raw_status)
    if result.raw_status in {"infeasible", "unbounded", "inforunbd", "not_attempted"}:
        raise ValueError("contradictory Stage I incumbent status")
    validation_start = clock()
    if validation_start >= deadline: return finish("deadline_before_validation")
    out.validation = validate_association(scenario, window, result.values, result.objective,
                                         mode=variables.objective_mode, reference=variables.objective_reference,
                                         weights=variables.weights)
    result.timings["validation_wall_seconds"] = clock()-validation_start
    if out.validation.get("reason") == "schema_error":
        raise ValueError(f"malformed Stage I incumbent: {out.validation['errors']}")
    result.validation = "valid" if out.validation["valid"] else "rejected"
    if not out.validation["valid"]: return finish("association_validation_rejected")
    out.stage1_reference = AssociationReference(window.window_index,
        tuple(AccessChoice(*k) for k in out.validation["access"]),
        tuple(EgressChoice(*k) for k in out.validation["egress"]))
    result.first_valid_incumbent_time = clock()-t0
    result.first_valid_incumbent_reason = "first_independent_final_incumbent_validation_not_solver_event"
    return finish("validated_association_incumbent", True)
