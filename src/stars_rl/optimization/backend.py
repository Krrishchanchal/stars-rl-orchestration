"""Bounded SCIP solves and explicit warm-start diagnostics."""

from __future__ import annotations

from importlib.metadata import version
import math
import time

from pyscipopt import Model, Eventhdlr, SCIP_EVENTTYPE

from .result import StageResult, StartResult, classify_status, gaps


PARAMETERS = {
    "numerics/feastol": 1e-9,
    "limits/gap": 0.0,
    "limits/absgap": 1e-8,
    "parallel/maxnthreads": 1,
    "randomization/randomseedshift": 0,
}


class _Progress(Eventhdlr):
    def __init__(self):
        self.records = []

    def eventinit(self):
        self.model.catchEvent(SCIP_EVENTTYPE.BESTSOLFOUND, self)

    def eventexit(self):
        self.model.dropEvent(SCIP_EVENTTYPE.BESTSOLFOUND, self)

    def eventexec(self, event):
        self.records.append({"solver_seconds": self.model.getSolvingTime(),
                             "primal_bound": _finite_bound(self.model, self.model.getPrimalbound()),
                             "dual_bound": _finite_bound(self.model, self.model.getDualbound()),
                             "kind": "solver_incumbent_event_not_independently_validated"})


def versions(model: Model) -> dict[str, str]:
    return {"pyscipopt": version("pyscipopt"), "scip":
            f"{model.getMajorVersion()}.{model.getMinorVersion()}.{model.getTechVersion()}"}


def create_model(name: str, *, propagation_objective: bool = False) -> Model:
    model = Model(name)
    model.hideOutput()
    for key, value in PARAMETERS.items():
        model.setParam(key, value)
    if propagation_objective:
        model.setParam("limits/absgap", 1e-10)
    return model


def submit_start(model: Model, values: dict[str, float], *, kind: str) -> StartResult:
    variables = {v.name: v for v in model.getVars()}
    if kind not in {"partial", "complete"} or not values.keys() <= variables.keys():
        raise ValueError("invalid start kind or unknown variable")
    if not all(math.isfinite(v) for v in values.values()):
        raise ValueError("nonfinite start")
    if kind == "complete" and values.keys() != variables.keys():
        raise ValueError("complete start must specify every variable")
    sol = model.createPartialSol() if kind == "partial" else model.createSol()
    for name, value in values.items():
        model.setSolVal(sol, variables[name], value)
    if kind == "partial":
        stored = bool(model.addSol(sol))
        return StartResult(kind, len(values), "unknown_partial", True, stored, "addSol",
                           "API reports storage only; unknown variables remain unknown")
    feasible = bool(model.checkSol(sol, printreason=False, completely=True, original=True))
    if not feasible:
        model.freeSol(sol)
        return StartResult(kind, len(values), "infeasible", False, None, "checkSol",
                           "complete infeasible candidate withheld")
    stored = bool(model.addSol(sol))
    return StartResult(kind, len(values), "feasible", True, stored, "checkSol/addSol",
                       "feasibility checked separately; not stored does not mean infeasible")


def _finite_bound(model: Model, value: float) -> float | None:
    return float(value) if math.isfinite(value) and not model.isInfinity(abs(value)) else None


def solve(model: Model, *, stage: str, objective_name: str, objective_units: str,
          time_limit: float = 10.0) -> StageResult:
    if not math.isfinite(time_limit) or time_limit <= 0:
        raise ValueError("time_limit must be positive and finite")
    counts = {"original_variables": model.getNVars(transformed=False),
              "original_constraints": model.getNConss(transformed=False)}
    model.setParam("limits/time", time_limit)
    progress = _Progress()
    model.includeEventhdlr(progress, "incumbent_progress", "solver incumbent events")
    start = time.perf_counter()
    model.optimize()
    elapsed = time.perf_counter() - start
    extraction_start = time.perf_counter()
    raw = str(model.getStatus())
    incumbent = model.getNSols() > 0
    primal = _finite_bound(model, model.getPrimalbound())
    dual = _finite_bound(model, model.getDualbound())
    absolute, relative, reason = gaps(primal, dual)
    values = {}
    objective = None
    if incumbent:
        sol = model.getBestSol()
        values = {v.name: float(model.getSolVal(sol, v)) for v in model.getVars()}
        objective = float(model.getSolObjVal(sol))
        if not all(math.isfinite(v) for v in [objective, *values.values()]):
            raise ValueError("nonfinite incumbent")
    counts.update(transformed_variables=model.getNVars(), transformed_constraints=model.getNConss())
    return StageResult(
        stage=stage, objective_name=objective_name, objective_units=objective_units,
        raw_status=raw, outcome=classify_status(raw, incumbent), has_incumbent=incumbent,
        objective=objective, primal_bound=primal, dual_bound=dual,
        absolute_gap=absolute, relative_gap=relative, relative_gap_reason=reason,
        raw_solver_gap=_finite_bound(model, model.getGap()), values=values,
        model_counts=counts, timings={"solve_wall_seconds": elapsed,
                                     "solver_seconds": model.getSolvingTime(),
                                     "extraction_seconds": time.perf_counter()-extraction_start},
        progress_log=progress.records,
        parameters={key: model.getParam(key) for key in [*PARAMETERS, "limits/time"]},
        backend_versions=versions(model),
    )
