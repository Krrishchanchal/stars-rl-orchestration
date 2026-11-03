"""Literal one-hot/event oracles, never objective auxiliary values."""
from dataclasses import replace

import pytest

from stars_rl.metrics import change_metrics
from stars_rl.models import AccessChoice, EgressChoice, InstanceKey
from stars_rl.optimization.repair import repair_previous


def test_one_switch_is_one_event_two_flips_and_half_normalized(temporal_case):
    s, w, p = temporal_case
    final = replace(p, window_index=1, access=(AccessChoice("u0", "s1"), p.access[1]))
    m = change_metrics(s, p, final, previous_available=True)
    assert (m.access_switches, m.alpha_l1, m.d_alpha) == (1, 2, .5)
    assert (m.assignment_changes, m.host_changes, m.instance_activations) == (0, 0, 0)
    # Repair equals final access, yet the forced switch is still counted.
    repaired = repair_previous(s, w, p)
    assert final.access == repaired.repair_candidate.access
    assert change_metrics(s, p, final, previous_available=True) == m


def test_host_changes_and_same_host_instance_changes_separate(temporal_case):
    s, _, p = temporal_case
    allocations = tuple(replace(a, instance=InstanceKey(a.instance.function_type_id, "i0", "s1"))
                        if a.user_id == "u0" else a for a in p.allocations)
    m = change_metrics(s, p, replace(p, window_index=1, allocations=allocations), previous_available=True)
    assert (m.assignment_changes, m.host_changes, m.instance_id_changes) == (2, 2, 0)
    assert (m.beta_l1, m.d_beta, m.instance_activations, m.instance_deactivations) == (4, .5, 2, 0)
    # u1 still uses both old instances: no deactivation charge.
    allocations = (replace(p.allocations[0], instance=InstanceKey("f0", "i1", "s0")), *p.allocations[1:])
    m = change_metrics(s, p, replace(p, window_index=1, allocations=allocations), previous_available=True)
    assert (m.assignment_changes, m.host_changes, m.instance_id_changes, m.instance_activations) == (1, 0, 1, 1)


def test_cpu_changes_do_not_count_and_unchanged_instance_identity_persists(temporal_case):
    s, _, p = temporal_case
    final = replace(p, window_index=1, allocations=tuple(replace(a, cpu_mips=a.cpu_mips+1) for a in p.allocations))
    m = change_metrics(s, p, final, previous_available=True)
    assert (m.beta_l1, m.host_changes, m.instance_id_changes, m.instance_activations) == (0, 0, 0, 0)


def test_gateway_pair_switch_counts_once_and_record_order_does_not_matter(temporal_case):
    s, _, p = temporal_case
    final = replace(p, window_index=1, access=tuple(reversed(p.access)),
                    allocations=tuple(reversed(p.allocations)),
                    egress=(p.egress[1], EgressChoice("u0", "s1", "g0")))
    m = change_metrics(s, p, final, previous_available=True)
    assert (m.egress_switches, m.xi_l1, m.d_xi) == (1, 2, .5)
    assert (m.access_switches, m.assignment_changes) == (0, 0)


def test_activation_charged_once_per_stable_instance_and_deactivation(temporal_case):
    s, _, p = temporal_case
    final = replace(p, window_index=1, allocations=tuple(replace(a, instance=InstanceKey(a.instance.function_type_id, "i1", "s0")) for a in p.allocations))
    m = change_metrics(s, p, final, previous_available=True)
    assert (m.assignment_changes, m.instance_activations, m.instance_deactivations) == (4, 2, 2)
    assert (m.beta_l1, m.d_beta) == (8, 1)


def test_initial_setup_and_missing_outcomes(temporal_case):
    s, _, p = temporal_case
    initial = change_metrics(s, None, p, previous_available=None)
    assert initial.initial_setup and initial.assignment_changes == initial.instance_activations == 0
    assert (initial.outage, initial.restoration) == (0, 0)
    failed = change_metrics(s, p, None, previous_available=True)
    assert (failed.outage, failed.restoration) == (1, 0)
    assert failed.access_switches is failed.beta_l1 is failed.instance_activations is None
    repeated = change_metrics(s, p, None, previous_available=False)
    assert repeated.outage == repeated.restoration == 0
    final = replace(p, window_index=2, access=(AccessChoice("u0", "s1"), p.access[1]))
    restored = change_metrics(s, p, final, previous_available=False)
    assert (restored.outage, restored.restoration, restored.access_switches) == (0, 1, 1)


def test_failure_before_first_success_does_not_invent_assignment_changes(temporal_case):
    s, _, p = temporal_case
    assert change_metrics(s, None, None, previous_available=None).beta_l1 is None
    m = change_metrics(s, None, replace(p, window_index=1), previous_available=False)
    assert m.initial_setup and m.restoration == 1 and m.assignment_changes == 0


@pytest.mark.parametrize("prior,availability", [(False, True), (True, None), (True, "yes")])
def test_inconsistent_history_rejected(temporal_case, prior, availability):
    s, _, p = temporal_case
    with pytest.raises(ValueError):
        change_metrics(s, p if prior else None, None, previous_available=availability)


def test_chronology_and_incomplete_structure_rejected(temporal_case):
    s, _, p = temporal_case
    with pytest.raises(ValueError):
        change_metrics(s, p, p, previous_available=True)
    with pytest.raises(ValueError):
        change_metrics(s, p, replace(p, window_index=1, access=()), previous_available=True)
