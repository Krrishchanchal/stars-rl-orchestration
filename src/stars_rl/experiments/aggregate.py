"""Saved-artifact analysis. Standard library only; never reconstruct or solve models."""
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import random

from .manifest import atomic_json,checked_path,digest,file_hash,read_json

EVENTS=('access_switches','egress_switches','assignment_changes','host_changes','instance_id_changes',
        'instance_activations','instance_deactivations','outage','restoration')
RATIOS=(.25,.5,1.,2.,4.)


def number(value,*,minimum=None):
    if type(value) not in (int,float) or not math.isfinite(value) or (minimum is not None and value<minimum):
        raise ValueError('finite numeric value outside required domain')
    return value


def percentile(values,q):
    if not 0<=q<=1:raise ValueError('quantile outside [0,1]')
    if not values:return None
    values=sorted(number(v) for v in values);position=q*(len(values)-1);lower=int(position)
    return values[lower]+(values[min(lower+1,len(values)-1)]-values[lower])*(position-lower)


def describe(values):
    values=[number(v) for v in values]
    return dict(n=len(values),mean=sum(values)/len(values) if values else None,p95=percentile(values,.95))


def episode_score(costs,horizon,*,failure_window=None,discount=.95):
    if type(horizon) is not int or horizon<1 or type(discount) not in (int,float) or not math.isfinite(discount) or not 0<=discount<=1:
        raise ValueError('invalid horizon or discount')
    if failure_window is not None and (type(failure_window) is not int or not 0<=failure_window<horizon):
        raise ValueError('invalid failure window')
    count=horizon if failure_window is None else failure_window
    if len(costs)!=count:raise ValueError('missing or fabricated observed costs')
    if any(not 0<=number(c)<=3 for c in costs) or (costs and costs[0]!=0):raise ValueError('invalid actual churn/setup cost')
    value=sum(discount**i*c for i,c in enumerate(costs))
    if failure_window is not None:value+=discount**failure_window*4*sum(discount**j for j in range(horizon-failure_window))
    return value


def crossed_bootstrap(matrix,seed=0):
    if type(seed) is not int or not matrix or not matrix[0]:raise ValueError('nonempty seed-group matrix and integer seed required')
    k,m=len(matrix),len(matrix[0])
    if any(len(row)!=m for row in matrix):raise ValueError('incomplete crossed seed-group grid')
    matrix=[[number(v) for v in row] for row in matrix];rng=random.Random(seed);draws=[]
    for _ in range(2000):
        rows=[rng.randrange(k) for _ in range(k)];columns=[rng.randrange(m) for _ in range(m)]
        draws.append(sum(matrix[i][j] for i in rows for j in columns)/(k*m))
    return dict(delta=sum(map(sum,matrix))/(k*m),interval_95=[percentile(draws,.025),percentile(draws,.975)],
        per_seed=[sum(row)/m for row in matrix],per_group=[sum(row[j] for row in matrix)/k for j in range(m)],
        training_seed_count=k,scenario_group_count=m,bootstrap_seed=seed,draw_count=2000,replicates=draws,
        resampling='Independent training-seed and scenario-group resampling; Cartesian grid and paired baseline preserved',
        interpretation='descriptive/exploratory; fewer than 3 seeds or 10 groups' if k<3 or m<10 else 'exploratory crossed bootstrap; grouping assumptions apply')


def paired_group_bootstrap(differences,seed=0):
    values=[number(v) for v in differences]
    if not values or type(seed) is not int:raise ValueError('nonempty paired group differences and integer seed required')
    rng=random.Random(seed);n=len(values)
    draws=[sum(values[rng.randrange(n)] for _ in range(n))/n for _ in range(2000)]
    return dict(delta=sum(values)/n,interval_95=[percentile(draws,.025),percentile(draws,.975)],
        scenario_group_count=n,bootstrap_seed=seed,draw_count=2000,replicates=draws,
        interpretation='descriptive/exploratory; paired groups only',resampling='Paired scenario groups, never individual windows')


def paired_scores(rows,baseline,policies,seed=0):
    """Average episodes inside groups before crossing policy seeds and groups."""
    lookup={};groups={};budgets=set()
    for row in rows:
        if row['status'] not in ('success','failed'):raise ValueError('invalid/error episodes cannot enter network statistics')
        key=(row['method'],row['trace_hash'])
        if key in lookup:raise ValueError('duplicate normalized episode for one method')
        lookup[key]=row;budgets.add(row['budget_seconds'])
        previous=groups.setdefault(row['trace_hash'],row['group'])
        if previous!=row['group']:raise ValueError('duplicate exogenous trace relabeled as independent groups')
    if len(budgets)!=1:raise ValueError('paired methods require identical window budgets')
    reference={h for method,h in lookup if method==baseline}
    if not reference:raise ValueError('paired baseline missing')
    ordered_groups=sorted({groups[h] for h in reference});matrix=[]
    for method in policies:
        if {h for name,h in lookup if name==method}!=reference:raise ValueError('missing episodes in paired method/seed grid')
        values=[]
        for group in ordered_groups:
            hashes=sorted(h for h in reference if groups[h]==group)
            values.append(sum(lookup[method,h]['score']-lookup[baseline,h]['score'] for h in hashes)/len(hashes))
        matrix.append(values)
    result=crossed_bootstrap(matrix,seed)
    return result|dict(method_order=list(policies),group_order=ordered_groups,differences=matrix,episode_count_per_method=len(reference))


def _hashes(folder,mapping):
    if type(mapping) is not dict or not mapping:raise ValueError('missing saved artifact hashes')
    for name,expected in mapping.items():
        if file_hash(checked_path(folder,name))!=expected:raise ValueError('saved artifact hash mismatch: '+name)


def _version(data):
    if type(data) is not dict or type(data.get('schema_version')) is not int or data['schema_version']!=1:
        raise ValueError('unsupported saved manifest schema/version')


def _trace(data):
    if type(data.get('trace_schema_version')) is not int or data['trace_schema_version']!=1:raise ValueError('unsupported saved trace schema')
    def normalize(value):
        if isinstance(value,dict):return {k:normalize(v) for k,v in value.items()}
        if isinstance(value,list):return [normalize(v) for v in value]
        return int(value) if type(value) is float and value.is_integer() else value
    def checksum(value):
        return hashlib.sha256(json.dumps(normalize(value),sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    payload={k:v for k,v in data.items() if k not in ('content_hash','artifact_hash')}
    if checksum(payload)!=data['artifact_hash']:raise ValueError('saved trace artifact checksum differs')
    source=dict(data['scenario'])
    for key in ('scenario_id','family_id','family_classification','metadata'):source.pop(key)
    if checksum(dict(content_hash_schema_version=1,scenario_inputs=source))!=data['content_hash']:
        raise ValueError('saved exogenous trace content checksum differs')
    return data['scenario']


def extract_episode(row,scenario,*,method,group,scope):
    """Physical samples are conditional on validated committed windows only."""
    if row['status'] not in ('success','failed'):raise ValueError('infrastructure/numerical/aborted episodes invalidate analysis')
    horizon=scenario['window_count'];windows=row['windows'];failure=row['failure_window']
    if len(windows)!=horizon or [w['window_index'] for w in windows]!=list(range(horizon)):
        raise ValueError('missing or reordered window records')
    attempted=horizon if failure is None else failure+1
    if (row['status']=='success')!=(failure is None):raise ValueError('failure outcome/index disagree')
    if type(attempted) is not int or not 1<=attempted<=horizon:raise ValueError('invalid attempted horizon')
    transitions=row.get('transitions')
    if transitions is not None and len(transitions)!=attempted:raise ValueError('missing transition records')
    costs=[];delays=[];cpu=[];active=[];decisions=[];solves=[];events={name:[] for name in EVENTS};actions=[0]*5;statuses=Counter();timeout=False
    physical_windows=[]
    capacities=sum(n['cpu_capacity_mips'] for n in scenario['satellites'])
    overhead={f['id']:f['base_overhead_mips'] for f in scenario['function_types']}
    for index,w in enumerate(windows):
        if index>=attempted:
            if w['status']!='not_attempted' or w['metrics'] is not None or w.get('export') is not None or w.get('committed_deployment') is not None:
                raise ValueError('unobserved physical windows must stay null/not_attempted')
            physical_windows.append(dict(window_index=index,delay_ms=None,cpu_utilization=None,active_instances=None))
            continue
        success=failure is None or index<failure
        if w.get('error') is not None:raise ValueError('recorded implementation error invalidates analysis')
        if success and w['status']!='committed':raise ValueError('successful prefix contains missing deployment')
        if not success and w['status'] not in ('failed','late'):raise ValueError('implementation error is not a modeled failure')
        metrics=w['metrics']
        if metrics is not None:
            for name in EVENTS:
                value=metrics[name]
                if value is not None:events[name].append(number(value,minimum=0))
        if success:
            if metrics is not None:
                cost=sum(number(metrics[key],minimum=0) for key in ('d_alpha','d_xi','d_beta'))
            elif scope=='controlled_test_adapter' and transitions is not None:cost=-number(transitions[index]['reward'])
            else:raise ValueError('committed actual change metrics missing')
            costs.append(cost)
        if transitions is not None:
            t=transitions[index]
            if t['window_index']!=index or bool(t['terminated'])!=(index==attempted-1):raise ValueError('invalid transition chronology')
            expected=-costs[-1] if success else -4*sum(.95**j for j in range(horizon-index))
            if abs(number(t['reward'])-expected)>1e-8:raise ValueError('reward disagrees with actual events/failure tail')
            action=t['action']
            if type(action) is not int or not 0<=action<5:raise ValueError('invalid recorded ratio action')
            if index:actions[action]+=1
        elif index and w['rho'] in RATIOS:actions[RATIOS.index(w['rho'])]+=1
        decisions.append(number(w['elapsed_seconds'],minimum=0))
        timeout|=w['status']=='late'
        for stage in w['stages'].values():
            raw=stage['raw_status']
            if raw=='not_attempted':continue
            if raw in ('unbounded','inforunbd','infrastructure_error','numerical_rejection') or stage.get('outcome')=='model_error':
                raise ValueError('stage model/implementation error invalidates analysis')
            statuses[raw]+=1;timeout|=raw=='timelimit'
            seconds=stage['timings'].get('solve_wall_seconds')
            if seconds is not None:solves.append(number(seconds,minimum=0))
        export=w['export']
        if not success:
            physical_windows.append(dict(window_index=index,delay_ms=None,cpu_utilization=None,active_instances=None));continue
        if export is None:
            if scope!='controlled_test_adapter':raise ValueError('committed physical export missing')
            physical_windows.append(dict(window_index=index,delay_ms=None,cpu_utilization=None,active_instances=None));continue
        if not w['commit_validation'].get('valid'):raise ValueError('physical samples lack independent commit approval')
        candidate=export['candidate'];samples=[1000*number(u['total_delay_seconds'],minimum=0) for u in candidate['users'].values()]
        if set(candidate['users'])!={u['id'] for u in scenario['users']}:raise ValueError('missing user delay samples')
        deployments=candidate['deployment']['allocations']
        allocated=sum(number(a['cpu_mips'],minimum=0) for a in deployments)
        activated=[a for a in candidate['activations'] if a['decoded']==1]
        used=allocated+sum(overhead[a['function_type_id']] for a in activated)
        if capacities<=0:raise ValueError('committed CPU requires positive capacity')
        utilization=used/capacities
        delays.extend(samples);cpu.append(utilization);active.append(len(activated))
        physical_windows.append(dict(window_index=index,delay_ms=samples,cpu_utilization=utilization,active_instances=len(activated)))
    score=episode_score(costs,horizon,failure_window=failure)
    if 'penalized_score' in row and abs(number(row['penalized_score'])-score)>1e-8:raise ValueError('saved score differs from episode-origin penalty')
    return dict(method=method,trace_hash=row['trace_content_hash'],group=group,scope=scope,status=row['status'],score=score,
        budget_seconds=number(row['budget_seconds'],minimum=0),attempted_windows=attempted,unattempted_windows=horizon-attempted,
        failure_cause=row.get('failure_cause'),timeout=timeout,delay_ms=delays,cpu_utilization=cpu,active_instances=active,
        decision_seconds=decisions,solve_seconds=solves,episode_wall_seconds=number(row['wall_seconds'],minimum=0),
        events={k:sum(v) if v else None for k,v in events.items()},event_sample_windows={k:len(v) for k,v in events.items()},
        action_counts=actions,solver_statuses=dict(statuses),physical_windows=physical_windows)


def load_evaluation(folder):
    folder=Path(folder).resolve();manifest=read_json(folder/'manifest.json');_version(manifest)
    if manifest['status']!='completed':raise ValueError('only completed evaluations can be analyzed')
    _hashes(folder,manifest['artifact_hashes'])
    frozen=read_json(folder/'frozen-selection.json');_version(frozen)
    if file_hash(folder/'frozen-selection.json')!=manifest['freeze_hash']:raise ValueError('evaluation freeze mismatch')
    split=read_json(folder/'split.json');_version(split)
    if digest({k:v for k,v in split.items() if k!='split_hash'})!=split['split_hash'] or split['split_hash']!=frozen['split_hash']:
        raise ValueError('evaluation split identity mismatch')
    _hashes(folder,frozen['all_input_hashes'])
    baseline='fixed-'+str(float(frozen['comparator_rho']));policies=[p['policy_id'] for p in frozen['policies']]
    if len(policies)!=len(set(policies)) or len({p['seed'] for p in frozen['policies']})!=len(policies):raise ValueError('duplicate policy/seed')
    methods=list(dict.fromkeys(['fixed-0.5',baseline]+policies));hashes=split['partitions']['test']
    expected={f'test-{h}-{method}.json' for h in hashes for method in methods}
    found={name for name in manifest['artifact_hashes'] if name.startswith('test-') and name.endswith('.json')}
    if expected!=found:raise ValueError('incomplete or duplicate test-method grid')
    rows=[]
    for h in hashes:
        saved=read_json(folder/('input-'+h+'.json'));scenario=_trace(saved)
        if saved['content_hash']!=h or saved['artifact_hash']!=split['traces'][h]['artifact_hash']:raise ValueError('test trace identity differs')
        for method in methods:
            raw=read_json(folder/f'test-{h}-{method}.json')
            if raw['policy_id']!=method or raw['trace_content_hash']!=h or raw['component_id']!=split['traces'][h]['component_id'] or raw['partition']!='test':
                raise ValueError('test grouping/method/trace differs')
            if raw['budget_seconds']!=frozen['budget_seconds'] or raw['scope']!=manifest['scope']:raise ValueError('paired budget/scope differs')
            rows.append(extract_episode(raw,scenario,method=method,group=raw['component_id'],scope=raw['scope']))
    return rows,dict(kind='C17 frozen evaluation',scope=manifest['scope'],baseline=baseline,policies=policies,
        directory=str(folder),
        split_hash=split['split_hash'],source_manifest_sha256=file_hash(folder/'manifest.json'),freeze_sha256=manifest['freeze_hash'])


def load_fixed_runs(folders):
    rows=[];sources=[]
    for directory in folders:
        folder=Path(directory).resolve();manifest=read_json(folder/'manifest.json');_version(manifest)
        if manifest['status']!='completed':raise ValueError('aborted/interrupted fixed run is not analyzable')
        _hashes(folder,manifest['input_hashes']);_hashes(folder,manifest['artifact_hashes'])
        settings=read_json(folder/'settings.json');_version(settings);trace=read_json(folder/'trace.json');scenario=_trace(trace)
        episode=read_json(checked_path(folder,manifest['active_attempt']+'/episode.json'))
        if not episode['transition_valid']:raise ValueError('implementation error invalidates fixed run')
        summary=read_json(checked_path(folder,manifest['active_attempt']+'/summary.json'))
        method=settings['method_id']+('-rho-'+str(float(settings['rho'])) if settings['method_id']=='stars-fixed' else '')
        raw=dict(status=episode['status'],failure_window=episode['failure_window'],windows=episode['windows'],
            trace_content_hash=trace['content_hash'],budget_seconds=episode['total_budget_seconds'],wall_seconds=summary['episode_wall_seconds'],
            failure_cause=None if episode['failure_window'] is None else episode['windows'][episode['failure_window']]['reason'])
        rows.append(extract_episode(raw,scenario,method=method,group=scenario['metadata']['scenario_group_id'],scope=episode['runtime_adapter']))
        sources.append(dict(directory=str(folder),run_id=manifest['run_id'],manifest_sha256=file_hash(folder/'manifest.json'),trace_hash=trace['content_hash']))
    # Enforce paired identity even when this is only a single-method description.
    seen=set();groups={}
    for row in rows:
        key=(row['method'],row['trace_hash'])
        if key in seen:raise ValueError('duplicate normalized fixed-run episode')
        seen.add(key)
        if groups.setdefault(row['trace_hash'],row['group'])!=row['group']:raise ValueError('duplicate trace relabeled as independent groups')
    return rows,dict(kind='C13 fixed-method diagnostics',scope='diagnostic; not held-out trained-policy evidence',sources=sources,policies=[])


def training_curve(folder):
    folder=Path(folder).resolve();manifest=read_json(folder/'manifest.json');_version(manifest)
    if manifest['status']!='completed':raise ValueError('training curve requires completed accepted episodes')
    _hashes(folder,manifest['input_hashes'])
    if file_hash(checked_path(folder,manifest['active_boundary']))!=manifest['active_boundary_file_hash']:raise ValueError('training boundary checksum differs')
    boundary=read_json(checked_path(folder,manifest['active_boundary']))
    if digest({k:v for k,v in boundary.items() if k!='state_hash'})!=boundary['state_hash']:raise ValueError('training boundary integrity differs')
    points=[];actions=[0]*5
    for index,accepted in enumerate(manifest['completed_episodes']):
        path=checked_path(folder,accepted['summary'])
        if file_hash(path)!=accepted['sha256']:raise ValueError('training episode checksum differs')
        data=read_json(path)
        if data['episode_index']!=index:raise ValueError('training curve episode order differs')
        for step in data['steps']:
            if file_hash(checked_path(path.parent,step['artifact']))!=step['artifact_hash']:raise ValueError('training step checksum differs')
            if step['learning_eligible']:actions[step['action']]+=1
        score=-sum(.95**i*number(s['reward']) for i,s in enumerate(data['steps']))
        if abs(score-number(data['penalized_score']))>1e-8:raise ValueError('training score differs')
        points.append(dict(episode=index,score=score,failure=data['failure'],wall_seconds=data['wall_seconds'],learning_updates=data['learning_updates']))
    if actions!=boundary['learner']['action_counts'] or len(points)!=boundary['next_episode_index']:raise ValueError('training counters differ from accepted curve')
    return dict(run=str(folder),manifest_sha256=file_hash(folder/'manifest.json'),scope=manifest['scope'],points=points,action_counts=actions,
                limitation='Accepted episode curve only; abandoned attempts are not policy learning progress. A curve does not establish convergence or gain.')


def summarize(rows):
    methods={}
    for name in sorted({r['method'] for r in rows}):
        values=[r for r in rows if r['method']==name];groups={}
        for r in values:groups.setdefault(r['group'],[]).append(r['score'])
        scores={g:sum(v)/len(v) for g,v in sorted(groups.items())}
        samples=lambda key:[v for r in values for v in r[key]]
        delays=sorted(samples('delay_ms'));events={k:[r['events'][k] for r in values if r['events'][k] is not None] for k in EVENTS}
        counts=[sum(r['action_counts'][i] for r in values) for i in range(5)]
        methods[name]=dict(episodes=len(values),groups=len(scores),group_scores=scores,mean_group_score=sum(scores.values())/len(scores),
            failures=sum(r['status']=='failed' for r in values),failure_rate=sum(r['status']=='failed' for r in values)/len(values),
            completion_rate=sum(r['status']=='success' for r in values)/len(values),
            timeout_episodes=sum(r['timeout'] for r in values),timeout_rate=sum(r['timeout'] for r in values)/len(values),
            failure_causes=dict(Counter(r['failure_cause'] or 'unspecified' for r in values if r['status']=='failed')),
            attempted_windows=sum(r['attempted_windows'] for r in values),unattempted_windows=sum(r['unattempted_windows'] for r in values),
            delay_ms=describe(delays),delay_cdf=[[v,(i+1)/len(delays)] for i,v in enumerate(delays)],
            cpu_utilization=describe(samples('cpu_utilization')),active_instances=describe(samples('active_instances')),
            decision_seconds=describe(samples('decision_seconds')),solve_seconds=describe(samples('solve_seconds')),
            episode_wall_seconds=describe([r['episode_wall_seconds'] for r in values]),
            events={k:sum(v) if v else None for k,v in events.items()},
            event_sample_windows={k:sum(r['event_sample_windows'][k] for r in values) for k in EVENTS},
            action_counts=counts,action_fractions=[c/sum(counts) for c in counts] if sum(counts) else [None]*5,
            solver_statuses=dict(sum((Counter(r['solver_statuses']) for r in values),Counter())))
    return methods


def analyze(output,*,evaluation=None,runs=None,training=(),bootstrap_seed=0):
    if (evaluation is None)==(not runs):raise ValueError('choose exactly one evaluation or fixed-run source')
    if type(bootstrap_seed) is not int:raise ValueError('integer bootstrap seed required')
    rows,source=load_evaluation(evaluation) if evaluation is not None else load_fixed_runs(runs)
    methods=summarize(rows);comparisons={}
    if source['policies']:
        comparisons['policy_minus_tuned_fixed']=paired_scores(rows,source['baseline'],source['policies'],bootstrap_seed)
        fixed=paired_scores(rows,source['baseline'],['fixed-0.5'],bootstrap_seed)
        comparisons['fixed_0.5_minus_tuned_fixed']=paired_group_bootstrap(fixed['differences'][0],bootstrap_seed)
    elif len(methods)>1:
        baseline='stars-fixed-rho-0.5' if 'stars-fixed-rho-0.5' in methods else sorted(methods)[0]
        source['baseline']=baseline
        for method in sorted(methods):
            if method==baseline:continue
            paired=paired_scores(rows,baseline,[method],bootstrap_seed)
            comparisons[method+'_minus_'+baseline]=paired_group_bootstrap(paired['differences'][0],bootstrap_seed)
    result=dict(schema_version=1,status='completed',source=source,methods=methods,comparisons=comparisons,
        episodes=rows,training=[training_curve(p) for p in training],bootstrap_seed=bootstrap_seed,
        aggregation='J includes modeled failures; equal episodes within group, equal groups, then equal training seeds. Physical samples conditional on committed user-windows.',
        physical_units=dict(delay='milliseconds',cpu='fraction of total MIPS including active-instance overhead',instances='active count',time='seconds'),
        exclusions=[],limitation='Infrastructure/errors/missing pairs reject analysis. Small samples and diagnostic/controlled sources are descriptive; no RL superiority claim.')
    folder=Path(output).resolve();folder.mkdir(parents=True,exist_ok=False)
    atomic_json(folder/'analysis.json',result)
    with (folder/'episodes.csv').open('w',newline='',encoding='utf-8') as f:
        fields=['method','trace_hash','group','scope','status','score','budget_seconds','attempted_windows','unattempted_windows','timeout','failure_cause']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in rows:writer.writerow({k:row[k] for k in fields})
    with (folder/'methods.csv').open('w',newline='',encoding='utf-8') as f:
        fields=['method','episodes','groups','mean_group_score','failures','failure_rate','timeout_rate','delay_mean_ms','delay_p95_ms','observed_user_windows']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for method,data in methods.items():writer.writerow(dict(method=method,**{k:data[k] for k in fields[1:7]},
            delay_mean_ms=data['delay_ms']['mean'],delay_p95_ms=data['delay_ms']['p95'],observed_user_windows=data['delay_ms']['n']))
    atomic_json(folder/'analysis_manifest.json',dict(schema_version=1,input_source=source,analysis_sha256=file_hash(folder/'analysis.json'),
        code_sha256=file_hash(Path(__file__)),tables={p.name:file_hash(p) for p in folder.glob('*.csv')},solver_calls=0,
        scope='Saved artifacts only; no model construction, solving or learning.'))
    return result
