"""Necessary-condition matching certificates and independent region bound."""
from collections import deque
from dataclasses import asdict
import math


def capacity_matching(users,satellites,allowed,capacities):
    """Integral augmenting paths; residual min-cut also certifies failure."""
    source=('source',);sink=('sink',);flow={};capacity={};adj={source:[],sink:[]}
    def edge(a,b,c):
        adj.setdefault(a,[]).append(b);adj.setdefault(b,[]).append(a)
        capacity[a,b]=c;capacity[b,a]=0;flow[a,b]=flow[b,a]=0
    for u in users:edge(source,('u',u),1)
    for u in users:
        for s in satellites:
            if (u,s) in allowed:edge(('u',u),('s',s),len(users)+1)
    for s in satellites:edge(('s',s),sink,capacities[s])
    value=0
    while True:
        parent={source:None};queue=deque([source])
        while queue and sink not in parent:
            a=queue.popleft()
            for b in adj[a]:
                if b not in parent and capacity[a,b]-flow[a,b]>0:parent[b]=a;queue.append(b)
        if sink not in parent:break
        b=sink
        while b!=source:
            a=parent[b];flow[a,b]+=1;flow[b,a]-=1;b=a
        value+=1
    reachable=set(parent)
    cut=sum(c for (a,b),c in capacity.items() if a in reachable and b not in reachable)
    return {'flow':value,'required':len(users),'passed':value==len(users),
            'unmatched_users':[u for u in users if flow[source,('u',u)]==0],
            'reachable_users':[u for u in users if ('u',u) in reachable],
            'bottleneck_satellites':[s for s in satellites if ('s',s) in reachable],
            'min_cut_capacity':cut}


def preflight(s,w):
    access={(u,n) for u in w.user_ids for n in w.satellite_ids if w.access_distance(u,n) is not None}
    gateway={n for n in w.satellite_ids if any(w.ground_distance(n,g) is not None for g in w.ground_station_ids)}
    egress={(u,n) for u in w.user_ids for n in gateway}
    a=capacity_matching(w.user_ids,w.satellite_ids,access,{n.id:n.access_capacity for n in s.satellites})
    g=capacity_matching(w.user_ids,w.satellite_ids,egress,{n.id:n.egress_capacity for n in s.satellites})
    minimum=sum(s.slice_for_user(u.id).demand_mbps*next(f.psi_instructions_per_bit for f in s.function_types if f.id==ft)
                for u in s.users for ft in s.slice_for_user(u.id).chain)
    cpu=sum(n.cpu_capacity_mips for n in s.satellites)
    return {'passed':a['passed'] and g['passed'] and minimum<=cpu,'access':a,'egress':g,
            'minimum_cpu_mips':minimum,'total_cpu_mips':cpu,'cpu_necessary_passed':minimum<=cpu,
            'scope':'necessary conditions only; not full routing/CPU/radio/delay feasibility'}


def region_cap_bound():
    # D09 independent algebra, no orbit/visibility/generator function calls.
    r=6371000.;h=500000.;e=math.radians(10)
    theta=math.acos(r/(r+h)*math.cos(e))-e
    expanded=theta+math.radians(6.5);rotation=7.2921150e-5*840
    lat,lon=math.radians(50),math.radians(-74.5)
    centre=(math.cos(lat)*math.cos(lon),math.cos(lat)*math.sin(lon),math.sin(lat));inc=math.radians(88)
    distances=[];eligible=[]
    for p,raan in enumerate((0,45,90,135)):
        a=math.radians(raan);normal=(math.sin(inc)*math.sin(a),-math.sin(inc)*math.cos(a),math.cos(inc))
        angle=math.asin(abs(sum(x*y for x,y in zip(normal,centre))))
        distances.append(math.degrees(angle))
        if angle-rotation<=expanded+1e-12:eligible.append(p)
    spacing=2*math.pi/15
    per_plane=math.floor((2*expanded+1e-12)/spacing)+1
    count=len(eligible)*per_plane
    return {'cap_angle_degrees':math.degrees(theta),'rectangle_radius_bound_degrees':6.5,
            'earth_rotation_bound_degrees':math.degrees(rotation),'plane_distances_at_epoch_degrees':distances,
            'eligible_planes':eligible,'maximum_per_eligible_plane':per_plane,'maximum_region_visible_satellites':count,
            'reference_access_capacity_bound':count*5,'reference_users':30,'reference_infeasible':count*5<30,
            'interval_seconds':[0,840],'scope':'frozen spherical geometry only; not a claim about other constellations'}


def audit_trace(trace):
    s=trace.scenario;windows=[]
    for w in trace.windows:
        check=preflight(s,w)
        degree={n:0 for n in w.satellite_ids};adj={n:[] for n in w.satellite_ids}
        for edge in w.isl_links:
            a,b=edge.satellite_a_id,edge.satellite_b_id;degree[a]+=1;degree[b]+=1;adj[a].append(b);adj[b].append(a)
        unseen=set(w.satellite_ids);components=[]
        while unseen:
            start=min(unseen);stack=[start];unseen.remove(start);members=[]
            while stack:
                a=stack.pop();members.append(a)
                for b in adj[a]:
                    if b in unseen:unseen.remove(b);stack.append(b)
            components.append(sorted(members))
        visible={u:[n for n in w.satellite_ids if w.access_distance(u,n) is not None] for u in w.user_ids}
        windows.append({'window_index':w.window_index,'time_seconds':w.start_seconds,'preflight':check,
            'visible_satellites_by_user':visible,'covered_users':sum(bool(v) for v in visible.values()),
            'region_union_visible_satellites':len({n for values in visible.values() for n in values}),
            'isl_edges':len(w.isl_links),'maximum_isl_degree':max(degree.values()),'components':components})
    result={'schema_version':1,'scenario_id':s.scenario_id,'family_id':s.family_id,'family_classification':s.family_classification,
            'trace_content_hash':trace.content_hash,'user_count':len(s.users),'satellite_count':len(s.satellites),
            'all_windows_necessary_passed':all(w['preflight']['passed'] for w in windows),'windows':windows,
            'region_bound':region_cap_bound() if s.orbit is not None else None,
            'layout':[{'user_id':u.id,'latitude':u.coordinates.latitude_degrees,'longitude':u.coordinates.longitude_degrees} for u in s.users if u.coordinates]}
    if s.orbit is not None:
        from .orbits import positions
        result['snapshot0_positions_ecef_m']=positions(s.orbit,0,trace.windows[0].satellite_ids)
        result['snapshot0_edges']=[[e.satellite_a_id,e.satellite_b_id] for e in trace.windows[0].isl_links]
        result['ground_stations']=[{'id':g.id,'latitude':g.coordinates.latitude_degrees,'longitude':g.coordinates.longitude_degrees} for g in s.ground_stations]
    return result
