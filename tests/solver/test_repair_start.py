"""Actual partial-start API, independent final validation and repair collisions."""
from dataclasses import asdict, replace
import json
from pathlib import Path

import pytest

from stars_rl.config import deployment_from_dict, load_scenario
from stars_rl.models import AccessChoice, AccessLink, AccessWindow, Deployment, EgressChoice, InstanceKey, StageAllocation
from stars_rl.optimization.backend import solve, submit_start
from stars_rl.optimization.constraints import build_association_model
from stars_rl.optimization.monolithic import build_full_model, export_solution
from stars_rl.optimization.repair import repair_previous, partial_start_values
from stars_rl.metrics import change_metrics
from stars_rl.topology.trace import build_trace
from stars_rl.validation.deployment import validate_export

pytestmark = pytest.mark.solver


def run(model):
    return solve(model, stage="c09_start_test", objective_name="feasibility",
                 objective_units="constant", time_limit=5)


def test_real_partial_warm_cold_and_original_state(tmp_path):
    s = load_scenario(Path(__file__).resolve().parents[2] / "configs/toy.yaml")
    trace = build_trace(s)
    m, v = build_full_model(s, trace.windows[0])
    result = run(m)
    exported = export_solution(m, s, trace.windows[0], v, result)
    assert validate_export(s, trace.windows[0], exported).valid
    previous = deployment_from_dict(exported["candidate"]["deployment"], s)
    before = asdict(previous)
    w = trace.windows[1]
    repaired = repair_previous(s, w, previous)
    outcomes = []
    for warm in (False, True):
        m, v = build_full_model(s, w)
        start = None
        if warm:
            values = partial_start_values(s, w, repaired)
            assert set(values) < {v.name for v in m.getVars()}
            start = submit_start(m, values, kind="partial")
            assert start.prevalidation == "unknown_partial"
        result = run(m)
        exported = export_solution(m, s, w, v, result)
        checked = validate_export(s, w, exported)
        assert checked.valid
        final = deployment_from_dict(exported["candidate"]["deployment"], s)
        metrics = change_metrics(s, previous, final, previous_available=True)
        outcomes.append({"warm": warm, "start": asdict(start) if start else None,
                         "export": exported, "validation": checked.to_dict(), "metrics": asdict(metrics)})
    assert outcomes[0]["export"]["solver_result"]["objective"] == outcomes[1]["export"]["solver_result"]["objective"] == 0
    assert asdict(previous) == before and repaired.original_previous is previous
    # Association-only starts omit beta; no occupancy or resource rows are added.
    m, v = build_association_model(s, w)
    start = submit_start(m, partial_start_values(s, w, repaired, include_placement=False), kind="partial")
    assert start.prevalidation == "unknown_partial" and run(m).has_incumbent
    (tmp_path / "repair_warm_cold.json").write_text(json.dumps(outcomes, indent=2, allow_nan=False))


def test_capacity_collision_stays_candidate_solver_rejects_without_dropping_users(tmp_path):
    s = load_scenario(Path(__file__).resolve().parents[2] / "configs/toy.yaml")
    s = replace(s, satellites=tuple(replace(n, access_capacity=1) if n.id == "s1" else n for n in s.satellites),
                access_schedule=tuple(AccessWindow(1, tuple(AccessLink(u, "s1", 500000) for u in ("u0", "u1")))
                                      if a.window_index == 1 else a for a in s.access_schedule))
    w = build_trace(s).windows[1]
    previous = Deployment(0, tuple(AccessChoice(u, "s0") for u in ("u0", "u1")),
                          tuple(EgressChoice(u, "s0", "g0") for u in ("u0", "u1")),
                          tuple(StageAllocation(u, k, InstanceKey(f, "i0", "s0"), cpu)
                                for u, cpus in (("u0", (20, 40)), ("u1", (30, 60)))
                                for k, (f, cpu) in enumerate(zip(("f0", "f1"), cpus))))
    repaired = repair_previous(s, w, previous)
    assert repaired.status == "candidate" and repaired.feasibility == "not_checked"
    assert len(repaired.repair_candidate.access) == 2
    assert all(a.satellite_id == "s1" for a in repaired.repair_candidate.access)
    m, v = build_full_model(s, w)
    start = submit_start(m, partial_start_values(s, w, repaired), kind="partial")
    assert start.prevalidation == "unknown_partial"
    result = run(m)
    assert result.raw_status == "infeasible" and not result.has_incumbent
    checked = validate_export(s, w, export_solution(m, s, w, v, result))
    assert checked.status == "no_incumbent"
    (tmp_path / "repair_collision.json").write_text(json.dumps({"repair": asdict(repaired), "start": asdict(start),
                                                               "result": asdict(result), "validation": checked.to_dict()}, indent=2, allow_nan=False))
