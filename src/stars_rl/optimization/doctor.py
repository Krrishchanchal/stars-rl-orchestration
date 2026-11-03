"""Small analytical backend checks, never a STARS simulation."""

from dataclasses import asdict
import platform

from .backend import create_model, solve, submit_start


def diagnose() -> dict:
    m = create_model("assignment")
    x = [[m.addVar(f"x_{u}_{s}", vtype="B") for s in range(2)] for u in range(2)]
    for u in range(2):
        m.addCons(sum(x[u]) == 1)
    for s in range(2):
        m.addCons(x[0][s] + x[1][s] <= 1)
    m.setObjective(x[0][0] + 4*x[0][1] + 3*x[1][0] + x[1][1])
    partial = submit_start(m, {"x_0_0": 1}, kind="partial")
    invalid = submit_start(m, {v.name: 1 for row in x for v in row}, kind="complete")
    assignment = solve(m, stage="capability", objective_name="assignment_cost", objective_units="cost")
    r = create_model("reciprocal")
    g = r.addVar("G", lb=1, ub=10)
    t = r.addVar("t", lb=0, ub=2)
    r.addCons(t*g == 6)
    r.setObjective(g)
    reciprocal = solve(r, stage="capability", objective_name="cpu", objective_units="algebraic")
    ok = (assignment.objective is not None and abs(assignment.objective - 2) <= 1e-8
          and reciprocal.objective is not None and abs(reciprocal.objective - 3) <= 1e-7
          and all(result.absolute_gap is not None and result.absolute_gap <= 1e-8
                  for result in [assignment, reciprocal])
          and invalid.prevalidation == "infeasible")
    return {"passed": ok, "python": platform.python_version(), "platform": platform.platform(),
            "assignment": asdict(assignment), "reciprocal": asdict(reciprocal),
            "partial_start": asdict(partial), "invalid_start": asdict(invalid),
            "scope": "backend smoke only; residual sweep is in the solver tests"}
