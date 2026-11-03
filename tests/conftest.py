"""Session-shared physical inputs; generation never retries for feasibility."""
import pytest


@pytest.fixture(scope='session')
def physical_traces():
    from stars_rl.topology.physical import generate_physical
    return {family:generate_physical(family,0) for family in ('paper-inputs-v1','development-physical-v1')}
