"""O-PACKET, O-COEFF and five-segment hand sums; no solver/graph builders."""
from dataclasses import replace

import pytest

from stars_rl.physics.delay import (
    RouteDistances, ProcessingStage, propagation_seconds, minimum_cpu_mips,
    processing_seconds, serialization_seconds, propagation_delay, end_to_end_delay,
)


def test_hand_derived_delays_and_workloads():
    assert propagation_seconds(300000) == pytest.approx(300000/299792458,rel=1e-14)
    assert propagation_seconds(0) == 0  # colocation, not an unavailable path
    assert minimum_cpu_mips(5,10) == 50  # 5e6 bit/s *10 /1e6
    assert processing_seconds(12000,10,100) == pytest.approx(.0012)  # 120000 /100e6
    assert serialization_seconds(12000,20e6) == pytest.approx(.0006)


def test_packet_is_not_window_traffic():
    generated_bits=2_000_000*60  # O-PACKET: 120 Mbit in a 60 s window
    assert generated_bits == 120000000
    assert serialization_seconds(generated_bits,20e6) == 6
    assert serialization_seconds(12000,20e6) == pytest.approx(.0006)


def test_psi_and_omega_remain_distinct():
    # O-COEFF: psi10 ->20 MIPS; omega20 ->0.012 s at that allocation.
    assert minimum_cpu_mips(2,10) == 20
    assert processing_seconds(12000,20,20) == pytest.approx(.012)
    assert processing_seconds(12000,10,20) == pytest.approx(.006)


def test_processing_decreases_with_cpu_without_fixing_allocation():
    delays=[processing_seconds(12000,10,cpu) for cpu in (20,40,100)]
    assert delays == pytest.approx([.006,.003,.0012])
    assert delays[0]>delays[1]>delays[2]


def test_five_route_segments_and_full_breakdown():
    # Five propagation classes: [300,600,(900+1200),1500,1800] km.
    route=RouteDistances(300000,600000,(900000,1200000),1500000,1800000)
    prop=propagation_delay(route,speed_of_light_mps=300000000)
    assert (prop.user_access_seconds,prop.access_first_host_seconds,prop.internal_host_seconds,
            prop.last_host_egress_seconds,prop.egress_ground_seconds) == (
                .001,.002,(.003,.004),.005,.006)
    assert prop.total_seconds == pytest.approx(.021)
    result=end_to_end_delay(route,12000,(ProcessingStage(10,100),ProcessingStage(20,100),
                                        ProcessingStage(10,200)),20e6,speed_of_light_mps=300000000)
    assert result.processing_seconds_by_stage == pytest.approx((.0012,.0024,.0006))
    assert result.processing_seconds == pytest.approx(.0042)
    assert result.access_transmission_seconds == pytest.approx(.0006)
    assert result.total_seconds == pytest.approx(.0258)


def test_single_stage_and_colocation():
    route=RouteDistances(500000,0,(),0,500000)
    result=end_to_end_delay(route,12000,(ProcessingStage(10,100),),20e6)
    assert result.propagation.internal_host_seconds == ()
    assert result.total_seconds == pytest.approx(1000000/299792458+.0012+.0006)
    two=replace(route,internal_host_paths_m=(0,))
    result=end_to_end_delay(two,12000,(ProcessingStage(10,100),ProcessingStage(20,100)),20e6)
    assert result.propagation.internal_host_seconds == (0,)


@pytest.mark.parametrize("bad", [0,-1,float("nan"),float("inf"),True,"10"])
def test_invalid_active_denominators_and_workloads(bad):
    for call in [lambda: processing_seconds(12000,10,bad),lambda: processing_seconds(bad,10,100),
                 lambda: processing_seconds(12000,bad,100),lambda: minimum_cpu_mips(bad,10),
                 lambda: minimum_cpu_mips(2,bad),lambda: serialization_seconds(12000,bad),
                 lambda: propagation_seconds(1,speed_of_light_mps=bad)]:
        with pytest.raises(ValueError): call()


@pytest.mark.parametrize("distance", [-1,float("nan"),float("inf"),None])
def test_unavailable_or_invalid_paths_are_not_zero(distance):
    with pytest.raises(ValueError): RouteDistances(1,1,(distance,),1,1)


def test_path_and_chain_dimensions_are_required():
    route=RouteDistances(1,1,(),1,1)
    with pytest.raises(ValueError): end_to_end_delay(route,12000,(),20e6)
    with pytest.raises(ValueError):
        end_to_end_delay(route,12000,(ProcessingStage(10,100),ProcessingStage(20,100)),20e6)
    with pytest.raises(ValueError): RouteDistances(1,1,[0],1,1)
