"""C08 hand-authored candidates: no SCIP, exporter, optimizer or physics helper."""
from copy import deepcopy
from dataclasses import replace
import ast
import json
import math
from pathlib import Path

import pytest

from stars_rl.models import (
    Scenario,TraceMetadata,GenerationMetadata,Radio,FunctionType,Slice,User,
    GroundStation,Satellite,InstanceKey,AccessWindow,AccessLink,GroundLink,
)
from stars_rl.topology.paths import Path as GraphPath,PathTable
from stars_rl.topology.trace import NetworkWindow
from stars_rl.validation.deployment import validate_export


def hand_case(*,instances=2,psi=10,omega=10,capacity=100,overhead=5,cpu=40,delay=.05,distance=300000):
    """Explicit synthetic mathematical fixture, never a measured solver result."""
    s=Scenario(1,"hand-validator-fixture","hand-validator-v1","analytical_fixture",1,60,
        TraceMetadata("hand-group","hand-root","hand-graph","hand-layout","hand-demand",None,0,60,
                      GenerationMetadata("authored",None,None,(),())),
        Radio(14e9,.1,15,40,100e6,290,"exogenous",0,299792458,1.380649e-23),
        (FunctionType("f0",psi,omega,overhead),),(Slice("slice0",("f0",),2,12000,delay),),
        (User("u0","slice0",None),),(GroundStation("g0",None),),(Satellite("a",capacity,1,1,2),),
        tuple(InstanceKey("f0",f"i{i}","a") for i in range(instances)),
        (AccessWindow(0,(AccessLink("u0","a",distance),)),),(GroundLink("a","g0",distance),),())
    # Only schema classes shared; even the identity path is authored explicitly.
    w=NetworkWindow(0,0,60,("u0",),("a",),("g0",),((distance,),),((distance,),),(),
                    PathTable(("a",),(GraphPath(("a",),0),)))
    raw={"alpha[u0,a]":1.,"xi[u0,a,g0]":1.,"access_link[u0,a,a]":1.,"egress_link[u0,a,a]":1.,
         "z[a,0]":0.,"z[a,1]":1.,"y[u0,a,1]":1.}
    for i in range(instances):
        selected=int(i==0);tag=f"u0,0,f0,i{i},a";L=2*psi
        raw.update({f"beta[{tag}]":selected,f"active[f0,i{i},a]":selected,
                    f"g[{tag}]":cpu/L if selected else 0,f"qhat[{tag}]":cpu/L if selected else 1,
                    f"tau[{tag}]":L/cpu if selected else 0})
    report={"export_schema_version":1,"scenario_id":s.scenario_id,"window_index":0,"validation":"not_run",
        "solver_result":{"stage":"hand-authored-not-a-measurement","raw_status":"timelimit","has_incumbent":True,"values":raw},
        "diagnostics":{"rate_provenance":"authored_coefficient_fixture","fixture":"hand-authored-not-a-measurement"},
        "candidate":{"deployment":{"window_index":0,"access":[{"user_id":"u0","satellite_id":"a"}],
            "egress":[{"user_id":"u0","satellite_id":"a","ground_station_id":"g0"}],
            "allocations":[{"user_id":"u0","stage_index":0,"instance":{"function_type_id":"f0","instance_id":"i0","satellite_id":"a"},"cpu_mips":cpu}]},
            "assignments":[],"activations":[],"occupancy":[],"radio_products":[],"users":{}}}
    sync_hand(s,report)
    return s,w,report,{("u0","a",1):12000000.}


def sync_hand(s,report):
    """Resynchronize only redundant wire fields after a controlled mutation.
    This computes no expected feasibility, residual or tolerance result.
    """
    c=report["candidate"];raw=report["solver_result"]["values"]
    L=s.slices[0].demand_mbps*s.function_types[0].psi_instructions_per_bit;A=12000*s.function_types[0].omega_instructions_per_bit/1e6
    c["assignments"]=[];c["activations"]=[]
    for instance in s.instances:
        i=instance.instance_id;tag=f"u0,0,f0,{i},a"
        b=raw[f"beta[{tag}]"];g=raw[f"g[{tag}]"];q=raw[f"qhat[{tag}]"];tau=raw[f"tau[{tag}]"]
        c["assignments"].append({"user_id":"u0","stage_index":0,"function_type_id":"f0","instance_id":i,"satellite_id":"a",
            "beta_raw":b,"beta_decoded":int(b>.5),"g":g,"qhat":q,"tau":tau,"cpu_mips":g*L,"q_mips":q*L,
            "processing_seconds":tau*(A/L),"required_mips":L,"amplitude":A,"time_scale_seconds":A/L})
        act=raw[f"active[f0,{i},a]"]
        c["activations"].append({"function_type_id":"f0","instance_id":i,"satellite_id":"a","raw":act,"decoded":int(act>.5)})
    c["deployment"]["allocations"][0]["cpu_mips"]=raw["g[u0,0,f0,i0,a]"]*L
    c["occupancy"]=[{"satellite_id":"a","occupancy":n,"raw":raw[f"z[a,{n}]"],"decoded":int(raw[f"z[a,{n}]"]>.5)} for n in [0,1]]
    c["radio_products"]=[{"user_id":"u0","satellite_id":"a","occupancy":1,"raw":raw["y[u0,a,1]"],"decoded":int(raw["y[u0,a,1]"]>.5),"rate_coefficient_bps":12000000.}]
    access=s.access_schedule[0].links[0].distance_m;ground=s.ground_links[0].distance_m
    parts={"user_access_seconds":raw["alpha[u0,a]"]*access/299792458,"access_first_host_seconds":0.,
           "internal_host_seconds":0.,"last_host_egress_seconds":0.,"egress_ground_seconds":raw["xi[u0,a,g0]"]*ground/299792458}
    proc=math.fsum(a["processing_seconds"] for a in c["assignments"]);tx=raw["y[u0,a,1]"]*.001
    c["users"]={"u0":{"propagation_components":parts,"processing_seconds":proc,"access_transmission_seconds":tx,
        "total_delay_seconds":math.fsum([*parts.values(),proc,tx]),"achieved_rate_bps":raw["y[u0,a,1]"]*12000000}}


def test_hand_candidate_and_nonoptimal_incumbent_are_valid():
    s,w,data,rates=hand_case();before=deepcopy(data)
    result=validate_export(s,w,data,radio_coefficients=rates)
    assert result.valid,result.errors
    assert result.solver_status=="timelimit" and not result.optimality_checked
    assert data==before
    assert result.recomputed["u0"]["physical_total_delay_seconds"]==pytest.approx(600000/299792458+.003+.001)
    assert result.recomputed["u0"]["processing_error_seconds"]<=1e-18
    json.dumps(result.to_dict(),allow_nan=False)


@pytest.mark.parametrize("mutation",["instance","user","raw","missing_stage","duplicate","extra_field"])
def test_unknown_or_missing_ids_fail_before_residual_comparisons(mutation):
    s,w,d,r=hand_case();c=d["candidate"]
    if mutation=="instance":c["assignments"][0]["instance_id"]="unknown"
    if mutation=="user":c["users"]["unknown"]=c["users"].pop("u0")
    if mutation=="raw":d["solver_result"]["values"]["g[unknown]"]=0
    if mutation=="missing_stage":c["deployment"]["allocations"].clear()
    if mutation=="duplicate":c["assignments"].append(deepcopy(c["assignments"][0]))
    if mutation=="extra_field":c["fake_path"]=["a","unknown"]
    result=validate_export(s,w,d,radio_coefficients=r)
    assert result.status=="schema_error"
    assert not result.residuals


@pytest.mark.parametrize("value",[float("nan"),float("inf"),-float("inf"),"not-a-number"])
def test_bad_numbers_rejected_before_comparisons(value):
    s,w,d,r=hand_case();d["candidate"]["assignments"][0]["cpu_mips"]=value
    result=validate_export(s,w,d,radio_coefficients=r)
    assert result.status=="schema_error" and not result.residuals


@pytest.mark.parametrize("raw_key,value,prefix",[
    ("alpha[u0,a]",0,"C1:"),("xi[u0,a,g0]",0,"C4:"),("beta[u0,0,f0,i0,a]",0,"C7:"),
    ("active[f0,i0,a]",0,"C8:"),("active[f0,i1,a]",1,"C9:"),
    ("access_link[u0,a,a]",0,"access_link-both:"),("egress_link[u0,a,a]",0,"egress_link-both:"),
    ("y[u0,a,1]",0,"throughput-raw:"),
])
def test_corrupt_logic_is_rejected_even_with_optimal_status(raw_key,value,prefix):
    s,w,d,r=hand_case();d["solver_result"]["raw_status"]="optimal"
    d["solver_result"]["values"][raw_key]=value;sync_hand(s,d)
    result=validate_export(s,w,d,radio_coefficients=r)
    assert not result.valid
    assert any(not x.passed and x.row_id.startswith(prefix) for x in result.residuals),(result.status,result.errors)


def test_plausible_rates_do_not_hide_corrupt_occupancy():
    s,w,d,r=hand_case();raw=d["solver_result"]["values"]
    raw["z[a,0]"]=1;raw["z[a,1]"]=0;sync_hand(s,d)
    assert d["candidate"]["users"]["u0"]["achieved_rate_bps"]==12000000
    result=validate_export(s,w,d,radio_coefficients=r)
    assert not result.valid
    assert any(not x.passed and x.row_id.startswith("occupancy-count:") for x in result.residuals)


def test_exported_rate_is_not_used_as_the_oracle():
    s,w,d,r=hand_case();d["candidate"]["radio_products"][0]["rate_coefficient_bps"]=24000000
    result=validate_export(s,w,d,radio_coefficients=r)
    assert not result.valid
    assert any(not x.passed and x.row_id.startswith("export-rate-coefficient:") for x in result.residuals)
    assert not validate_export(s,w,d).valid  # Missing trusted authored table cannot approve.


@pytest.mark.parametrize("new_cpu,prefix",[(10,"C13:"),(110,"C14:")])
def test_original_cpu_rows(new_cpu,prefix):
    s,w,d,r=hand_case();raw=d["solver_result"]["values"]
    raw["g[u0,0,f0,i0,a]"]=new_cpu/20;raw["qhat[u0,0,f0,i0,a]"]=new_cpu/20
    raw["tau[u0,0,f0,i0,a]"]=20/new_cpu;sync_hand(s,d)
    result=validate_export(s,w,d,radio_coefficients=r)
    assert not result.valid
    assert any(not x.passed and x.row_id.startswith(prefix) for x in result.residuals)


def test_instance_limit_and_reciprocal_corruption():
    s,w,d,r=hand_case();s=replace(s,satellites=(replace(s.satellites[0],max_active_instances=0),))
    result=validate_export(s,w,d,radio_coefficients=r)
    assert any(not x.passed and x.row_id.startswith("C15:") for x in result.residuals)
    s,w,d,r=hand_case();d["solver_result"]["values"]["tau[u0,0,f0,i0,a]"]+=.01;sync_hand(s,d)
    result=validate_export(s,w,d,radio_coefficients=r)
    assert any(not x.passed and x.row_id.startswith("reciprocal-product:") for x in result.residuals)


@pytest.mark.parametrize("factor,passed",[(.5,True),(2,False)])
def test_cpu_boundary_in_full_candidate(factor,passed):
    # L=C=100 gives qhat variation small enough that the CPU family is isolated.
    s,w,d,r=hand_case(psi=50,overhead=0,cpu=100)
    cpu=100+factor*1e-6;raw=d["solver_result"]["values"]
    raw["g[u0,0,f0,i0,a]"]=cpu/100;raw["qhat[u0,0,f0,i0,a]"]=cpu/100
    raw["tau[u0,0,f0,i0,a]"]=100/cpu;sync_hand(s,d)
    result=validate_export(s,w,d,radio_coefficients=r)
    assert result.valid==passed,(result.errors,[x for x in result.residuals if not x.passed])
    assert next(x for x in result.residuals if x.row_id=="C14:a").passed==passed


@pytest.mark.parametrize("factor,passed",[(.5,True),(2,False)])
def test_raw_c16_boundary(factor,passed):
    s,w,d,r=hand_case();total=d["candidate"]["users"]["u0"]["total_delay_seconds"]
    s=replace(s,slices=(replace(s.slices[0],delay_limit_seconds=total-factor*2.5e-8),))
    result=validate_export(s,w,d,radio_coefficients=r)
    assert result.valid==passed,(result.errors,[x for x in result.residuals if not x.passed])
    assert next(x for x in result.residuals if x.row_id=="C16-raw:u0").passed==passed


@pytest.mark.parametrize("factor,passed",[(.5,True),(2,False)])
def test_other_reconstruction_budget_in_full_candidate(factor,passed):
    # Explicit algebraic amplification fixture, not orbital geometry. Tiny raw
    # near-binary association errors obey count rows but have measurable delay.
    eps=5e-9;distance=(factor*2.5e-8)/(2*eps)*299792458
    s,w,d,r=hand_case(distance=distance,delay=100)
    raw=d["solver_result"]["values"];raw["alpha[u0,a]"]=1-eps;raw["xi[u0,a,g0]"]=1+eps
    sync_hand(s,d);result=validate_export(s,w,d,radio_coefficients=r)
    assert result.valid==passed,(result.errors,[x for x in result.residuals if not x.passed])
    assert next(x for x in result.residuals if x.row_id=="nonprocessing-error:u0").passed==passed


@pytest.mark.parametrize("factor,passed",[(.5,True),(1,False)])
def test_476_inactive_terms_are_summed(factor,passed):
    s,w,d,r=hand_case(instances=477,psi=5,omega=90)
    raw=d["solver_result"]["values"]
    for i in range(1,477):raw[f"tau[u0,0,f0,i{i},a]"]=factor*1e-9
    sync_hand(s,d);result=validate_export(s,w,d,radio_coefficients=r)
    assert result.valid==passed,(result.errors,[x for x in result.residuals if not x.passed][:4])
    assert result.recomputed["u0"]["processing_error_seconds"]==pytest.approx(factor*5.1408e-8,rel=1e-8,abs=0)


def test_mixed_active_inactive_errors_must_share_one_budget():
    s,w,d,r=hand_case(instances=477,psi=5,omega=90);raw=d["solver_result"]["values"]
    raw["tau[u0,0,f0,i0,a]"]+=2e-10/.108
    for i in range(1,477):raw[f"tau[u0,0,f0,i{i},a]"]=4.99e-8/(476*.108)
    sync_hand(s,d);result=validate_export(s,w,d,radio_coefficients=r)
    assert not result.valid and not result.errors
    assert result.recomputed["u0"]["processing_error_seconds"]==pytest.approx(5.01e-8,rel=1e-8,abs=0)
    assert all(x.passed for x in result.residuals if x.family=="reciprocal")


def test_tiny_negative_inactive_cpu_cannot_supply_capacity_credits():
    # Each raw inactive G=-5e-6 is within its2e-5 CPU tolerance; qhat is only
    # 5e-9 below1. Raw C13/C14 sums pass, but committed selected CPU exceeds2000.
    s,w,d,r=hand_case(instances=477,psi=50,capacity=2000,overhead=0,cpu=1000)
    s=replace(s,slices=(replace(s.slices[0],demand_mbps=20),))
    raw=d["solver_result"]["values"];selected=(1000+476*5e-6)/1000
    for i in range(477):
        g=selected if i==0 else -5e-9
        raw[f"g[u0,0,f0,i{i},a]"]=g;raw[f"qhat[u0,0,f0,i{i},a]"]=g if i==0 else 1+g
        raw[f"tau[u0,0,f0,i{i},a]"]=1/g if i==0 else 0
    sync_hand(s,d)
    s=replace(s,users=(s.users[0],User("u1","slice0",None)),satellites=(replace(s.satellites[0],access_capacity=2,egress_capacity=2),),
              access_schedule=(AccessWindow(0,(AccessLink("u0","a",300000),AccessLink("u1","a",300000))),))
    w=replace(w,user_ids=("u0","u1"),access_distances_m=((300000,),(300000,)))
    for key,value in list(raw.items()):
        if "u0" in key:raw[key.replace("u0","u1")]=value
    raw["z[a,1]"]=0;raw["z[a,2]"]=1
    for u in ("u0","u1"):raw[f"y[{u},a,1]"]=0;raw[f"y[{u},a,2]"]=1
    c=d["candidate"]
    for section in ("access","egress","allocations"):
        item=deepcopy(c["deployment"][section][0]);item["user_id"]="u1";c["deployment"][section].append(item)
    second=[{**deepcopy(a),"user_id":"u1"} for a in c["assignments"]];c["assignments"].extend(second)
    c["occupancy"]=[{"satellite_id":"a","occupancy":k,"raw":raw[f"z[a,{k}]"],"decoded":int(k==2)} for k in range(3)]
    c["radio_products"]=[{"user_id":u,"satellite_id":"a","occupancy":k,"raw":int(k==2),"decoded":int(k==2),
                          "rate_coefficient_bps":100000000} for u in ("u0","u1") for k in (1,2)]
    user=deepcopy(c["users"]["u0"]);user["access_transmission_seconds"]=.00012;user["achieved_rate_bps"]=100000000
    user["total_delay_seconds"]=math.fsum([*user["propagation_components"].values(),user["processing_seconds"],.00012])
    c["users"]={"u0":deepcopy(user),"u1":deepcopy(user)}
    rates={(u,"a",k):100000000 for u in ("u0","u1") for k in (1,2)}
    result=validate_export(s,w,d,radio_coefficients=rates)
    assert not result.valid and not result.errors
    assert next(x for x in result.residuals if x.row_id=="C14:a").passed
    assert not next(x for x in result.residuals if x.row_id=="C14-physical:a").passed
    assert all(x.passed for x in result.residuals if x.row_id!="C14-physical:a")


@pytest.mark.parametrize("value,passed",[(1-5e-9,True),(1-2e-8,False),(.5,False)])
def test_binary_decode_boundaries(value,passed):
    s,w,d,r=hand_case();d["solver_result"]["values"]["active[f0,i0,a]"]=value;sync_hand(s,d)
    result=validate_export(s,w,d,radio_coefficients=r)
    assert result.valid==passed,(result.errors,[x for x in result.residuals if not x.passed])


@pytest.mark.parametrize("cause",["infeasible","timelimit"])
def test_no_incumbent_preserves_cause_without_value_access(cause):
    s,w,d,r=hand_case();d["solver_result"].update(raw_status=cause,has_incumbent=False,values={});d["candidate"]=None
    result=validate_export(s,w,d,radio_coefficients=r)
    assert result.status=="no_incumbent" and result.reason==cause and not result.valid
    assert not result.residuals


def test_validator_has_no_builder_or_physics_dependencies():
    root=Path(__file__).resolve().parents[2]/"src/stars_rl/validation"
    for path in root.glob("*.py"):
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):
                assert not (node.module or "").startswith(("stars_rl.optimization","stars_rl.physics","stars_rl.topology","stars_rl.config"))
            elif isinstance(node,ast.Import):
                assert not any(n.name.startswith(("pyscipopt","stars_rl.optimization","stars_rl.physics","stars_rl.topology")) for n in node.names)
