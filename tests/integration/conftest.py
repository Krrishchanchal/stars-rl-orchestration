"""Authored, disconnected two-host episodes with literal forced moves."""
from dataclasses import replace
from pathlib import Path
import pytest

from stars_rl.config import load_scenario
from stars_rl.models import AccessWindow,AccessLink
from stars_rl.topology.trace import build_trace


@pytest.fixture
def episode_trace():
    def make(*,forced=True,empty_window=None,cpu=100):
        s=load_scenario(Path(__file__).resolve().parents[2]/'configs/toy.yaml')
        satellites=tuple(replace(n,cpu_capacity_mips=cpu) for n in s.satellites if n.id in ('s0','s1'))
        schedule=tuple(AccessWindow(k,() if empty_window==k else (AccessLink('u0','s1' if forced and k>0 else 's0',500000),)) for k in range(3))
        s=replace(s,scenario_id='c12-forced-v1',family_id='c12-authored-v1',family_classification='analytical_fixture',
            function_types=(replace(s.function_types[0],base_overhead_mips=0),),slices=(replace(s.slices[0],chain=('f0',)),),
            users=(s.users[0],),satellites=satellites,instances=tuple(i for i in s.instances if i.function_type_id=='f0' and i.instance_id=='i0' and i.satellite_id in ('s0','s1')),
            access_schedule=schedule,isl_links=(),ground_links=tuple(replace(g,distance_m=300000 if g.satellite_id=='s0' else 500000) for g in s.ground_links))
        trace=build_trace(s)
        rates={w.window_index:{(u,n,k):12000000 for u in w.user_ids for n in w.satellite_ids if w.access_distance(u,n) is not None
                              for k in range(1,next(x.access_capacity for x in s.satellites if x.id==n)+1)} for w in trace.windows}
        return trace,rates
    return make
