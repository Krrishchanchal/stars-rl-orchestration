"""C13/C14/C15 and gating hand oracles; full independent validation is C08."""
import pytest
from pyscipopt import quicksum

from stars_rl.optimization.monolithic import build_full_model, export_solution

pytestmark=pytest.mark.solver


def test_minimum_cpu_is_a_continuous_decision(full_case,solve_case):
    s,w,r=full_case(nodes=("a",));m,v=build_full_model(s,w,radio_coefficients=r)
    m.setObjective(quicksum(v.resources.cpu_mips.values()))
    result=solve_case(m,objective_name="total_cpu",objective_units="MIPS");data=export_solution(m,s,w,v,result)
    assert result.has_incumbent
    assert sum(x["cpu_mips"] for x in data["candidate"]["assignments"])==pytest.approx(20,abs=1e-6)
    assert all(t.g.vtype()=="CONTINUOUS" for t in v.resources.terms.values())
    assert data["validation"]=="not_run"


@pytest.mark.parametrize("unused_capacity",[0,1000])
def test_qbound_unused_undersized_host_does_not_break_feasibility(full_case,solve_case,unused_capacity):
    # O-QBOUND: L=1500, A=0.9. Inactive a has G=0,q=1500 even at C=0.
    s,w,r=full_case(demand=20,psi=75,omega=75,capacities={"a":unused_capacity,"b":2000},coefficient=100e6)
    m,v=build_full_model(s,w,radio_coefficients=r)
    m.addCons(v.discrete.beta[("u0",0,"f0","i0","b")]==1)
    result=solve_case(m);data=export_solution(m,s,w,v,result)
    assert result.has_incumbent
    for a in data["candidate"]["assignments"]:
        if a["satellite_id"]=="a":
            assert a["cpu_mips"]==pytest.approx(0,abs=1e-6)
            assert a["q_mips"]==pytest.approx(1500,abs=1e-5)
            assert abs(a["processing_seconds"])<=5e-8
    m,v=build_full_model(s,w,radio_coefficients=r)
    m.addCons(v.discrete.beta[("u0",0,"f0","i0","a")]==1)
    assert solve_case(m).raw_status=="infeasible"


@pytest.mark.parametrize("capacity,share,feasible",[(45,True,True),(44,True,False),(45,False,False),(50,False,True)])
def test_cpu_overhead_charged_once_per_active_instance(full_case,solve_case,capacity,share,feasible):
    # Two requests each need20 MIPS. Shared instance adds5 =>45; two add10 =>50.
    s,w,r=full_case(nodes=("a",),users=2,capacities={"a":capacity},overhead=5)
    m,v=build_full_model(s,w,radio_coefficients=r)
    for user,instance in [("u0","i0"),("u1","i0" if share else "i1")]:
        m.addCons(v.discrete.beta[(user,0,"f0",instance,"a")]==1)
    result=solve_case(m)
    assert result.has_incumbent==feasible
    if feasible:
        assert sum(result.values[x.name] for x in v.discrete.active.values())==(1 if share else 2)


@pytest.mark.parametrize("same_instance,limit,feasible",[(True,1,True),(False,1,False),(False,2,True)])
def test_active_instance_limit(full_case,solve_case,same_instance,limit,feasible):
    s,w,r=full_case(nodes=("a",),users=2,capacities={"a":200},instance_limit=limit)
    m,v=build_full_model(s,w,radio_coefficients=r)
    m.addCons(v.discrete.beta[("u0",0,"f0","i0","a")]==1)
    m.addCons(v.discrete.beta[("u1",0,"f0","i0" if same_instance else "i1","a")]==1)
    assert solve_case(m).has_incumbent==feasible


def test_inactive_cpu_gate_rejects_positive_allocation(full_case,solve_case):
    s,w,r=full_case();m,v=build_full_model(s,w,radio_coefficients=r)
    selected=("u0",0,"f0","i0","a");unused=("u0",0,"f0","i1","a")
    m.addCons(v.discrete.beta[selected]==1)
    m.addCons(v.resources.cpu_mips[unused]>=1)
    assert solve_case(m).raw_status=="infeasible"


def test_psi_and_omega_are_separate_in_resource_terms(full_case,solve_case):
    s,w,r=full_case(nodes=("a",),psi=10,omega=20);m,v=build_full_model(s,w,radio_coefficients=r)
    key=("u0",0,"f0","i0","a");m.addCons(v.discrete.beta[key]==1)
    m.addCons(v.resources.cpu_mips[key]==20)
    result=solve_case(m);data=export_solution(m,s,w,v,result)
    assignment=next(x for x in data["candidate"]["assignments"] if x["beta_decoded"]==1)
    assert assignment["required_mips"]==20
    assert assignment["amplitude"]==pytest.approx(.24)
    assert assignment["processing_seconds"]==pytest.approx(.012,abs=5e-8)
