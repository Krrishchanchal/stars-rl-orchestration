"""F-C07/type/repeated-stage oracles with explicit fixed binary assignments."""
from dataclasses import replace
from itertools import product
import json

import pytest
from pyscipopt import quicksum

from stars_rl.optimization.constraints import build_discrete_model
from stars_rl.optimization.variables import decode_binary

pytestmark=pytest.mark.solver


def test_exhaustive_instance_assignment_oracle(scenario_factory,solve_case,tmp_path):
    s,w=scenario_factory();records=[]
    for bits in product((0,1),repeat=4):
        m,v=build_discrete_model(s,w)
        keys=[("u0",0,"f0",i,n) for i in ("i0","i1") for n in ("a","b")]
        for key,bit in zip(keys,bits):m.addCons(v.beta[key]==bit)
        result=solve_case(m)
        expected=sum(bits)==1
        assert result.has_incumbent==expected
        if expected:
            assert all(decode_binary(value)==value for value in result.values.values())
            assert sum(result.values[x.name] for x in v.active.values())==1
        records.append({"bits":bits,"expected_feasible":expected,"raw_status":result.raw_status,
                        "values":result.values,"absolute_gap":result.absolute_gap})
    assert sum(r["expected_feasible"] for r in records)==4
    (tmp_path/"placement_oracle.json").write_text(json.dumps(records,indent=2))


def test_function_type_domains_and_no_substitution(scenario_factory,solve_case,fix_choice):
    s,w=scenario_factory();m,v=build_discrete_model(s,w)
    assert {key[2] for key in v.beta}=={"f0"}
    assert ("u0",0,"f1","i0","a") not in v.beta
    fix_choice(m,v.beta,("u0",0,"f1","i0","a"),1)
    assert solve_case(m).raw_status=="infeasible"
    # No f0 instance anywhere: type-incompatible f1 instances cannot rescue it.
    s=replace(s,instances=tuple(i for i in s.instances if i.function_type_id=="f1"))
    m,v=build_discrete_model(s,w)
    assert not v.beta
    assert solve_case(m).raw_status=="infeasible"


def test_repeated_types_rejected_before_model_construction(scenario_factory):
    with pytest.raises(ValueError,match="repeated"):
        scenario_factory(chain=("f0","f0"))


def test_reachable_multihop_host_is_not_filtered(scenario_factory,solve_case,fix_choice):
    s,w=scenario_factory(nodes=("a","b","c"),access=(("u0","a"),),ground=(("a","g0"),))
    # A zero-CPU host still belongs to C06's discrete domain; C07 CPU gating
    # will prevent its use. Transit/visibility do not prune compatible instances.
    s=replace(s,satellites=tuple(replace(x,cpu_capacity_mips=0) if x.id=="c" else x for x in s.satellites))
    m,v=build_discrete_model(s,w)
    key=("u0",0,"f0","i0","c")
    assert key in v.beta
    assert ("u0","a","c") in v.access_link
    fix_choice(m,v.beta,key,1)
    result=solve_case(m)
    assert result.has_incumbent
    assert result.values[v.access_link[("u0","a","c")].name]==1
    assert result.values[v.egress_link[("u0","c","a")].name]==1


def test_names_and_insertion_order_are_stable(scenario_factory):
    s,w=scenario_factory(chain=("f0","f1"))
    a,_=build_discrete_model(s,w)
    reordered=replace(s,users=s.users[::-1],satellites=s.satellites[::-1],instances=s.instances[::-1])
    b,_=build_discrete_model(reordered,w)
    assert [x.name for x in a.getVars()]==[x.name for x in b.getVars()]
    assert [c.name for c in a.getConss()]==[c.name for c in b.getConss()]
    assert len({x.name for x in a.getVars()})==a.getNVars()
    assert len({c.name for c in a.getConss()})==a.getNConss()
    assert all(x.vtype()=="BINARY" for x in a.getVars())
    # Resource/delay and objective/deviation layers have not been introduced.
    assert not any(c.name.startswith(("C13_","C14_","C15_","C16_","C17_")) for c in a.getConss())


@pytest.mark.parametrize("connected,expected_optimum",[(True,5),(False,10)])
def test_joint_discrete_objective_against_enumerated_classes(scenario_factory,solve_case,tmp_path,connected,expected_optimum):
    # An algebraic test objective, not an implemented STARS method/objective.
    # Classes are access, stage0-host, stage1-host, egress; instance-ID ties allowed.
    costs=[{"a":4,"b":1},{"a":2,"b":5},{"a":7,"b":1},{"a":1,"b":3}]
    enumerated=[]
    for choices in product(("a","b"),repeat=4):
        feasible=connected or len(set(choices))==1  # two isolated singleton components
        enumerated.append({"choices":choices,"feasible":feasible,"cost":sum(c[n] for c,n in zip(costs,choices))})
    oracle=min(x["cost"] for x in enumerated if x["feasible"])
    assert oracle==expected_optimum
    s,w=scenario_factory(chain=("f0","f1"),edges=(("a","b",100000),) if connected else ())
    m,v=build_discrete_model(s,w)
    objective=quicksum(costs[0][n]*x for (u,n),x in v.alpha.items())
    objective+=quicksum(costs[3][n]*x for (u,n,g),x in v.xi.items())
    objective+=quicksum(costs[k+1][n]*x for (u,k,f,i,n),x in v.beta.items())
    m.setObjective(objective)
    result=solve_case(m)
    assert result.objective==oracle
    assert result.absolute_gap==0
    chosen=(next(n for (u,n),x in v.alpha.items() if result.values[x.name]==1),
            next(n for (u,k,f,i,n),x in v.beta.items() if k==0 and result.values[x.name]==1),
            next(n for (u,k,f,i,n),x in v.beta.items() if k==1 and result.values[x.name]==1),
            next(n for (u,n,g),x in v.xi.items() if result.values[x.name]==1))
    assert any(tuple(x["choices"])==chosen and x["feasible"] and x["cost"]==oracle for x in enumerated)
    (tmp_path/"joint_discrete_oracle.json").write_text(json.dumps({"classes":enumerated,"expected":oracle,
        "observed_objective":result.objective,"raw_status":result.raw_status,"values":result.values},indent=2))
