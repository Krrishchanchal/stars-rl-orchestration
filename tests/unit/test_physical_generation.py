"""Draw scopes/reproducibility and independent physical cache checks."""
from dataclasses import replace
import hashlib
import math
import random
from pathlib import Path
import pytest

from stars_rl.config import load_scenario
from stars_rl.models import Coordinates,GroundStation
from stars_rl.topology.audit import audit_trace,capacity_matching,preflight,region_cap_bound
from stars_rl.topology.physical import generate_physical,named_seeds,sample_layout,GenerationError
from stars_rl.topology.trace import build_trace,save_trace,load_trace
from stars_rl.validation.physical import verify_window


def test_legacy_toy_hash_unchanged():
    t=build_trace(load_scenario(Path(__file__).resolve().parents[2]/'configs/toy.yaml'))
    assert t.content_hash=='6c6e0c00f1be0f1563afdd3b04d5450d01b6cbfbf076620d9dc1ab12cfb8e5ec'


def test_sample_ranges_scopes_separation_and_stream_independence(physical_traces):
    t,stats=physical_traces['paper-inputs-v1'];s=t.scenario
    assert len(s.users)==30 and len(s.slices)==6 and len(s.instances)==960
    assert stats['accepted_users']==30 and stats['attempts']>=30
    assert len({seed.seed for seed in s.metadata.generation.seeds})==7
    for i,u in enumerate(s.users):
        lat=math.radians(u.coordinates.latitude_degrees);lon=math.radians(u.coordinates.longitude_degrees)
        for v in s.users[:i]:
            other_lat=math.radians(v.coordinates.latitude_degrees);other_lon=math.radians(v.coordinates.longitude_degrees)
            hav=math.sin((lat-other_lat)/2)**2+math.cos(lat)*math.cos(other_lat)*math.sin((lon-other_lon)/2)**2
            assert 2*math.asin(math.sqrt(hav))>=math.radians(.5)-1e-14
    cpu_seed=int.from_bytes(hashlib.sha256(b'physical-generator-v1:0:cpu').digest(),'big')
    assert s.satellites[0].cpu_capacity_mips==random.Random(cpu_seed).uniform(1000,2000)
    dev,_=physical_traces['development-physical-v1']
    assert [u.coordinates for u in s.users[:4]]==[u.coordinates for u in dev.scenario.users]
    assert s.satellites==dev.scenario.satellites and s.function_types==dev.scenario.function_types
    assert s.metadata.root_lineage_id==dev.scenario.metadata.root_lineage_id
    assert all(f.psi_instructions_per_bit==f.omega_instructions_per_bit for f in s.function_types)
    assert all(sum(u.slice_id==sl.id for u in s.users)==5 for sl in s.slices)
    assert set(named_seeds(0).values()).isdisjoint(named_seeds(1).values())


def test_reproducible_generation_does_not_mutate_global_rng(physical_traces):
    state=random.getstate();again,stats=generate_physical('development-physical-v1',0)
    assert random.getstate()==state
    expected,_=physical_traces['development-physical-v1']
    assert again==expected and again.content_hash==expected.content_hash


def test_generation_failure_is_explicit_and_does_not_retry_seed():
    with pytest.raises(GenerationError) as info:sample_layout(random.Random(0),4,max_attempts=1)
    assert info.value.diagnostics=={'attempts':1,'accepted_users':1,'requested_users':4}


def test_independent_all_snapshot_geometry_and_dynamic_links(physical_traces):
    t,_=physical_traces['development-physical-v1']
    for w in t.windows:
        assert verify_window(t.scenario,w)>0
        assert w.start_seconds==w.window_index*60
    assert t.scenario.ground_links==t.scenario.isl_links==()
    assert t.windows[0].ground_distances_m!=t.windows[1].ground_distances_m
    assert t.windows[0].isl_links!=t.windows[1].isl_links


def test_physical_serialization_and_corrupt_cache_rejection(physical_traces,tmp_path):
    t,_=physical_traces['development-physical-v1'];path=tmp_path/'physical.json';save_trace(t,path)
    again=load_trace(path);assert again==t
    w=t.windows[0];matrix=[list(row) for row in w.ground_distances_m]
    row,col=next((i,j) for i,r in enumerate(matrix) for j,v in enumerate(r) if v is not None)
    matrix[row][col]+=1
    with pytest.raises(ValueError,match='slant'):verify_window(t.scenario,replace(w,ground_distances_m=tuple(map(tuple,matrix))))
    with pytest.raises(ValueError,match='ISLs'):verify_window(t.scenario,replace(w,isl_links=w.isl_links[1:]))


def test_independent_cap_bound_and_uncensored_reference(physical_traces):
    bound=region_cap_bound()
    assert bound['cap_angle_degrees']==pytest.approx(14.056535,abs=1e-6)
    assert bound['plane_distances_at_epoch_degrees']==pytest.approx([40.223203389,35.862892981,11.443845906,16.833793424],abs=1e-8)
    assert bound['eligible_planes']==[2,3]
    assert bound['maximum_region_visible_satellites']==4 and bound['reference_access_capacity_bound']==20<30
    t,_=physical_traces['paper-inputs-v1'];report=audit_trace(t)
    assert not report['all_windows_necessary_passed']
    assert all(w['region_union_visible_satellites']<=4 and w['preflight']['access']['flow']<=20 for w in report['windows'])
    assert all(w['maximum_isl_degree']<=4 for w in report['windows'])
    dev,_=physical_traces['development-physical-v1'];report=audit_trace(dev)
    assert not report['all_windows_necessary_passed']
    assert any(w['covered_users']<4 for w in report['windows'])


def test_matching_certificate_and_distinct_gateway_pool(temporal_case):
    c=capacity_matching(('u0','u1'),('a','b'),{('u0','a'),('u1','a')},{'a':1,'b':1})
    assert c['flow']==c['min_cut_capacity']==1 and len(c['unmatched_users'])==1
    assert c['bottleneck_satellites']==['a']
    s,w,p=temporal_case
    s=replace(s,ground_stations=(*s.ground_stations,GroundStation('g1',None)),
              satellites=tuple(replace(n,egress_capacity=1) for n in s.satellites))
    w=replace(w,ground_station_ids=('g0','g1'),ground_distances_m=((500000,500000),(None,None),(None,None)))
    check=preflight(s,w)
    assert check['egress']['flow']==1  # two GS choices do not double satellite capacity


def test_preflight_blocks_physical_reference_before_any_model(physical_traces):
    from stars_rl.simulation import simulate,RuntimeServices
    t,_=physical_traces['paper-inputs-v1']
    def forbidden(*args,**kwargs):raise AssertionError('known preflight failure must not build optimizer')
    result=simulate(t,services=RuntimeServices(stage1=forbidden,stage2=forbidden,monolithic=forbidden))
    assert result.status=='failed' and result.transition_valid
    assert result.total_budget_seconds==60
    assert result.windows[0].reason=='preflight_infeasible'
    assert all(stage.raw_status=='not_attempted' for stage in result.windows[0].stages.values())
    assert result.windows[0].preflight['access']['flow']<30
    assert all(w.status=='not_attempted' for w in result.windows[1:])


def test_full_validator_independently_checks_physical_inputs_without_solver(physical_traces):
    from stars_rl.validation.deployment import validate_export
    t,_=physical_traces['development-physical-v1'];w=t.windows[11]
    raw={'export_schema_version':1,'scenario_id':t.scenario.scenario_id,'window_index':11,'validation':'not_run',
         'solver_result':{'stage':'input_geometry_only_no_solver','raw_status':'not_attempted','has_incumbent':False,'values':{}},'diagnostics':{},'candidate':None}
    result=validate_export(t.scenario,w,raw)
    assert result.status=='no_incumbent' and result.reason=='not_attempted' and not result.valid
    broken=replace(w,isl_links=w.isl_links[1:])
    assert validate_export(t.scenario,broken,raw).status=='input_error'


def test_physical_family_cannot_reduce_users_raise_capacity_or_collocate(physical_traces):
    t,_=physical_traces['development-physical-v1'];s=t.scenario
    with pytest.raises(ValueError,match='population'):
        replace(s,users=s.users[:2])
    with pytest.raises(ValueError,match='capacity'):
        replace(s,satellites=(replace(s.satellites[0],access_capacity=6),*s.satellites[1:]))
    with pytest.raises(ValueError,match='separation'):
        replace(s,users=(s.users[0],replace(s.users[1],coordinates=s.users[0].coordinates),*s.users[2:]))


def test_changed_physical_access_source_not_trusted_as_authored_data(physical_traces):
    t,_=physical_traces['development-physical-v1'];s=t.scenario
    first=s.access_schedule[0];links=(replace(first.links[0],distance_m=first.links[0].distance_m+1),*first.links[1:])
    bad=replace(s,access_schedule=(replace(first,links=links),*s.access_schedule[1:]))
    with pytest.raises(ValueError,match='physical access source'):build_trace(bad)
