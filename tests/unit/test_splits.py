"""Content, roots, transitive groups, episode guards and phase aliases."""
from dataclasses import replace
import pytest

from stars_rl.experiments.manifest import atomic_json,read_json
from stars_rl.experiments.splits import create_split,load_split,split_manifest
from stars_rl.topology.trace import build_trace


def variant(s,label,*,demand=2,root=None,group=None,constellation=None,layout=None,start=0,epoch=None):
    metadata=replace(s.metadata,root_lineage_id=root or label,scenario_group_id=group or label,
        constellation_id=constellation or label,layout_id=layout or label,epoch_utc=epoch,
        interval_start_seconds=start,interval_end_seconds=start+s.window_count*s.window_seconds)
    return build_trace(replace(s,scenario_id=label,metadata=metadata,
        slices=tuple(replace(sl,demand_mbps=demand) for sl in s.slices)))


def parts(s):
    return dict(train=[variant(s,'train',demand=2)],validation=[variant(s,'validation',demand=3)],test=[variant(s,'test',demand=4)])


def test_frozen_split_roundtrip_and_no_overwrite(temporal_case,tmp_path):
    s,_,_=temporal_case;p=parts(s)
    manifest=create_split(p,tmp_path/'split')
    assert len(manifest['components'])==3 and manifest['guard_seconds']==180
    loaded,traces=load_split(tmp_path/'split')
    assert loaded==manifest
    assert traces['test'][0].content_hash==p['test'][0].content_hash
    with pytest.raises(FileExistsError):create_split(p,tmp_path/'split')


def test_duplicate_hash_ignores_labels_and_epoch(temporal_case):
    s,_,_=temporal_case;p=parts(s)
    p['test']=[variant(s,'other-seed',demand=2,start=9999,epoch='2030-01-01T00:00:00Z')]
    assert p['train'][0].content_hash==p['test'][0].content_hash
    with pytest.raises(ValueError,match='duplicate normalized'):split_manifest(p)


@pytest.mark.parametrize('field',['root','group'])
def test_shared_root_or_declared_group_rejected_despite_distinct_content(temporal_case,field):
    s,_,_=temporal_case;p=parts(s)
    p['test']=[variant(s,'test',demand=4,**{field:'train'})]
    with pytest.raises(ValueError,match='component crosses'):split_manifest(p)


@pytest.mark.parametrize('start',[60,180,100000])
def test_overlap_guard_and_repeated_layout_grouped(temporal_case,start):
    s,_,_=temporal_case;p=parts(s)
    p['test']=[variant(s,'test',demand=4,constellation='train',layout='train',start=start)]
    with pytest.raises(ValueError,match='component crosses'):split_manifest(p)


def test_guard_must_cover_maximum_episode(temporal_case):
    with pytest.raises(ValueError,match='at least one'):split_manifest(parts(temporal_case[0]),guard_seconds=179)


def test_transitive_linkage_not_just_pairwise_partition_labels(temporal_case):
    s,_,_=temporal_case;p=parts(s)
    p['train'].append(variant(s,'bridge',demand=5,root='train',group='shared'))
    p['test']=[variant(s,'test',demand=4,group='shared')]
    with pytest.raises(ValueError,match='component crosses'):split_manifest(p)


def test_known_phase_aliases_across_distant_intervals(temporal_case):
    p=parts(temporal_case[0])
    phases={p['train'][0].content_hash:'cycle',p['test'][0].content_hash:'cycle'}
    with pytest.raises(ValueError,match='component crosses'):split_manifest(p,phase_groups=phases)


def test_same_split_variants_share_component_and_tamper_is_rejected(temporal_case,tmp_path):
    s,_,_=temporal_case;p=parts(s)
    p['train'].append(variant(s,'load-variant',demand=5,root='train'))
    manifest=create_split(p,tmp_path/'split')
    keys=manifest['partitions']['train']
    assert manifest['traces'][keys[0]]['component_id']==manifest['traces'][keys[1]]['component_id']
    path=tmp_path/'split/manifest.json';data=read_json(path);data['traces'][keys[0]]['root']='forged'
    atomic_json(path,data)
    with pytest.raises(ValueError,match='manifest lineage'):load_split(tmp_path/'split')


def test_bad_phase_keys_and_incomplete_partitions_rejected(temporal_case):
    p=parts(temporal_case[0])
    with pytest.raises(ValueError):split_manifest(p,phase_groups={'unknown':'cycle'})
    p['test']=[]
    with pytest.raises(ValueError):split_manifest(p)


def test_absolute_epoch_guard_and_retained_group_reason(temporal_case):
    s,_,_=temporal_case;p=parts(s)
    first=variant(s,'first',demand=5,constellation='c',layout='l',epoch='2030-01-01T00:00:00Z')
    second=variant(s,'second',demand=6,constellation='c',layout='l',epoch='2030-01-01T00:02:00Z')
    p['train']=[first,second]
    result=split_manifest(p)
    assert any(e['reason']=='overlap_or_episode_guard' for e in result['edges'])
    assert result['traces'][first.content_hash]['component_id']==result['traces'][second.content_hash]['component_id']


def test_real_physical_geometry_family_survives_relabeling(physical_traces,temporal_case):
    trace,_=physical_traces['development-physical-v1']
    s=trace.scenario
    # Resource-variant provenance fixture only: preserve the draw ledger and
    # all geometry. No solver, training, screening or feasibility claim.
    satellites=tuple(replace(n,cpu_capacity_mips=n.cpu_capacity_mips+(.1 if n.cpu_capacity_mips<1999 else -.1)) for n in s.satellites)
    capacities={n.id:n.cpu_capacity_mips for n in satellites}
    generation=replace(s.metadata.generation,draws=tuple(replace(d,value=capacities[d.entity_id])
        if d.parameter=='cpu_capacity_mips' else d for d in s.metadata.generation.draws))
    changed=build_trace(replace(s,metadata=replace(s.metadata,root_lineage_id='renamed',scenario_group_id='renamed',
        constellation_id='renamed',layout_id='renamed',generation=generation),satellites=satellites))
    p=dict(train=[trace],validation=[variant(temporal_case[0],'authored',demand=9)],test=[changed])
    assert trace.content_hash!=changed.content_hash
    with pytest.raises(ValueError,match='component crosses'):split_manifest(p)
