"""C8/C9 equivalence and stable (type,instance,host) identities."""
import pytest

from stars_rl.optimization.constraints import build_discrete_model

pytestmark=pytest.mark.solver


def test_shared_instance_activates_once_with_occurrence_bound(scenario_factory,solve_case,fix_choice):
    s,w=scenario_factory(users=2);m,v=build_discrete_model(s,w)
    for u in ("u0","u1"):fix_choice(m,v.beta,(u,0,"f0","i0","a"),1)
    cons=next(c for c in m.getConss() if c.name=="C08_assignment_requires_activation[f0,i0,a]")
    coefficients=m.getValsLinear(cons)
    assert coefficients[v.active[("f0","i0","a")].name]==-2  # 2 users in ONE slice, not hosts/instances
    assert coefficients[v.beta[("u0",0,"f0","i0","a")].name]==1
    assert coefficients[v.beta[("u1",0,"f0","i0","a")].name]==1
    result=solve_case(m)
    assert result.has_incumbent
    assert result.values[v.active[("f0","i0","a")].name]==1
    assert sum(result.values[x.name] for x in v.active.values())==1
    # This counts one activation. C07 adds CPU overhead in the C14 resource rows.


def test_c08_assignment_with_inactive_instance_fails(scenario_factory,solve_case,fix_choice):
    s,w=scenario_factory();m,v=build_discrete_model(s,w)
    fix_choice(m,v.beta,("u0",0,"f0","i0","a"),1)
    fix_choice(m,v.active,("f0","i0","a"),0)
    assert solve_case(m).raw_status=="infeasible"


def test_c09_unused_instance_cannot_activate(scenario_factory,solve_case,fix_choice):
    s,w=scenario_factory();m,v=build_discrete_model(s,w)
    fix_choice(m,v.beta,("u0",0,"f0","i0","a"),1)
    fix_choice(m,v.active,("f0","i1","a"),1)
    assert solve_case(m).raw_status=="infeasible"


def test_same_instance_id_at_two_hosts_is_distinct(scenario_factory,solve_case,fix_choice):
    s,w=scenario_factory(users=2);m,v=build_discrete_model(s,w)
    fix_choice(m,v.beta,("u0",0,"f0","i0","a"),1)
    fix_choice(m,v.beta,("u1",0,"f0","i0","b"),1)
    result=solve_case(m)
    assert result.has_incumbent
    assert result.values[v.active[("f0","i0","a")].name]==1
    assert result.values[v.active[("f0","i0","b")].name]==1
    assert v.active[("f0","i0","a")].name!=v.active[("f1","i0","a")].name


def test_zero_eligible_occurrences_force_unused_type_inactive(scenario_factory,solve_case,fix_choice):
    s,w=scenario_factory();m,v=build_discrete_model(s,w)
    result=solve_case(m)
    assert all(result.values[var.name]==0 for (f,i,n),var in v.active.items() if f=="f1")
    m,v=build_discrete_model(s,w)
    fix_choice(m,v.active,("f1","i0","a"),1)
    assert solve_case(m).raw_status=="infeasible"
