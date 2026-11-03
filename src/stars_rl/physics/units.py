"""Explicit SI conversions and finite-domain checks. No implicit unit inference."""
import math

SPEED_OF_LIGHT_MPS = 299792458.0
BOLTZMANN_JOULES_PER_KELVIN = 1.380649e-23


def _finite(value: float, name: str) -> float:
    try:
        if type(value) not in (float, int) or not math.isfinite(value):
            raise ValueError(f"{name}: expected finite number")
        return float(value)
    except OverflowError as exc:
        raise ValueError(f"{name}: number outside float range") from exc


def _nonnegative(value: float, name: str) -> float:
    value = _finite(value, name)
    if value < 0:
        raise ValueError(f"{name}: must be nonnegative")
    return value


def _positive(value: float, name: str) -> float:
    value = _finite(value, name)
    if value <= 0:
        raise ValueError(f"{name}: must be positive")
    return value


def _power_of_ten(exponent: float, name: str) -> float:
    try:
        return _positive(10.0 ** exponent, name)
    except OverflowError as exc:
        raise ValueError(f"{name}: result outside float range") from exc


def dbm_to_watts(dbm: float) -> float:
    return _power_of_ten((_finite(dbm, "dbm") - 30) / 10, "watts")


def dbi_to_linear(dbi: float) -> float:
    return _power_of_ten(_finite(dbi, "dbi") / 10, "linear_gain")


def milliseconds_to_seconds(milliseconds: float) -> float:
    return _nonnegative(milliseconds, "milliseconds") / 1000


def seconds_to_milliseconds(seconds: float) -> float:
    return _nonnegative(_nonnegative(seconds, "seconds") * 1000, "milliseconds")


def mbps_to_bps(mbps: float) -> float:
    return _nonnegative(_nonnegative(mbps, "mbps") * 1e6, "bps")


def bps_to_mbps(bps: float) -> float:
    return _nonnegative(bps, "bps") / 1e6


def mips_to_ips(mips: float) -> float:
    return _nonnegative(_nonnegative(mips, "mips") * 1e6, "instructions_per_second")


def ips_to_mips(ips: float) -> float:
    return _nonnegative(ips, "instructions_per_second") / 1e6


def kilometers_to_meters(kilometers: float) -> float:
    return _nonnegative(_nonnegative(kilometers, "kilometers") * 1000, "meters")


def meters_to_kilometers(meters: float) -> float:
    return _nonnegative(meters, "meters") / 1000
