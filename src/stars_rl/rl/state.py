"""Pre-action bins using allocation-independent demand and known geometry only."""
import math

OBSERVATION_SCHEMA = 'stars-observation-v1'


def _bin(value, low, high):
    return 0 if value <= low else 1 if value <= high else 2


def observation(trace, index, previous=None, previous_churn=0):
    if type(index) is not int or not 0 <= index < len(trace.windows):
        raise ValueError('observation requires an active window')
    s = trace.scenario
    functions = {f.id:f for f in s.function_types}
    demand = {(u.id,k):s.slice_for_user(u.id).demand_mbps*functions[f].psi_instructions_per_bit
              for u in s.users for k,f in enumerate(s.slice_for_user(u.id).chain)}
    capacity = sum(n.cpu_capacity_mips for n in s.satellites)
    global_ratio = sum(demand.values()) / capacity if capacity else math.inf
    pressure = global_ratio
    loss = 0
    if previous is not None:
        used = {a.instance for a in previous.allocations}
        host_load = {n.id:sum(demand[a.user_id,a.stage_index] for a in previous.allocations if a.instance.satellite_id==n.id)
                     + sum(functions[i.function_type_id].base_overhead_mips for i in used if i.satellite_id==n.id)
                     for n in s.satellites}
        pressure = max(host_load[n.id]/n.cpu_capacity_mips if n.cpu_capacity_mips else (math.inf if host_load[n.id] else 0)
                       for n in s.satellites)
        access = {a.user_id:a.satellite_id for a in previous.access}
        egress = {e.user_id:(e.satellite_id,e.ground_station_id) for e in previous.egress}
        snapshots = trace.windows[index:min(index+2,len(trace.windows))]
        loss = sum(any(w.access_distance(u.id,access[u.id]) is None or w.ground_distance(*egress[u.id]) is None
                       for w in snapshots) for u in s.users)/len(s.users)
    return (int(previous is None), len(trace.windows)-index, _bin(global_ratio,.25,.75),
            _bin(pressure,.5,.9), _bin(loss,0,.5), _bin(previous_churn/3,0,1/3))
