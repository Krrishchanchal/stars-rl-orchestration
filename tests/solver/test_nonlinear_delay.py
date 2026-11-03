"""Independent analytical CPU optima and original-unit C07 draft diagnostics."""
from dataclasses import replace
from itertools import product
from pathlib import Path
import json

import pytest
from pyscipopt import quicksum

from stars_rl.config import load_scenario
from stars_rl.topology.trace import build_trace
from stars_rl.physics.delay import ProcessingStage, end_to_end_delay
from stars_rl.optimization.backend import create_model
from stars_rl.optimization.resources import add_processing_term
from stars_rl.optimization.monolithic import build_full_model, export_solution, check_model_size, ModelSizeLimitError

pytestmark=pytest.mark.solver


@pytest.mark.parametrize("minimum,expected_g,expected_objective",[(1,(3,6),1),(4,(4,5),1.05)])
def test_alloc2_production_reciprocals_against_closed_form(solve_case,minimum,expected_g,expected_objective):
    # O-ALLOC2: Cauchy-Schwarz gives (3,6),1; binding G1>=4 gives (4,5),1.05.
    # Explicit algebraic fixture, not a physical scenario or local-NLP oracle.
    m=create_model("allocation_oracle");terms=[]
    for k,(lower,a) in enumerate([(minimum,1),(1,4)]):
        b=m.addVar(f"b{k}",vtype="B");m.addCons(b==1)
        terms.append(add_processing_term(m,b,lower,a,9,("algebraic",k)))
    m.addCons(quicksum(t.cpu_mips for t in terms)/9<=1)
    m.setObjective(quicksum(t.processing_seconds for t in terms))
    result=solve_case(m,objective_name="sum_processing_delay",objective_units="algebraic_seconds")
    actual=[result.values[t.g.name]*t.required_mips for t in terms]
    assert result.objective==pytest.approx(expected_objective,abs=1e-7)
    assert actual==pytest.approx(expected_g,abs=1e-3)
    assert result.absolute_gap<=1e-8


def test_tight_delay_requires_more_cpu_than_throughput_minimum(full_case,solve_case):
    # G required: .12/(D - 1e6/c - .001)=.12/.002=60 MIPS, while L=20.
    budget=1000000/299792458+.001+.002
    s,w,r=full_case(nodes=("a",),delay=budget);m,v=build_full_model(s,w,radio_coefficients=r)
    key=("u0",0,"f0","i0","a");m.addCons(v.discrete.beta[key]==1)
    m.setObjective(quicksum(v.resources.cpu_mips.values()))
    result=solve_case(m,objective_name="total_cpu",objective_units="MIPS");data=export_solution(m,s,w,v,result)
    selected=next(x for x in data["candidate"]["assignments"] if x["beta_decoded"])
    assert selected["cpu_mips"]==pytest.approx(60,abs=1e-6)
    assert selected["cpu_mips"]>20
    assert data["candidate"]["users"]["u0"]["total_delay_seconds"]==pytest.approx(budget,abs=1e-7)


def test_impossible_delay_is_infeasible_and_export_has_no_candidate(full_case,solve_case):
    s,w,r=full_case(nodes=("a",),delay=.001);m,v=build_full_model(s,w,radio_coefficients=r)
    result=solve_case(m)
    assert result.raw_status=="infeasible"
    report=export_solution(m,s,w,v,result)
    assert report["candidate"] is None
    assert report["solver_result"]["values"]=={}


def test_all_five_route_components_are_encoded(full_case,solve_case):
    s,w,r=full_case(nodes=("a","b","c"),chain=("f0","f1"),
        access=(("u0","a"),),ground=(("c","g0"),),capacities={"a":100,"b":100,"c":100})
    m,v=build_full_model(s,w,radio_coefficients=r)
    m.addCons(v.discrete.beta[("u0",0,"f0","i0","b")]==1)
    m.addCons(v.discrete.beta[("u0",1,"f1","i0","c")]==1)
    result=solve_case(m);data=export_solution(m,s,w,v,result)
    parts=data["candidate"]["users"]["u0"]["propagation_components"]
    assert parts==pytest.approx({"user_access_seconds":500000/299792458,
        "access_first_host_seconds":100000/299792458,"internal_host_seconds":100000/299792458,
        "last_host_egress_seconds":0,"egress_ground_seconds":500000/299792458},abs=2.5e-8)


@pytest.mark.parametrize("hosts",[("b","b"),("a","b"),("a","a")])
@pytest.mark.parametrize("bridge",[False,True])
def test_endpoint_rejection_with_full_resources(full_case,solve_case,hosts,bridge):
    s,w,r=full_case(chain=("f0","f1"),edges=(("a","b",100000),) if bridge else (),
                   access=(("u0","a"),),ground=(("b","g0"),))
    m,v=build_full_model(s,w,radio_coefficients=r)
    m.addCons(v.discrete.beta[("u0",0,"f0","i0",hosts[0])]==1)
    m.addCons(v.discrete.beta[("u0",1,"f1","i0",hosts[1])]==1)
    assert solve_case(m).has_incumbent==bridge


def _original_processing_error(assignments):
    # Test-only independent arithmetic, not the forthcoming full validator.
    return sum(abs(a["processing_seconds"]-a["amplitude"]/a["cpu_mips"]) if a["beta_decoded"]
               else abs(a["processing_seconds"]) for a in assignments)


def test_real_toy_export_and_c04_consistency(solve_case,tmp_path):
    t=build_trace(load_scenario(Path(__file__).resolve().parents[2]/"configs/toy.yaml"))
    s,w=t.scenario,t.windows[0];m,v=build_full_model(s,w);result=solve_case(m)
    report=export_solution(m,s,w,v,result)
    assert result.has_incumbent
    assert report["validation"]=="not_run"
    assert len(report["candidate"]["assignments"])==len(v.discrete.beta)
    for user in w.user_ids:
        all_terms=[a for a in report["candidate"]["assignments"] if a["user_id"]==user]
        assert _original_processing_error(all_terms)<=5e-8
        selected=sorted((a for a in all_terms if a["beta_decoded"]),key=lambda a:a["stage_index"])
        d=report["candidate"]["deployment"]
        access=next(a["satellite_id"] for a in d["access"] if a["user_id"]==user)
        egress=next(a for a in d["egress"] if a["user_id"]==user)
        route=w.route_distances(user,access,tuple(a["satellite_id"] for a in selected),egress["satellite_id"],egress["ground_station_id"])
        stages=tuple(ProcessingStage(next(f.omega_instructions_per_bit for f in s.function_types if f.id==a["function_type_id"]),a["cpu_mips"]) for a in selected)
        rate=report["candidate"]["users"][user]["achieved_rate_bps"]
        direct=end_to_end_delay(route,s.slice_for_user(user).packet_bits,stages,rate)
        encoded=report["candidate"]["users"][user]["total_delay_seconds"]
        assert abs(direct.total_seconds-encoded)<=1e-7
        assert direct.total_seconds<=s.slice_for_user(user).delay_limit_seconds+1e-7
    (tmp_path/"toy_full_export.json").write_text(json.dumps(report,indent=2,allow_nan=False))


def test_scaled_processing_extremes_and_all_candidate_error(tmp_path,solve_case):
    records=[]
    # Supported extremes: independent L=demand*psi, A=packet*omega/1e6.
    # One active term plus four inactive terms for each of 128 combinations.
    for demand,psi,omega,packet,capacity,stages in product([2,20],[5,90],[5,90],[512,12000],[0,10,1800,2000],[1,4]):
        required=demand*psi;amplitude=packet*omega/1e6
        m=create_model("scaled_production_terms");terms=[]
        for k in range(stages):
            for i in range(5):
                b=m.addVar(f"b{k}_{i}",vtype="B");m.addCons(b==int(i==0))
                terms.append((int(i==0),add_processing_term(m,b,required,amplitude,capacity,(k,i))))
        result=solve_case(m)
        if capacity<required:
            assert result.raw_status=="infeasible"
            error=None
        else:
            assert result.has_incumbent
            error=0
            for bit,term in terms:
                g=result.values[term.g.name];q=result.values[term.qhat.name];tau=result.values[term.tau.name]
                assert abs(q-(g+1-bit))<=1e-8
                assert abs(tau*q-bit)<=1e-8
                cpu=g*required;tau_delay=tau*amplitude/required
                assert cpu>=-max(1e-6,1e-8*capacity)
                assert cpu-capacity*bit<=max(1e-6,1e-8*capacity)
                error+=abs(tau_delay-amplitude/cpu) if bit else abs(tau_delay)
            assert error<=5e-8
        records.append({"inputs":[demand,psi,omega,packet,capacity,stages],"raw_status":result.raw_status,
                        "processing_error_seconds":error,"values":result.values})
    (tmp_path/"processing_extremes.json").write_text(json.dumps(records,indent=2,allow_nan=False))


def test_size_guard_before_large_construction():
    check_model_size(250000)
    for kwargs in ({},{"allow_large_model":True},{"measured_memory_forecast_bytes":1000}):
        with pytest.raises(ModelSizeLimitError):check_model_size(250001,**kwargs)
    check_model_size(250001,allow_large_model=True,measured_memory_forecast_bytes=1024**3)
    with pytest.raises(ModelSizeLimitError):
        check_model_size(1,measured_memory_forecast_bytes=3*1024**3)


def test_export_rejects_missing_nonfinite_or_stale_snapshot(full_case,solve_case):
    s,w,r=full_case(nodes=("a",));m,v=build_full_model(s,w,radio_coefficients=r)
    result=solve_case(m)
    key=next(iter(result.values))
    for raw in [{k:x for k,x in result.values.items() if k!=key},
                {**result.values,key:float("nan")},{**result.values,key:result.values[key]+.5}]:
        with pytest.raises(ValueError):export_solution(m,s,w,v,replace(result,values=raw))
