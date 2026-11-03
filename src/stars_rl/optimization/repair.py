"""Deterministic visibility references, never deployment feasibility repairs."""
from dataclasses import dataclass

from stars_rl.models import (
    AccessChoice, Deployment, EgressChoice, InstanceKey, Scenario,
    validate_deployment_structure,
)
from stars_rl.topology.trace import NetworkWindow
from .variables import check_inputs, name


@dataclass(frozen=True, slots=True)
class PlacementReference:
    user_id: str
    stage_index: int
    instance: InstanceKey


@dataclass(frozen=True, slots=True)
class RepairFailure:
    user_id: str
    family: str
    reason: str


@dataclass(frozen=True, slots=True)
class RepairCandidate:
    window_index: int
    access: tuple[AccessChoice, ...]
    egress: tuple[EgressChoice, ...]
    placements: tuple[PlacementReference, ...]


@dataclass(frozen=True, slots=True)
class RepairResult:
    original_previous: Deployment | None
    repair_candidate: RepairCandidate | None
    failures: tuple[RepairFailure, ...]
    status: str
    feasibility: str = "not_checked"


def repair_previous(scenario: Scenario, window: NetworkWindow,
                    previous: Deployment | None) -> RepairResult:
    """Retain valid links, otherwise minimize propagation with stable-ID ties.

    Capacities, throughput, CPU and complete routes are intentionally unchecked.
    A failure leaves explicit incomplete choices, never a deployable Deployment.
    Placements preserve full instance identity but carry no stale CPU or q/t.
    """
    check_inputs(scenario, window)
    if previous is None:
        return RepairResult(None, None, (), "initial")
    validate_deployment_structure(previous, scenario)
    if previous.window_index >= window.window_index:
        raise ValueError("repair requires an earlier committed deployment")
    old_access = {a.user_id: a.satellite_id for a in previous.access}
    old_egress = {e.user_id: (e.satellite_id, e.ground_station_id) for e in previous.egress}
    access, egress, failures = [], [], []
    pairs = sorted((window.ground_distance(s, g), s, g)
                   for s in window.satellite_ids for g in window.ground_station_ids
                   if window.ground_distance(s, g) is not None)
    for user in sorted(window.user_ids):
        choices = sorted((window.access_distance(user, s), s)
                         for s in window.satellite_ids
                         if window.access_distance(user, s) is not None)
        old = old_access[user]
        if window.access_distance(user, old) is not None:
            access.append(AccessChoice(user, old))
        elif choices:
            access.append(AccessChoice(user, choices[0][1]))
        else:
            failures.append(RepairFailure(user, "access", "no_visible_access"))
        old_sat, old_gs = old_egress[user]
        if window.ground_distance(old_sat, old_gs) is not None:
            egress.append(EgressChoice(user, old_sat, old_gs))
        else:
            same_sat = [p for p in pairs if p[1] == old_sat]
            alternatives = same_sat or pairs
            if alternatives:
                _, sat, gs = alternatives[0]
                egress.append(EgressChoice(user, sat, gs))
            else:
                failures.append(RepairFailure(user, "egress", "no_visible_gateway_pair"))
    placements = tuple(PlacementReference(a.user_id, a.stage_index, a.instance)
                       for a in sorted(previous.allocations, key=lambda a: (a.user_id, a.stage_index)))
    candidate = RepairCandidate(window.window_index, tuple(access), tuple(egress), placements)
    return RepairResult(previous, candidate, tuple(failures), "failed" if failures else "candidate")


def partial_start_values(scenario: Scenario, window: NetworkWindow,
                         repair: RepairResult, *, include_placement: bool = True) -> dict[str, float]:
    """Export only current-domain alpha/xi/(optional beta), including zeros.

    Submit through backend.submit_start(..., kind="partial"). Unknown auxiliaries
    must remain unknown. This export neither checks nor claims feasibility.
    """
    check_inputs(scenario, window)
    # Reconstruct the trusted repair rather than accepting forged/stale choices.
    expected = repair_previous(scenario, window, repair.original_previous)
    if repair != expected:
        raise ValueError("repair does not match current inputs")
    if repair.status == "initial":
        return {}
    if repair.status != "candidate":
        raise ValueError("failed repair cannot supply a reference/start")
    candidate = repair.repair_candidate
    access = {(a.user_id, a.satellite_id) for a in candidate.access}
    egress = {(e.user_id, e.satellite_id, e.ground_station_id) for e in candidate.egress}
    values = {name("alpha", u, s): float((u, s) in access)
              for u in window.user_ids for s in window.satellite_ids
              if window.access_distance(u, s) is not None}
    values.update({name("xi", u, s, g): float((u, s, g) in egress)
                   for u in window.user_ids for s in window.satellite_ids for g in window.ground_station_ids
                   if window.ground_distance(s, g) is not None})
    if include_placement:
        placements = {(a.user_id, a.stage_index, *a.instance.identity) for a in candidate.placements}
        for u in window.user_ids:
            for k, f in enumerate(scenario.slice_for_user(u).chain):
                for i in sorted(scenario.instances, key=lambda i: i.identity):
                    if i.function_type_id == f:
                        key = (u, k, *i.identity)
                        values[name("beta", *key)] = float(key in placements)
    return values
