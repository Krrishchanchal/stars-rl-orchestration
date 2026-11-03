"""Explicit temporal starting state; no optimizer used to obtain expectations."""
from pathlib import Path

import pytest

from stars_rl.config import load_scenario
from stars_rl.models import AccessChoice, Deployment, EgressChoice, InstanceKey, StageAllocation
from stars_rl.topology.trace import build_trace


@pytest.fixture
def temporal_case():
    scenario = load_scenario(Path(__file__).resolve().parents[2] / "configs/toy.yaml")
    previous = Deployment(0, tuple(AccessChoice(u, "s0") for u in ("u0", "u1")),
                          tuple(EgressChoice(u, "s0", "g0") for u in ("u0", "u1")),
                          tuple(StageAllocation(u, k, InstanceKey(f, "i0", "s0"), cpu)
                                for u, cpus in (("u0", (20, 40)), ("u1", (30, 60)))
                                for k, (f, cpu) in enumerate(zip(("f0", "f1"), cpus))))
    return scenario, build_trace(scenario).windows[1], previous
