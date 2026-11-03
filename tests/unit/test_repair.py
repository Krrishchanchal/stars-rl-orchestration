"""Independent visibility-order, failure and immutable-reference checks."""
from dataclasses import FrozenInstanceError, asdict, replace

import pytest

from stars_rl.models import AccessChoice, EgressChoice
from stars_rl.optimization.repair import repair_previous, partial_start_values


def test_retain_visible_links_even_when_alternative_is_closer(temporal_case):
    s, w, p = temporal_case
    w = replace(w, access_distances_m=((500000, 1, None), (500000, 1, None)),
                ground_distances_m=((500000,), (1,), (None,)))
    result = repair_previous(s, w, p)
    assert result.repair_candidate.access == p.access
    assert result.repair_candidate.egress == p.egress
    assert result.original_previous is p
    assert result.feasibility == "not_checked"


@pytest.mark.parametrize("distances,chosen", [((None, 10, 10), "s1"), ((None, 10, 5), "s2")])
def test_forced_access_nearest_tie_stable_ids_and_immutability(temporal_case, distances, chosen):
    s, w, p = temporal_case
    snapshot = asdict(p)
    w = replace(w, access_distances_m=(distances, (500000, 1, None)))
    r = repair_previous(s, w, p)
    assert r.repair_candidate.access == (AccessChoice("u0", chosen), AccessChoice("u1", "s0"))
    assert asdict(p) == snapshot
    assert tuple(a.instance for a in r.repair_candidate.placements) == tuple(a.instance for a in p.allocations)
    with pytest.raises(FrozenInstanceError):
        r.repair_candidate.window_index = 2


def test_repair_order_independent_of_previous_record_order(temporal_case):
    s, w, p = temporal_case
    shuffled = replace(p, access=tuple(reversed(p.access)), egress=tuple(reversed(p.egress)),
                       allocations=tuple(reversed(p.allocations)))
    a, b = repair_previous(s, w, p), repair_previous(s, w, shuffled)
    assert a.repair_candidate == b.repair_candidate
    assert partial_start_values(s, w, a) == partial_start_values(s, w, b)


@pytest.mark.parametrize("distances,expected", [
    (((9, 2), (1, 1), (None, None)), ("s0", "g1")),
    (((None, None), (9, 2), (1, 3)), ("s2", "g0")),
    (((None, None), (2, 2), (2, 2)), ("s1", "g0")),
])
def test_gateway_full_fallback_order(temporal_case, distances, expected):
    # Add a window GS domain for these pure visibility-order fixtures.
    from stars_rl.models import GroundStation
    s, w, p = temporal_case
    s = replace(s, ground_stations=(*s.ground_stations, GroundStation("g1", None)))
    # Old pair is g0. Make it invisible when retaining old satellite is tested.
    if expected == ("s0", "g1"):
        distances = ((None, 2), (1, 1), (None, None))
    w = replace(w, ground_station_ids=("g0", "g1"), ground_distances_m=distances)
    r = repair_previous(s, w, p)
    assert r.repair_candidate.egress == tuple(EgressChoice(u, *expected) for u in ("u0", "u1"))


@pytest.mark.parametrize("family", ["access", "egress", "both"])
def test_no_alternative_is_explicit_failure_not_deployment(temporal_case, family):
    s, w, p = temporal_case
    if family in ("access", "both"):
        w = replace(w, access_distances_m=((None, None, None), (None, None, None)))
    if family in ("egress", "both"):
        w = replace(w, ground_distances_m=((None,), (None,), (None,)))
    r = repair_previous(s, w, p)
    assert r.status == "failed" and len(r.failures) == (4 if family == "both" else 2)
    assert r.original_previous is p and r.feasibility == "not_checked"
    with pytest.raises(ValueError, match="failed repair"):
        partial_start_values(s, w, r)


def test_initial_has_no_reference_or_start(temporal_case):
    s, w, _ = temporal_case
    r = repair_previous(s, w, None)
    assert r.status == "initial" and r.repair_candidate is None
    assert partial_start_values(s, w, r) == {}


def test_partial_only_compatible_binaries_never_stale_auxiliaries(temporal_case):
    s, w, p = temporal_case
    r = repair_previous(s, w, p)
    values = partial_start_values(s, w, r)
    assert {key.split("[")[0] for key in values} == {"alpha", "xi", "beta"}
    assert "alpha[u0,s0]" not in values
    assert values["alpha[u0,s1]"] == 1
    assert values["beta[u0,0,f0,i0,s0]"] == 1
    assert values["beta[u0,0,f0,i1,s0]"] == 0
    assert set(values.values()) == {0, 1}
    association = partial_start_values(s, w, r, include_placement=False)
    assert not any(key.startswith("beta[") for key in association)
    assert len(association) == 7  # 3 visible access and 2*2 visible gateway pairs


def test_stale_forged_reference_and_wrong_window_rejected(temporal_case):
    s, w, p = temporal_case
    with pytest.raises(ValueError, match="earlier"):
        repair_previous(s, w, replace(p, window_index=1))
    r = repair_previous(s, w, p)
    forged = replace(r, repair_candidate=replace(r.repair_candidate, access=p.access))
    with pytest.raises(ValueError, match="current inputs"):
        partial_start_values(s, w, forged)
    with pytest.raises(ValueError, match="current inputs"):
        partial_start_values(s, replace(w, window_index=2), r)
