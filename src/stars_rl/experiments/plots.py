"""Standalone optional Matplotlib renderer. Reads saved analysis only; no solver imports."""
import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import sys
import textwrap


def render(analysis_path,output):
    source=Path(analysis_path).resolve()
    def invalid(value):raise ValueError('nonfinite analysis value: '+value)
    data=json.loads(source.read_text(encoding='utf-8'),parse_constant=invalid)
    if type(data.get('schema_version')) is not int or data['schema_version']!=1 or data.get('status')!='completed':
        raise ValueError('unsupported/incomplete saved analysis')
    metadata=json.loads((source.parent/'analysis_manifest.json').read_text(encoding='utf-8'))
    if type(metadata.get('schema_version')) is not int or metadata['schema_version']!=1:
        raise ValueError('unsupported analysis provenance schema')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=metadata['analysis_sha256']:raise ValueError('saved analysis checksum differs')
    folder=Path(output).resolve();folder.mkdir(parents=True,exist_ok=False)
    os.environ.setdefault('MPLCONFIGDIR',str(folder/'.matplotlib-cache'))
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError as exc:raise RuntimeError('Matplotlib is optional: use an existing plotting interpreter via --plot-python.') from exc
    methods=data['methods'];names=list(methods)
    if not names:raise ValueError('no methods to plot')
    labels=[('Q seed '+n.split('-seed-')[-1]) if n.startswith('q-') else
            ('STARS rho '+n.removeprefix('stars-fixed-rho-')) if n.startswith('stars-fixed-rho-') else n.replace('fixed-','rho ') for n in names]
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    scope=data['source']['scope'];files={}
    source_hashes=([data['source']['source_manifest_sha256']] if 'source_manifest_sha256' in data['source']
                   else [s['manifest_sha256'] for s in data['source'].get('sources',[])])
    scenarios=sorted({r['trace_hash'][:10] for r in data['episodes']})
    caption=(f"Analysis {digest[:16]}; run manifests {','.join(h[:10] for h in source_hashes)}; scenarios {','.join(scenarios)}; {data['source']['kind']}; scope: {scope}. "
             'Scores: equal groups; failures included. Physical metrics: committed samples only. Diagnostic/small samples are descriptive.')
    def save(fig,name,title,rule):
        fig.suptitle(title,fontsize=13)
        fig.text(.02,.015,'\n'.join(textwrap.wrap(caption+' '+rule,145)),ha='left',va='bottom',fontsize=7)
        fig.tight_layout(rect=(0,.15,1,.94))
        path=folder/(name+'.png');fig.savefig(path,dpi=160);plt.close(fig)
        files[path.name]=dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),methods=names,
            scenarios=sorted({r['trace_hash'] for r in data['episodes']}),rule=rule,analysis_sha256=digest)
    x=list(range(len(names)))
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    axes[0].bar(x,[methods[n]['mean_group_score'] for n in names]);axes[0].set_ylabel('Penalized episode score J (lower is better)')
    axes[1].bar(x,[methods[n]['failure_rate'] for n in names],label='Modeled failure')
    axes[1].plot(x,[methods[n]['timeout_rate'] for n in names],'o',color='black',label='Timeout/late episode')
    axes[1].set(ylim=(0,1.05),ylabel='Fraction of all episodes');axes[1].legend()
    for ax in axes:ax.set_xticks(x,labels,rotation=25,ha='right');ax.grid(axis='y',alpha=.2)
    save(fig,'scores-and-failures','Saved episode scores and completion outcomes','Score groups have equal weight; rates use all episodes, not only successes.')
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    any_delay=False
    for n,label in zip(names,labels):
        cdf=methods[n]['delay_cdf']
        if cdf:
            any_delay=True
            start=max(0,cdf[0][0]-max(.000001,.01*(cdf[-1][0]-cdf[0][0])))
            axes[0].step([start]+[v[0] for v in cdf],[0]+[v[1] for v in cdf],where='post',label=label)
    if any_delay:axes[0].legend(fontsize=8)
    else:axes[0].text(.5,.5,'No observed physical delay samples',ha='center',transform=axes[0].transAxes)
    axes[0].set(xlabel='End-to-end delay (ms)',ylabel='Empirical fraction of observed user-windows',ylim=(0,1.05))
    for i,n in enumerate(names):
        stat=methods[n]['delay_ms']
        if stat['n']:
            axes[1].plot([i,i],[stat['mean'],stat['p95']],'-',color='gray')
            axes[1].plot(i,stat['mean'],'o',color='C0',label='Mean' if i==0 else None)
            axes[1].plot(i,stat['p95'],'^',color='C1',label='p95 (linear interpolation)' if i==0 else None)
        else:axes[1].text(i,.02,'NA',ha='center')
    axes[1].set_xticks(x,labels,rotation=25,ha='right');axes[1].set_ylabel('Conditional delay mean / p95 (ms)')
    if any_delay:axes[1].legend(fontsize=8)
    for ax in axes:ax.grid(alpha=.2)
    save(fig,'conditional-delay','Conditional delay of committed deployments','CDF and linearly interpolated p95 pool observed user-windows; no failed/unattempted delay is imputed.')
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for ax,key,label in zip(axes,('cpu_utilization','active_instances'),('CPU / total capacity (includes overhead)','Active instances (count)')):
        for i,n in enumerate(names):
            value=methods[n][key]['mean']
            if value is None:ax.text(i,.02,'NA',ha='center')
            else:ax.bar(i,value)
        ax.set_xticks(x,labels,rotation=25,ha='right');ax.set_ylabel(label);ax.grid(axis='y',alpha=.2)
    save(fig,'conditional-resources','Conditional CPU and instance usage','Arithmetic means over committed windows; missing resources stay NA.')
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for key,style,label in [('solve_seconds','o','Stage solve'),('decision_seconds','s','Window decision'),('episode_wall_seconds','^','Episode wall')]:
        valid=[(i,methods[n][key]['mean']) for i,n in enumerate(names) if methods[n][key]['mean'] is not None]
        if valid:axes[0].plot([p[0] for p in valid],[p[1] for p in valid],style,label=label)
    axes[0].set_xticks(x,labels,rotation=25,ha='right');axes[0].set_ylabel('Mean duration (seconds; distinct denominators)');axes[0].legend(fontsize=8)
    statuses=sorted({s for n in names for s in methods[n]['solver_statuses']});bottom=[0]*len(names)
    for status in statuses:
        counts=[methods[n]['solver_statuses'].get(status,0) for n in names]
        axes[1].bar(x,counts,bottom=bottom,label=status);bottom=[b+c for b,c in zip(bottom,counts)]
    axes[1].set_xticks(x,labels,rotation=25,ha='right');axes[1].set_ylabel('Attempted stage records (count)');axes[1].legend(fontsize=7)
    save(fig,'runtime-and-status','Saved durations and raw solver statuses','Stage, attempted-window and episode timings have different denominators; status counts are stage records.')
    fig,ax=plt.subplots(figsize=(12,5));width=.8/max(1,len(names))
    for i,(n,label) in enumerate(zip(names,labels)):
        ax.bar([j-.4+width*(i+.5) for j in range(5)],methods[n]['action_counts'],width,label=label)
    ax.set(xticks=range(5),xticklabels=['0.25','0.5','1','2','4'],xlabel='Chosen weight ratio rho',ylabel='Observed action count (initialization excluded)');ax.legend(fontsize=8)
    save(fig,'actions','Selected-action frequencies','Counts include attempted learned/adaptive decisions; forced initialization excluded. Empty decisions have zero counts, not physical samples.')
    if data['comparisons']:
        fig,ax=plt.subplots(figsize=(12,5))
        for i,(name,value) in enumerate(data['comparisons'].items()):
            lo,hi=value['interval_95'];ax.plot([lo,hi],[i,i],'-',linewidth=2);ax.plot(value['delta'],i,'o')
        comparison_labels=[]
        for name,value in data['comparisons'].items():
            label='Q minus tuned fixed' if name=='policy_minus_tuned_fixed' else 'rho 0.5 minus tuned fixed' if name=='fixed_0.5_minus_tuned_fixed' else name.replace('_',' ')
            counts=(f'K={value["training_seed_count"]}, ' if 'training_seed_count' in value else '')+f'M={value["scenario_group_count"]}'
            comparison_labels.append(label+' ('+counts+')')
        ax.axvline(0,color='gray',linestyle='--');ax.set_yticks(range(len(data['comparisons'])),comparison_labels);ax.set_xlabel('Paired penalized score difference (policy/method minus baseline)')
        save(fig,'paired-uncertainty','Exploratory paired differences and 95% bootstrap intervals','2000 resamples; Q comparisons cross training seeds and scenario groups. Fixed ablations resample paired groups. Small K/M is descriptive.')
    if data['training']:
        fig,ax=plt.subplots(figsize=(12,5))
        for i,run in enumerate(data['training']):
            ax.plot([p['episode'] for p in run['points']],[p['score'] for p in run['points']],'o-',label=f'Run {i+1} [{run["manifest_sha256"][:10]}]: '+run['scope'])
        ax.set(xlabel='Completed training episode index',ylabel='Observed penalized episode score J');ax.legend(fontsize=8)
        save(fig,'training-curves','Saved accepted training episodes','Training run manifest hashes: '+','.join(t['manifest_sha256'][:10] for t in data['training'])+'. No smoothing/dropped failures/abandoned updates. A curve does not establish convergence or improvement.')
    provenance=dict(schema_version=1,analysis_path=str(source),analysis_sha256=digest,python=sys.version,
        matplotlib=matplotlib.__version__,platform=platform.platform(),backend='Agg',dpi=160,
        renderer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source=data['source'],figures=files,solver_calls=0,scope='Rendering saved analysis; no fitting, solving or policy changes')
    (folder/'plot_manifest.json').write_text(json.dumps(provenance,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return provenance


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--analysis',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();result=render(args.analysis,args.output)
    print(json.dumps({'figures':len(result['figures']),'solver_calls':0}))


if __name__=='__main__':main()
