"""Hand-authored C06 fixtures; no sampling, placement heuristic or solver oracle."""
import pytest
from pyscipopt import quicksum

from stars_rl.models import (
    Scenario, TraceMetadata, GenerationMetadata, Radio, FunctionType, Slice, User,
    GroundStation, Satellite, InstanceKey, AccessWindow, AccessLink, GroundLink, ISLLink,
)
from stars_rl.topology.trace import build_trace
from stars_rl.optimization.backend import solve


@pytest.fixture
def scenario_factory():
    def make(*, users=1, nodes=("a","b"), chain=("f0",), ground_ids=("g0",),
             edges=None, access=None, ground=None, access_capacity=2, egress_capacity=2):
        user_ids=tuple(f"u{i}" for i in range(users))
        if edges is None: edges=tuple((a,b,100000) for a,b in zip(nodes,nodes[1:]))
        if access is None: access=tuple((u,s) for u in user_ids for s in nodes)
        if ground is None: ground=tuple((s,g) for s in nodes for g in ground_ids)
        s=Scenario(1,"c06-fixture","c06-fixtures-v1","analytical_fixture",1,60,
            TraceMetadata("c06-group","c06-root","authored-graph","authored-layout","authored-demand",
                          None,0,60,GenerationMetadata("authored",None,None,(),())),
            Radio(14e9,.1,15,40,100e6,290,"exogenous",0,299792458,1.380649e-23),
            (FunctionType("f0",10,10,5),FunctionType("f1",20,20,10)),
            (Slice("slice0",chain,2,12000,.05),),tuple(User(u,"slice0",None) for u in user_ids),
            tuple(GroundStation(g,None) for g in ground_ids),
            tuple(Satellite(n,300,access_capacity,egress_capacity,4) for n in nodes),
            tuple(InstanceKey(f,i,n) for f in ("f0","f1") for i in ("i0","i1") for n in nodes),
            (AccessWindow(0,tuple(AccessLink(u,n,500000) for u,n in access)),),
            tuple(GroundLink(n,g,500000) for n,g in ground),tuple(ISLLink(a,b,d) for a,b,d in edges))
        trace=build_trace(s)
        return trace.scenario,trace.windows[0]
    return make


@pytest.fixture
def solve_case():
    def run(model):
        return solve(model,stage="c06_discrete",objective_name="feasibility",objective_units="constant",time_limit=2)
    return run


@pytest.fixture
def fix_choice():
    def fix(model,registry,key,value):
        # A missing variable is a logical zero. Fixing it to 1 must be infeasible,
        # never add a forbidden-domain variable to the production model.
        model.addCons(quicksum([registry.get(key,0)])==value)
    return fix
