"""C05 literal connectivity/serialization/hash oracles; no placement optimizer."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from stars_rl.config import load_scenario, scenario_from_dict, scenario_to_dict
from stars_rl.models import Coordinates
from stars_rl.physics.delay import end_to_end_delay, ProcessingStage
from stars_rl.physics.radio import access_link
from stars_rl.topology.trace import (
    build_trace, trace_to_dict, trace_from_dict, trace_to_json, save_trace, load_trace,
    RouteUnavailableError,
)

ROOT=Path(__file__).resolve().parents[2]
ORACLES=json.loads((ROOT/"tests/fixtures/topology_oracles.json").read_text())


def toy():
    return load_scenario(ROOT/"configs/toy.yaml")


def fixture_scenario(case):
    # Explicit one-user analytical fixtures; no users are removed from production input.
    raw=scenario_to_dict(toy())
    raw.update(scenario_id=case["id"],family_id="connectivity-fixtures-v1",family_classification="analytical_fixture",
               window_count=1,users=[{"id":"u0","slice_id":"slice0","coordinates":None}],
               ground_stations=[{"id":"g0","coordinates":None}])
    raw["metadata"].update(interval_end_seconds=60)
    raw["slices"]=raw["slices"][:1]
    raw["slices"][0]["chain"]=["f0","f1"][:len(case["hosts"])]
    raw["satellites"]=[{"id":n,"cpu_capacity_mips":300,"access_capacity":2,"egress_capacity":2,
                        "max_active_instances":4} for n in case["nodes"]]
    raw["instances"]=[{"function_type_id":f,"instance_id":"i0","satellite_id":n}
                       for n in case["nodes"] for f in ["f0","f1"]]
    raw["access_schedule"]=[{"window_index":0,"links":[{"user_id":"u0","satellite_id":case["access"],"distance_m":500000}]}]
    raw["ground_links"]=[{"satellite_id":case["egress"],"ground_station_id":"g0","distance_m":500000}]
    raw["isl_links"]=[{"satellite_a_id":a,"satellite_b_id":b,"distance_m":w} for a,b,w in case["edges"]]
    return scenario_from_dict(raw)


def test_toy_literal_matrices_and_paths():
    t=build_trace(toy());expected=ORACLES["toy"]
    assert t.content_hash==ORACLES["toy_content_hash"]
    assert len(t.windows)==3
    assert [w.start_seconds for w in t.windows] == expected["start_seconds"]
    for k,w in enumerate(t.windows):
        assert list(w.satellite_ids) == expected["node_ids"]
        assert [list(row) for row in w.access_visibility] == expected["access_visibility"][k]
        assert [list(row) for row in w.ground_visibility] == expected["ground_visibility"]
        assert [[w.paths.get(a,b).distance_m for b in w.satellite_ids] for a in w.satellite_ids] == expected["distance_matrix_m"]
        assert w.paths.get("s0","s2").nodes == ("s0","s1","s2")
        assert w.access_distance("u0","s2") is None  # zero-capacity s2 retained, never pruned
        assert w.ground_distance("s2","g0") is None
    assert t.windows[0].access_distance("u0","s0")==500000
    assert t.windows[1].access_distance("u0","s0") is None
    assert t.windows[1].access_distances_m == t.windows[2].access_distances_m
    with pytest.raises(ValueError,match="unknown"):
        t.windows[0].access_distance("missing","s0")


@pytest.mark.parametrize("case",ORACLES["route_cases"],ids=lambda c:c["id"])
def test_isolated_route_fixtures(case):
    w=build_trace(fixture_scenario(case)).windows[0]
    args=("u0",case["access"],tuple(case["hosts"]),case["egress"],"g0")
    if "error" in case:
        with pytest.raises(RouteUnavailableError) as error:
            w.route_distances(*args)
        assert error.value.segment == case["error"]
    else:
        r=w.route_distances(*args)
        assert [r.user_access_m,r.access_first_host_m,list(r.internal_host_paths_m),r.last_host_egress_m,r.egress_ground_m] == case["expected"]


def test_distinct_access_and_egress_hand_witness():
    case=next(c for c in ORACLES["route_cases"] if c["id"]=="distinct-access-egress")
    s=fixture_scenario(case);w=build_trace(s).windows[0]
    r=w.route_distances("u0","a",("a","b"),"b","g0")
    # Independent witness: each stage100 MIPS + its type overhead5/10 fits300;
    # minimum CPU20/40; one access/egress flow each within separate pools2.
    assert 100+5<300 and 100+10<300 and 100>=20 and 100>=40
    rate=access_link(500000,1,s.radio).rate_bps
    assert rate>12e6
    delay=end_to_end_delay(r,12000,(ProcessingStage(10,100),ProcessingStage(20,100)),rate)
    conservative=1100000/299792458+.0012+.0024+.001
    assert delay.total_seconds<=conservative<.009<.05


def test_unavailable_visible_endpoints_are_typed_failures():
    w=build_trace(toy()).windows[1]
    with pytest.raises(RouteUnavailableError) as error:
        w.route_distances("u0","s0",("s1",),"s1","g0")
    assert error.value.segment=="access_visibility"
    with pytest.raises(RouteUnavailableError) as error:
        w.route_distances("u0","s1",("s1",),"s2","g0")
    assert error.value.segment=="ground_visibility"


def test_roundtrip_determinism_and_immutability(tmp_path):
    s=toy();t=build_trace(s)
    assert t == trace_from_dict(trace_to_dict(t))
    assert trace_to_json(t)==trace_to_json(build_trace(s))
    save_trace(t,tmp_path/"trace.json")
    assert load_trace(tmp_path/"trace.json")==t
    copy=deepcopy(t)
    with pytest.raises(FrozenInstanceError): copy.windows[0].duration_seconds=1
    data=trace_to_dict(copy);data["windows"][0]["access_distances_m"][0][0]=1
    assert t.windows[0].access_distance("u0","s0")==500000
    # Fresh processes cannot depend on interpreter hash randomization.
    command="from stars_rl.config import load_scenario; from stars_rl.topology.trace import build_trace,trace_to_json; print(trace_to_json(build_trace(load_scenario('configs/toy.yaml'))))"
    result=subprocess.run([sys.executable,"-c",command],cwd=ROOT,capture_output=True,text=True,check=True)
    assert result.stdout.strip()==trace_to_json(t)


def test_entity_and_edge_order_do_not_change_trace():
    s=toy()
    reordered=replace(s,users=s.users[::-1],satellites=s.satellites[::-1],slices=s.slices[::-1],
        function_types=s.function_types[::-1],instances=s.instances[::-1],ground_links=s.ground_links[::-1],
        isl_links=tuple(replace(e,satellite_a_id=e.satellite_b_id,satellite_b_id=e.satellite_a_id) for e in s.isl_links[::-1]),
        access_schedule=tuple(replace(w,links=w.links[::-1]) for w in s.access_schedule))
    assert trace_to_json(build_trace(reordered))==trace_to_json(build_trace(s))


def test_content_hash_excludes_labels_and_irrelevant_absolute_times():
    s=toy();a=build_trace(s)
    other=replace(s,scenario_id="other-label",metadata=replace(s.metadata,scenario_group_id="other-group",
        root_lineage_id="other-root",epoch_utc="2026-01-01T00:00:00Z",interval_start_seconds=600,interval_end_seconds=780))
    b=build_trace(other)
    assert a.content_hash==b.content_hash
    assert a.artifact_hash!=b.artifact_hash  # provenance retained, never erased


@pytest.mark.parametrize("change",["visibility","distance","demand","capacity","geometry","duration"])
def test_content_hash_changes_with_exogenous_inputs(change):
    s=toy();old=build_trace(s).content_hash
    if change=="visibility":
        s=replace(s,access_schedule=(replace(s.access_schedule[0],links=s.access_schedule[0].links[1:]),*s.access_schedule[1:]))
    if change=="distance":s=replace(s,isl_links=(replace(s.isl_links[0],distance_m=123456),s.isl_links[1]))
    if change=="demand":s=replace(s,slices=(replace(s.slices[0],demand_mbps=4),s.slices[1]))
    if change=="capacity":s=replace(s,satellites=(replace(s.satellites[0],cpu_capacity_mips=201),*s.satellites[1:]))
    if change=="geometry":s=replace(s,users=(replace(s.users[0],coordinates=Coordinates(0,0)),s.users[1]))
    if change=="duration":s=replace(s,window_seconds=30,metadata=replace(s.metadata,interval_end_seconds=90))
    assert build_trace(s).content_hash!=old


@pytest.mark.parametrize("field",["windows","scenario","artifact_hash","content_hash","trace_schema_version"])
def test_tampered_or_unsupported_trace_is_rejected(field):
    data=trace_to_dict(build_trace(toy()))
    if field=="windows":data[field][0]["access_distances_m"][0][0]=1
    elif field=="scenario":data[field]["users"][0]["id"]="missing"
    elif field=="trace_schema_version":data[field]=2
    else:data[field]="0"*64
    with pytest.raises(ValueError):trace_from_dict(data)


def test_modified_cache_rejected_even_with_recomputed_checksum():
    # Independent checksum recomputation emulates a corrupt/stale cache file, not
    # an authentication attack. Loading must rebuild shortest paths from inputs.
    import hashlib
    data=trace_to_dict(build_trace(toy()))
    data["windows"][0]["paths"]["entries"][2]["distance_m"]=0
    payload={k:v for k,v in data.items() if k not in ("artifact_hash","content_hash")}
    data["artifact_hash"]=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    with pytest.raises(ValueError,match="derived"):
        trace_from_dict(data)


def test_no_change_trace_and_no_random_sampling(monkeypatch):
    import random
    def forbidden(*args,**kwargs):raise AssertionError("authored traces do not sample")
    monkeypatch.setattr(random,"Random",forbidden)
    s=toy();unchanged=replace(s,access_schedule=tuple(replace(s.access_schedule[0],window_index=k) for k in range(3)))
    t=build_trace(unchanged)
    assert all(w.access_distances_m==t.windows[0].access_distances_m for w in t.windows)


def test_physical_generation_is_not_impersonated():
    s=replace(toy(),family_id="development-physical-v1",family_classification="development_candidate")
    with pytest.raises(ValueError,match="authored"):
        build_trace(s)


def test_strict_json_input(tmp_path):
    p=tmp_path/"bad.json"
    for text in ['{"trace_schema_version":1,"trace_schema_version":1}', '{"value":NaN}', '{']:
        p.write_text(text)
        with pytest.raises(ValueError):load_trace(p)


def test_numeric_representation_does_not_split_content_identity():
    s=toy()
    equivalent=replace(s,window_seconds=60.0,
        satellites=tuple(replace(x,cpu_capacity_mips=float(x.cpu_capacity_mips)) for x in s.satellites),
        radio=replace(s.radio,carrier_hz=14000000000.0,external_interference_watts=-0.0))
    assert trace_to_json(build_trace(equivalent))==trace_to_json(build_trace(s))


def seeded_fixture(seed):
    # Hand-fixed sampled metadata; no generator and no RNG is run.
    raw=scenario_to_dict(toy())
    raw.update(scenario_id="seed-fixture",family_id="seed-fixtures-v1",family_classification="analytical_fixture")
    gen=raw["metadata"]["generation"]
    gen.update(method="sampled",rng_algorithm="hand-fixed-test",rng_library_version="1",
               seeds=[{"stream":n,"seed":seed+i} for i,n in enumerate(
                   ["layout","chain","demand","delay","cpu","coefficients","overhead"])])
    for section,scope,parameters in [
        ("slices","slice",[("chain","function_ids"),("demand_mbps","Mbps"),("delay_limit_seconds","seconds")]),
        ("satellites","satellite",[("cpu_capacity_mips","MIPS")]),
        ("function_types","function_type",[("psi_instructions_per_bit","instructions/bit"),
             ("omega_instructions_per_bit","instructions/bit"),("base_overhead_mips","MIPS")])]:
        for entity in raw[section]:
            for parameter,units in parameters:
                gen["draws"].append({"parameter":parameter,"scope":scope,"entity_id":entity["id"],
                    "units":units,"distribution":"hand-fixed-test-values","value":entity[parameter]})
    return scenario_from_dict(raw)


def test_same_persisted_seed_config_and_different_seed_labels():
    a=build_trace(seeded_fixture(7));b=build_trace(seeded_fixture(7));c=build_trace(seeded_fixture(100))
    assert trace_to_json(a)==trace_to_json(b)
    assert a.content_hash==c.content_hash
    assert a.artifact_hash!=c.artifact_hash
    assert len(c.scenario.metadata.generation.seeds)==7
    assert len(c.scenario.metadata.generation.draws)==15


def test_zero_capacity_does_not_hide_visibility_or_transit():
    s=toy();s=replace(s,satellites=(replace(s.satellites[0],cpu_capacity_mips=0),*s.satellites[1:]))
    w=build_trace(s).windows[0]
    assert w.access_distance("u0","s0")==500000
    assert w.paths.get("s0","s2").nodes==("s0","s1","s2")


@pytest.mark.parametrize("mutation",["radio","chain","packet","psi","egress_pool","instances"])
def test_additional_exogenous_hash_fields(mutation):
    s=toy();a=build_trace(s)
    if mutation=="radio":s=replace(s,radio=replace(s.radio,transmit_watts=.2))
    if mutation=="chain":s=replace(s,slices=(replace(s.slices[0],chain=("f1","f0")),s.slices[1]))
    if mutation=="packet":s=replace(s,slices=(replace(s.slices[0],packet_bits=6000),s.slices[1]))
    if mutation=="psi":s=replace(s,function_types=(replace(s.function_types[0],psi_instructions_per_bit=11),s.function_types[1]))
    if mutation=="egress_pool":s=replace(s,satellites=(replace(s.satellites[0],egress_capacity=1),*s.satellites[1:]))
    if mutation=="instances":s=replace(s,instances=s.instances[:-1])
    assert build_trace(s).content_hash!=a.content_hash


def test_direct_window_and_trace_construction_reject_inconsistent_cache():
    t=build_trace(toy());w=t.windows[0]
    with pytest.raises(ValueError,match="matrix"):
        replace(w,access_distances_m=())
    with pytest.raises(ValueError,match="derived"):
        replace(t,windows=(replace(w,start_seconds=1),*t.windows[1:]))
    with pytest.raises(ValueError):
        replace(w,access_distances_m=((float("nan"),None,None),w.access_distances_m[1]))


def test_non_json_cache_payload_rejected():
    data=trace_to_dict(build_trace(toy()))
    data["windows"][0]["not_serializable"]=object()
    with pytest.raises(ValueError,match="JSON"):
        trace_from_dict(data)
