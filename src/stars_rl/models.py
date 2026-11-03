"""Immutable, unit-explicit inputs and deployment candidates (C03).

Structural validity never certifies networking/optimization feasibility.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
import math
import re
from types import UnionType
from typing import Literal, get_args, get_origin, get_type_hints


def check_type(value, annotation, path: str) -> None:
    """Strict runtime typing; reject coercion, mutable sequences and nonfinite floats."""
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is UnionType:
        for option in args:
            try:
                check_type(value, option, path)
                return
            except ValueError:
                pass
        raise ValueError(f"{path}: expected {annotation}, got {value!r}")
    if origin is Literal:
        if not any(type(value) is type(a) and value == a for a in args):
            raise ValueError(f"{path}: expected one of {args}")
    elif origin is tuple:
        if type(value) is not tuple:
            raise ValueError(f"{path}: expected immutable tuple")
        for i, item in enumerate(value):
            check_type(item, args[0], f"{path}[{i}]")
    elif annotation is float:
        try:
            finite = type(value) in (int,float) and math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError(f"{path}: expected finite number")
    elif annotation is int:
        if type(value) is not int:
            raise ValueError(f"{path}: expected integer")
    elif not isinstance(value, annotation):
        raise ValueError(f"{path}: expected {annotation.__name__}")


def _fields(record) -> None:
    hints = get_type_hints(type(record))
    for f in fields(record):
        value = getattr(record, f.name)
        check_type(value, hints[f.name], f"{type(record).__name__}.{f.name}")
        if (f.name == "id" or f.name.endswith("_id")) and isinstance(value, str):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
                raise ValueError(f"{f.name}: malformed stable id {value!r}")


def _range(name: str, value: float, minimum: float, maximum: float = math.inf) -> None:
    if not minimum <= value <= maximum:
        raise ValueError(f"{name}: expected range [{minimum}, {maximum}]")


def _positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name}: must be positive")


def _unique(values, name: str) -> None:
    values = tuple(values)
    if len(set(values)) != len(values):
        raise ValueError(f"{name}: duplicate identity")


def _known(value, domain, name: str) -> None:
    if value not in domain:
        raise ValueError(f"unknown {name}: {value!r}")


class Record:
    __slots__ = ()

    def __post_init__(self):
        _fields(self)


@dataclass(frozen=True, slots=True)
class Coordinates(Record):
    latitude_degrees: float
    longitude_degrees: float

    def __post_init__(self):
        _fields(self)
        _range("latitude_degrees", self.latitude_degrees, -90, 90)
        _range("longitude_degrees", self.longitude_degrees, -180, 180)


@dataclass(frozen=True, slots=True)
class User(Record):
    id: str
    slice_id: str
    coordinates: Coordinates | None


@dataclass(frozen=True, slots=True)
class GroundStation(Record):
    id: str
    coordinates: Coordinates | None


@dataclass(frozen=True, slots=True)
class FunctionType(Record):
    id: str
    psi_instructions_per_bit: float
    omega_instructions_per_bit: float
    base_overhead_mips: float

    def __post_init__(self):
        _fields(self)
        _range("psi_instructions_per_bit", self.psi_instructions_per_bit, 5, 90)
        _range("omega_instructions_per_bit", self.omega_instructions_per_bit, 5, 90)
        _range("base_overhead_mips", self.base_overhead_mips, 0)


@dataclass(frozen=True, slots=True)
class Slice(Record):
    id: str
    chain: tuple[str, ...]
    demand_mbps: float
    packet_bits: int
    delay_limit_seconds: float

    def __post_init__(self):
        _fields(self)
        _range("chain length", len(self.chain), 1, 4)
        if len(set(self.chain)) != len(self.chain):
            raise ValueError("chain: repeated function types are unsupported in version 1")
        _range("demand_mbps", self.demand_mbps, 2, 20)
        _range("packet_bits", self.packet_bits, 512, 12000)
        _positive("delay_limit_seconds", self.delay_limit_seconds)


@dataclass(frozen=True, slots=True)
class Satellite(Record):
    id: str
    cpu_capacity_mips: float
    access_capacity: int
    egress_capacity: int
    max_active_instances: int

    def __post_init__(self):
        _fields(self)
        _range("cpu_capacity_mips", self.cpu_capacity_mips, 0, 2000)
        for name in ("access_capacity", "egress_capacity", "max_active_instances"):
            _range(name, getattr(self, name), 0)


@dataclass(frozen=True, slots=True)
class InstanceKey(Record):
    function_type_id: str
    instance_id: str
    satellite_id: str

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.function_type_id, self.instance_id, self.satellite_id


@dataclass(frozen=True, slots=True)
class Radio(Record):
    carrier_hz: float
    transmit_watts: float
    user_gain_dbi: float
    satellite_gain_dbi: float
    bandwidth_hz: float
    temperature_kelvin: float
    interference_model: Literal["exogenous"]
    external_interference_watts: float
    speed_of_light_mps: float
    boltzmann_joules_per_kelvin: float

    def __post_init__(self):
        _fields(self)
        for name in ("carrier_hz", "transmit_watts", "bandwidth_hz", "temperature_kelvin",
                     "speed_of_light_mps", "boltzmann_joules_per_kelvin"):
            _positive(name, getattr(self, name))
        _range("external_interference_watts", self.external_interference_watts, 0)


@dataclass(frozen=True, slots=True)
class NamedSeed(Record):
    stream: Literal["layout", "chain", "demand", "delay", "cpu", "coefficients", "overhead"]
    seed: int

    def __post_init__(self):
        _fields(self)
        _range("seed", self.seed, 0)


# Explicit draw scopes, not per-user copies of slice/type parameters (D27).
DRAW_SCOPES = {
    "chain": ("slice", "function_ids"),
    "demand_mbps": ("slice", "Mbps"),
    "delay_limit_seconds": ("slice", "seconds"),
    "cpu_capacity_mips": ("satellite", "MIPS"),
    "psi_instructions_per_bit": ("function_type", "instructions/bit"),
    "omega_instructions_per_bit": ("function_type", "instructions/bit"),
    "base_overhead_mips": ("function_type", "MIPS"),
    "latitude_degrees": ("user", "degrees"),
    "longitude_degrees": ("user", "degrees"),
}


@dataclass(frozen=True, slots=True)
class Draw(Record):
    parameter: str
    scope: str
    entity_id: str
    units: str
    distribution: str
    value: float | tuple[str, ...]

    def __post_init__(self):
        _fields(self)
        if DRAW_SCOPES.get(self.parameter) != (self.scope, self.units):
            raise ValueError(f"draw {self.parameter}: unsupported scope or units")
        if not self.distribution.strip():
            raise ValueError("draw distribution must be recorded")
        check_type(self.value, tuple[str, ...] if self.parameter == "chain" else float, "draw.value")


@dataclass(frozen=True, slots=True)
class GenerationMetadata(Record):
    method: Literal["authored", "sampled"]
    rng_algorithm: str | None
    rng_library_version: str | None
    seeds: tuple[NamedSeed, ...]
    draws: tuple[Draw, ...]

    def __post_init__(self):
        _fields(self)
        _unique((s.stream for s in self.seeds), "seed streams")
        _unique(((d.parameter,d.entity_id) for d in self.draws), "draws")
        if self.method == "authored":
            if self.seeds or self.draws or self.rng_algorithm is not None or self.rng_library_version is not None:
                raise ValueError("authored inputs must not claim random generation")
        elif not (self.rng_algorithm and self.rng_library_version and self.draws
                  and {s.stream for s in self.seeds} ==
                  {"layout","chain","demand","delay","cpu","coefficients","overhead"}):
            raise ValueError("sampled generation requires RNG/version, all seven named seeds and draws")


@dataclass(frozen=True, slots=True)
class TraceMetadata(Record):
    scenario_group_id: str
    root_lineage_id: str
    constellation_id: str
    layout_id: str
    demand_family_id: str
    epoch_utc: str | None
    interval_start_seconds: float
    interval_end_seconds: float
    generation: GenerationMetadata

    def __post_init__(self):
        _fields(self)
        _range("interval_start_seconds", self.interval_start_seconds, 0)
        if self.interval_end_seconds <= self.interval_start_seconds:
            raise ValueError("trace interval end must follow start")
        if self.epoch_utc is not None:
            try:
                epoch = datetime.fromisoformat(self.epoch_utc.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("epoch_utc: expected ISO timestamp") from exc
            if epoch.utcoffset() is None or epoch.utcoffset().total_seconds() != 0:
                raise ValueError("epoch_utc: UTC timezone required")


@dataclass(frozen=True, slots=True)
class AccessLink(Record):
    user_id: str
    satellite_id: str
    distance_m: float

    def __post_init__(self):
        _fields(self)
        _positive("distance_m", self.distance_m)


@dataclass(frozen=True, slots=True)
class AccessWindow(Record):
    window_index: int
    links: tuple[AccessLink, ...]

    def __post_init__(self):
        _fields(self)
        _range("window_index", self.window_index, 0)
        _unique(((l.user_id,l.satellite_id) for l in self.links), "access links")


@dataclass(frozen=True, slots=True)
class GroundLink(Record):
    satellite_id: str
    ground_station_id: str
    distance_m: float

    def __post_init__(self):
        _fields(self)
        _positive("distance_m", self.distance_m)


@dataclass(frozen=True, slots=True)
class ISLLink(Record):
    satellite_a_id: str
    satellite_b_id: str
    distance_m: float

    def __post_init__(self):
        _fields(self)
        _positive("distance_m", self.distance_m)
        if self.satellite_a_id == self.satellite_b_id:
            raise ValueError("ISL endpoints must differ; colocation is an identity path")


FAMILIES = {"toy-v1":"authored_toy", "paper-inputs-v1":"reference_audit",
            "development-physical-v1":"development_candidate"}


@dataclass(frozen=True, slots=True)
class PhysicalOrbit(Record):
    """Frozen D09 v1 inputs; changing geometry requires a new approved family."""
    earth_radius_m: float = 6371000.0
    gravitational_parameter_m3_s2: float = 3.986004418e14
    rotation_rad_s: float = 7.2921150e-5
    altitude_m: float = 500000.0
    inclination_degrees: float = 88.0
    planes: int = 4
    satellites_per_plane: int = 15
    phasing_factor: int = 1
    raan_degrees: tuple[float, ...] = (0.0,45.0,90.0,135.0)
    elevation_mask_degrees: float = 10.0
    epoch_utc: str = '2026-01-01T00:00:00Z'
    greenwich_angle_at_epoch_rad: float = 0.0
    angular_roundoff_radians: float = 1e-12

    def __post_init__(self):
        _fields(self)
        if any(getattr(self,f.name)!=f.default for f in fields(self)):
            raise ValueError('physical v1 constants are frozen; a changed geometry requires a new approved family')


@dataclass(frozen=True, slots=True)
class Scenario(Record):
    schema_version: Literal[1]
    scenario_id: str
    family_id: str
    family_classification: Literal["authored_toy", "reference_audit", "development_candidate", "analytical_fixture"]
    window_count: int
    window_seconds: float
    metadata: TraceMetadata
    radio: Radio
    function_types: tuple[FunctionType, ...]
    slices: tuple[Slice, ...]
    users: tuple[User, ...]
    ground_stations: tuple[GroundStation, ...]
    satellites: tuple[Satellite, ...]
    instances: tuple[InstanceKey, ...]
    access_schedule: tuple[AccessWindow, ...]
    ground_links: tuple[GroundLink, ...]
    isl_links: tuple[ISLLink, ...]
    orbit: PhysicalOrbit | None = None

    def __post_init__(self):
        _fields(self)
        _positive("window_count", self.window_count)
        _positive("window_seconds", self.window_seconds)
        if self.family_id in FAMILIES:
            if self.family_classification != FAMILIES[self.family_id]:
                raise ValueError("family_classification conflicts with approved family")
        elif self.family_classification != "analytical_fixture":
            raise ValueError("unknown physical/toy family; versioned approval required")
        if self.orbit is not None:
            if (self.family_id not in ('paper-inputs-v1','development-physical-v1')
                    or len(self.satellites)!=60 or self.window_count!=14 or self.window_seconds!=60
                    or self.metadata.epoch_utc!=self.orbit.epoch_utc or self.metadata.interval_start_seconds!=0
                    or self.metadata.generation.method!='sampled' or self.ground_links or self.isl_links
                    or any(u.coordinates is None for u in self.users) or any(g.coordinates is None for g in self.ground_stations)):
                raise ValueError('physical source requires approved sampled v1 geometry; ground/ISLs are derived per window')
            populations=(30,6,5) if self.family_id=='paper-inputs-v1' else (4,2,2)
            if (len(self.users)!=populations[0] or len(self.slices)!=populations[1] or len(self.function_types)!=8
                    or any(sum(u.slice_id==sl.id for u in self.users)!=populations[2] for sl in self.slices)
                    or any((n.access_capacity,n.egress_capacity,n.max_active_instances)!=(5,5,8) or n.cpu_capacity_mips<1000 for n in self.satellites)
                    or any(f.psi_instructions_per_bit!=f.omega_instructions_per_bit or not 1<=f.base_overhead_mips<=17 for f in self.function_types)
                    or any(not 2<=len(sl.chain)<=4 or sl.packet_bits!=12000 or not .035<=sl.delay_limit_seconds<=.150 for sl in self.slices)
                    or self.radio!=Radio(14e9,.1,15,40,100e6,290,'exogenous',0,299792458,1.380649e-23)
                    or {g.id:(g.coordinates.latitude_degrees,g.coordinates.longitude_degrees) for g in self.ground_stations}!={'g0':(49.93,-79.53),'g1':(49.93,-69.53)}
                    or any(not 49<=u.coordinates.latitude_degrees<=51 or not -80<=u.coordinates.longitude_degrees<=-69 for u in self.users)):
                raise ValueError('physical family population, ranges or capacity assumptions differ from frozen v1')
            expected_instances={(f.id,i,n.id) for f in self.function_types for n in self.satellites for i in ('i0','i1')}
            if {i.identity for i in self.instances}!=expected_instances:raise ValueError('physical v1 needs two stable instances per type/host')
            for index,u in enumerate(self.users):
                lat,lon=math.radians(u.coordinates.latitude_degrees),math.radians(u.coordinates.longitude_degrees)
                for other in self.users[:index]:
                    a,b=math.radians(other.coordinates.latitude_degrees),math.radians(other.coordinates.longitude_degrees)
                    hav=math.sin((lat-a)/2)**2+math.cos(lat)*math.cos(a)*math.sin((lon-b)/2)**2
                    if 2*math.asin(math.sqrt(max(0,min(1,hav))))+self.orbit.angular_roundoff_radians<math.radians(.5):
                        raise ValueError('physical layout violates .5 degree user separation')
        for name in ("function_types", "slices", "users", "ground_stations", "satellites"):
            values = getattr(self, name)
            if not values:
                raise ValueError(f"{name}: must not be empty")
            _unique((x.id for x in values), name)
        functions = {f.id for f in self.function_types}
        satellites = {s.id for s in self.satellites}
        slices = {s.id for s in self.slices}
        users = {u.id for u in self.users}
        ground = {g.id for g in self.ground_stations}
        for u in self.users:
            _known(u.slice_id, slices, "slice")
        for sl in self.slices:
            for f in sl.chain:
                _known(f, functions, "function")
        _unique((i.identity for i in self.instances), "instances")
        for i in self.instances:
            _known(i.function_type_id, functions, "function")
            _known(i.satellite_id, satellites, "satellite")
        if (len(self.access_schedule) != self.window_count
                or any(w.window_index != i for i,w in enumerate(self.access_schedule))):
            raise ValueError("access_schedule: require each window once in chronological order")
        for w in self.access_schedule:
            for link in w.links:
                _known(link.user_id, users, "user")
                _known(link.satellite_id, satellites, "satellite")
        _unique(((l.satellite_id,l.ground_station_id) for l in self.ground_links), "ground links")
        for link in self.ground_links:
            _known(link.satellite_id, satellites, "satellite")
            _known(link.ground_station_id, ground, "ground station")
        _unique((tuple(sorted((l.satellite_a_id,l.satellite_b_id))) for l in self.isl_links), "undirected ISLs")
        for link in self.isl_links:
            _known(link.satellite_a_id, satellites, "satellite")
            _known(link.satellite_b_id, satellites, "satellite")
        span = self.metadata.interval_end_seconds-self.metadata.interval_start_seconds
        if not math.isclose(span,self.window_count*self.window_seconds,rel_tol=0,abs_tol=1e-9):
            raise ValueError("metadata interval must equal the episode duration")
        if self.metadata.generation.method == "sampled":
            expected_draws = {(parameter, entity.id)
                              for parameter, (scope, _) in DRAW_SCOPES.items()
                              for entity in {"slice":self.slices,"satellite":self.satellites,
                                             "function_type":self.function_types,"user":self.users}[scope]
                              if scope != "user" or entity.coordinates is not None}
            observed_draws = {(d.parameter,d.entity_id) for d in self.metadata.generation.draws}
            if observed_draws != expected_draws:
                raise ValueError("sampled generation: incomplete or unknown persisted draws")
        for draw in self.metadata.generation.draws:
            domain = {"slice":self.slices,"satellite":self.satellites,
                      "function_type":self.function_types,"user":self.users}[draw.scope]
            entity = next((e for e in domain if e.id == draw.entity_id), None)
            if entity is None:
                raise ValueError(f"unknown draw entity: {draw.entity_id}")
            source = entity.coordinates if draw.parameter in ("latitude_degrees","longitude_degrees") else entity
            if source is None or getattr(source,draw.parameter) != draw.value:
                raise ValueError("draw value disagrees with persisted scenario input")

    def slice_for_user(self, user_id: str) -> Slice:
        user = next((u for u in self.users if u.id == user_id), None)
        if user is None:
            raise ValueError(f"unknown user: {user_id}")
        return next(s for s in self.slices if s.id == user.slice_id)

    def activation_bound(self, function_type_id: str) -> int:
        """Count eligible user-stage occurrences; never slices, hosts or instances."""
        _known(function_type_id, {f.id for f in self.function_types}, "function")
        return sum(self.slice_for_user(u.id).chain.count(function_type_id) for u in self.users)


@dataclass(frozen=True, slots=True)
class AccessChoice(Record):
    user_id: str
    satellite_id: str


@dataclass(frozen=True, slots=True)
class EgressChoice(Record):
    user_id: str
    satellite_id: str
    ground_station_id: str


@dataclass(frozen=True, slots=True)
class StageAllocation(Record):
    user_id: str
    stage_index: int
    instance: InstanceKey
    cpu_mips: float

    def __post_init__(self):
        _fields(self)
        _range("stage_index", self.stage_index, 0)
        _range("cpu_mips", self.cpu_mips, 0)


@dataclass(frozen=True, slots=True)
class Deployment(Record):
    window_index: int
    access: tuple[AccessChoice, ...]
    egress: tuple[EgressChoice, ...]
    allocations: tuple[StageAllocation, ...]

    def __post_init__(self):
        _fields(self)
        _range("window_index", self.window_index, 0)
        _unique((a.user_id for a in self.access), "access choices")
        _unique((e.user_id for e in self.egress), "egress choices")
        _unique(((a.user_id,a.stage_index) for a in self.allocations), "stage allocations")


def validate_deployment_structure(deployment: Deployment, scenario: Scenario) -> None:
    """Check IDs/completeness/types only. C08 must independently check feasibility."""
    check_type(deployment, Deployment, "deployment")
    _range("window_index", deployment.window_index, 0, scenario.window_count-1)
    users = {u.id for u in scenario.users}
    satellites = {s.id for s in scenario.satellites}
    ground = {g.id for g in scenario.ground_stations}
    if {a.user_id for a in deployment.access} != users or {e.user_id for e in deployment.egress} != users:
        raise ValueError("deployment: missing or unknown user associations")
    for a in (*deployment.access,*deployment.egress):
        _known(a.satellite_id,satellites,"satellite")
    for e in deployment.egress:
        _known(e.ground_station_id,ground,"ground station")
    expected = {(u.id,k) for u in scenario.users for k in range(len(scenario.slice_for_user(u.id).chain))}
    if {(a.user_id,a.stage_index) for a in deployment.allocations} != expected:
        raise ValueError("deployment: missing or unknown user/stage allocation")
    identities = {i.identity for i in scenario.instances}
    for a in deployment.allocations:
        _known(a.instance.identity,identities,"instance")
        if scenario.slice_for_user(a.user_id).chain[a.stage_index] != a.instance.function_type_id:
            raise ValueError("deployment: incompatible function type at stage")


@dataclass(frozen=True, slots=True)
class WindowOutcome(Record):
    window_index: int
    status: Literal["candidate", "failed", "not_attempted"]
    deployment: Deployment | None
    failure_reason: str | None

    def __post_init__(self):
        _fields(self)
        _range("window_index", self.window_index, 0)
        if self.status == "candidate":
            if self.deployment is None or self.failure_reason is not None:
                raise ValueError("candidate requires deployment and no failure reason")
            if self.deployment.window_index != self.window_index:
                raise ValueError("deployment window differs from outcome")
        elif self.deployment is not None or not self.failure_reason:
            raise ValueError("failed/not_attempted outcome requires reason and no deployment")
