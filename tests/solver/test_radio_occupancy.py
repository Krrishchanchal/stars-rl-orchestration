"""O-RADIOSELECT: gated user-level service, occupancy and explicit fixtures."""
from dataclasses import replace
import pytest

from stars_rl.optimization.monolithic import build_full_model, export_solution
from stars_rl.config import load_scenario
from pathlib import Path

pytestmark=pytest.mark.solver


@pytest.mark.parametrize("selected",["a","b"])
def test_positive_demand_does_not_apply_to_unselected_satellites(full_case,solve_case,selected):
    s,w,r=full_case();m,v=build_full_model(s,w,radio_coefficients=r)
    m.addCons(v.discrete.alpha[("u0",selected)]==1)
    result=solve_case(m);data=export_solution(m,s,w,v,result)
    assert result.has_incumbent
    assert data["candidate"]["users"]["u0"]["achieved_rate_bps"]==pytest.approx(12e6)
    assert data["candidate"]["users"]["u0"]["access_transmission_seconds"]==pytest.approx(.001)
    for record in data["candidate"]["radio_products"]:
        if record["satellite_id"]!=selected:assert record["decoded"]==0


def test_insufficient_rates_rejected(full_case,solve_case):
    s,w,r=full_case(coefficient=1e6);m,v=build_full_model(s,w,radio_coefficients=r)
    assert solve_case(m).raw_status=="infeasible"


def test_occupancy_two_uses_its_own_rate(full_case,solve_case):
    s,w,r=full_case(nodes=("a",),users=2,capacities={"a":200})
    for key in r:r[key]=12e6 if key[-1]==1 else 6e6
    m,v=build_full_model(s,w,radio_coefficients=r);result=solve_case(m)
    data=export_solution(m,s,w,v,result)
    assert result.has_incumbent
    assert result.values[v.radio.z[("a",2)].name]==1
    assert result.values[v.radio.z[("a",0)].name]==0
    for user in ("u0","u1"):
        assert data["candidate"]["users"][user]["achieved_rate_bps"]==pytest.approx(6e6)
        assert data["candidate"]["users"][user]["access_transmission_seconds"]==pytest.approx(.002)


def test_assigned_user_cannot_take_zero_occupancy(full_case,solve_case):
    s,w,r=full_case(nodes=("a",));m,v=build_full_model(s,w,radio_coefficients=r)
    m.addCons(v.radio.z[("a",0)]==1)
    assert solve_case(m).raw_status=="infeasible"


def test_physical_lookup_matches_independent_radio_golden(full_case):
    s,w,_=full_case();m,v=build_full_model(s,w)
    assert v.radio.rate_provenance=="physical_radio"
    assert v.radio.rates[("u0","a",1)]==pytest.approx(93912842.05644351,rel=2e-14)
    assert v.radio.rates[("u0","a",2)]==pytest.approx(75160797.65360864,rel=2e-14)


def test_coefficient_overrides_are_explicit_analytical_inputs_only(full_case):
    s,w,r=full_case()
    for modified in [{}, {**r,("missing","a",1):1}, {k:0 for k in r}]:
        with pytest.raises(ValueError):build_full_model(s,w,radio_coefficients=modified)
    toy=load_scenario(Path(__file__).resolve().parents[2]/"configs/toy.yaml")
    from stars_rl.topology.trace import build_trace
    t=build_trace(toy)
    with pytest.raises(ValueError,match="analytical"):
        build_full_model(t.scenario,t.windows[0],radio_coefficients=r)
