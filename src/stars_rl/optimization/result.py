"""Stage-local solver records. Solver success is distinct from validation."""

from __future__ import annotations

from dataclasses import dataclass, field
import math


def classify_status(raw: str, has_incumbent: bool) -> str:
    if raw == "not_attempted":
        return raw
    if raw == "infeasible":
        return "proven_infeasible"
    if raw in {"unbounded", "inforunbd"}:
        return "model_error"
    if raw == "optimal" and has_incumbent:
        return "optimal_within_solver_tolerances"
    return "feasible_nonoptimal" if has_incumbent else "stopped_without_incumbent"


def gaps(primal: float | None, dual: float | None) -> tuple[float | None, float | None, str | None]:
    """SCIP-style relative gap, undefined for zero/opposite-sign bounds."""
    if primal is None or dual is None:
        return None, None, "missing_finite_bounds"
    if not math.isfinite(primal) or not math.isfinite(dual):
        raise ValueError("nonfinite bound")
    absolute = abs(primal - dual)
    if primal == 0 or dual == 0:
        return absolute, None, "zero_bound"
    if primal * dual < 0:
        return absolute, None, "opposite_sign_bounds"
    return absolute, absolute / min(abs(primal), abs(dual)), None


@dataclass
class StageResult:
    stage: str
    objective_name: str
    objective_units: str
    raw_status: str = "not_attempted"
    outcome: str = "not_attempted"
    has_incumbent: bool = False
    objective: float | None = None
    primal_bound: float | None = None
    dual_bound: float | None = None
    absolute_gap: float | None = None
    relative_gap: float | None = None
    relative_gap_reason: str | None = "not_attempted"
    raw_solver_gap: float | None = None
    values: dict[str, float] = field(default_factory=dict)
    model_counts: dict[str, int] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)
    first_valid_incumbent_time: float | None = None
    first_valid_incumbent_reason: str = "independent_validation_not_run"
    progress_log: list[dict] = field(default_factory=list)
    validation: str = "not_run"
    parameters: dict[str, float | int] = field(default_factory=dict)
    backend_versions: dict[str, str] = field(default_factory=dict)


@dataclass
class StartResult:
    kind: str
    specified_variables: int
    prevalidation: str
    submission_attempted: bool
    stored: bool | None
    api: str
    diagnostic: str
