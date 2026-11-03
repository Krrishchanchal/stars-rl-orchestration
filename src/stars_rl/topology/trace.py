"""Immutable authored snapshots, route connectivity and versioned JSON artifacts.

No sampling, orbital generation, user screening or optimization occurs here.
"""
from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path as FilePath
from typing import Literal

from stars_rl.config import scenario_from_dict, scenario_to_dict
from stars_rl.models import ISLLink, Record, Scenario, check_type
from stars_rl.physics.delay import RouteDistances
from .paths import PathTable, all_pairs_shortest_paths


class RouteUnavailableError(ValueError):
    """Well-formed endpoint choices with an unavailable link/path; never zero cost."""
    def __init__(self, segment: str, source_id: str, target_id: str):
        self.segment=segment
        self.source_id=source_id
        self.target_id=target_id
        super().__init__(f"{segment}: unavailable {source_id} -> {target_id}")


def _index(values: tuple[str,...], key: str) -> int:
    if key not in values:
        raise ValueError(f"unknown endpoint ID: {key!r}")
    return values.index(key)


@dataclass(frozen=True, slots=True)
class NetworkWindow(Record):
    window_index: int
    start_seconds: float  # relative to episode origin; absolute provenance stays in metadata
    duration_seconds: float
    user_ids: tuple[str,...]
    satellite_ids: tuple[str,...]
    ground_station_ids: tuple[str,...]
    access_distances_m: tuple[tuple[float | None,...],...]
    ground_distances_m: tuple[tuple[float | None,...],...]
    isl_links: tuple[ISLLink,...]
    paths: PathTable

    def __post_init__(self):
        Record.__post_init__(self)
        if self.window_index<0 or self.start_seconds<0 or self.duration_seconds<=0:
            raise ValueError("window: invalid index/time bounds")
        for ids in (self.user_ids,self.satellite_ids,self.ground_station_ids):
            if not ids or tuple(sorted(set(ids)))!=ids:
                raise ValueError("window: require sorted unique entity IDs")
        if len(self.access_distances_m)!=len(self.user_ids) or any(len(row)!=len(self.satellite_ids) for row in self.access_distances_m):
            raise ValueError("window: invalid access matrix dimensions")
        if len(self.ground_distances_m)!=len(self.satellite_ids) or any(len(row)!=len(self.ground_station_ids) for row in self.ground_distances_m):
            raise ValueError("window: invalid ground matrix dimensions")
        for matrix in (self.access_distances_m,self.ground_distances_m):
            if any(x is not None and x<=0 for row in matrix for x in row):
                raise ValueError("window: visible access/ground distances must be positive")
        if self.paths.node_ids!=self.satellite_ids:
            raise ValueError("window: path nodes differ from satellite IDs")

    @property
    def access_visibility(self) -> tuple[tuple[bool,...],...]:
        return tuple(tuple(d is not None for d in row) for row in self.access_distances_m)

    @property
    def ground_visibility(self) -> tuple[tuple[bool,...],...]:
        return tuple(tuple(d is not None for d in row) for row in self.ground_distances_m)

    def access_distance(self, user_id: str, satellite_id: str) -> float | None:
        return self.access_distances_m[_index(self.user_ids,user_id)][_index(self.satellite_ids,satellite_id)]

    def ground_distance(self, satellite_id: str, ground_station_id: str) -> float | None:
        return self.ground_distances_m[_index(self.satellite_ids,satellite_id)][_index(self.ground_station_ids,ground_station_id)]

    def route_distances(self, user_id: str, access_id: str, host_ids: tuple[str,...],
                        egress_id: str, ground_station_id: str) -> RouteDistances:
        """Connectivity only. Resource/type/SLA feasibility belongs to C06–C08."""
        check_type(host_ids,tuple[str,...],"host_ids")
        if not host_ids:
            raise ValueError("host_ids: nonempty chain required")
        for node in (*host_ids,access_id,egress_id):
            _index(self.satellite_ids,node)
        access=self.access_distance(user_id,access_id)
        ground=self.ground_distance(egress_id,ground_station_id)
        if access is None:
            raise RouteUnavailableError("access_visibility",user_id,access_id)
        if ground is None:
            raise RouteUnavailableError("ground_visibility",egress_id,ground_station_id)
        def distance(a,b,segment):
            path=self.paths.get(a,b)
            if path is None:
                raise RouteUnavailableError(segment,a,b)
            return path.distance_m
        first=distance(access_id,host_ids[0],"access_to_first_host")
        internal=tuple(distance(a,b,f"internal_host_path[{k}]")
                       for k,(a,b) in enumerate(zip(host_ids,host_ids[1:])))
        last=distance(host_ids[-1],egress_id,"last_host_to_egress")
        return RouteDistances(access,first,internal,last,ground)


def _ordered_scenario(s: Scenario) -> Scenario:
    generation=s.metadata.generation
    generation=replace(generation,seeds=tuple(sorted(generation.seeds,key=lambda x:x.stream)),
                        draws=tuple(sorted(generation.draws,key=lambda x:(x.parameter,x.entity_id))))
    edges=tuple(ISLLink(*sorted((e.satellite_a_id,e.satellite_b_id)),e.distance_m) for e in s.isl_links)
    return replace(s,
        metadata=replace(s.metadata,generation=generation),
        users=tuple(sorted(s.users,key=lambda x:x.id)),slices=tuple(sorted(s.slices,key=lambda x:x.id)),
        function_types=tuple(sorted(s.function_types,key=lambda x:x.id)),
        satellites=tuple(sorted(s.satellites,key=lambda x:x.id)),
        ground_stations=tuple(sorted(s.ground_stations,key=lambda x:x.id)),
        instances=tuple(sorted(s.instances,key=lambda x:x.identity)),
        access_schedule=tuple(replace(w,links=tuple(sorted(w.links,key=lambda x:(x.user_id,x.satellite_id)))) for w in s.access_schedule),
        ground_links=tuple(sorted(s.ground_links,key=lambda x:(x.satellite_id,x.ground_station_id))),
        isl_links=tuple(sorted(edges,key=lambda x:(x.satellite_a_id,x.satellite_b_id))))


def _authored_windows(s: Scenario) -> tuple[NetworkWindow,...]:
    if s.orbit is not None:
        from .physical import physical_windows
        return physical_windows(s)
    if s.family_classification not in ("authored_toy","analytical_fixture"):
        raise ValueError("C05 constructs authored traces only; physical generation is C14")
    users=tuple(u.id for u in s.users);satellites=tuple(x.id for x in s.satellites)
    ground=tuple(g.id for g in s.ground_stations)
    paths=all_pairs_shortest_paths(satellites,s.isl_links)
    gs={(l.satellite_id,l.ground_station_id):l.distance_m for l in s.ground_links}
    ground_matrix=tuple(tuple(gs.get((a,b)) for b in ground) for a in satellites)
    windows=[]
    for w in s.access_schedule:
        access={(l.user_id,l.satellite_id):l.distance_m for l in w.links}
        matrix=tuple(tuple(access.get((u,a)) for a in satellites) for u in users)
        windows.append(NetworkWindow(w.window_index,w.window_index*s.window_seconds,s.window_seconds,
                       users,satellites,ground,matrix,ground_matrix,s.isl_links,paths))
    return tuple(windows)


@dataclass(frozen=True, slots=True)
class NetworkTrace(Record):
    trace_schema_version: Literal[1]
    scenario: Scenario
    windows: tuple[NetworkWindow,...]

    def __post_init__(self):
        Record.__post_init__(self)
        if self.scenario != _ordered_scenario(self.scenario):
            raise ValueError("trace: source scenario must use canonical ID order")
        if self.windows != _authored_windows(self.scenario):
            raise ValueError("trace: derived windows/paths disagree with authored inputs")

    @property
    def content_hash(self) -> str:
        inputs=scenario_to_dict(self.scenario)
        # Stable entity IDs remain semantic keys. Family/group/run/seed labels and
        # absolute timestamps are provenance, not exogenous-content identity.
        for key in ("scenario_id","family_id","family_classification","metadata"):
            inputs.pop(key)
        return _digest({"content_hash_schema_version":1,"scenario_inputs":inputs})

    @property
    def artifact_hash(self) -> str:
        return _digest(_payload(self))


def build_trace(scenario: Scenario) -> NetworkTrace:
    check_type(scenario,Scenario,"scenario")
    scenario=_ordered_scenario(scenario)
    return NetworkTrace(1,scenario,_authored_windows(scenario))


def _normalize(data):
    """Canonicalize list order upstream; normalize equivalent int/float values.
    No rounding is applied to nonintegral floats; negative zero becomes zero.
    """
    if isinstance(data,dict):
        return {k:_normalize(v) for k,v in data.items()}
    if isinstance(data,(tuple,list)):
        return [_normalize(v) for v in data]
    if type(data) is float and data.is_integer():
        return int(data)
    return data


def _json(data) -> str:
    try:
        return json.dumps(_normalize(data),sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    except (TypeError,OverflowError) as exc:
        raise ValueError("trace: payload is not canonical JSON data") from exc


def _digest(data) -> str:
    return hashlib.sha256(_json(data).encode("utf-8")).hexdigest()


def _payload(trace: NetworkTrace) -> dict:
    return _normalize({"trace_schema_version":trace.trace_schema_version,
                       "scenario":scenario_to_dict(trace.scenario),"windows":[asdict(w) for w in trace.windows]})


def trace_to_dict(trace: NetworkTrace) -> dict:
    check_type(trace,NetworkTrace,"trace")
    return {**_payload(trace),"content_hash":trace.content_hash,"artifact_hash":trace.artifact_hash}


def trace_to_json(trace: NetworkTrace) -> str:
    return _json(trace_to_dict(trace))


def trace_from_dict(data: dict) -> NetworkTrace:
    keys={"trace_schema_version","scenario","windows","content_hash","artifact_hash"}
    if type(data) is not dict or data.keys()!=keys:
        raise ValueError("trace: missing or unknown fields")
    if type(data["trace_schema_version"]) is not int or data["trace_schema_version"]!=1:
        raise ValueError("trace: unsupported schema version")
    payload={k:v for k,v in data.items() if k not in ("content_hash","artifact_hash")}
    if _digest(payload)!=data["artifact_hash"]:
        raise ValueError("trace: artifact checksum mismatch")
    trace=build_trace(scenario_from_dict(data["scenario"]))
    if trace.content_hash!=data["content_hash"]:
        raise ValueError("trace: content hash mismatch")
    if _json(_payload(trace))!=_json(payload):
        raise ValueError("trace: derived cache differs from canonical source reconstruction")
    return trace


def save_trace(trace: NetworkTrace, path: str | FilePath) -> None:
    FilePath(path).write_text(trace_to_json(trace)+"\n",encoding="utf-8")


def _unique_pairs(pairs):
    out={}
    for key,value in pairs:
        if key in out:
            raise ValueError(f"trace JSON: duplicate field {key!r}")
        out[key]=value
    return out


def _nonfinite_json(value):
    raise ValueError(f"trace JSON: nonfinite number {value}")


def load_trace(path: str | FilePath) -> NetworkTrace:
    data=json.loads(FilePath(path).read_text(encoding="utf-8"),object_pairs_hook=_unique_pairs,
                    parse_constant=_nonfinite_json)
    return trace_from_dict(data)
