"""C06 binary domains. No CPU, occupancy, delay or deviation variables yet."""
from __future__ import annotations

from dataclasses import dataclass

from pyscipopt import Model, Variable, Expr, quicksum

from stars_rl.models import Scenario, check_type
from stars_rl.topology.trace import NetworkWindow


def name(prefix: str, *keys: str | int) -> str:
    # Stable IDs exclude commas/brackets; unlike underscore concatenation this
    # remains unambiguous for IDs containing underscores, hyphens and periods.
    return f"{prefix}[{','.join(str(k) for k in keys)}]"


def check_inputs(scenario: Scenario, window: NetworkWindow) -> None:
    if not isinstance(scenario,Scenario) or not isinstance(window,NetworkWindow):
        raise ValueError("expected validated Scenario and NetworkWindow")
    if (window.user_ids!=tuple(sorted(u.id for u in scenario.users))
            or window.satellite_ids!=tuple(sorted(s.id for s in scenario.satellites))
            or window.ground_station_ids!=tuple(sorted(g.id for g in scenario.ground_stations))
            or not 0<=window.window_index<scenario.window_count
            or window.duration_seconds!=scenario.window_seconds):
        raise ValueError("scenario/window entity or time domains differ")


@dataclass
class AssociationVariables:
    alpha: dict[tuple[str,str],Variable]
    xi: dict[tuple[str,str,str],Variable]
    egress: dict[tuple[str,str],Expr]


@dataclass
class DiscreteVariables:
    association: AssociationVariables
    beta: dict[tuple[str,int,str,str,str],Variable]  # u,k,type,instance,host
    active: dict[tuple[str,str,str],Variable]  # stable (type,instance,host)
    host: dict[tuple[str,int,str],Expr]  # exact sums, binary under the exact-one C7 rows
    access_link: dict[tuple[str,str,str],Variable]
    chi: dict[tuple[str,int,str,str],Variable]
    egress_link: dict[tuple[str,str,str],Variable]

    @property
    def alpha(self):
        return self.association.alpha

    @property
    def xi(self):
        return self.association.xi


def create_association_variables(model: Model, scenario: Scenario, window: NetworkWindow) -> AssociationVariables:
    check_inputs(scenario,window)
    # C2/C5 are enforced by visibility domains, not by weakening a row.
    alpha={(u,s):model.addVar(name("alpha",u,s),vtype="B")
           for u in window.user_ids for s in window.satellite_ids if window.access_distance(u,s) is not None}
    xi={(u,s,g):model.addVar(name("xi",u,s,g),vtype="B")
        for u in window.user_ids for s in window.satellite_ids for g in window.ground_station_ids
        if window.ground_distance(s,g) is not None}
    egress={(u,s):quicksum(x for (user,sat,g),x in xi.items() if (user,sat)==(u,s))
            for u in window.user_ids for s in window.satellite_ids}
    return AssociationVariables(alpha,xi,egress)


def create_discrete_variables(model: Model, scenario: Scenario, window: NetworkWindow,
                              association: AssociationVariables) -> DiscreteVariables:
    check_inputs(scenario,window)
    instances=tuple(sorted(scenario.instances,key=lambda x:x.identity))
    beta={}
    host={}
    for u in window.user_ids:
        for k,f in enumerate(scenario.slice_for_user(u).chain):
            for i in instances:
                if i.function_type_id==f:
                    key=(u,k,*i.identity)
                    beta[key]=model.addVar(name("beta",*key),vtype="B")
            for s in window.satellite_ids:
                host[(u,k,s)]=quicksum(x for (user,stage,ft,inst,sat),x in beta.items()
                                       if (user,stage,sat)==(u,k,s))
    active={i.identity:model.addVar(name("active",*i.identity),vtype="B") for i in instances}
    # Only unreachable auxiliary links are omitted. Every unreachable endpoint
    # combination gets a separate prohibition row in constraints.py.
    reachable=tuple((s,t) for s in window.satellite_ids for t in window.satellite_ids
                    if window.paths.get(s,t) is not None)
    access_link={(u,s,t):model.addVar(name("access_link",u,s,t),vtype="B")
                 for u in window.user_ids for s,t in reachable}
    chi={(u,k,s,t):model.addVar(name("chi",u,k,s,t),vtype="B")
         for u in window.user_ids for k in range(len(scenario.slice_for_user(u).chain)-1) for s,t in reachable}
    egress_link={(u,s,t):model.addVar(name("egress_link",u,s,t),vtype="B")
                 for u in window.user_ids for s,t in reachable}
    return DiscreteVariables(association,beta,active,host,access_link,chi,egress_link)


def decode_binary(value: float) -> int:
    """Decode only within the fixed 1e-8 target, never repair fractional output.
    Raw values stay in StageResult. Decoding does not check any constraint residual.
    """
    check_type(value,float,"binary value")
    if abs(value)<=1e-8:
        return 0
    if abs(value-1)<=1e-8:
        return 1
    raise ValueError("raw value outside binary decoding tolerance")
