"""C07 exports checked independently after solver state is discarded."""
from copy import deepcopy
from dataclasses import replace
from itertools import product
import json
from pathlib import Path

import pytest

from stars_rl.config import load_scenario
from stars_rl.topology.trace import build_trace
from stars_rl.topology.paths import PathTable,Path as GraphPath
from stars_rl.optimization.monolithic import build_full_model,export_solution
from stars_rl.optimization.backend import solve
from stars_rl.validation.deployment import validate_export

pytestmark=pytest.mark.solver


def test_all_toy_windows_validate_without_live_solver(tmp_path):
    t=build_trace(load_scenario(Path(__file__).resolve().parents[2]/"configs/toy.yaml"));reports=[]
    for w in t.windows:
        m,v=build_full_model(t.scenario,w)
        r=solve(m,stage="c08_toy_oracle",objective_name="feasibility",objective_units="constant",time_limit=10)
        exported=json.loads(json.dumps(export_solution(m,t.scenario,w,v,r),allow_nan=False))
        assert r.has_incumbent
        m.freeProb()  # Validation cannot depend on solver expressions/slacks.
        validation=validate_export(t.scenario,w,exported)
        assert validation.valid,(w.window_index,validation.errors,[x for x in validation.residuals if not x.passed])
        reports.append({"export":exported,"validation":validation.to_dict()})
    (tmp_path/"validated_toy_windows.json").write_text(json.dumps(reports,indent=2,allow_nan=False))


@pytest.mark.parametrize("capacity",[0,1000])
def test_production_zero_undersized_host_original_units(full_case,solve_case,capacity):
    s,w,rates=full_case(demand=20,psi=75,omega=75,capacities={"a":capacity,"b":2000},coefficient=100e6)
    m,v=build_full_model(s,w,radio_coefficients=rates)
    m.addCons(v.discrete.beta[("u0",0,"f0","i0","b")]==1)
    result=solve_case(m);d=export_solution(m,s,w,v,result)
    check=validate_export(s,w,d,radio_coefficients=rates)
    assert check.valid,(check.errors,[x for x in check.residuals if not x.passed])


def test_full_deployment_extreme_sweep(full_case,tmp_path):
    records=[]
    # Complete encoded models with every validator family active; endpoints and
    # oracle values are explicit. 1/4 stages use distinct types in hand fixtures.
    for demand,psi,omega,packet,capacity,stages in product([2,20],[5,90],[5,90],[512,12000],[0,10,1800,2000],[1,4]):
        # Build a one-stage source then explicitly supply 1 or4 distinct types.
        s,w,rates=full_case(nodes=("a",),demand=demand,psi=psi,omega=omega,capacities={"a":capacity},coefficient=100e6,delay=1)
        from stars_rl.models import FunctionType,InstanceKey
        types=tuple(FunctionType(f"f{k}",psi,omega,0) for k in range(stages))
        s=replace(s,function_types=types,slices=(replace(s.slices[0],chain=tuple(f.id for f in types),packet_bits=packet),),
                  instances=tuple(InstanceKey(f.id,"i0","a") for f in types),
                  satellites=(replace(s.satellites[0],max_active_instances=4),))
        m,v=build_full_model(s,w,radio_coefficients=rates)
        result=solve(m,stage="c08_extreme_sweep",objective_name="feasibility",objective_units="constant",time_limit=3)
        data=export_solution(m,s,w,v,result)
        checked=validate_export(s,w,data,radio_coefficients=rates)
        expected=capacity>=stages*demand*psi
        assert result.has_incumbent==expected
        assert checked.valid==expected,(demand,psi,omega,packet,capacity,stages,checked.errors,[x for x in checked.residuals if not x.passed][:5])
        if not expected:assert checked.status=="no_incumbent" and result.raw_status=="infeasible"
        records.append({"inputs":[demand,psi,omega,packet,capacity,stages],"export":data,"validation":checked.to_dict()})
    (tmp_path/"full_deployment_extremes.json").write_text(json.dumps(records,indent=2,allow_nan=False))


def test_fake_path_cache_and_raw_route_products_are_rejected():
    t=build_trace(load_scenario(Path(__file__).resolve().parents[2]/"configs/toy.yaml"));w=t.windows[0]
    m,v=build_full_model(t.scenario,w);result=solve(m,stage="c08_corruption",objective_name="feasibility",objective_units="constant",time_limit=10)
    exported=export_solution(m,t.scenario,w,v,result)
    entries=list(w.paths.entries)
    for i in (1,3):entries[i]=GraphPath(entries[i].nodes,entries[i].distance_m+100000)
    fake=replace(w,paths=PathTable(w.paths.node_ids,tuple(entries)))
    assert validate_export(t.scenario,fake,exported).status=="input_error"
    corrupted=deepcopy(exported)
    key=next(k for k in corrupted["solver_result"]["values"] if k.startswith("chi["))
    corrupted["solver_result"]["values"][key]=1-corrupted["solver_result"]["values"][key]
    assert not validate_export(t.scenario,w,corrupted).valid
