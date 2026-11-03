"""Frozen lineage/content/geometry components, before any validation tuning.

Repeated constellation/layout families are conservatively kept together even
when intervals are far apart. A temporal gap alone never proves independence.
"""
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import math

from .manifest import atomic_json,checked_path,digest,file_hash,read_json
from stars_rl.topology.trace import load_trace,trace_to_dict

PARTITIONS=('train','validation','test')


def _identity(trace):
    s=trace.scenario;m=s.metadata
    duration=len(trace.windows)*s.window_seconds
    if not math.isclose(m.interval_end_seconds-m.interval_start_seconds,duration,rel_tol=0,abs_tol=1e-9):
        raise ValueError('lineage interval must describe exactly one episode')
    origin=0 if m.epoch_utc is None else datetime.fromisoformat(m.epoch_utc.replace('Z','+00:00')).timestamp()
    geometry=None
    if s.orbit is not None:
        orbit=asdict(s.orbit);orbit.pop('epoch_utc')
        geometry=digest(dict(orbit=orbit,users=sorted((u.coordinates.latitude_degrees,u.coordinates.longitude_degrees)
                                                    for u in s.users),
                             ground=sorted((g.coordinates.latitude_degrees,g.coordinates.longitude_degrees) for g in s.ground_stations)))
    return dict(content_hash=trace.content_hash,artifact_hash=trace.artifact_hash,
        group_id=m.scenario_group_id,root=m.root_lineage_id,constellation=m.constellation_id,layout=m.layout_id,
        demand_family=m.demand_family_id,epoch_utc=m.epoch_utc,
        interval=[origin+m.interval_start_seconds,origin+m.interval_end_seconds],
        time_basis='UTC' if m.epoch_utc is not None else 'relative:'+m.constellation_id,
        duration_seconds=duration,horizon=len(trace.windows),physical_geometry_family=geometry,
        family_id=s.family_id,family_classification=s.family_classification)


def split_manifest(partitions,*,guard_seconds=None,phase_groups=None):
    if type(partitions) is not dict or set(partitions)!=set(PARTITIONS) or any(not partitions[p] for p in PARTITIONS):
        raise ValueError('nonempty train, validation and test partitions required')
    entries={};members={}
    for partition in PARTITIONS:
        for trace in partitions[partition]:
            row=_identity(trace);key=row['content_hash']
            if key in entries:raise ValueError('duplicate normalized exogenous content across/in partitions: '+key)
            entries[key]=row;members[key]=partition
    minimum=max(row['duration_seconds'] for row in entries.values())
    guard=minimum if guard_seconds is None else guard_seconds
    if type(guard) not in (int,float) or not math.isfinite(guard) or guard<minimum:
        raise ValueError('split guard must be at least one maximum episode duration')
    if phase_groups is not None and type(phase_groups) is not dict:raise ValueError('phase groups must be a JSON map')
    phases={} if phase_groups is None else dict(phase_groups)
    if any(k not in entries or type(v) is not str or not v for k,v in phases.items()):
        raise ValueError('known phase groups must reference supplied content hashes')
    parent={key:key for key in entries};edges=[]
    def find(k):
        while parent[k]!=k:k=parent[k]
        return k
    keys=sorted(entries)
    for i,a in enumerate(keys):
        for b in keys[i+1:]:
            x,y=entries[a],entries[b];reason=None
            same_family=(x['constellation'],x['layout'])==(y['constellation'],y['layout'])
            same_geometry=x['physical_geometry_family'] is not None and x['physical_geometry_family']==y['physical_geometry_family']
            gap=max(x['interval'][0],y['interval'][0])-min(x['interval'][1],y['interval'][1])
            if x['root']==y['root']:reason='same_root_lineage'
            elif x['group_id']==y['group_id']:reason='same_declared_group'
            elif a in phases and b in phases and phases[a]==phases[b]:reason='known_repeated_phase_cycle'
            elif (same_family or same_geometry) and x['time_basis']==y['time_basis'] and gap<guard:
                reason='overlap_or_episode_guard'
            elif same_family or same_geometry:reason='repeated_layout_family_conservative'
            if reason:
                parent[find(b)]=find(a);edges.append(dict(a=a,b=b,reason=reason))
    components={}
    for key in keys:components.setdefault(find(key),[]).append(key)
    groups=[]
    for component in components.values():
        assigned={members[k] for k in component}
        if len(assigned)!=1:raise ValueError('connected lineage/interval/phase component crosses splits: '+','.join(sorted(assigned)))
        group=digest(component)
        groups.append(dict(id=group,members=component,partition=next(iter(assigned))))
        for key in component:entries[key]['component_id']=group
    payload=dict(schema_version=1,scope='frozen grouped split before validation tuning',
        partitions={p:sorted(k for k in keys if members[k]==p) for p in PARTITIONS},traces=entries,
        components=sorted(groups,key=lambda g:g['id']),edges=edges,guard_seconds=guard,phase_groups=phases,
        screening='No screening performed here; every supplied trace retained, including modeled failures. Upstream selection is not inferred.',
        limitation='Shared constellation design can correlate groups. Label lineage truthfully; an interval gap is not proof of independence.')
    return payload|{'split_hash':digest(payload)}


def create_split(partitions,output,*,guard_seconds=None,phase_groups=None):
    manifest=split_manifest(partitions,guard_seconds=guard_seconds,phase_groups=phase_groups)
    folder=Path(output).resolve();folder.mkdir(parents=True,exist_ok=False)
    files={}
    for traces in partitions.values():
        for trace in traces:
            name=trace.content_hash+'.json';atomic_json(folder/name,trace_to_dict(trace));files[name]=file_hash(folder/name)
    atomic_json(folder/'manifest.json',manifest|{'input_files':files})
    return manifest


def load_split(folder):
    folder=Path(folder).resolve();saved=read_json(folder/'manifest.json')
    if type(saved) is not dict or 'input_files' not in saved:raise ValueError('invalid split manifest')
    partitions={p:[] for p in PARTITIONS}
    expected_files={key+'.json' for p in PARTITIONS for key in saved['partitions'][p]}
    if set(saved['input_files'])!=expected_files:raise ValueError('split input file domain differs')
    for p in PARTITIONS:
        for key in saved['partitions'][p]:
            name=key+'.json';path=checked_path(folder,name)
            if file_hash(path)!=saved['input_files'][name]:raise ValueError('split input hash mismatch')
            trace=load_trace(path)
            if trace.content_hash!=key:raise ValueError('split trace identity differs')
            partitions[p].append(trace)
    actual=split_manifest(partitions,guard_seconds=saved['guard_seconds'],phase_groups=saved['phase_groups'])
    if actual!={k:v for k,v in saved.items() if k!='input_files'}:raise ValueError('split manifest lineage/group/hash mismatch')
    return actual,partitions
