"""Independent C07-export validation. Reconstruct, never query a solver/model.

Immutable input schemas are shared. All domains, path costs, radio, constraint
rows and physical delays are recomputed here without production numeric helpers.
"""
from dataclasses import dataclass,asdict
import math
import time

from stars_rl.models import Scenario
from .residuals import Residual,Residuals,finite,processing_error


class SchemaError(ValueError):pass
class InputError(ValueError):pass


@dataclass(frozen=True,slots=True)
class ValidationReport:
    status: str
    reason: str
    solver_status: str | None
    residuals: tuple[Residual,...]
    errors: tuple[str,...]
    recomputed: dict
    elapsed_seconds: float
    optimality_checked: bool=False

    @property
    def valid(self):return self.status=="valid"

    def to_dict(self):
        return {**asdict(self),"valid":self.valid,"failed_rows":sum(not r.passed for r in self.residuals)}


def _require(condition,message):
    if not condition:raise SchemaError(message)


def _plain(value,path="$",ancestors=None):
    """Reject nonfinite/cyclic/non-plain inputs before any constraint comparison."""
    ancestors=set() if ancestors is None else ancestors
    if type(value) in (dict,list):
        if id(value) in ancestors:raise SchemaError(f"{path}: cyclic data")
        ancestors.add(id(value))
        if type(value) is dict:
            if not all(type(k) is str for k in value):raise SchemaError(f"{path}: string field names required")
            for key,item in value.items():_plain(item,f"{path}.{key}",ancestors)
        else:
            for i,item in enumerate(value):_plain(item,f"{path}[{i}]",ancestors)
        ancestors.remove(id(value))
    elif type(value) in (int,float):finite(value,path)
    elif value is not None and type(value) not in (str,bool):raise SchemaError(f"{path}: plain JSON data required")


def _fields(record,names,label):
    _require(type(record) is dict and record.keys()==set(names),f"{label}: missing or unknown fields")


def _records(items,fields,key_fields,expected,label,numeric=()):
    _require(type(items) is list,f"{label}: list required")
    indexed={}
    for item in items:
        _fields(item,fields,label)
        key=tuple(item[k] for k in key_fields)
        for k in key_fields:
            if k in ("stage_index","occupancy"):_require(type(item[k]) is int,f"{label}: integer {k} required")
            else:_require(type(item[k]) is str,f"{label}: string {k} required")
        _require(key not in indexed,f"{label}: duplicate identity {key}")
        _require(key in expected,f"{label}: unknown identity {key}")
        for f in numeric:finite(item[f],f"{label}.{f}")
        indexed[key]=item
    _require(indexed.keys()==set(expected),f"{label}: missing identities")
    return indexed


def _wire(actual,expected,label,operations=1):
    """Redundant export fields must describe the same raw snapshot. The envelope
    is floating arithmetic roundoff in serialization/evaluation, not a relaxed
    feasibility threshold. It also permits equivalent hand-authored decimals.
    """
    a=finite(actual,label);b=finite(expected,label)
    envelope=8*max(1,operations)*math.ulp(max(abs(a),abs(b),1e-300))
    _require(abs(a-b)<=envelope,f"{label}: export/raw snapshot or scaling mismatch")


def _variable(prefix,*keys):return f"{prefix}[{','.join(str(x) for x in keys)}]"


def _context(s,w):
    if not isinstance(s,Scenario):raise InputError("validated Scenario input required")
    users=tuple(sorted(u.id for u in s.users));sats=tuple(sorted(n.id for n in s.satellites));gs=tuple(sorted(g.id for g in s.ground_stations))
    if (w.user_ids,w.satellite_ids,w.ground_station_ids)!=(users,sats,gs):raise InputError("scenario/window ID domains differ")
    if not 0<=w.window_index<s.window_count or w.start_seconds!=w.window_index*s.window_seconds or w.duration_seconds!=s.window_seconds:
        raise InputError("scenario/window time domains differ")
    access={(l.user_id,l.satellite_id):l.distance_m for l in s.access_schedule[w.window_index].links}
    geometry_roundoff=0
    if s.orbit is not None:
        from .physical import verify_window
        try:geometry_roundoff=verify_window(s,w)
        except ValueError as exc:raise InputError(str(exc)) from exc
        ground={(n,g):w.ground_distances_m[i][j] for i,n in enumerate(sats) for j,g in enumerate(gs) if w.ground_distances_m[i][j] is not None}
    else:ground={(l.satellite_id,l.ground_station_id):l.distance_m for l in s.ground_links}
    if w.access_distances_m!=tuple(tuple(access.get((u,n)) for n in sats) for u in users):raise InputError("access trace differs from source")
    if w.ground_distances_m!=tuple(tuple(ground.get((n,g)) for g in gs) for n in sats):raise InputError("ground trace differs from source")
    edges={tuple(sorted((e.satellite_a_id,e.satellite_b_id))):e.distance_m for e in (w.isl_links if s.orbit is not None else s.isl_links)}
    if edges!={tuple(sorted((e.satellite_a_id,e.satellite_b_id))):e.distance_m for e in w.isl_links}:raise InputError("ISL trace differs from source")
    # Independent Floyd-Warshall, not the C05 Dijkstra/path cache.
    d={(a,b):(0.0 if a==b else edges.get(tuple(sorted((a,b))),math.inf)) for a in sats for b in sats}
    for k in sats:
        for a in sats:
            for b in sats:d[(a,b)]=min(d[(a,b)],d[(a,k)]+d[(k,b)])
    for a in sats:
        for b in sats:
            path=w.paths.get(a,b);expected=d[(a,b)]
            if math.isinf(expected):
                if path is not None:raise InputError("unreachable pair has a cached path")
                continue
            if path is None:raise InputError("reachable pair lacks a cached path")
            pairs=list(zip(path.nodes,path.nodes[1:]))
            if path.nodes[0]!=a or path.nodes[-1]!=b or any(tuple(sorted(pair)) not in edges for pair in pairs):raise InputError("cached path uses nonexistent endpoints/edges")
            length=math.fsum(edges[tuple(sorted(pair))] for pair in pairs)
            rounding=max(1,len(sats))*(geometry_roundoff+math.ulp(max(abs(expected),abs(length),abs(path.distance_m),1e-300)))
            if abs(length-expected)>rounding or abs(path.distance_m-length)>rounding:raise InputError("cached path cost is not the source shortest distance")
    return users,sats,gs,access,ground,d


def _rates(s,access,alpha,coefficients):
    capacities={n.id:n.access_capacity for n in s.satellites}
    keys={(u,n,k) for u,n in alpha for k in range(1,capacities[n]+1)}
    if coefficients is not None:
        if s.family_classification!="analytical_fixture" or type(coefficients) is not dict or coefficients.keys()!=keys:
            raise InputError("trusted analytical radio fixture has wrong classification/domain")
        out={}
        for key,v in coefficients.items():
            if type(key[-1]) is not int:raise InputError("radio occupancy keys must be integers")
            v=finite(v,"trusted radio coefficient")
            if v<=0:raise InputError("trusted radio coefficients must be positive")
            out[key]=v
        return out,"authored_coefficient_fixture"
    r=s.radio;out={}
    for u,n,k in keys:
        bw=r.bandwidth_hz/k
        gain=10**((r.user_gain_dbi+r.satellite_gain_dbi)/10)
        signal=r.transmit_watts*gain*(r.speed_of_light_mps/(4*math.pi*r.carrier_hz*access[(u,n)]))**2
        noise=r.boltzmann_joules_per_kelvin*r.temperature_kelvin*bw+r.external_interference_watts
        ratio=signal/noise
        rate=bw*(math.log2(1+ratio) if ratio>1e-8 else math.log1p(ratio)/math.log(2))
        if finite(rate,"recomputed rate")<=0:raise InputError("nonpositive physical rate")
        out[(u,n,k)]=rate
    return out,"physical_radio"


def validate_export(scenario: Scenario,window,export: dict,*,radio_coefficients: dict | None=None) -> ValidationReport:
    started=time.perf_counter();rows=Residuals();recomputed={};solver_status=None
    def finish(status,reason,errors=()):
        return ValidationReport(status,reason,solver_status,tuple(rows.rows),tuple(errors),recomputed,time.perf_counter()-started)
    try:
        _plain(export)
        _fields(export,{"export_schema_version","scenario_id","window_index","validation","solver_result","diagnostics","candidate"},"export")
        _require(type(export["export_schema_version"]) is int and export["export_schema_version"]==1,"unsupported export schema")
        _require(export["scenario_id"]==scenario.scenario_id and type(export["window_index"]) is int and export["window_index"]==window.window_index,"export/scenario identity mismatch")
        users,sats,ground_ids,access,ground,distance=_context(scenario,window)
        solver=export["solver_result"]
        _require(type(solver) is dict and {"raw_status","has_incumbent","values"}<=solver.keys(),"incomplete solver record")
        solver_status=solver["raw_status"]
        _require(type(solver_status) is str and type(solver["has_incumbent"]) is bool and type(solver["values"]) is dict,"invalid solver metadata")
        if not solver["has_incumbent"]:
            _require(export["candidate"] is None and solver["values"]=={},"absent incumbent has candidate/raw values")
            return finish("no_incumbent",solver_status)
        _require(solver_status not in ("infeasible","unbounded","inforunbd","not_attempted"),"incumbent contradicts solver termination")
        _require(type(export["candidate"]) is dict,"missing candidate")
        _validate_candidate(scenario,window,export,users,sats,ground_ids,access,ground,distance,radio_coefficients,rows,recomputed)
        return finish("valid","within_declared_feasibility_tolerances") if all(r.passed for r in rows.rows) else finish("rejected","constraint_or_numerical_rejection")
    except InputError as exc:return finish("input_error","invalid_trusted_context",(str(exc),))
    except (SchemaError,KeyError,TypeError,ValueError,OverflowError,ZeroDivisionError,RecursionError) as exc:
        return finish("schema_error","malformed_or_inconsistent_export",(str(exc),))


def _validate_candidate(s,w,export,users,sats,gs,access,ground,dist,coefficients,r,recomputed):
    request={u:s.slice_for_user(u) for u in users};functions={f.id:f for f in s.function_types};caps={n.id:n for n in s.satellites}
    alpha=tuple((u,n) for u in users for n in sats if (u,n) in access)
    xi=tuple((u,n,g) for u in users for n in sats for g in gs if (n,g) in ground)
    beta=tuple((u,k,f,i.instance_id,i.satellite_id) for u in users for k,f in enumerate(request[u].chain)
               for i in sorted(s.instances,key=lambda x:x.identity) if i.function_type_id==f)
    active=tuple(i.identity for i in s.instances)
    reachable=tuple((a,b) for a in sats for b in sats if math.isfinite(dist[(a,b)]))
    a_links=tuple((u,a,b) for u in users for a,b in reachable)
    chi=tuple((u,k,a,b) for u in users for k in range(len(request[u].chain)-1) for a,b in reachable)
    e_links=a_links
    z=tuple((n,k) for n in sats for k in range(caps[n].access_capacity+1))
    y=tuple((u,n,k) for u,n in alpha for k in range(1,caps[n].access_capacity+1))
    binary_domains={"alpha":alpha,"xi":xi,"beta":beta,"active":active,"access_link":a_links,"chi":chi,"egress_link":e_links,"z":z,"y":y}
    binary_names={_variable(p,*key) for p,domain in binary_domains.items() for key in domain}
    expected=binary_names|{_variable(p,*key) for p in ("g","qhat","tau") for key in beta}
    raw=export["solver_result"]["values"]
    _require(raw.keys()==expected,"unknown or missing raw variable IDs")
    for key,v in raw.items():finite(v,key)
    decoded={}
    def v(prefix,*key):return raw[_variable(prefix,*key)]
    def bit(prefix,*key):return decoded[_variable(prefix,*key)]
    def host(u,k,n,decode=False):return math.fsum((bit if decode else v)("beta",*key) for key in beta if (key[0],key[1],key[-1])==(u,k,n))
    def exit_sat(u,n,decode=False):return math.fsum((bit if decode else v)("xi",*key) for key in xi if key[:2]==(u,n))
    rates,provenance=_rates(s,access,alpha,coefficients)
    _require(type(export["diagnostics"]) is dict and export["diagnostics"].get("rate_provenance")==provenance,
             "radio provenance mismatch: original trusted fixture coefficients required")
    c=export["candidate"]
    _fields(c,{"deployment","assignments","users","activations","occupancy","radio_products"},"candidate")
    af={"user_id","stage_index","function_type_id","instance_id","satellite_id","beta_raw","beta_decoded","g","qhat","tau","cpu_mips","q_mips","processing_seconds","required_mips","amplitude","time_scale_seconds"}
    assignments=_records(c["assignments"],af,("user_id","stage_index","function_type_id","instance_id","satellite_id"),beta,"assignments",af-{"user_id","stage_index","function_type_id","instance_id","satellite_id"})
    activations=_records(c["activations"],{"function_type_id","instance_id","satellite_id","raw","decoded"},("function_type_id","instance_id","satellite_id"),active,"activations",("raw","decoded"))
    occupancies=_records(c["occupancy"],{"satellite_id","occupancy","raw","decoded"},("satellite_id","occupancy"),z,"occupancy",("raw","decoded"))
    products=_records(c["radio_products"],{"user_id","satellite_id","occupancy","raw","decoded","rate_coefficient_bps"},("user_id","satellite_id","occupancy"),y,"radio_products",("raw","decoded","rate_coefficient_bps"))
    _require(type(c["users"]) is dict and c["users"].keys()==set(users),"missing or unknown user totals")
    part_names={"user_access_seconds","access_first_host_seconds","internal_host_seconds","last_host_egress_seconds","egress_ground_seconds"}
    for u in users:
        _fields(c["users"][u],{"propagation_components","processing_seconds","access_transmission_seconds","total_delay_seconds","achieved_rate_bps"},"user totals")
        _fields(c["users"][u]["propagation_components"],part_names,"propagation components")
        for value in c["users"][u]["propagation_components"].values():finite(value,"propagation component")
        for key,value in c["users"][u].items():
            if key!="propagation_components":finite(value,f"user total {key}")
    dep=c["deployment"];_fields(dep,{"window_index","access","egress","allocations"},"deployment")
    _require(type(dep["window_index"]) is int and dep["window_index"]==w.window_index,"deployment window mismatch")
    access_choices=_records(dep["access"],{"user_id","satellite_id"},("user_id",),{(u,) for u in users},"deployment access")
    egress_choices=_records(dep["egress"],{"user_id","satellite_id","ground_station_id"},("user_id",),{(u,) for u in users},"deployment egress")
    stages={(u,k) for u in users for k in range(len(request[u].chain))}
    allocations=_records(dep["allocations"],{"user_id","stage_index","instance","cpu_mips"},("user_id","stage_index"),stages,"deployment stages",("cpu_mips",))
    for a in access_choices.values():_require(a["satellite_id"] in sats,"unknown access satellite")
    for e in egress_choices.values():_require(e["satellite_id"] in sats and e["ground_station_id"] in gs,"unknown egress pair")
    for (u,k),a in allocations.items():
        _fields(a["instance"],{"function_type_id","instance_id","satellite_id"},"selected instance")
        i=a["instance"];key=(u,k,i["function_type_id"],i["instance_id"],i["satellite_id"])
        _require(key in assignments,"unknown or incompatible selected instance")
    # All identities and numeric fields are checked before any residual comparison.
    for key in sorted(binary_names):
        value=raw[key];error=min(abs(value),abs(value-1))
        row=r.add("binary",key,error)
        if row.passed:decoded[key]=0 if abs(value)<=1e-8 else 1
    if len(decoded)!=len(binary_names):return
    for (u,k),a in allocations.items():
        i=a["instance"];key=(u,k,i["function_type_id"],i["instance_id"],i["satellite_id"])
        _wire(a["cpu_mips"],assignments[key]["cpu_mips"],"deployment cpu")
    for prefix,indexed in (("active",activations),("z",occupancies),("y",products)):
        for key,item in indexed.items():
            _require(type(item["decoded"]) is int and item["decoded"]==bit(prefix,*key),f"{prefix}: decoded/raw mismatch")
            _wire(item["raw"],v(prefix,*key),f"{prefix}: raw field")
    for u in users:
        r.eq("counts",f"C1:{u}",math.fsum(v("alpha",*k) for k in alpha if k[0]==u),1)
        r.logic(f"C1-decoded:{u}",sum(bit("alpha",*k) for k in alpha if k[0]==u)==1)
        r.eq("counts",f"C4:{u}",math.fsum(v("xi",*k) for k in xi if k[0]==u),1)
        r.logic(f"C4-decoded:{u}",sum(bit("xi",*k) for k in xi if k[0]==u)==1)
        declared_a=access_choices[(u,)]["satellite_id"];declared_e=egress_choices[(u,)]
        r.logic(f"C2:{u}",(u,declared_a) in access)
        r.logic(f"C5:{u}",(declared_e["satellite_id"],declared_e["ground_station_id"]) in ground)
        r.logic(f"export-alpha:{u}",{k[1] for k in alpha if k[0]==u and bit("alpha",*k)}=={declared_a})
        r.logic(f"export-xi:{u}",{k[1:] for k in xi if k[0]==u and bit("xi",*k)}=={(declared_e["satellite_id"],declared_e["ground_station_id"])})
        for k,f in enumerate(request[u].chain):
            selected=[key for key in beta if key[:2]==(u,k)]
            r.eq("counts",f"C7:{u}:{k}",math.fsum(v("beta",*key) for key in selected),1)
            declared=allocations[(u,k)]["instance"]
            r.logic(f"C7-decoded:{u}:{k}",sum(bit("beta",*key) for key in selected)==1)
            r.logic(f"export-beta:{u}:{k}",{key[2:] for key in selected if bit("beta",*key)}=={(declared["function_type_id"],declared["instance_id"],declared["satellite_id"])})
    for n in sats:
        for prefix,domain,limit in (("alpha",alpha,caps[n].access_capacity),("xi",xi,caps[n].egress_capacity)):
            chosen=[key for key in domain if key[1]==n]
            r.le("counts",f"capacity-{prefix}:{n}",math.fsum(v(prefix,*key) for key in chosen),limit)
            r.logic(f"capacity-{prefix}-decoded:{n}",sum(bit(prefix,*key) for key in chosen)<=limit)
    for key in active:
        f,i,n=key;assigned=[b for b in beta if b[2:]==key]
        eligible=sum(ft==f for u in users for ft in request[u].chain)
        count=math.fsum(v("beta",*b) for b in assigned)
        r.le("counts",f"C8:{key}",count,eligible*v("active",*key))
        r.le("counts",f"C9:{key}",v("active",*key),count)
        r.logic(f"activation-decoded:{key}",bit("active",*key)==int(any(bit("beta",*b) for b in assigned)))
    def conjunction(prefix,key,left,right,left_bit,right_bit):
        product=v(prefix,*key)
        r.le("counts",f"{prefix}-source:{key}",product,left)
        r.le("counts",f"{prefix}-target:{key}",product,right)
        r.ge("counts",f"{prefix}-both:{key}",product,left+right-1)
        r.logic(f"{prefix}-decoded:{key}",bit(prefix,*key)==left_bit*right_bit)
    for u in users:
        last=len(request[u].chain)-1
        for a in sats:
            for b in sats:
                av=raw.get(_variable("alpha",u,a),0);ab=decoded.get(_variable("alpha",u,a),0)
                pairs=[("access_link",(u,a,b),av,host(u,0,b),ab,host(u,0,b,True)),
                       ("egress_link",(u,a,b),host(u,last,a),exit_sat(u,b),host(u,last,a,True),exit_sat(u,b,True))]
                pairs.extend(("chi",(u,k,a,b),host(u,k,a),host(u,k+1,b),host(u,k,a,True),host(u,k+1,b,True)) for k in range(last))
                for prefix,key,left,right,lb,rb in pairs:
                    if math.isfinite(dist[(a,b)]):conjunction(prefix,key,left,right,lb,rb)
                    else:
                        r.le("counts",f"unreachable-{prefix}:{key}",left+right,1)
                        r.logic(f"unreachable-{prefix}-decoded:{key}",lb+rb<=1)
        for prefix,domain in (("access_link",a_links),("egress_link",e_links)):
            r.eq("counts",f"{prefix}-sum:{u}",math.fsum(v(prefix,*key) for key in domain if key[0]==u),1)
            r.logic(f"{prefix}-sum-decoded:{u}",sum(bit(prefix,*key) for key in domain if key[0]==u)==1)
        for k in range(last):
            r.eq("counts",f"chi-sum:{u}:{k}",math.fsum(v("chi",*key) for key in chi if key[:2]==(u,k)),1)
            r.logic(f"chi-sum-decoded:{u}:{k}",sum(bit("chi",*key) for key in chi if key[:2]==(u,k))==1)
    _resources_and_delay(s,w,users,sats,access,ground,dist,request,functions,caps,beta,active,z,y,rates,
                         assignments,products,access_choices,egress_choices,allocations,c,v,bit,r,recomputed)


def _resources_and_delay(s,w,users,sats,access,ground,dist,request,functions,caps,beta,active,z,y,rates,
                         assignments,products,access_choices,egress_choices,allocations,c,v,bit,r,recomputed):
    for key,a in assignments.items():
        u,k,f,i,n=key;L=request[u].demand_mbps*functions[f].psi_instructions_per_bit
        A=request[u].packet_bits*functions[f].omega_instructions_per_bit/1000000
        scale=A/L;b=v("beta",*key);g=v("g",*key);q=v("qhat",*key);tau=v("tau",*key);capacity=caps[n].cpu_capacity_mips
        for field,expected in {"beta_raw":b,"g":g,"qhat":q,"tau":tau,"required_mips":L,"amplitude":A,
                               "time_scale_seconds":scale,"cpu_mips":g*L,"q_mips":q*L,"processing_seconds":tau*scale}.items():
            _wire(a[field],expected,f"assignment {key} {field}")
        _require(type(a["beta_decoded"]) is int and a["beta_decoded"]==bit("beta",*key),"assignment decoded/raw mismatch")
        r.ge("cpu",f"G-lower:{key}",a["cpu_mips"],0,reference=capacity)
        r.le("cpu",f"G-upper:{key}",a["cpu_mips"],capacity,reference=capacity)
        r.le("cpu",f"G-gate:{key}",a["cpu_mips"],capacity*b,reference=capacity)
        r.eq("reciprocal",f"q-definition:{key}",q,g+1-b)
        r.ge("reciprocal",f"q-lower:{key}",q,1)
        r.le("reciprocal",f"q-upper:{key}",q,max(capacity/L,1))
        r.le("reciprocal",f"q-conditional:{key}",q,capacity/L*b+1-b)
        r.ge("reciprocal",f"tau-lower:{key}",tau,0);r.le("reciprocal",f"tau-upper:{key}",tau,1)
        r.eq("reciprocal",f"reciprocal-product:{key}",tau*q,b)
        if bit("beta",*key):
            r.logic(f"selected-G-positive:{key}",a["cpu_mips"]>0)
            r.ge("cpu",f"selected-minimum:{key}",a["cpu_mips"],L,reference=capacity)
    for u in users:
        for k,f in enumerate(request[u].chain):
            L=request[u].demand_mbps*functions[f].psi_instructions_per_bit
            r.ge("cpu",f"C13:{u}:{k}",math.fsum(a["cpu_mips"] for key,a in assignments.items() if key[:2]==(u,k)),L,
                 reference=max(n.cpu_capacity_mips for n in caps.values()))
    for n in sats:
        load=math.fsum(a["cpu_mips"] for key,a in assignments.items() if key[-1]==n)
        overhead=math.fsum(functions[f].base_overhead_mips*v("active",f,i,host) for f,i,host in active if host==n)
        r.le("cpu",f"C14:{n}",load+overhead,caps[n].cpu_capacity_mips,reference=caps[n].cpu_capacity_mips)
        used={key[2:] for key in beta if key[-1]==n and bit("beta",*key)}
        physical_load=math.fsum(a["cpu_mips"] for key,a in assignments.items() if key[-1]==n and bit("beta",*key))
        physical_overhead=math.fsum(functions[f].base_overhead_mips for f,i,host in used)
        r.le("cpu",f"C14-physical:{n}",physical_load+physical_overhead,caps[n].cpu_capacity_mips,reference=caps[n].cpu_capacity_mips)
        r.logic(f"C15-physical:{n}",len(used)<=caps[n].max_active_instances)
        count=math.fsum(v("active",*key) for key in active if key[-1]==n)
        r.le("counts",f"C15:{n}",count,caps[n].max_active_instances)
        r.logic(f"C15-decoded:{n}",sum(bit("active",*key) for key in active if key[-1]==n)<=caps[n].max_active_instances)
        r.eq("counts",f"occupancy-choice:{n}",math.fsum(v("z",*key) for key in z if key[0]==n),1)
        r.logic(f"occupancy-choice-decoded:{n}",sum(bit("z",*key) for key in z if key[0]==n)==1)
        occupancy=math.fsum(k*v("z",n,k) for node,k in z if node==n)
        associations=math.fsum(v("alpha",u,node) for u,node in access if node==n)
        r.eq("counts",f"occupancy-count:{n}",occupancy,associations)
        r.logic(f"occupancy-count-decoded:{n}",sum(k*bit("z",n,k) for node,k in z if node==n)==sum(bit("alpha",u,node) for u,node in access if node==n))
    for key in y:
        u,n,k=key;product=v("y",*key);a=v("alpha",u,n);level=v("z",n,k)
        r.le("counts",f"y-access:{key}",product,a);r.le("counts",f"y-occupancy:{key}",product,level)
        r.ge("counts",f"y-both:{key}",product,a+level-1)
        r.logic(f"y-decoded:{key}",bit("y",*key)==bit("alpha",u,n)*bit("z",n,k))
        r.eq("throughput",f"export-rate-coefficient:{key}",products[key]["rate_coefficient_bps"],rates[key],reference=request[u].demand_mbps*1e6)
    for u,n in access:
        r.eq("counts",f"y-sum:{u}:{n}",math.fsum(v("y",*key) for key in y if key[:2]==(u,n)),v("alpha",u,n))
        r.logic(f"y-sum-decoded:{u}:{n}",sum(bit("y",*key) for key in y if key[:2]==(u,n))==bit("alpha",u,n))
    speed=s.radio.speed_of_light_mps
    for u in users:
        user_terms=[(bit("beta",*key),a["cpu_mips"],a["amplitude"],a["processing_seconds"]) for key,a in assignments.items() if key[0]==u]
        ep=processing_error(user_terms)
        if ep is not None:r.add("processing",f"E_proc:{u}",ep)
        else:r.logic(f"E_proc-positive-G:{u}",False)
        service=math.fsum(v("y",*key)*rate for key,rate in rates.items() if key[0]==u)
        r.ge("throughput",f"throughput-raw:{u}",service,request[u].demand_mbps*1e6,reference=request[u].demand_mbps*1e6)
        raw_parts={
            "user_access_seconds":math.fsum(v("alpha",u,n)*d/speed for (user,n),d in access.items() if user==u),
            "access_first_host_seconds":math.fsum(v("access_link",u,a,b)*d/speed for (a,b),d in dist.items() if math.isfinite(d)),
            "internal_host_seconds":math.fsum(v("chi",u,k,a,b)*d/speed for k in range(len(request[u].chain)-1) for (a,b),d in dist.items() if math.isfinite(d)),
            "last_host_egress_seconds":math.fsum(v("egress_link",u,a,b)*d/speed for (a,b),d in dist.items() if math.isfinite(d)),
            "egress_ground_seconds":math.fsum(v("xi",u,n,g)*d/speed for (n,g),d in ground.items())}
        raw_tx=math.fsum(v("y",*key)*request[u].packet_bits/rate for key,rate in rates.items() if key[0]==u)
        raw_proc=math.fsum(t for selected,g,a,t in user_terms);raw_total=math.fsum([*raw_parts.values(),raw_tx,raw_proc])
        reported=c["users"][u];operations=max(1,len(user_terms),len(dist),len(y))
        for key,x in raw_parts.items():_wire(reported["propagation_components"][key],x,f"{u}:{key}",operations)
        for key,x in {"processing_seconds":raw_proc,"access_transmission_seconds":raw_tx,"total_delay_seconds":raw_total,"achieved_rate_bps":service}.items():
            _wire(reported[key],x,f"{u}:{key}",operations)
        raw_excess=max(0,raw_total-request[u].delay_limit_seconds)
        r.add("raw_delay",f"C16-raw:{u}",raw_excess)
        chosen_a=access_choices[(u,)]["satellite_id"];chosen_e=egress_choices[(u,)]
        selected=[allocations[(u,k)] for k in range(len(request[u].chain))]
        hosts=[a["instance"]["satellite_id"] for a in selected];egress=chosen_e["satellite_id"];gs=chosen_e["ground_station_id"]
        pairs=[(chosen_a,hosts[0]),*zip(hosts,hosts[1:]),(hosts[-1],egress)]
        path_ok=all(math.isfinite(dist[p]) for p in pairs) and (u,chosen_a) in access and (egress,gs) in ground
        r.logic(f"physical-route:{u}",path_ok)
        physical_total=None;other=None
        level=sum(bit("alpha",user,n) for user,n in access if n==chosen_a)
        physical_rate=rates.get((u,chosen_a,level))
        r.logic(f"physical-radio-occupancy:{u}",physical_rate is not None)
        if physical_rate is not None:
            r.ge("throughput",f"throughput-physical:{u}",physical_rate,request[u].demand_mbps*1e6,reference=request[u].demand_mbps*1e6)
        if path_ok and physical_rate is not None and all(a["cpu_mips"]>0 for a in selected):
            parts={"user_access_seconds":access[(u,chosen_a)]/speed,
                   "access_first_host_seconds":dist[pairs[0]]/speed,
                   "internal_host_seconds":math.fsum(dist[p] for p in pairs[1:-1])/speed,
                   "last_host_egress_seconds":dist[pairs[-1]]/speed,"egress_ground_seconds":ground[(egress,gs)]/speed}
            physical_tx=request[u].packet_bits/physical_rate
            physical_proc=math.fsum(request[u].packet_bits*functions[a["instance"]["function_type_id"]].omega_instructions_per_bit/(a["cpu_mips"]*1000000) for a in selected)
            physical_total=math.fsum([*parts.values(),physical_tx,physical_proc])
            other=math.fsum([*(abs(raw_parts[k]-parts[k]) for k in parts),abs(raw_tx-physical_tx)])
            r.add("reconstruction",f"nonprocessing-error:{u}",other)
            r.le("e2e",f"C16-physical:{u}",physical_total,request[u].delay_limit_seconds)
            if ep is not None:r.add("total_error",f"error-budget:{u}",ep+other+raw_excess)
        recomputed[u]={"processing_error_seconds":ep,"other_reconstruction_error_seconds":other,
                       "raw_delay_excess_seconds":raw_excess,"physical_total_delay_seconds":physical_total,
                       "raw_total_delay_seconds":raw_total,"raw_service_bps":service,"physical_rate_bps":physical_rate}
