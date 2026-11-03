"""Per-packet delay, preserving every route segment and continuous CPU input."""
from dataclasses import dataclass
import math

from .units import SPEED_OF_LIGHT_MPS, _nonnegative, _positive


def propagation_seconds(distance_m: float, *, speed_of_light_mps: float = SPEED_OF_LIGHT_MPS) -> float:
    return _nonnegative(_nonnegative(distance_m, "distance_m")
                        / _positive(speed_of_light_mps, "speed_of_light_mps"), "propagation_seconds")


def minimum_cpu_mips(demand_mbps: float, psi_instructions_per_bit: float) -> float:
    """Throughput lower bound L. This does not select the optimizer's CPU allocation."""
    return _positive(_positive(demand_mbps, "demand_mbps")
                     * _positive(psi_instructions_per_bit, "psi_instructions_per_bit"), "minimum_cpu_mips")


def processing_seconds(packet_bits: float, omega_instructions_per_bit: float, cpu_mips: float) -> float:
    """Active-stage packet delay; unused assignments are handled by later model gating."""
    work = _positive(_positive(packet_bits, "packet_bits")
                     * _positive(omega_instructions_per_bit, "omega_instructions_per_bit"), "packet_instructions")
    ips = _positive(_positive(cpu_mips, "cpu_mips") * 1e6, "cpu_ips")
    return _positive(work / ips, "processing_seconds")


def serialization_seconds(bits: float, rate_bps: float) -> float:
    """Serialize the explicitly supplied bits. E2E callers supply packet_bits, not window load."""
    return _positive(_positive(bits, "bits") / _positive(rate_bps, "rate_bps"), "serialization_seconds")


@dataclass(frozen=True, slots=True)
class RouteDistances:
    user_access_m: float
    access_first_host_m: float
    internal_host_paths_m: tuple[float, ...]
    last_host_egress_m: float
    egress_ground_m: float

    def __post_init__(self):
        if type(self.internal_host_paths_m) is not tuple:
            raise ValueError("internal_host_paths_m: expected immutable tuple")
        for name in ("user_access_m", "access_first_host_m", "last_host_egress_m", "egress_ground_m"):
            _nonnegative(getattr(self, name), name)
        for distance in self.internal_host_paths_m:
            _nonnegative(distance, "internal_host_path_m")


@dataclass(frozen=True, slots=True)
class PropagationDelay:
    user_access_seconds: float
    access_first_host_seconds: float
    internal_host_seconds: tuple[float, ...]
    last_host_egress_seconds: float
    egress_ground_seconds: float

    def __post_init__(self):
        if type(self.internal_host_seconds) is not tuple:
            raise ValueError("internal_host_seconds: expected immutable tuple")
        for value in (self.user_access_seconds, self.access_first_host_seconds, *self.internal_host_seconds,
                      self.last_host_egress_seconds, self.egress_ground_seconds):
            _nonnegative(value, "propagation component")

    @property
    def total_seconds(self) -> float:
        return _sum((self.user_access_seconds, self.access_first_host_seconds, *self.internal_host_seconds,
                     self.last_host_egress_seconds, self.egress_ground_seconds))


def _sum(values: tuple[float, ...]) -> float:
    try:
        return _nonnegative(math.fsum(values), "total_seconds")
    except OverflowError as exc:
        raise ValueError("delay sum outside float range") from exc


def propagation_delay(route: RouteDistances, *, speed_of_light_mps: float = SPEED_OF_LIGHT_MPS) -> PropagationDelay:
    if not isinstance(route, RouteDistances):
        raise ValueError("route: expected RouteDistances")
    def seconds(distance):
        return propagation_seconds(distance, speed_of_light_mps=speed_of_light_mps)
    return PropagationDelay(seconds(route.user_access_m), seconds(route.access_first_host_m),
                            tuple(seconds(d) for d in route.internal_host_paths_m),
                            seconds(route.last_host_egress_m), seconds(route.egress_ground_m))


@dataclass(frozen=True, slots=True)
class ProcessingStage:
    omega_instructions_per_bit: float
    cpu_mips: float

    def __post_init__(self):
        _positive(self.omega_instructions_per_bit, "omega_instructions_per_bit")
        _positive(self.cpu_mips, "cpu_mips")


@dataclass(frozen=True, slots=True)
class DelayBreakdown:
    propagation: PropagationDelay
    processing_seconds_by_stage: tuple[float, ...]
    access_transmission_seconds: float

    def __post_init__(self):
        if not isinstance(self.propagation, PropagationDelay):
            raise ValueError("propagation: expected PropagationDelay")
        if type(self.processing_seconds_by_stage) is not tuple or not self.processing_seconds_by_stage:
            raise ValueError("processing_seconds_by_stage: expected nonempty immutable tuple")
        for delay in self.processing_seconds_by_stage:
            _positive(delay, "processing_seconds")
        _positive(self.access_transmission_seconds, "access_transmission_seconds")

    @property
    def processing_seconds(self) -> float:
        return _sum(self.processing_seconds_by_stage)

    @property
    def total_seconds(self) -> float:
        return _sum((self.propagation.total_seconds, self.processing_seconds, self.access_transmission_seconds))


def end_to_end_delay(route: RouteDistances, packet_bits: float, stages: tuple[ProcessingStage, ...],
                     rate_bps: float, *, speed_of_light_mps: float = SPEED_OF_LIGHT_MPS) -> DelayBreakdown:
    """One packet unchanged along the chain. Distances are already resolved paths.

    Each internal_host_paths_m entry is the path between consecutive stage hosts,
    not an individual ISL edge. C05 computes paths; C08 checks selected IDs/routes.
    """
    if not isinstance(route, RouteDistances):
        raise ValueError("route: expected RouteDistances")
    if type(stages) is not tuple or not stages or not all(isinstance(s, ProcessingStage) for s in stages):
        raise ValueError("stages: expected nonempty immutable tuple of ProcessingStage")
    if len(route.internal_host_paths_m) != len(stages) - 1:
        raise ValueError("route: require exactly one internal path per consecutive stage pair")
    return DelayBreakdown(propagation_delay(route, speed_of_light_mps=speed_of_light_mps),
                          tuple(processing_seconds(packet_bits, s.omega_instructions_per_bit, s.cpu_mips)
                                for s in stages), serialization_seconds(packet_bits, rate_bps))
