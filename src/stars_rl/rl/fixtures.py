"""Literal analytical topology for the C15 action gate; never training data.

Two 3000 km arms join hosts x,y to egress e; access a is 100 km
from y and b is 100 km from x. At the decision window, 6000 km
access links make crossed host routes exceed the 50 ms SLA. Prior a's
100 km access link permits the independently validated initial (a,x).
"""
from stars_rl.models import (Scenario,TraceMetadata,GenerationMetadata,Radio,FunctionType,Slice,User,
    GroundStation,Satellite,InstanceKey,AccessWindow,AccessLink,GroundLink,ISLLink)
from stars_rl.topology.trace import build_trace
from stars_rl.optimization.monolithic import build_full_model, export_solution
from stars_rl.optimization.backend import solve
from stars_rl.validation.deployment import validate_export
from .environment import StarsEnvironment
from .actions import RATIOS
from .sensitivity import decision_class, replay_actions


def tradeoff_fixture(regime='X', *, aliased=False, budget=10):
    if regime not in ('X','Y'):
        raise ValueError('regime X or Y required')
    next_links = (AccessLink('u','a',6000000),) if regime=='X' else (AccessLink('u','b',6000000),)
    if regime=='Y' and aliased:
        next_links += (AccessLink('u','a',20000000),)
    schedule = (AccessWindow(0,(AccessLink('u','a',100000),)),
                AccessWindow(1,(AccessLink('u','a',6000000),AccessLink('u','b',6000000))),
                AccessWindow(2,next_links))
    s = Scenario(1,'c15-tradeoff-'+regime+('-alias' if aliased else ''),'c15-analytical-v1','analytical_fixture',3,60,
        TraceMetadata('c15-group','c15-root','literal-graph','one-user','constant',None,0,180,
                      GenerationMetadata('authored',None,None,(),())),
        Radio(14e9,.1,15,40,100e6,290,'exogenous',0,299792458,1.380649e-23),
        (FunctionType('f',10,10,0),),(Slice('slice',('f',),2,12000,.05),),(User('u','slice',None),),
        (GroundStation('g',None),),tuple(Satellite(n,100 if n in ('x','y') else 0,2,2,2) for n in ('a','b','e','x','y')),
        (InstanceKey('f','i','x'),InstanceKey('f','i','y')),schedule,(GroundLink('e','g',500000),),
        (ISLLink('a','y',100000),ISLLink('b','x',100000),ISLLink('e','x',3000000),ISLLink('e','y',3000000)))
    trace = build_trace(s)
    rates = {w.window_index:{('u',n,k):12000000 for n in w.satellite_ids if w.access_distance('u',n) is not None
                             for k in (1,2)} for w in trace.windows}
    initial = _fixed_class(trace,0,'a','x',rates[0],budget)
    if not initial['valid']:
        raise RuntimeError('constructed initial state failed independent validation')
    return trace,rates,initial['export']


def _fixed_class(trace,index,access,host,rates,budget):
    s,w = trace.scenario,trace.windows[index]
    model,v = build_full_model(s,w,radio_coefficients=rates)
    model.addCons(v.discrete.alpha['u',access]==1)
    model.addCons(v.discrete.beta['u',0,'f','i',host]==1)
    result = solve(model,stage='class_enumeration',objective_name='feasibility',objective_units='constant',time_limit=budget)
    export = export_solution(model,s,w,v,result)
    checked = validate_export(s,w,export,radio_coefficients=rates).to_dict() if result.has_incumbent else None
    return dict(access=access,host=host,status=result.raw_status,outcome=result.outcome,
                valid=checked is not None and checked['valid'],validation=checked,export=export,
                absolute_gap=result.absolute_gap)


def constructed_report(budget=10):
    reports = []
    for regime,aliased in (('X',False),('Y',False),('Y',True)):
        trace,rates,initial = tradeoff_fixture(regime,aliased=aliased,budget=budget)
        env = StarsEnvironment(trace,total_budget_seconds=budget,radio_coefficients_by_window=rates,initial_export=initial)
        env.reset();env.step(1)
        sensitivity = replay_actions(env)
        classes = {}
        for index in (1,2):
            rows = []
            for a in trace.windows[index].satellite_ids:
                if trace.windows[index].access_distance('u',a) is not None:
                    for host in ('x','y'):
                        row = _fixed_class(trace,index,a,host,rates[index],budget)
                        # Fixed-class feasibility certificates retain raw export and independent checks.
                        rows.append(row)
            classes[str(index)] = rows
        sequences = []
        for first_action in range(5):
            first = env.fork()
            _,r1,done,_,_ = first.step(first_action)
            if done:
                raise RuntimeError('constructed decision unexpectedly failed')
            for second_action in range(5):
                second = first.fork()
                _,r2,done,_,_ = second.step(second_action)
                sequences.append(dict(actions=[first_action,second_action],rewards=[r1,r2],return_from_decision=r1+.95*r2,
                                      classes=[decision_class(first.records[-1].committed_deployment),
                                               decision_class(second.records[-1].committed_deployment)],terminated=done))
        meaningful = [r for r in classes['1'] if r['valid']]
        expected = {(r['access'],r['host']) for r in meaningful} == {('a','y'),('b','x')}
        certified = all(r['status'] in ('optimal','infeasible') for rows in classes.values() for r in rows)
        objective_checked = all(row['stages']['stage2']['status']=='optimal'
            and row['stages']['stage2']['absolute_gap'] is not None
            and row['stages']['stage2']['absolute_gap']<=1e-8
            and abs(row['stages']['stage2']['objective']-min(row['rho'],.5))<=1e-8
            for row in sensitivity['actions'])
        margins = {str(rho):abs(rho-.5) for rho in RATIOS}
        returns = {a:max(r['return_from_decision'] for r in sequences if r['actions'][0]==a) for a in range(5)}
        best = max(returns.values())
        reports.append(dict(regime=regime,aliased=aliased,trace_hash=trace.content_hash,
                            observation=list(sensitivity['observation']),sensitivity=sensitivity,classes=classes,sequences=sequences,
                            meaningful_current_classes_valid=expected,all_classes_certified=certified,
                            objective_optima_checked=objective_checked,
                            objective_margins=margins,first_action_returns=returns,
                            best_first_actions=[a for a in returns if abs(returns[a]-best)<1e-8],
                            return_margin=max(returns.values())-min(returns.values())))
    x,y,alias = reports
    passed = (all(r['meaningful_current_classes_valid'] and r['all_classes_certified'] and r['objective_optima_checked']
                  and abs(r['return_margin']-1.9)<=1e-8
                  and all(seq['terminated'] and seq['rewards'][0]==-1 and seq['rewards'][1] in (0,-2) for seq in r['sequences'])
                  for r in reports)
              and x['observation']!=y['observation'] and x['observation']==alias['observation']
              and set(x['best_first_actions']).isdisjoint(alias['best_first_actions'])
              and all(r['sensitivity']['distinct_successful_classes']==2 for r in reports))
    return dict(schema_version=1,constructed_gate_passed=passed,regimes=reports,
                discount=.95,scope='Analytical constructed solver gate only; no physical training readiness or RL gain claim')
