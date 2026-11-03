"""Free-space uplink and equal-bandwidth Shannon calculations (paper eqs 3–4)."""
from dataclasses import dataclass
import math

from stars_rl.models import Radio
from .units import (
    SPEED_OF_LIGHT_MPS, BOLTZMANN_JOULES_PER_KELVIN,
    _nonnegative, _positive, dbi_to_linear,
)


def _occupancy(count: int) -> int:
    if type(count) is not int or count < 0:
        raise ValueError("occupancy: expected nonnegative integer")
    return count


def shared_bandwidth_hz(total_bandwidth_hz: float, occupancy: int) -> float | None:
    """None denotes no active user at n=0; never divide by zero or invent a rate."""
    total = _positive(total_bandwidth_hz, "total_bandwidth_hz")
    return _positive(total / occupancy, "bandwidth_hz") if _occupancy(occupancy) else None


def received_power_watts(*, distance_m: float, transmit_watts: float, carrier_hz: float,
                         user_gain_dbi: float, satellite_gain_dbi: float,
                         speed_of_light_mps: float = SPEED_OF_LIGHT_MPS) -> float:
    distance = _positive(distance_m, "distance_m")
    power = _positive(transmit_watts, "transmit_watts")
    wavelength = _positive(speed_of_light_mps, "speed_of_light_mps") / _positive(carrier_hz, "carrier_hz")
    gain = dbi_to_linear(user_gain_dbi) * dbi_to_linear(satellite_gain_dbi)
    try:
        result = power * gain * (wavelength / (4 * math.pi * distance)) ** 2
    except OverflowError as exc:
        raise ValueError("received power outside float range") from exc
    return _positive(result, "received_power_watts")


def thermal_noise_watts(bandwidth_hz: float, temperature_kelvin: float, *,
                        boltzmann_joules_per_kelvin: float = BOLTZMANN_JOULES_PER_KELVIN) -> float:
    noise = (_positive(boltzmann_joules_per_kelvin, "boltzmann_joules_per_kelvin")
             * _positive(temperature_kelvin, "temperature_kelvin")
             * _positive(bandwidth_hz, "bandwidth_hz"))
    return _positive(noise, "noise_watts")


def sinr(received_watts: float, noise_watts: float, interference_watts: float) -> float:
    denominator = _positive(_nonnegative(noise_watts, "noise_watts")
                            + _nonnegative(interference_watts, "interference_watts"), "noise_plus_interference")
    return _nonnegative(_nonnegative(received_watts, "received_watts") / denominator, "sinr")


def shannon_rate_bps(bandwidth_hz: float, signal_to_noise: float) -> float:
    # log1p preserves small positive SINR instead of rounding 1+SINR to 1.
    bandwidth = _positive(bandwidth_hz, "bandwidth_hz")
    ratio = _nonnegative(signal_to_noise, "sinr")
    return _nonnegative(bandwidth * math.log1p(ratio) / math.log(2), "rate_bps")


@dataclass(frozen=True, slots=True)
class LinkBudget:
    occupancy: int
    bandwidth_hz: float
    received_power_watts: float
    noise_watts: float
    interference_watts: float
    sinr: float
    rate_bps: float

    def __post_init__(self):
        if _occupancy(self.occupancy) == 0:
            raise ValueError("LinkBudget represents positive occupancy only")
        for name in ("bandwidth_hz", "received_power_watts", "noise_watts"):
            _positive(getattr(self, name), name)
        for name in ("interference_watts", "sinr", "rate_bps"):
            _nonnegative(getattr(self, name), name)


def access_link(distance_m: float, occupancy: int, radio: Radio) -> LinkBudget | None:
    """Exogenous radio inputs. Visibility and throughput constraints are later gates."""
    _positive(distance_m, "distance_m")
    if not isinstance(radio, Radio):
        raise ValueError("radio: expected validated Radio record")
    bandwidth = shared_bandwidth_hz(radio.bandwidth_hz, occupancy)
    if bandwidth is None:
        return None
    power = received_power_watts(distance_m=distance_m, transmit_watts=radio.transmit_watts,
                                 carrier_hz=radio.carrier_hz, user_gain_dbi=radio.user_gain_dbi,
                                 satellite_gain_dbi=radio.satellite_gain_dbi,
                                 speed_of_light_mps=radio.speed_of_light_mps)
    noise = thermal_noise_watts(bandwidth, radio.temperature_kelvin,
                               boltzmann_joules_per_kelvin=radio.boltzmann_joules_per_kelvin)
    ratio = sinr(power, noise, radio.external_interference_watts)
    return LinkBudget(occupancy, bandwidth, power, noise, radio.external_interference_watts,
                      ratio, shannon_rate_bps(bandwidth, ratio))


def access_rate_table(distance_m: float, max_occupancy: int, radio: Radio) -> tuple[LinkBudget | None, ...]:
    """Index n holds this candidate edge's rate at occupancy n; index 0 is None."""
    _occupancy(max_occupancy)
    return tuple(access_link(distance_m, n, radio) for n in range(max_occupancy + 1))
