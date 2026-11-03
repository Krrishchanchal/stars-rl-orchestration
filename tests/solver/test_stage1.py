"""Independent tiny Stage I optima, deviations and temporal reference oracles."""
from dataclasses import asdict, replace
from itertools import product
import json
from pathlib import Path

import pytest

from stars_rl.config import load_scenario
from stars_rl.models import AccessChoice, Deployment, EgressChoice, InstanceKey, StageAllocation
from stars_rl.optimization.backend import create_model, solve
from stars_rl.optimization.objectives import add_absolute_deviation
from stars_rl.optimization.stage1 import build_stage1_model, run_stage1
from stars_rl.topology.trace import build_trace
from stars_rl.validation.association import validate_association

pytestmark = pytest.mark.solver


def toy():
    s = load_scenario(Path(__file__).resolve().parents[2]/"configs/toy.yaml")
    p = Deployment(0, tuple(AccessChoice(u,"s0") for u in ("u0","u1")),
                   tuple(EgressChoice(u,"s0","g0") for u in ("u0","u1")),
                   tuple(StageAllocation(u,k,InstanceKey(f,"i0","s0"),cpu)
                         for u,cpus in (("u0",(20,40)),("u1",(30,60)))
                         for k,(f,cpu) in enumerate(zip(("f0","f1"),cpus))))
    return s, build_trace(s).windows[1], p


def check(s,w,m,v):
    r = solve(m,stage="stage1",objective_name=v.objective_mode,objective_units="seconds" if v.objective_mode=="propagation" else "dimensionless",time_limit=5)
    assert r.has_incumbent
    validation = validate_association(s,w,r.values,r.objective,mode=v.objective_mode,reference=v.objective_reference,weights=v.weights)
    assert validation["valid"], validation
    return r,validation


def test_initial_hand_enumerated_assignment_and_scope(scenario_factory,tmp_path):
    s,w = scenario_factory(users=2,ground_ids=("g0","g1"),access_capacity=1,egress_capacity=1)
    w = replace(w,access_distances_m=((1,4),(3,1)),ground_distances_m=((2,9),(3,1)))
    m,v = build_stage1_model(s,w)
    r,c = check(s,w,m,v)
    distances=[]
    for a0,a1,e0,e1 in product(range(2),range(2),range(4),range(4)):
        if a0==a1 or e0//2==e1//2:continue
        distances.append(((1,4)[a0]+(3,1)[a1]+(2,9,3,1)[e0]+(2,9,3,1)[e1]))
    expected=min(distances)/299792458
    assert min(distances)==5
    assert r.objective==pytest.approx(expected,abs=1e-14)
    assert c["actual_objective"]==pytest.approx(expected,abs=1e-14)
    assert {var.name.split('[')[0] for var in m.getVars()}=={"alpha","xi"}
    assert all(var.vtype()=="BINARY" for var in m.getVars())
    assert r.parameters["limits/absgap"]==1e-10
    assert r.parameters["parallel/maxnthreads"]==1 and r.parameters["randomization/randomseedshift"]==0
    (tmp_path/'stage1_initial.json').write_text(json.dumps({'result':asdict(r),'validation':c,'enumerated_distance_costs':distances},indent=2))


@pytest.mark.parametrize("reference_mode,expected",[("repaired",0),("original",.5)])
def test_d04_forced_change_against_repaired_vs_original(reference_mode,expected,tmp_path):
    s,w,p = toy()
    m,v = build_stage1_model(s,w,p,reference_mode=reference_mode)
    r,c = check(s,w,m,v)
    assert r.objective==pytest.approx(expected,abs=1e-9)
    assert c['actual_objective']==pytest.approx(expected,abs=1e-9)
    assert ('u0','s1') in c['access'] and ('u1','s0') in c['access']
    assert len(v.d_alpha)==6 and len(v.d_xi)==6
    assert r.parameters['limits/absgap']==1e-8
    (tmp_path/f'stage1_{reference_mode}.json').write_text(json.dumps({'result':asdict(r),'validation':c},indent=2))


def test_later_retains_feasible_reference_despite_closer_alternative():
    s,w,p=toy();w=replace(w,access_distances_m=((500000,1,None),(500000,1,None)))
    m,v=build_stage1_model(s,w,p);r,c=check(s,w,m,v)
    assert r.objective==0 and set(c['access'])=={('u0','s0'),('u1','s0')}


def test_capacity_colliding_reference_is_soft_and_optimizer_repairs_it():
    s,w,p=toy();w=replace(w,access_distances_m=((500000,500000,None),(500000,500000,None)))
    s=replace(s,satellites=tuple(replace(n,access_capacity=1) if n.id=='s0' else n for n in s.satellites))
    m,v=build_stage1_model(s,w,p);r,c=check(s,w,m,v)
    assert r.objective==pytest.approx(.5)
    assert sum(sat=='s0' for u,sat in c['access'])==1


def test_full_and_filtered_domains_have_same_actual_normalization():
    s,w,p=toy();m,v=build_stage1_model(s,w,p,reference_mode='original')
    for key,var in v.association.alpha.items():m.addCons(var==int(key in {('u0','s1'),('u1','s0')}))
    _,filtered=check(s,w,m,v)
    w=replace(w,access_distances_m=((500000,500000,None),(500000,500000,None)))
    m,v=build_stage1_model(s,w,p,reference_mode='original')
    for key,var in v.association.alpha.items():m.addCons(var==int(key in {('u0','s1'),('u1','s0')}))
    _,full=check(s,w,m,v)
    assert filtered['deviations']==full['deviations']==(.5,0)


@pytest.mark.parametrize("ref,value,expected",[(0,0,0),(0,1,1),(1,0,1),(1,1,0)])
def test_absolute_epigraph_truth_table(ref,value,expected):
    m=create_model('absolute_truth');x=m.addVar('x',vtype='B');m.addCons(x==value)
    d=add_absolute_deviation(m,x,ref,variable_name='d');m.setObjective(d)
    r=solve(m,stage='oracle',objective_name='abs',objective_units='count',time_limit=2)
    assert r.objective==expected and r.values['d']==expected


def test_zero_weight_slack_auxiliaries_are_not_actual_deviations():
    s,w,p=toy();m,v=build_stage1_model(s,w,p,weights=(0,0))
    for d in (*v.d_alpha.values(),*v.d_xi.values()):m.addCons(d==1)
    for key,var in v.association.alpha.items():m.addCons(var==int(key in {('u0','s1'),('u1','s0')}))
    for key,var in v.association.xi.items():m.addCons(var==int(key in {('u0','s0','g0'),('u1','s0','g0')}))
    r,c=check(s,w,m,v)
    assert sum(r.values[k.name] for k in v.d_alpha.values())==6
    assert c['deviations']==(0,0) and c['actual_objective']==0


def test_gateway_deviation_uses_xi_and_its_own_positive_negative_rows():
    s,w,p=toy();m,v=build_stage1_model(s,w,p)
    for key,var in v.association.alpha.items():m.addCons(var==int(key in {('u0','s1'),('u1','s0')}))
    for key,var in v.association.xi.items():m.addCons(var==int(key in {('u0','s1','g0'),('u1','s0','g0')}))
    r,c=check(s,w,m,v)
    assert c['deviations']==(0,.5) and r.objective==pytest.approx(.5)
    assert r.values['d_xi[u0,s0,g0]']==r.values['d_xi[u0,s1,g0]']==1
    assert all(r.values[d.name]==0 for d in v.d_alpha.values())


def test_stage1_can_reference_association_that_full_model_cannot_deploy(scenario_factory):
    s,w=scenario_factory(nodes=('a',),access_capacity=1,egress_capacity=1)
    s=replace(s,satellites=(replace(s.satellites[0],cpu_capacity_mips=0),))
    out=run_stage1(s,w)
    assert out.status=='reference_ready' and out.validation['scope']=='association_C1_C6_only'
    from stars_rl.optimization.monolithic import build_full_model
    m,_=build_full_model(s,w)
    assert solve(m,stage='full',objective_name='feasibility',objective_units='constant',time_limit=2).raw_status=='infeasible'


def test_runner_real_start_and_infeasible_no_reference(tmp_path):
    s,w,p=toy();out=run_stage1(s,w,p)
    assert out.status=='reference_ready' and out.stage_result.validation=='valid'
    assert out.start.prevalidation=='unknown_partial'
    assert out.original_previous is p and out.stage1_reference is not out.repair_candidate
    (tmp_path/'stage1_run.json').write_text(json.dumps(asdict(out),indent=2))
    s=replace(s,satellites=tuple(replace(n,access_capacity=0) for n in s.satellites))
    out=run_stage1(s,w,p)
    assert out.status=='stage1_no_reference' and out.reason=='infeasible' and out.stage1_reference is None
