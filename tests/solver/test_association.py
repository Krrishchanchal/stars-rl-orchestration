"""F-C01–C06: exact-one choices, visibility and separate satellite pools."""
from itertools import product
import json

import pytest
from pyscipopt import quicksum

from stars_rl.optimization.constraints import build_association_model
from stars_rl.optimization.variables import decode_binary

pytestmark=pytest.mark.solver


@pytest.mark.parametrize("selected,feasible",[((),False),(("a",),True),(("a","b"),False)])
def test_c01_exactly_one_access(scenario_factory,solve_case,fix_choice,selected,feasible):
    s,w=scenario_factory();m,v=build_association_model(s,w)
    for node in ("a","b"):fix_choice(m,v.alpha,("u0",node),int(node in selected))
    assert solve_case(m).has_incumbent==feasible


def test_c02_invisible_selection_is_impossible(scenario_factory,solve_case,fix_choice):
    s,w=scenario_factory(access=(("u0","a"),));m,v=build_association_model(s,w)
    assert ("u0","b") not in v.alpha
    assert solve_case(m).has_incumbent
    m,v=build_association_model(s,w);fix_choice(m,v.alpha,("u0","b"),1)
    assert solve_case(m).raw_status=="infeasible"


@pytest.mark.parametrize("collide",[False,True])
def test_c03_access_capacity_boundary(scenario_factory,solve_case,fix_choice,collide):
    s,w=scenario_factory(users=2,access_capacity=1);m,v=build_association_model(s,w)
    fix_choice(m,v.alpha,("u0","a"),1)
    fix_choice(m,v.alpha,("u1","a" if collide else "b"),1)
    assert solve_case(m).has_incumbent==(not collide)


@pytest.mark.parametrize("pairs,feasible",[((),False),((("a","g0"),),True),((("a","g0"),("b","g0")),False)])
def test_c04_one_egress_pair_globally(scenario_factory,solve_case,fix_choice,pairs,feasible):
    s,w=scenario_factory();m,v=build_association_model(s,w)
    for key in v.xi:fix_choice(m,v.xi,key,int(key[1:] in pairs))
    assert solve_case(m).has_incumbent==feasible


def test_literal_per_satellite_egress_contradiction(scenario_factory,solve_case):
    s,w=scenario_factory();m,v=build_association_model(s,w)
    assert solve_case(m).has_incumbent  # corrected one-pair model feasible
    m,v=build_association_model(s,w)
    for node in ("a","b"):
        m.addCons(quicksum(var for (u,n,g),var in v.xi.items() if n==node)==1)
    assert solve_case(m).raw_status=="infeasible"  # literal C4 requires two pairs


def test_c05_invisible_gateway_and_empty_domains(scenario_factory,solve_case,fix_choice):
    s,w=scenario_factory(ground=(("a","g0"),));m,v=build_association_model(s,w)
    assert ("u0","b","g0") not in v.xi
    fix_choice(m,v.xi,("u0","b","g0"),1)
    assert solve_case(m).raw_status=="infeasible"
    for kwargs in ({"access":()},{"ground":()}):
        s,w=scenario_factory(**kwargs);m,v=build_association_model(s,w)
        assert solve_case(m).raw_status=="infeasible"


@pytest.mark.parametrize("same_satellite",[False,True])
def test_c06_counts_flows_once_across_gs_choices(scenario_factory,solve_case,fix_choice,same_satellite):
    s,w=scenario_factory(users=2,ground_ids=("g0","g1"),egress_capacity=1)
    m,v=build_association_model(s,w)
    fix_choice(m,v.xi,("u0","a","g0"),1)
    fix_choice(m,v.xi,("u1","a" if same_satellite else "b","g1"),1)
    assert solve_case(m).has_incumbent==(not same_satellite)


def test_access_and_egress_pools_are_independent(scenario_factory,solve_case,fix_choice):
    s,w=scenario_factory(access_capacity=1,egress_capacity=1);m,v=build_association_model(s,w)
    fix_choice(m,v.alpha,("u0","a"),1);fix_choice(m,v.xi,("u0","a","g0"),1)
    assert solve_case(m).has_incumbent


def test_exhaustive_binary_association_oracle(scenario_factory,solve_case,tmp_path):
    # All 2^8 raw assignments: hand conditions give 2 access permutations times
    # 2 egress permutations =4 feasible; the other252 patterns violate a rule.
    s,w=scenario_factory(users=2,access_capacity=1,egress_capacity=1);records=[]
    for bits in product((0,1),repeat=8):
        alpha=[bits[:2],bits[2:4]];xi=[bits[4:6],bits[6:8]]
        expected=(all(sum(row)==1 for row in alpha+xi)
                  and all(alpha[0][k]+alpha[1][k]<=1 and xi[0][k]+xi[1][k]<=1 for k in (0,1)))
        m,v=build_association_model(s,w)
        variables=[v.alpha[(u,n)] for u in ("u0","u1") for n in ("a","b")]
        variables += [v.xi[(u,n,"g0")] for u in ("u0","u1") for n in ("a","b")]
        for var,bit in zip(variables,bits):m.addCons(var==bit)
        result=solve_case(m)
        assert result.has_incumbent==expected,bits
        if expected:
            assert all(decode_binary(x)==x for x in result.values.values())
        records.append({"bits":bits,"expected_feasible":expected,"raw_status":result.raw_status,
                        "values":result.values,"primal_bound":result.primal_bound,"dual_bound":result.dual_bound})
    assert sum(r["expected_feasible"] for r in records)==4
    (tmp_path/"association_oracle.json").write_text(json.dumps(records,indent=2))


def test_binary_domains_and_association_scope(scenario_factory,solve_case):
    s,w=scenario_factory();m,v=build_association_model(s,w)
    assert all(x.vtype()=="BINARY" for x in m.getVars())
    assert all(c.name.startswith(("C01_","C03_","C04_","C06_")) for c in m.getConss())
    assert all(x.name.startswith(("alpha[","xi[")) for x in m.getVars())
    m.addCons(v.alpha[("u0","a")]==.5)
    assert solve_case(m).raw_status=="infeasible"


@pytest.mark.parametrize("value",[.5,2e-8,1-2e-8,float("nan"),float("inf"),True])
def test_no_fractional_or_nonfinite_decoding(value):
    with pytest.raises(ValueError):decode_binary(value)


def test_near_binary_decoding_retains_a_strict_gate():
    assert decode_binary(5e-9)==0
    assert decode_binary(1-5e-9)==1
    with pytest.raises(ValueError):decode_binary(10**1000)


def test_mismatched_scenario_window_rejected(scenario_factory):
    s,w=scenario_factory();_,other=scenario_factory(nodes=("x","y"))
    with pytest.raises(ValueError,match="domains"):
        build_association_model(s,other)
