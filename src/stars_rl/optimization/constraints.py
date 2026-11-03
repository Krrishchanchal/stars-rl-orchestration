"""Common discrete C1–C12 and all endpoint/internal linkage rows (C06).

These builders intentionally do not claim complete SFC feasibility. C07 adds
resources/delay; C08 independently validates exported candidates.
"""
from pyscipopt import Model, quicksum

from stars_rl.models import Scenario
from stars_rl.topology.trace import NetworkWindow
from .backend import create_model
from .variables import (
    AssociationVariables, DiscreteVariables, name, create_association_variables, create_discrete_variables,
)


def add_association_constraints(model: Model, scenario: Scenario, window: NetworkWindow,
                                 variables: AssociationVariables) -> None:
    a=variables.alpha;x=variables.xi
    for u in window.user_ids:
        model.addCons(quicksum(v for (user,s),v in a.items() if user==u)==1,name=name("C01_exact_access",u))
        # D01 correction: one pair over all satellites AND ground stations.
        model.addCons(quicksum(v for (user,s,g),v in x.items() if user==u)==1,name=name("C04_exact_egress_pair",u))
    for sat in sorted(scenario.satellites,key=lambda s:s.id):
        model.addCons(quicksum(v for (u,s),v in a.items() if s==sat.id)<=sat.access_capacity,
                      name=name("C03_access_capacity",sat.id))
        model.addCons(quicksum(v for (u,s,g),v in x.items() if s==sat.id)<=sat.egress_capacity,
                      name=name("C06_egress_flow_capacity",sat.id))


def add_and_constraints(model: Model, product, left, right, *, names: tuple[str,str,str]) -> None:
    model.addCons(product<=left,name=names[0])
    model.addCons(product<=right,name=names[1])
    model.addCons(product>=left+right-1,name=names[2])


def add_placement_constraints(model: Model, scenario: Scenario, window: NetworkWindow,
                               variables: DiscreteVariables) -> None:
    for u in window.user_ids:
        for k,f in enumerate(scenario.slice_for_user(u).chain):
            model.addCons(quicksum(v for (user,stage,ft,i,s),v in variables.beta.items() if (user,stage)==(u,k))==1,
                          name=name("C07_exact_instance",u,k))
    for (f,i,s),active in variables.active.items():
        assignments=quicksum(v for (u,k,ft,inst,sat),v in variables.beta.items() if (ft,inst,sat)==(f,i,s))
        bound=scenario.activation_bound(f)
        model.addCons(assignments<=bound*active,name=name("C08_assignment_requires_activation",f,i,s))
        model.addCons(active<=assignments,name=name("C09_unused_instance_inactive",f,i,s))


def add_linkage_constraints(model: Model, scenario: Scenario, window: NetworkWindow,
                             variables: DiscreteVariables) -> None:
    v=variables
    for u in window.user_ids:
        stages=len(scenario.slice_for_user(u).chain)
        for s in window.satellite_ids:
            for t in window.satellite_ids:
                alpha=v.alpha.get((u,s),0)
                first=v.host[(u,0,t)]
                last=v.host[(u,stages-1,s)]
                egress=v.association.egress[(u,t)]
                if window.paths.get(s,t) is None:
                    model.addCons(alpha+first<=1,name=name("UNREACHABLE_access",u,s,t))
                    model.addCons(last+egress<=1,name=name("UNREACHABLE_egress",u,s,t))
                    for k in range(stages-1):
                        model.addCons(v.host[(u,k,s)]+v.host[(u,k+1,t)]<=1,
                                      name=name("UNREACHABLE_internal",u,k,s,t))
                    continue
                add_and_constraints(model,v.access_link[(u,s,t)],alpha,first,
                    names=tuple(name(prefix,u,s,t) for prefix in ("ENDACCESS_source","ENDACCESS_target","ENDACCESS_both")))
                add_and_constraints(model,v.egress_link[(u,s,t)],last,egress,
                    names=tuple(name(prefix,u,s,t) for prefix in ("ENDEGRESS_source","ENDEGRESS_target","ENDEGRESS_both")))
                for k in range(stages-1):
                    add_and_constraints(model,v.chi[(u,k,s,t)],v.host[(u,k,s)],v.host[(u,k+1,t)],
                        names=tuple(name(prefix,u,k,s,t) for prefix in ("C10_internal_source","C11_internal_target","C12_internal_both")))
        model.addCons(quicksum(x for (user,s,t),x in v.access_link.items() if user==u)==1,
                      name=name("ENDACCESS_exact_link",u))
        model.addCons(quicksum(x for (user,s,t),x in v.egress_link.items() if user==u)==1,
                      name=name("ENDEGRESS_exact_link",u))
        for k in range(stages-1):
            model.addCons(quicksum(x for (user,stage,s,t),x in v.chi.items() if (user,stage)==(u,k))==1,
                          name=name("C12_internal_exact_link",u,k))


def build_association_model(scenario: Scenario, window: NetworkWindow) -> tuple[Model,AssociationVariables]:
    """C1–C6 feasibility only; no Stage I objective/reference behavior yet."""
    model=create_model("association_feasibility")
    variables=create_association_variables(model,scenario,window)
    add_association_constraints(model,scenario,window,variables)
    return model,variables


def build_discrete_model(scenario: Scenario, window: NetworkWindow) -> tuple[Model,DiscreteVariables]:
    """C1–C12 plus completed connectivity, with zero feasibility objective."""
    model,association=build_association_model(scenario,window)
    variables=create_discrete_variables(model,scenario,window,association)
    add_placement_constraints(model,scenario,window,variables)
    add_linkage_constraints(model,scenario,window,variables)
    return model,variables
