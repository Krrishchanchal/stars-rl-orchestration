"""Independent C03 expectations from toy-v1 and O-DATA/O-DRAWSCOPE."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest
import yaml

from stars_rl.config import (
    load_scenario, scenario_from_dict, scenario_to_dict, dump_scenario,
    deployment_from_dict, deployment_to_dict, outcome_from_dict, outcome_to_dict,
)
from stars_rl.models import (
    AccessChoice, Coordinates, Deployment, EgressChoice, InstanceKey,
    StageAllocation, WindowOutcome, validate_deployment_structure,
)

TOY = Path(__file__).resolve().parents[2] / "configs/toy.yaml"


@pytest.fixture
def raw():
    return yaml.safe_load(TOY.read_text(encoding="utf-8"))


def test_frozen_toy_values_and_round_trip(tmp_path):
    s = load_scenario(TOY)
    assert s.family_id == "toy-v1" and s.family_classification == "authored_toy"
    assert (s.window_count, s.window_seconds) == (3, 60)
    assert [(x.id, x.cpu_capacity_mips, x.access_capacity, x.egress_capacity, x.max_active_instances)
            for x in s.satellites] == [("s0",200,2,2,4),("s1",300,2,2,4),("s2",0,0,0,0)]
    assert [(x.id,x.psi_instructions_per_bit,x.omega_instructions_per_bit,x.base_overhead_mips)
            for x in s.function_types] == [("f0",10,10,5),("f1",20,20,10)]
    assert [(x.chain,x.demand_mbps,x.packet_bits,x.delay_limit_seconds)
            for x in s.slices] == [(("f0","f1"),2,12000,.05),(("f0","f1"),3,12000,.05)]
    assert [(x.id,x.slice_id,x.coordinates) for x in s.users] == [("u0","slice0",None),("u1","slice1",None)]
    assert [(g.id,g.coordinates) for g in s.ground_stations] == [("g0",None)]
    assert {i.identity for i in s.instances} == {
        (f,i,h) for f in ("f0","f1") for i in ("i0","i1") for h in ("s0","s1","s2")}
    assert [[(l.user_id,l.satellite_id,l.distance_m) for l in w.links] for w in s.access_schedule] == [
        [("u0","s0",500000),("u0","s1",500000),("u1","s0",500000),("u1","s1",500000)],
        [("u0","s1",500000),("u1","s0",500000),("u1","s1",500000)],
        [("u0","s1",500000),("u1","s0",500000),("u1","s1",500000)]]
    assert [(l.satellite_id,l.ground_station_id,l.distance_m) for l in s.ground_links] == [
        ("s0","g0",500000),("s1","g0",500000)]
    assert [(l.satellite_a_id,l.satellite_b_id,l.distance_m) for l in s.isl_links] == [
        ("s0","s1",100000),("s1","s2",100000)]
    assert (s.radio.carrier_hz,s.radio.transmit_watts,s.radio.user_gain_dbi,s.radio.satellite_gain_dbi,
            s.radio.bandwidth_hz,s.radio.temperature_kelvin,s.radio.external_interference_watts,
            s.radio.speed_of_light_mps,s.radio.boltzmann_joules_per_kelvin) == (
                14e9,.1,15,40,100e6,290,0,299792458,1.380649e-23)
    assert s.metadata.generation.method == "authored"
    assert s.metadata.generation.seeds == s.metadata.generation.draws == ()
    assert s.activation_bound("f0") == s.activation_bound("f1") == 2
    assert scenario_from_dict(scenario_to_dict(s)) == s
    dump_scenario(s, tmp_path / "toy.yaml")
    assert load_scenario(tmp_path / "toy.yaml") == s


@pytest.mark.parametrize("section,index,field,value,message", [
    ("users",0,"id","bad id","id"),
    ("users",0,"slice_id","missing","unknown slice"),
    ("slices",0,"chain",["f0","f0"],"repeated"),
    ("slices",0,"chain",["missing"],"unknown function"),
    ("slices",0,"chain",[],"chain"),
    ("slices",0,"demand_mbps",0,"demand_mbps"),
    ("slices",0,"demand_mbps","2 Mbps","demand_mbps"),
    ("slices",0,"packet_bits",-1,"packet_bits"),
    ("slices",0,"delay_limit_seconds",0,"delay_limit_seconds"),
    ("satellites",0,"cpu_capacity_mips",-1,"cpu_capacity_mips"),
    ("satellites",0,"access_capacity",1.5,"access_capacity"),
    ("satellites",0,"egress_capacity",True,"egress_capacity"),
    ("function_types",0,"psi_instructions_per_bit",0,"psi"),
    ("function_types",0,"omega_instructions_per_bit",0,"omega"),
    ("function_types",0,"base_overhead_mips",-1,"overhead"),
    ("instances",0,"satellite_id","missing","unknown satellite"),
    ("instances",0,"function_type_id","missing","unknown function"),
])
def test_invalid_entity(raw,section,index,field,value,message):
    raw[section][index][field] = value
    with pytest.raises(ValueError, match=message):
        scenario_from_dict(raw)


@pytest.mark.parametrize("value", [float("nan"),float("inf"),-float("inf")])
@pytest.mark.parametrize("section,field", [("slices","demand_mbps"),("function_types","omega_instructions_per_bit"),
                                         ("satellites","cpu_capacity_mips")])
def test_nonfinite(raw,section,field,value):
    raw[section][0][field] = value
    with pytest.raises(ValueError,match="finite"):
        scenario_from_dict(raw)


@pytest.mark.parametrize("section", ["users","slices","satellites","ground_stations","function_types","instances"])
def test_duplicate_identity(raw,section):
    raw[section].append(deepcopy(raw[section][0]))
    with pytest.raises(ValueError,match="duplicate"):
        scenario_from_dict(raw)


def test_distinct_coefficients_and_slice_draw_scopes(raw):
    raw["function_types"][0]["omega_instructions_per_bit"] = 20
    raw["users"].extend([{"id":"u2","slice_id":"slice0","coordinates":None},
                         {"id":"u3","slice_id":"slice1","coordinates":None}])
    s = scenario_from_dict(raw)
    assert s.function_types[0].psi_instructions_per_bit == 10
    assert s.function_types[0].omega_instructions_per_bit == 20
    # Four user-stage occurrences of each type, not number of slices or hosts.
    assert s.activation_bound("f0") == 4
    assert [s.slice_for_user(u.id).demand_mbps for u in s.users] == [2,3,2,3]
    assert s.satellites[0].access_capacity == s.satellites[0].egress_capacity == 2
    with pytest.raises(ValueError,match="unknown function"):
        s.activation_bound("missing")


def test_unknown_missing_fields_and_no_coercion(raw):
    raw["slices"][0]["demand_bps"] = raw["slices"][0].pop("demand_mbps")
    with pytest.raises(ValueError,match="demand_bps|demand_mbps"):
        scenario_from_dict(raw)


def test_interference_rejected(raw):
    raw["radio"]["interference_model"] = "decision_dependent"
    with pytest.raises(ValueError,match="interference_model"):
        scenario_from_dict(raw)


@pytest.mark.parametrize("lat,lon", [(91,0),(-91,0),(0,181),(0,-181),(float("nan"),0)])
def test_invalid_coordinates(lat,lon):
    with pytest.raises(ValueError):
        Coordinates(lat,lon)


def test_coordinates_and_nested_immutability(raw):
    raw["users"][0]["coordinates"] = {"latitude_degrees":90,"longitude_degrees":-180}
    s = scenario_from_dict(raw)
    raw["satellites"][0]["cpu_capacity_mips"] = 999
    assert s.satellites[0].cpu_capacity_mips == 200
    with pytest.raises(FrozenInstanceError):
        s.satellites[0].cpu_capacity_mips = 999
    exported = scenario_to_dict(s)
    exported["access_schedule"][0]["links"].clear()
    assert len(s.access_schedule[0].links) == 4
    with pytest.raises(ValueError):
        replace(s, users=list(s.users))


@pytest.mark.parametrize("mutation", ["window","link","ground","isl","family","metadata"])
def test_invalid_references_and_metadata(raw,mutation):
    if mutation == "window": raw["access_schedule"][1]["window_index"] = 0
    if mutation == "link": raw["access_schedule"][0]["links"][0]["user_id"] = "missing"
    if mutation == "ground": raw["ground_links"][0]["ground_station_id"] = "missing"
    if mutation == "isl": raw["isl_links"][0]["satellite_b_id"] = "missing"
    if mutation == "family": raw["family_classification"] = "development_candidate"
    if mutation == "metadata": raw["metadata"]["interval_end_seconds"] = 0
    with pytest.raises(ValueError): scenario_from_dict(raw)


def deployment():
    return Deployment(0,(AccessChoice("u0","s0"),AccessChoice("u1","s1")),
        (EgressChoice("u0","s0","g0"),EgressChoice("u1","s1","g0")),
        tuple(StageAllocation(u,k,InstanceKey(f,"i0",h),cpu)
              for u,h,cpu in [("u0","s0",40),("u1","s1",60)] for k,f in enumerate(["f0","f1"])))


def test_deployment_structure_and_run_isolation():
    s = load_scenario(TOY)
    d = deployment()
    validate_deployment_structure(d,s)
    second_run = deepcopy(d)
    changed = replace(second_run, allocations=second_run.allocations[:-1])
    assert len(d.allocations) == 4 and len(changed.allocations) == 3
    with pytest.raises(ValueError,match="stage"):
        validate_deployment_structure(changed,s)
    wrong_type = replace(d.allocations[0],instance=InstanceKey("f1","i0","s0"))
    with pytest.raises(ValueError,match="type"):
        validate_deployment_structure(replace(d,allocations=(wrong_type,*d.allocations[1:])),s)
    unknown = replace(d.allocations[0],instance=InstanceKey("f0","missing","s0"))
    with pytest.raises(ValueError,match="instance"):
        validate_deployment_structure(replace(d,allocations=(unknown,*d.allocations[1:])),s)
    # This is a schema check, not CPU/delay/visibility feasibility certification.
    overallocated = replace(d.allocations[0],cpu_mips=1000)
    validate_deployment_structure(replace(d,allocations=(overallocated,*d.allocations[1:])),s)


def test_outcomes_do_not_fabricate_deployments():
    WindowOutcome(0,"not_attempted",None,"earlier_window_failed")
    WindowOutcome(0,"candidate",deployment(),None)
    with pytest.raises(ValueError): WindowOutcome(0,"failed",deployment(),"infeasible")
    with pytest.raises(ValueError): WindowOutcome(0,"candidate",None,None)


def test_yaml_duplicate_fields_and_unsafe_tags(tmp_path):
    p=tmp_path/"bad.yaml"
    for text in ["schema_version: 1\nschema_version: 2\n", "!!python/object:example {}", "users: [\n"]:
        p.write_text(text,encoding="utf-8")
        with pytest.raises(ValueError): load_scenario(p)


def test_deployment_and_outcome_round_trip():
    s = load_scenario(TOY)
    d = deployment()
    assert deployment_from_dict(deployment_to_dict(d),s) == d
    for outcome in [WindowOutcome(0,"candidate",d,None),
                    WindowOutcome(0,"failed",None,"proven_infeasible"),
                    WindowOutcome(1,"not_attempted",None,"earlier_window_failed")]:
        assert outcome_from_dict(outcome_to_dict(outcome),s) == outcome
    with pytest.raises(ValueError,match="window_index"):
        outcome_from_dict(outcome_to_dict(WindowOutcome(3,"not_attempted",None,"failed")),s)
    bad = deployment_to_dict(d)
    bad["allocations"][0]["cpu_mips"] = float("nan")
    with pytest.raises(ValueError,match="finite"):
        deployment_from_dict(bad,s)


def sampled_metadata(raw):
    # This is a hand-authored metadata fixture, not a generation implementation.
    # Explicit independent scope/unit table rather than production DRAW_SCOPES.
    generation = raw["metadata"]["generation"]
    generation.update(method="sampled",rng_algorithm="fixture-rng",rng_library_version="fixture-v1",
        seeds=[{"stream":name,"seed":i} for i,name in enumerate(
            ["layout","chain","demand","delay","cpu","coefficients","overhead"])])
    draws = []
    for section,scope,parameters in [
            ("slices","slice",[("chain","function_ids"),("demand_mbps","Mbps"),("delay_limit_seconds","seconds")]),
            ("satellites","satellite",[("cpu_capacity_mips","MIPS")]),
            ("function_types","function_type",[("psi_instructions_per_bit","instructions/bit"),
               ("omega_instructions_per_bit","instructions/bit"),("base_overhead_mips","MIPS")])]:
        for entity in raw[section]:
            for parameter,units in parameters:
                draws.append({"parameter":parameter,"scope":scope,"entity_id":entity["id"],
                              "units":units,"distribution":"hand-authored-test-value","value":entity[parameter]})
    generation["draws"] = draws
    return generation


def test_generation_metadata_round_trip_without_sampling(raw):
    sampled_metadata(raw)
    before = deepcopy(raw)
    scenario = scenario_from_dict(raw)
    assert raw == before  # input dictionaries are not rewritten
    assert len(scenario.metadata.generation.draws) == 15  # 2*3 slice +3 host +2*3 type
    assert scenario_from_dict(scenario_to_dict(scenario)) == scenario
    assert [d.scope for d in scenario.metadata.generation.draws[:3]] == ["slice"]*3
    # One shared per-type coefficient record, not one per host/instance.
    assert len([d for d in scenario.metadata.generation.draws if d.parameter == "psi_instructions_per_bit"]) == 2


@pytest.mark.parametrize("mutation", ["scope","units","value","missing_draw","missing_seed","duplicate_seed","unknown_entity"])
def test_invalid_generation_metadata(raw,mutation):
    gen = sampled_metadata(raw)
    if mutation == "scope": gen["draws"][1]["scope"] = "user"
    if mutation == "units": gen["draws"][1]["units"] = "bits/s"
    if mutation == "value": gen["draws"][1]["value"] = 7
    if mutation == "missing_draw": gen["draws"].pop()
    if mutation == "missing_seed": gen["seeds"].pop()
    if mutation == "duplicate_seed": gen["seeds"].append(deepcopy(gen["seeds"][0]))
    if mutation == "unknown_entity": gen["draws"][0]["entity_id"] = "missing"
    with pytest.raises(ValueError): scenario_from_dict(raw)


@pytest.mark.parametrize("field,value", [("schema_version",True),("schema_version",2),("window_count",0),
                                       ("window_count",3.0),("window_seconds",float("inf"))])
def test_invalid_scenario_fields(raw,field,value):
    raw[field]=value
    with pytest.raises(ValueError): scenario_from_dict(raw)


def test_disconnected_inputs_are_retained_not_repaired(raw):
    raw["access_schedule"][0]["links"] = []
    raw["ground_links"] = []
    raw["isl_links"] = []
    s=scenario_from_dict(raw)
    assert s.access_schedule[0].links == s.ground_links == s.isl_links == ()


def test_distinct_antenna_pools_and_immutable_chains(raw):
    raw["satellites"][0]["access_capacity"] = 1
    raw["satellites"][0]["egress_capacity"] = 5
    s=scenario_from_dict(raw)
    assert (s.satellites[0].access_capacity,s.satellites[0].egress_capacity) == (1,5)
    raw["slices"][0]["chain"].clear()
    assert s.slices[0].chain == ("f0","f1")


def test_loading_never_draws_random_values(monkeypatch):
    import random
    def forbidden(*args,**kwargs):
        raise AssertionError("configuration loading must not draw random values")
    monkeypatch.setattr(random,"random",forbidden)
    monkeypatch.setattr(random,"Random",forbidden)
    monkeypatch.setattr(random,"SystemRandom",forbidden)
    assert load_scenario(TOY) == load_scenario(TOY)


@pytest.mark.parametrize("value", ["2026-01-01T00:00:00", "not-a-date", "2026-01-01T00:00:00+01:00"])
def test_epoch_requires_explicit_utc(raw,value):
    raw["metadata"]["epoch_utc"] = value
    with pytest.raises(ValueError,match="epoch_utc"):
        scenario_from_dict(raw)


def test_epoch_with_utc_round_trips(raw):
    raw["metadata"]["epoch_utc"]="2026-01-01T00:00:00Z"
    s=scenario_from_dict(raw)
    assert scenario_from_dict(scenario_to_dict(s)) == s


@pytest.mark.parametrize("link_kind", ["access","ground","isl"])
def test_duplicate_edges_rejected(raw,link_kind):
    if link_kind == "access":
        raw["access_schedule"][0]["links"].append(deepcopy(raw["access_schedule"][0]["links"][0]))
    elif link_kind == "ground":
        raw["ground_links"].append(deepcopy(raw["ground_links"][0]))
    else:
        raw["isl_links"].append({"satellite_a_id":"s1","satellite_b_id":"s0","distance_m":100000})
    with pytest.raises(ValueError,match="duplicate"):
        scenario_from_dict(raw)


def test_deployment_unknown_associations_and_duplicates():
    s=load_scenario(TOY)
    d=deployment()
    with pytest.raises(ValueError,match="unknown ground"):
        validate_deployment_structure(replace(d,egress=(EgressChoice("u0","s0","missing"),d.egress[1])),s)
    with pytest.raises(ValueError,match="associations"):
        validate_deployment_structure(replace(d,access=d.access[:1]),s)
    with pytest.raises(ValueError,match="duplicate"):
        replace(d,allocations=(*d.allocations,d.allocations[0]))


@pytest.mark.parametrize("field,value", [("demand_mbps",21),("packet_bits",12001)])
def test_inputs_outside_calibrated_domain_rejected(raw,field,value):
    raw["slices"][0][field]=value
    with pytest.raises(ValueError,match=field): scenario_from_dict(raw)


def test_malformed_mapping_keys_and_extreme_integers(raw):
    raw["radio"]["carrier_hz"] = 10**1000
    with pytest.raises(ValueError,match="finite"):
        scenario_from_dict(raw)
    with pytest.raises(ValueError,match="field names"):
        scenario_from_dict({1:1,"unknown":1})


def test_window_count_is_checked_without_allocating_a_range(raw):
    raw["window_count"]=10**1000
    with pytest.raises(ValueError,match="access_schedule"):
        scenario_from_dict(raw)
