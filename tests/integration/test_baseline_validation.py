"""Independent baseline objective and original-reference corruption oracles."""
from copy import deepcopy
import pytest

from stars_rl.simulation import simulate
from stars_rl.validation.monolithic import validate_monolithic

pytestmark=pytest.mark.solver


@pytest.mark.parametrize('family',['d_alpha','d_xi','d_beta','unknown','objective','nan'])
def test_monolithic_validator_independently_rejects_corruptions(episode_trace,family):
    trace,rates=episode_trace();out=simulate(trace,'mono-temporal',total_budget_seconds=2,radio_coefficients_by_window=rates)
    assert out.status=='success'
    record=out.windows[1];data=deepcopy(record.export);raw=data['solver_result']['values']
    if family.startswith('d_'):
        raw[next(k for k in raw if k.startswith(family+'['))]=2
    elif family=='unknown':raw['unknown_aux[u0]']=0
    elif family=='nan':raw[next(k for k in raw if k.startswith('d_alpha['))]=float('nan')
    else:data['solver_result']['objective']=99
    result=validate_monolithic(trace.scenario,trace.windows[1],data,mode='temporal',previous=record.previous_committed,radio_coefficients=rates[1])
    assert not result['valid']


def test_monolithic_Q_objective_recomputed_not_trusted(episode_trace):
    trace,rates=episode_trace();out=simulate(trace,'mono-delay',total_budget_seconds=2,radio_coefficients_by_window=rates)
    assert out.status=='success'
    data=deepcopy(out.windows[0].export);data['solver_result']['objective']=99
    result=validate_monolithic(trace.scenario,trace.windows[0],data,mode='Q',radio_coefficients=rates[0])
    assert not result['valid'] and result['deployment']['valid']


def test_Q_mean_over_two_users_with_literal_fixed_allocations(episode_trace):
    from dataclasses import replace
    from stars_rl.models import User,AccessWindow,AccessLink
    from stars_rl.topology.trace import build_trace
    from stars_rl.optimization.baselines import build_monolithic_method
    from stars_rl.optimization.monolithic import export_solution
    from stars_rl.optimization.backend import solve
    trace,_=episode_trace(forced=False);s=trace.scenario
    s=replace(s,users=(*s.users,User('u1','slice0',None)),
              access_schedule=tuple(AccessWindow(k,tuple(AccessLink(u,'s0',500000) for u in ('u0','u1'))) for k in range(3)))
    w=build_trace(s).windows[0]
    rates={(u,'s0',n):12000000 for u in ('u0','u1') for n in (1,2)}
    m,v=build_monolithic_method(s,w,'mono-delay',radio_coefficients=rates)
    # This is an encoding/normalization oracle at explicit G50 allocations,
    # not a performance claim about solving an unrestricted allocation problem.
    for u in ('u0','u1'):m.addCons(v.full.resources.terms[(u,0,'f0','i0','s0')].g==2.5)
    r=solve(m,stage='monolithic',objective_name='Q',objective_units='dimensionless',time_limit=2)
    d=export_solution(m,s,w,v.full,r)
    checked=validate_monolithic(s,w,d,mode='Q',radio_coefficients=rates)
    expected=(800000/299792458+.0024+.001)/.05
    assert checked['valid'] and r.absolute_gap<=1e-8
    assert r.objective==pytest.approx(expected,rel=0,abs=1e-8)
    assert checked['objective']['actual']==pytest.approx(expected,rel=0,abs=1e-8)
