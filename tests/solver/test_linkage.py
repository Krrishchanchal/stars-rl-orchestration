"""Independent AND truth tables, all endpoint products and disconnected routes."""
from itertools import product

import pytest

from stars_rl.optimization.backend import create_model
from stars_rl.optimization.constraints import add_and_constraints, build_discrete_model

pytestmark=pytest.mark.solver


@pytest.mark.parametrize("left,right,z",list(product((0,1),repeat=3)))
def test_c10_c11_c12_and_truth_table(solve_case,left,right,z):
    # (0,1,1) isolates C10, (1,0,1) isolates C11, (1,1,0) isolates C12.
    m=create_model("and_truth_table")
    x=m.addVar("left",vtype="B");y=m.addVar("right",vtype="B");p=m.addVar("product",vtype="B")
    add_and_constraints(m,p,x,y,names=("C10_source","C11_target","C12_both"))
    for var,value in ((x,left),(y,right),(p,z)):m.addCons(var==value)
    assert solve_case(m).has_incumbent==(z==left*right)


@pytest.mark.parametrize("access,h0,h1,egress",list(product(("a","b"),repeat=4)))
def test_all_selected_linkage_classes(scenario_factory,solve_case,fix_choice,access,h0,h1,egress):
    s,w=scenario_factory(chain=("f0","f1"));m,v=build_discrete_model(s,w)
    fix_choice(m,v.alpha,("u0",access),1)
    fix_choice(m,v.xi,("u0",egress,"g0"),1)
    fix_choice(m,v.beta,("u0",0,"f0","i0",h0),1)
    fix_choice(m,v.beta,("u0",1,"f1","i0",h1),1)
    result=solve_case(m)
    assert result.has_incumbent
    for a,b in product(("a","b"),repeat=2):
        assert result.values[v.access_link[("u0",a,b)].name]==int((a,b)==(access,h0))
        assert result.values[v.chi[("u0",0,a,b)].name]==int((a,b)==(h0,h1))
        assert result.values[v.egress_link[("u0",a,b)].name]==int((a,b)==(h1,egress))


@pytest.mark.parametrize("hosts,row",[(('b','b'),'UNREACHABLE_access[u0,a,b]'),
    (('a','b'),'UNREACHABLE_internal[u0,0,a,b]'),(('a','a'),'UNREACHABLE_egress[u0,a,b]')])
@pytest.mark.parametrize("bridge",[False,True])
def test_each_disconnection_rejected_inside_optimizer(scenario_factory,solve_case,fix_choice,hosts,row,bridge):
    s,w=scenario_factory(chain=("f0","f1"),edges=(("a","b",100000),) if bridge else (),
                         access=(("u0","a"),),ground=(("b","g0"),))
    m,v=build_discrete_model(s,w)
    if not bridge:
        assert row in {c.name for c in m.getConss()}
        assert ("u0","a","b") not in v.access_link
        assert ("u0",0,"a","b") not in v.chi
        assert ("u0","a","b") not in v.egress_link
    fix_choice(m,v.beta,("u0",0,"f0","i0",hosts[0]),1)
    fix_choice(m,v.beta,("u0",1,"f1","i0",hosts[1]),1)
    result=solve_case(m)
    assert result.has_incumbent==bridge
    if not bridge:assert result.raw_status=="infeasible"


def test_each_link_class_has_exact_one_consistency(scenario_factory):
    s,w=scenario_factory(chain=("f0","f1"));m,v=build_discrete_model(s,w)
    names={c.name for c in m.getConss()}
    assert {'ENDACCESS_exact_link[u0]','C12_internal_exact_link[u0,0]','ENDEGRESS_exact_link[u0]'}<=names
    assert {'C10_internal_source[u0,0,a,b]','C11_internal_target[u0,0,a,b]','C12_internal_both[u0,0,a,b]'}<=names
