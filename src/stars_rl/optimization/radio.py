"""Exact exogenous occupancy lookup and user-summed throughput (C07 draft)."""
from dataclasses import dataclass

from pyscipopt import Model, Variable, Expr, quicksum

from stars_rl.models import Scenario
from stars_rl.physics.radio import access_link
from stars_rl.physics.units import _positive
from stars_rl.topology.trace import NetworkWindow
from .constraints import add_and_constraints
from .variables import DiscreteVariables, name


@dataclass
class RadioVariables:
    z: dict[tuple[str,int],Variable]
    y: dict[tuple[str,str,int],Variable]
    rates: dict[tuple[str,str,int],float]
    rate_provenance: str
    achieved_rate_bps: dict[str,Expr]
    transmission_seconds: dict[str,Expr]


def add_radio_constraints(model: Model, scenario: Scenario, window: NetworkWindow,
                           discrete: DiscreteVariables, *, radio_coefficients: dict | None=None) -> RadioVariables:
    capacities={s.id:s.access_capacity for s in scenario.satellites}
    keys=tuple((u,s,n) for u,s in discrete.alpha for n in range(1,capacities[s]+1))
    if radio_coefficients is not None:
        if scenario.family_classification!="analytical_fixture":
            raise ValueError("radio coefficients may be overridden only by explicit analytical fixtures")
        if not isinstance(radio_coefficients,dict) or radio_coefficients.keys()!=set(keys):
            raise ValueError("radio coefficient domain must exactly cover visible positive-occupancy entries")
        rates={key:_positive(radio_coefficients[key],"radio rate coefficient") for key in keys}
        provenance="authored_coefficient_fixture"
    else:
        rates={key:_positive(access_link(window.access_distance(key[0],key[1]),key[2],scenario.radio).rate_bps,
                             "physical radio rate") for key in keys}
        provenance="physical_radio"
    z={(s,n):model.addVar(name("z",s,n),vtype="B") for s in window.satellite_ids for n in range(capacities[s]+1)}
    for s in window.satellite_ids:
        model.addCons(quicksum(z[(s,n)] for n in range(capacities[s]+1))==1,name=name("RADIO_one_occupancy",s))
        model.addCons(quicksum(n*z[(s,n)] for n in range(capacities[s]+1))==
                      quicksum(x for (u,sat),x in discrete.alpha.items() if sat==s),name=name("RADIO_occupancy_count",s))
    y={key:model.addVar(name("y",*key),vtype="B") for key in keys}
    for (u,s,n),product in y.items():
        add_and_constraints(model,product,discrete.alpha[(u,s)],z[(s,n)],
            names=tuple(name(prefix,u,s,n) for prefix in ("RADIO_y_access","RADIO_y_occupancy","RADIO_y_both")))
    for (u,s),alpha in discrete.alpha.items():
        model.addCons(quicksum(y[(u,s,n)] for n in range(1,capacities[s]+1))==alpha,
                      name=name("RADIO_selected_nonzero_occupancy",u,s))
    achieved={};transmission={}
    for u in window.user_ids:
        request=scenario.slice_for_user(u);demand=request.demand_mbps*1e6
        achieved[u]=quicksum(rates[key]*x for key,x in y.items() if key[0]==u)
        transmission[u]=quicksum(_positive(request.packet_bits/rates[key],"serialization coefficient")*x
                                 for key,x in y.items() if key[0]==u)
        model.addCons(achieved[u]/demand>=1,name=name("THROUGHPUT_user_sum",u))
    return RadioVariables(z,y,rates,provenance,achieved,transmission)
