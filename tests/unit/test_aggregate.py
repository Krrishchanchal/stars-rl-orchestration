"""Independent arithmetic and statistical-unit oracles, not implementation copies."""
from copy import deepcopy
import random
import pytest

from stars_rl.experiments.aggregate import (crossed_bootstrap,paired_group_bootstrap,paired_scores,episode_score,
    extract_episode,percentile,summarize)


@pytest.mark.parametrize('discount',[0,.5,.95,1])
def test_early_failure_episode_origin_discount(discount):
    assert episode_score([0],3,failure_window=1,discount=discount)==pytest.approx(discount*4*(1+discount))
    assert episode_score([],3,failure_window=0,discount=discount)==pytest.approx(4*(1+discount+discount**2))
    assert episode_score([0,1,2],3,discount=discount)==pytest.approx(discount+2*discount**2)
    assert episode_score([0],3,failure_window=1,discount=.5)==3 # O-SCOREDISCOUNT, not 6


def test_no_fabricated_missing_churn_or_nonfinite_scores():
    with pytest.raises(ValueError):episode_score([0],3)
    with pytest.raises(ValueError):episode_score([1],1)
    with pytest.raises(ValueError):episode_score([0,float('nan')],2)
    with pytest.raises(ValueError):episode_score([0],3,failure_window=True)


def test_crossed_oracle_and_cartesian_resamples():
    global_state=random.getstate()
    result=crossed_bootstrap([[1,3],[5,7]],seed=19)
    assert result['delta']==4 and result['per_seed']==[2,6] and result['per_group']==[3,5]
    assert result['draw_count']==len(result['replicates'])==2000
    # For 1+4*r+2*c, independently resampling 2 rows and 2 columns gives
    # integer-valued means only. Independent cell resampling can give halves.
    assert all(v==int(v) and 1<=v<=7 for v in result['replicates'])
    assert result==crossed_bootstrap([[1,3],[5,7]],seed=19)
    assert random.getstate()==global_state
    assert 'descriptive' in result['interpretation']


def test_degenerate_crossed_and_fixed_group_bootstrap():
    assert crossed_bootstrap([[2]],0)['interval_95']==[2,2]
    assert paired_group_bootstrap([0,0],0)['interval_95']==[0,0]
    with pytest.raises(ValueError):crossed_bootstrap([[1,2],[3]],0)
    with pytest.raises(ValueError):crossed_bootstrap([[float('inf')]],0)


def row(method,trace,group,score):
    return dict(method=method,trace_hash=trace,group=group,score=score,budget_seconds=10,status='success')


def test_average_inside_group_before_equal_group_seed_weighting():
    rows=[row('base','a1','a',0),row('base','a2','a',0),row('base','b','b',0),
          row('s1','a1','a',0),row('s1','a2','a',2),row('s1','b','b',3),
          row('s2','a1','a',4),row('s2','a2','a',6),row('s2','b','b',7)]
    result=paired_scores(rows,'base',['s1','s2'],0)
    assert result['differences']==[[1,3],[5,7]] and result['delta']==4
    assert result['episode_count_per_method']==3
    rows[-1]['status']='failed'
    assert paired_scores(rows,'base',['s1','s2'],0)['delta']==4 # failure is included
    with pytest.raises(ValueError,match='duplicate normalized'):paired_scores(rows+[dict(rows[0])],'base',['s1','s2'])
    with pytest.raises(ValueError,match='missing episodes'):paired_scores(rows[:-1],'base',['s1','s2'])
    broken=deepcopy(rows);broken[-1]['group']='fake-independent'
    with pytest.raises(ValueError,match='relabeled'):paired_scores(broken,'base',['s1','s2'])
    broken=deepcopy(rows);broken[-1]['budget_seconds']=20
    with pytest.raises(ValueError,match='budgets'):paired_scores(broken,'base',['s1','s2'])


def hand_episode():
    metrics={name:0 for name in ('access_switches','egress_switches','assignment_changes','host_changes','instance_id_changes',
                               'instance_activations','instance_deactivations','outage','restoration')}
    metrics.update(d_alpha=0,d_xi=0,d_beta=0)
    candidate=dict(users={'u':{'total_delay_seconds':.01}},deployment={'allocations':[{'cpu_mips':20}]},
                   activations=[{'decoded':1,'function_type_id':'f'}])
    window=dict(window_index=0,status='committed',metrics=metrics,export={'candidate':candidate},
                commit_validation={'valid':True},rho=.5,elapsed_seconds=.5,
                stages={'stage1':{'raw_status':'optimal','timings':{'solve_wall_seconds':.2}}})
    episode=dict(status='success',failure_window=None,windows=[window],trace_content_hash='trace',budget_seconds=1,wall_seconds=.7)
    scenario=dict(window_count=1,satellites=[{'cpu_capacity_mips':100}],function_types=[{'id':'f','base_overhead_mips':10}],users=[{'id':'u'}])
    return episode,scenario


def test_literal_physical_units_cpu_overhead_and_conditional_statistics():
    episode,scenario=hand_episode();result=extract_episode(episode,scenario,method='fixed',group='g',scope='standard')
    assert result['delay_ms']==[10] and result['cpu_utilization']==[.3] and result['active_instances']==[1]
    summary=summarize([result])['fixed']
    assert summary['delay_ms']==dict(n=1,mean=10,p95=10) and summary['delay_cdf']==[[10,1]]
    assert summary['solve_seconds']['mean']==.2 and summary['decision_seconds']['mean']==.5
    assert summary['events']['access_switches']==0 and summary['action_counts']==[0]*5
    assert summary['action_fractions']==[None]*5
    assert percentile([0,10],.95)==9.5 and percentile([], .95) is None


def test_failed_and_unattempted_physical_metrics_are_not_zeros():
    episode,scenario=hand_episode();scenario['window_count']=3
    failed=dict(window_index=1,status='failed',metrics=None,export=None,rho=.5,elapsed_seconds=.4,
                stages={'stage1':{'raw_status':'timelimit','timings':{'solve_wall_seconds':.3}}})
    unattempted=dict(window_index=2,status='not_attempted',metrics=None,export=None,committed_deployment=None)
    episode.update(status='failed',failure_window=1,windows=episode['windows']+[failed,unattempted])
    result=extract_episode(episode,scenario,method='fixed',group='g',scope='standard')
    assert result['score']==pytest.approx(7.41) and result['timeout']
    assert result['delay_ms']==[10] and result['physical_windows'][2]['delay_ms'] is None
    assert result['physical_windows'][1]['cpu_utilization'] is None
    assert summarize([result])['fixed']['failure_rate']==1
    unattempted['metrics']={}
    with pytest.raises(ValueError,match='null'):extract_episode(episode,scenario,method='fixed',group='g',scope='standard')


def test_implementation_error_not_a_network_score():
    episode,scenario=hand_episode();episode['status']='infrastructure_error'
    with pytest.raises(ValueError,match='invalidate'):extract_episode(episode,scenario,method='x',group='g',scope='standard')
    episode['status']='success';episode['windows'][0]['stages']['stage1']['raw_status']='infrastructure_error'
    with pytest.raises(ValueError,match='invalidates'):extract_episode(episode,scenario,method='x',group='g',scope='standard')
