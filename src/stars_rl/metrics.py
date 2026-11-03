"""Observed changes against original committed state, independent of objectives."""
from dataclasses import dataclass

from .models import Deployment, Scenario, validate_deployment_structure


@dataclass(frozen=True, slots=True)
class ChangeMetrics:
    access_switches: int | None
    egress_switches: int | None
    assignment_changes: int | None
    instance_id_changes: int | None
    host_changes: int | None
    instance_activations: int | None
    instance_deactivations: int | None
    alpha_l1: int | None
    xi_l1: int | None
    beta_l1: int | None
    d_alpha: float | None
    d_xi: float | None
    d_beta: float | None
    outage: int
    restoration: int
    initial_setup: bool


def change_metrics(scenario: Scenario, original_previous: Deployment | None,
                   final_deployment: Deployment | None, *,
                   previous_available: bool | None) -> ChangeMetrics:
    """Count a switch once; L1 counts its two one-hot flips.

    previous_available describes the immediately preceding outcome (None only
    before the first window). Keep original_previous across outages; restoration
    then compares with that last committed deployment. Missing final decisions
    have null change fields, not zero. Availability is a window-level event, not
    a packet loss or per-user outage measurement.
    """
    if previous_available is not None and type(previous_available) is not bool:
        raise ValueError("previous_available must be bool or None")
    if previous_available is True and original_previous is None:
        raise ValueError("available prior outcome requires committed state")
    if previous_available is None and original_previous is not None:
        raise ValueError("initial outcome cannot have committed prior state")
    for deployment in (original_previous, final_deployment):
        if deployment is not None:
            validate_deployment_structure(deployment, scenario)
    if (original_previous is not None and final_deployment is not None
            and original_previous.window_index >= final_deployment.window_index):
        raise ValueError("final deployment must follow committed prior state")
    available = final_deployment is not None
    outage = int(previous_available is True and not available)
    restoration = int(previous_available is False and available)
    initial = available and original_previous is None
    if not available:
        return ChangeMetrics(*([None] * 13), outage, restoration, False)
    if original_previous is None:
        return ChangeMetrics(*([0] * 13), outage, restoration, initial)
    old_a = {a.user_id: a.satellite_id for a in original_previous.access}
    old_x = {e.user_id: (e.satellite_id, e.ground_station_id) for e in original_previous.egress}
    old_b = {(a.user_id, a.stage_index): a.instance for a in original_previous.allocations}
    new_b = {(a.user_id, a.stage_index): a.instance for a in final_deployment.allocations}
    da = sum(old_a[a.user_id] != a.satellite_id for a in final_deployment.access)
    dx = sum(old_x[e.user_id] != (e.satellite_id, e.ground_station_id) for e in final_deployment.egress)
    db = sum(old_b[k] != new_b[k] for k in old_b)
    di = sum(old_b[k].instance_id != new_b[k].instance_id for k in old_b)
    dh = sum(old_b[k].satellite_id != new_b[k].satellite_id for k in old_b)
    old_active = {i.identity for i in old_b.values()}
    new_active = {i.identity for i in new_b.values()}
    users, stages = len(scenario.users), len(old_b)
    return ChangeMetrics(da, dx, db, di, dh, len(new_active - old_active),
                         len(old_active - new_active), 2 * da, 2 * dx, 2 * db,
                         da / users, dx / users, db / stages, outage, restoration, False)
