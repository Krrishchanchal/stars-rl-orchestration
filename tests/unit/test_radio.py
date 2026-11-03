"""C04 numeric radio oracles; occupancy constraints themselves enter at C07."""
from dataclasses import replace
from pathlib import Path
import math

import pytest

from stars_rl.config import load_scenario
from stars_rl.physics.radio import (
    access_link, access_rate_table, received_power_watts, shared_bandwidth_hz,
    thermal_noise_watts, sinr, shannon_rate_bps,
)


def toy_radio():
    return load_scenario(Path(__file__).resolve().parents[2]/"configs/toy.yaml").radio


def test_direct_algebraic_radio_oracles():
    # lambda=1 m and distance=1/(4*pi) give path factor 1; unity antenna gains.
    p=received_power_watts(distance_m=1/(4*math.pi),transmit_watts=8,carrier_hz=299792458,
                           user_gain_dbi=0,satellite_gain_dbi=0)
    assert p == pytest.approx(8,rel=1e-14)
    assert thermal_noise_watts(4,2,boltzmann_joules_per_kelvin=1) == 8
    assert sinr(8,8,0) == 1
    assert sinr(8,8,8) == .5
    assert shannon_rate_bps(4,1) == 4  # 4*log2(2)
    assert shannon_rate_bps(4,3) == 8  # 4*log2(4)
    assert shannon_rate_bps(4,0) == 0


def test_toy_against_independent_decimal_reference():
    # 60-digit Decimal derivation with literal pi, 10**5.5 combined gain,
    # wavelength=299792458/14e9, distance=500000, k=1.380649e-23, T=290.
    # These constants were calculated without production helpers.
    expected_rates=[93912842.05644351,75160797.65360864,63590053.21145122,55581533.33135109]
    table=access_rate_table(500000,4,toy_radio())
    assert table[0] is None
    for n,expected in enumerate(expected_rates,1):
        link=table[n]
        assert link.occupancy == n
        assert link.received_power_watts == pytest.approx(3.6730394914928883e-13,rel=2e-14)
        assert link.noise_watts == pytest.approx(4.0038821e-13/n,rel=2e-14)
        assert link.rate_bps == pytest.approx(expected,rel=2e-14)
        # Same-helper table/direct agreement is consistency evidence only.
        assert link == access_link(500000,n,toy_radio())


def test_equal_bandwidth_sharing_recomputes_noise():
    r=replace(toy_radio(),carrier_hz=299792458,transmit_watts=8,user_gain_dbi=0,
              satellite_gain_dbi=0,bandwidth_hz=8,temperature_kelvin=2,boltzmann_joules_per_kelvin=1)
    one=access_link(1/(4*math.pi),1,r)
    two=access_link(1/(4*math.pi),2,r)
    assert (one.bandwidth_hz,one.noise_watts,one.sinr) == pytest.approx((8,16,.5))
    assert (two.bandwidth_hz,two.noise_watts,two.sinr,two.rate_bps) == pytest.approx((4,8,1,4))
    assert two.rate_bps != pytest.approx(one.rate_bps/2)


def test_empty_occupancy_has_no_active_rate():
    assert shared_bandwidth_hz(100e6,0) is None
    assert shared_bandwidth_hz(100e6,2) == 50e6
    assert access_link(500000,0,toy_radio()) is None
    assert access_rate_table(500000,0,toy_radio()) == (None,)


def test_distance_and_interference_effects():
    r=toy_radio()
    near=access_link(500000,1,r)
    far=access_link(1000000,1,r)
    noisy=access_link(500000,1,replace(r,external_interference_watts=1e-12))
    assert far.received_power_watts == pytest.approx(near.received_power_watts/4)
    assert noisy.rate_bps < near.rate_bps
    # For these fixed powers/noise-density inputs, more bandwidth increases rate;
    # SINR also changes, so fixed-SINR linear scaling is not assumed.
    assert access_link(500000,1,replace(r,bandwidth_hz=200e6)).rate_bps > near.rate_bps


@pytest.mark.parametrize("occupancy", [-1,1.5,True,float("nan")])
def test_invalid_occupancy(occupancy):
    with pytest.raises(ValueError): access_link(500000,occupancy,toy_radio())


@pytest.mark.parametrize("distance", [0,-1,float("inf"),float("nan")])
def test_invalid_radio_distance(distance):
    with pytest.raises(ValueError): access_link(distance,1,toy_radio())


def test_invalid_denominators_and_negative_powers():
    for call in [lambda: thermal_noise_watts(0,290),lambda: thermal_noise_watts(100e6,0),
                 lambda: sinr(1,0,0),lambda: sinr(-1,1,0),lambda: sinr(1,1,-1),
                 lambda: shannon_rate_bps(0,1),lambda: shannon_rate_bps(1,-1),
                 lambda: shared_bandwidth_hz(0,0)]:
        with pytest.raises(ValueError): call()


@pytest.mark.parametrize("bad", [float("nan"),float("inf"),True])
def test_scalar_radio_rejects_nonfinite_or_boolean_inputs(bad):
    for call in [lambda: thermal_noise_watts(bad,290),lambda: sinr(bad,1,0),
                 lambda: sinr(1,bad,0),lambda: sinr(1,1,bad),lambda: shannon_rate_bps(1,bad)]:
        with pytest.raises(ValueError): call()


def test_weak_signal_does_not_disappear_through_one_plus_rounding():
    # log2(1+x) / x -> 1/ln(2); the next-order correction is below double precision here.
    assert shannon_rate_bps(1,1e-20) == pytest.approx(1.4426950408889634e-20,rel=1e-14,abs=0)
