"""Independent Stage I raw algebra, decoded C1-C6 and objective recomputation.

No solver or objective-builder imports. This does not validate SFC resources.
"""
import math
from dataclasses import asdict
from .residuals import Residuals, finite


def validate_association(scenario, window, values, objective, *, mode, reference, weights):
    rows = Residuals()
    try:
        a = {(u, s): f"alpha[{u},{s}]" for u in window.user_ids for s in window.satellite_ids if window.access_distance(u, s) is not None}
        x = {(u, s, g): f"xi[{u},{s},{g}]" for u in window.user_ids for s in window.satellite_ids for g in window.ground_station_ids if window.ground_distance(s, g) is not None}
        da = {(u, s): f"d_alpha[{u},{s}]" for u in window.user_ids for s in window.satellite_ids} if mode == "temporal" else {}
        dx = {(u, s, g): f"d_xi[{u},{s},{g}]" for u in window.user_ids for s in window.satellite_ids for g in window.ground_station_ids} if mode == "temporal" else {}
        if type(values) is not dict or set(values) != set(a.values()) | set(x.values()) | set(da.values()) | set(dx.values()):
            raise ValueError("unknown/missing Stage I variables")
        for k, value in values.items(): finite(value, k)
        finite(objective, "objective")
        decoded = {}
        for key in (*a.values(), *x.values()):
            v = values[key]
            error = min(abs(v), abs(v-1))
            rows.add("binary", key, error)
            if error <= 1e-8: decoded[key] = int(abs(v-1) <= 1e-8)
        if len(decoded) != len(a)+len(x):
            return {"valid": False, "errors": ["nonintegral association"], "residuals": [asdict(r) for r in rows.rows]}
        for label, domain in (("C1", a), ("C4", x)):
            for u in window.user_ids:
                names = [n for k,n in domain.items() if k[0] == u]
                rows.eq("counts", f"{label}:{u}", math.fsum(values[n] for n in names), 1)
                rows.logic(f"{label}-decoded:{u}", sum(decoded[n] for n in names) == 1)
        for sat in scenario.satellites:
            for label, domain, capacity in (("C3", a, sat.access_capacity), ("C6", x, sat.egress_capacity)):
                names = [n for k,n in domain.items() if k[1] == sat.id]
                rows.le("counts", f"{label}:{sat.id}", math.fsum(values[n] for n in names), capacity)
                rows.logic(f"{label}-decoded:{sat.id}", sum(decoded[n] for n in names) <= capacity)
        actual_a = tuple(k for k,n in a.items() if decoded[n])
        actual_x = tuple(k for k,n in x.items() if decoded[n])
        if mode == "propagation":
            encoded = math.fsum([values[n]*window.access_distance(*k)/scenario.radio.speed_of_light_mps for k,n in a.items()] +
                                [values[n]*window.ground_distance(k[1],k[2])/scenario.radio.speed_of_light_mps for k,n in x.items()])
            actual = math.fsum([window.access_distance(*k)/scenario.radio.speed_of_light_mps for k in actual_a] +
                               [window.ground_distance(k[1],k[2])/scenario.radio.speed_of_light_mps for k in actual_x])
            tolerance = 1e-10
            deviations = None
        elif mode == "temporal":
            old_a = {(c.user_id,c.satellite_id) for c in reference.access}
            old_x = {(c.user_id,c.satellite_id,c.ground_station_id) for c in reference.egress}
            for domain, source, old in ((da,a,old_a),(dx,x,old_x)):
                for k,n in domain.items():
                    d = values[n]; raw = values[source[k]] if k in source else 0
                    rows.ge("counts", n+":lower", d, 0); rows.le("counts", n+":upper", d, 1)
                    rows.ge("counts", n+":positive", d, raw-int(k in old))
                    rows.ge("counts", n+":negative", d, int(k in old)-raw)
            denominator = 2*len(window.user_ids)
            deviations = (len(set(actual_a)^old_a)/denominator, len(set(actual_x)^old_x)/denominator)
            encoded = (weights[0]*math.fsum(values[n] for n in da.values()) + weights[1]*math.fsum(values[n] for n in dx.values()))/denominator
            actual = weights[0]*deviations[0]+weights[1]*deviations[1]
            tolerance = 1e-8
        else: raise ValueError("unknown objective mode")
        errors = [] if abs(objective-encoded) <= tolerance else ["solver objective differs from independently recomputed encoded objective"]
        return {"valid": not errors and all(r.passed for r in rows.rows), "errors": errors,
                "residuals": [asdict(r) for r in rows.rows], "encoded_objective": encoded,
                "actual_objective": actual, "deviations": deviations,
                "access": actual_a, "egress": actual_x, "scope": "association_C1_C6_only"}
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return {"valid": False, "reason": "schema_error", "errors": [str(exc)], "residuals": []}
