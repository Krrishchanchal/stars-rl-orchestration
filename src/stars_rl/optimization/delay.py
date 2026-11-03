"""All five route terms, all candidate processing terms and access serialization."""
from dataclasses import dataclass
from pyscipopt import Model, Expr, quicksum

from stars_rl.models import Scenario
from stars_rl.topology.trace import NetworkWindow
from .variables import DiscreteVariables, name
from .resources import ResourceVariables
from .radio import RadioVariables


@dataclass
class DelayExpressions:
    propagation_components: dict[str,dict[str,Expr]]
    processing_seconds: dict[str,Expr]
    total_seconds: dict[str,Expr]


def add_delay_constraints(model: Model, scenario: Scenario, window: NetworkWindow,
                           discrete: DiscreteVariables, resources: ResourceVariables,
                           radio: RadioVariables) -> DelayExpressions:
    c=scenario.radio.speed_of_light_mps
    components={};processing={};total={}
    for u in window.user_ids:
        parts={
            "user_access_seconds":quicksum(window.access_distance(u,s)/c*x for (user,s),x in discrete.alpha.items() if user==u),
            "access_first_host_seconds":quicksum(window.paths.get(s,t).distance_m/c*x for (user,s,t),x in discrete.access_link.items() if user==u),
            "internal_host_seconds":quicksum(window.paths.get(s,t).distance_m/c*x for (user,k,s,t),x in discrete.chi.items() if user==u),
            "last_host_egress_seconds":quicksum(window.paths.get(s,t).distance_m/c*x for (user,s,t),x in discrete.egress_link.items() if user==u),
            "egress_ground_seconds":quicksum(window.ground_distance(s,g)/c*x for (user,s,g),x in discrete.xi.items() if user==u),
        }
        components[u]=parts
        processing[u]=quicksum(x for key,x in resources.processing_seconds.items() if key[0]==u)
        total[u]=quicksum(parts.values())+processing[u]+radio.transmission_seconds[u]
        model.addCons(total[u]/scenario.slice_for_user(u).delay_limit_seconds<=1,name=name("C16_end_to_end_delay",u))
    return DelayExpressions(components,processing,total)
