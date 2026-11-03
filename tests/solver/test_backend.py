"""C02 independent algebraic oracles; no network builder is used."""
from dataclasses import asdict
from itertools import product
import json
import math

import pytest

from stars_rl.optimization.backend import create_model, solve, submit_start
from stars_rl.optimization.doctor import diagnose
from stars_rl.optimization.result import StageResult, classify_status, gaps

pytestmark = pytest.mark.solver


def run(m):
    return solve(m, stage="capability", objective_name="fixture", objective_units="declared_fixture_units")


def test_doctor():
    report = diagnose()
    assert report["passed"]
    assert report["assignment"]["values"] == {"x_0_0": 1, "x_0_1": 0, "x_1_0": 0, "x_1_1": 1}
    assert report["partial_start"]["prevalidation"] == "unknown_partial"
    assert report["invalid_start"]["submission_attempted"] is False
    assert report["assignment"]["validation"] == "not_run"
    json.dumps(report, allow_nan=False)


def test_infeasible_has_no_extraction():
    m = create_model("contradiction")
    x = m.addVar("x", ub=1)
    m.addCons(x >= 2)
    result = run(m)
    assert result.raw_status == "infeasible"
    assert result.outcome == "proven_infeasible"
    assert not result.has_incumbent and result.values == {} and result.objective is None


@pytest.mark.parametrize("raw,incumbent,expected", [
    ("timelimit", False, "stopped_without_incumbent"),
    ("timelimit", True, "feasible_nonoptimal"),
    ("gaplimit", True, "feasible_nonoptimal"),
    ("infeasible", False, "proven_infeasible"),
    ("unbounded", False, "model_error"),
])
def test_status_logic(raw, incumbent, expected):
    assert classify_status(raw, incumbent) == expected


def test_stage_records_and_zero_gap():
    assert StageResult("stage2", "H", "normalized").raw_status == "not_attempted"
    assert gaps(0, 0) == (0, None, "zero_bound")
    assert gaps(1e-10, -1e-10) == (2e-10, None, "opposite_sign_bounds")
    assert gaps(2, 1) == (1, 1, None)
    with pytest.raises(ValueError):
        gaps(float("nan"), 0)
    m = create_model("zero")
    m.addVar("x", vtype="B")
    result = run(m)
    assert result.objective == 0 and result.absolute_gap == 0
    assert result.relative_gap is None
    assert result.parameters["limits/gap"] == 0
    assert create_model("prop", propagation_objective=True).getParam("limits/absgap") == 1e-10
    json.dumps(asdict(result), allow_nan=False)


def test_complete_start_storage_is_not_feasibility():
    m = create_model("starts")
    x = m.addVar("x", vtype="B")
    m.addCons(x == 1)
    first = submit_start(m, {"x": 1}, kind="complete")
    again = submit_start(m, {"x": 1}, kind="complete")
    assert first.prevalidation == again.prevalidation == "feasible"
    assert first.stored is True
    assert again.stored is False
    assert run(m).objective == 0
    with pytest.raises(ValueError):
        submit_start(create_model("bad"), {"missing": 0}, kind="partial")


@pytest.mark.parametrize("scaled,capacity,active", product([False, True], [0, 1000], [0, 1]))
def test_qbound(scaled, capacity, active):
    # O-QBOUND: L=1500, second host has 2000; only host2 can be active.
    m = create_model("qbound")
    bs, gs, qs, ts = [], [], [], []
    for i, c in enumerate([capacity, 2000]):
        b = m.addVar(f"b{i}", vtype="B")
        factor = 1500 if scaled else 1
        g = m.addVar(f"g{i}", ub=c/factor)
        q = m.addVar(f"q{i}", lb=1500/factor, ub=max(c, 1500)/factor)
        t = m.addVar(f"t{i}", ub=1 if scaled else .008)
        m.addCons(g <= c/factor*b)
        m.addCons(q == g + 1500/factor*(1-b))
        m.addCons(q <= c/factor*b + 1500/factor*(1-b))
        m.addCons(t*q == (1 if scaled else 12)*b)
        bs.append(b); gs.append(g); qs.append(q); ts.append(t)
    m.addCons(sum(bs) == 1)
    m.addCons(bs[0] == active)
    result = run(m)
    if active:
        assert result.raw_status == "infeasible"
    else:
        assert result.has_incumbent
        assert result.values["b0"] == result.values["g0"] == result.values["t0"] == 0
        assert result.values["q0"] == (1 if scaled else 1500)
        assert result.values["b1"] == 1


@pytest.mark.parametrize("lower,expected_g,expected_obj", [(1, (3, 6), 1), (4, (4, 5), 1.05)])
def test_alloc2(lower, expected_g, expected_obj):
    # Cauchy-Schwarz oracle, plus binding-lower-bound oracle, O-ALLOC2.
    m = create_model("two_cpu")
    g1 = m.addVar("g1", lb=lower, ub=9)
    g2 = m.addVar("g2", lb=1, ub=9)
    t1 = m.addVar("t1", ub=1)
    t2 = m.addVar("t2", ub=4)
    m.addCons(g1+g2 <= 9)
    m.addCons(t1*g1 == 1)
    m.addCons(t2*g2 == 4)
    m.setObjective(t1+t2)
    result = run(m)
    assert result.objective == pytest.approx(expected_obj, abs=1e-7)
    # CPU values approach the optimum more slowly than objective values.
    assert (result.values["g1"], result.values["g2"]) == pytest.approx(expected_g, abs=1e-3)


def test_scaled_physical_extremes(tmp_path):
    records = []
    # Independent L=demand*psi, A=packet*omega/1e6, expected G=C.
    for demand, psi, omega, packet, capacity, stages in product(
            [2, 20], [5, 90], [5, 90], [512, 12000], [0, 10, 1800, 2000], [1, 4]):
        required = demand*psi
        amplitude = packet*omega/1e6
        m = create_model("scaled_extreme")
        gs, taus = [], []
        for k in range(stages):
            g = m.addVar(f"g{k}", ub=capacity/required)
            q = m.addVar(f"q{k}", lb=1, ub=max(1, capacity/required))
            tau = m.addVar(f"tau{k}", ub=1)
            m.addCons(q == g)
            m.addCons(q <= capacity/required)
            m.addCons(tau*q == 1)
            gs.append(g); taus.append(tau)
        m.setObjective(sum(taus))
        result = run(m)
        record = {"inputs": [demand, psi, omega, packet, capacity, stages],
                  "raw_status": result.raw_status, "values": result.values}
        if capacity < required:
            assert result.raw_status == "infeasible"
        else:
            assert result.has_incumbent
            error = 0
            for k in range(stages):
                g = result.values[f"g{k}"]
                tau = result.values[f"tau{k}"]
                assert abs(tau*g-1) <= 1e-8
                assert abs(g*required-capacity) <= max(1e-6, 1e-8*capacity)
                error += abs(tau*amplitude/required - amplitude/(g*required))
            assert error <= 5e-8
            record["processing_error_seconds"] = error
        records.append(record)
    (tmp_path / "physical_extremes.json").write_text(json.dumps(records, indent=2), encoding="utf-8")


def test_invalid_time_limits():
    for limit in [0, -1, math.inf, math.nan]:
        with pytest.raises(ValueError):
            solve(create_model("bad"), stage="test", objective_name="x", objective_units="x", time_limit=limit)


def test_installed_try_sol_rejects_invalid_complete_candidate():
    # trySol is a transformed-stage API; checkSol is used before solve in production.
    from pyscipopt import SCIP_PARAMSETTING
    m = create_model("try_sol")
    m.setPresolve(SCIP_PARAMSETTING.OFF)
    x = m.addVar("x", vtype="B")
    m.addCons(x == 1)
    m.presolve()
    candidate = m.createSol()
    m.setSolVal(candidate, x, 0)
    assert m.checkSol(candidate, printreason=False, completely=True) is False
    assert m.trySol(candidate, printreason=False, completely=True) is False


@pytest.mark.parametrize("has_incumbent", [False, True])
def test_timeout_adapter_fake(has_incumbent):
    # Exercise extraction through solve itself; a timeout must not become infeasible.
    class Fake:
        params = {}
        def setParam(self, k, v): self.params[k] = v
        def getParam(self, k): return self.params.get(k, 0)
        def getNVars(self, **kwargs): return 0
        def getNConss(self, **kwargs): return 0
        def includeEventhdlr(self, *args): pass
        def optimize(self): pass
        def getStatus(self): return "timelimit"
        def getNSols(self): return int(has_incumbent)
        def getPrimalbound(self): return 2 if has_incumbent else 1e20
        def getDualbound(self): return 1
        def isInfinity(self, v): return v >= 1e20
        def getBestSol(self):
            assert has_incumbent, "must not extract an absent solution"
            return object()
        def getVars(self): return []
        def getSolObjVal(self, sol): return 2
        def getGap(self): return 1 if has_incumbent else 1e20
        def getSolvingTime(self): return .01
        def getMajorVersion(self): return 10
        def getMinorVersion(self): return 0
        def getTechVersion(self): return 2
    result = run(Fake())
    assert result.raw_status == "timelimit"
    assert result.has_incumbent == has_incumbent
    assert result.outcome == ("feasible_nonoptimal" if has_incumbent else "stopped_without_incumbent")
    assert result.objective == (2 if has_incumbent else None)
