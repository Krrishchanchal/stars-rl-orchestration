"""Bounded linear epigraphs on full logical association domains."""
import math

from pyscipopt import quicksum
from .variables import name


def weights_checked(weights):
    if len(weights) != 2 or any(type(w) not in (int, float) or not math.isfinite(w) or w < 0 for w in weights):
        raise ValueError("two finite nonnegative weights required")
    return tuple(weights)


def add_absolute_deviation(model, variable, reference, *, variable_name):
    if reference not in (0, 1):
        raise ValueError("binary reference required")
    d = model.addVar(variable_name, lb=0, ub=1)
    model.addCons(d >= variable-reference, name=variable_name+"_positive")
    model.addCons(d >= reference-variable, name=variable_name+"_negative")
    return d


def association_deviations(model, scenario, window, association, reference):
    old_a = {(a.user_id, a.satellite_id) for a in reference.access}
    old_x = {(e.user_id, e.satellite_id, e.ground_station_id) for e in reference.egress}
    da, dx = {}, {}
    for u in window.user_ids:
        for s in window.satellite_ids:
            key = (u, s)
            da[key] = add_absolute_deviation(model, association.alpha.get(key, 0), int(key in old_a), variable_name=name("d_alpha", *key))
            for g in window.ground_station_ids:
                key = (u, s, g)
                dx[key] = add_absolute_deviation(model, association.xi.get(key, 0), int(key in old_x), variable_name=name("d_xi", *key))
    return da, dx


def temporal_expression(da, dx, users, weights):
    wa, wx = weights_checked(weights)
    return (wa*quicksum(da.values()) + wx*quicksum(dx.values()))/(2*users)
