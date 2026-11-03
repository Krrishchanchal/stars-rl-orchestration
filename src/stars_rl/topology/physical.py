"""Frozen physical families with independent named sampling streams."""
from dataclasses import replace
import hashlib
import math
from pathlib import Path
import random
import sys
import yaml

from stars_rl.config import _UniqueSafeLoader
from stars_rl.models import (Scenario,PhysicalOrbit,Coordinates,User,GroundStation,FunctionType,Slice,Satellite,
    InstanceKey,AccessLink,AccessWindow,Radio,TraceMetadata,GenerationMetadata,NamedSeed,Draw)
from .geometry import surface_ecef,central_angle,distance
from .orbits import positions
from .visibility import visible,isl_links

STREAMS=('layout','chain','demand','delay','cpu','coefficients','overhead')


class GenerationError(ValueError):
    def __init__(self,message,diagnostics):super().__init__(message);self.diagnostics=diagnostics


def named_seeds(root_seed):
    if type(root_seed) is not int or not 0<=root_seed<2**63:raise ValueError('root seed must be a nonnegative signed63-bit integer')
    return {s:int.from_bytes(hashlib.sha256(f'physical-generator-v1:{root_seed}:{s}'.encode()).digest(),'big') for s in STREAMS}


def sample_layout(rng,count,*,max_attempts=100000):
    accepted=[];attempts=0
    while len(accepted)<count:
        if attempts>=max_attempts:raise GenerationError('layout separation rejection cap reached',{'attempts':attempts,'accepted_users':len(accepted),'requested_users':count})
        attempts+=1
        lat=math.degrees(math.asin(rng.uniform(math.sin(math.radians(49)),math.sin(math.radians(51)))))
        lon=rng.uniform(-80,-69);coord=Coordinates(lat,lon);unit=surface_ecef(lat,lon,1)
        if all(central_angle(unit,surface_ecef(c.latitude_degrees,c.longitude_degrees,1))>=math.radians(.5) for c in accepted):accepted.append(coord)
    return tuple(accepted),{'attempts':attempts,'accepted_users':count,'rejected_proposals':attempts-count,'maximum_attempts':max_attempts}


def physical_windows(scenario,*,check_access=True):
    from .trace import NetworkWindow
    from .paths import all_pairs_shortest_paths
    orbit=scenario.orbit
    if orbit is None:raise ValueError('physical orbit metadata required')
    users=tuple(u.id for u in scenario.users);satellites=tuple(n.id for n in scenario.satellites);ground=tuple(g.id for g in scenario.ground_stations)
    user_xyz={u.id:surface_ecef(u.coordinates.latitude_degrees,u.coordinates.longitude_degrees,orbit.earth_radius_m) for u in scenario.users}
    gs_xyz={g.id:surface_ecef(g.coordinates.latitude_degrees,g.coordinates.longitude_degrees,orbit.earth_radius_m) for g in scenario.ground_stations}
    windows=[]
    for k in range(scenario.window_count):
        time=k*scenario.window_seconds;xyz=positions(orbit,time,satellites)
        access=tuple(tuple(distance(user_xyz[u],xyz[n]) if visible(user_xyz[u],xyz[n],orbit) else None for n in satellites) for u in users)
        gs=tuple(tuple(distance(xyz[n],gs_xyz[g]) if visible(gs_xyz[g],xyz[n],orbit) else None for g in ground) for n in satellites)
        edges=isl_links(orbit,satellites,xyz)
        w=NetworkWindow(k,time,scenario.window_seconds,users,satellites,ground,access,gs,edges,all_pairs_shortest_paths(satellites,edges))
        source=AccessWindow(k,tuple(AccessLink(u,n,access[i][j]) for i,u in enumerate(users) for j,n in enumerate(satellites) if access[i][j] is not None))
        if check_access and source!=scenario.access_schedule[k]:raise ValueError('physical access source differs from orbital geometry')
        windows.append(w)
    return tuple(windows)


def generate_physical(family_id='development-physical-v1',root_seed=0):
    from .trace import build_trace
    if family_id not in ('paper-inputs-v1','development-physical-v1'):raise ValueError('unapproved physical family')
    seeds=named_seeds(root_seed);rng={s:random.Random(v) for s,v in seeds.items()};orbit=PhysicalOrbit()
    slice_count,per_slice=(6,5) if family_id=='paper-inputs-v1' else (2,2)
    count=slice_count*per_slice
    try:coordinates,stats=sample_layout(rng['layout'],count)
    except GenerationError as exc:
        exc.diagnostics.update(family_id=family_id,root_seed=root_seed,named_seeds=seeds);raise
    draws=[]
    def record(parameter,scope,entity,units,distribution,value):draws.append(Draw(parameter,scope,entity,units,distribution,value))
    functions=[]
    for k in range(8):
        fid=f'f{k}';coefficient=rng['coefficients'].uniform(5,90);overhead=rng['overhead'].uniform(1,17)
        functions.append(FunctionType(fid,coefficient,coefficient,overhead))
        for key in ('psi_instructions_per_bit','omega_instructions_per_bit'):record(key,'function_type',fid,'instructions/bit','uniform[5,90]; shared psi=omega',coefficient)
        record('base_overhead_mips','function_type',fid,'MIPS','uniform[1,17]',overhead)
    slices=[]
    for k in range(slice_count):
        sid=f'slice{k}';chain=tuple(rng['chain'].sample([f.id for f in functions],rng['chain'].choice((2,3,4))))
        demand=rng['demand'].uniform(2,20);delay=rng['delay'].uniform(.035,.150)
        slices.append(Slice(sid,chain,demand,12000,delay))
        record('chain','slice',sid,'function_ids','length uniform{2,3,4}; ordered sample without replacement',chain)
        record('demand_mbps','slice',sid,'Mbps','uniform[2,20]',demand);record('delay_limit_seconds','slice',sid,'seconds','uniform[.035,.150]',delay)
    users=[]
    for k,coord in enumerate(coordinates):
        uid=f'u{k:02d}';users.append(User(uid,f'slice{k//per_slice}',coord))
        record('latitude_degrees','user',uid,'degrees','uniform sin(latitude),49..51; .5deg rejection',coord.latitude_degrees)
        record('longitude_degrees','user',uid,'degrees','uniform[-80,-69]; .5deg rejection',coord.longitude_degrees)
    satellites=[]
    for k in range(60):
        sid=f's{k:02d}';cpu=rng['cpu'].uniform(1000,2000);satellites.append(Satellite(sid,cpu,5,5,8))
        record('cpu_capacity_mips','satellite',sid,'MIPS','uniform[1000,2000]',cpu)
    generation=GenerationMetadata('sampled','python.random.Random/MT19937',sys.version.split()[0],tuple(NamedSeed(s,seeds[s]) for s in STREAMS),tuple(draws))
    metadata=TraceMetadata(f'physical-group-{root_seed}',f'physical-root-{root_seed}','walker-star-f1-v1',f'layout-root-{root_seed}',
        f'demand-root-{root_seed}',orbit.epoch_utc,0,840,generation)
    ground=(GroundStation('g0',Coordinates(49.93,-79.53)),GroundStation('g1',Coordinates(49.93,-69.53)))
    scenario=Scenario(1,f'{family_id}-seed-{root_seed}',family_id,'reference_audit' if slice_count==6 else 'development_candidate',14,60,metadata,
        Radio(14e9,.1,15,40,100e6,290,'exogenous',0,299792458,1.380649e-23),tuple(functions),tuple(slices),tuple(users),ground,tuple(satellites),
        tuple(InstanceKey(f.id,f'i{i}',s.id) for f in functions for s in satellites for i in range(2)),
        tuple(AccessWindow(k,()) for k in range(14)),(),(),orbit)
    # Materialize source access data without building an unused first path cache.
    access=[];satellite_ids=tuple(n.id for n in satellites)
    for k in range(14):
        xyz=positions(orbit,k*60,satellite_ids);links=[]
        for user in users:
            surface=surface_ecef(user.coordinates.latitude_degrees,user.coordinates.longitude_degrees,orbit.earth_radius_m)
            links.extend(AccessLink(user.id,n,distance(surface,xyz[n])) for n in satellite_ids if visible(surface,xyz[n],orbit))
        access.append(AccessWindow(k,tuple(links)))
    return build_trace(replace(scenario,access_schedule=tuple(access))),stats


def load_physical_config(path):
    data=yaml.load(Path(path).read_text(encoding='utf-8'),Loader=_UniqueSafeLoader)
    if type(data) is not dict or set(data)!={'physical_schema_version','family_id','root_seed'} or type(data['physical_schema_version']) is not int or data['physical_schema_version']!=1:raise ValueError('invalid physical config schema')
    return generate_physical(data['family_id'],data['root_seed'])
