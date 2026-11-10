"""Summarize saved matrix outputs; no solver calls. Requires Matplotlib."""
from pathlib import Path
import argparse,csv,hashlib,html,json,shutil,zipfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
 p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 source=a.results.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 rows=json.loads((source/'authored-results.json').read_text());physical=json.loads((source/'physical-results.json').read_text());status=json.loads((source/'status.json').read_text());assert status['status']=='completed'
 errors=[r for r in rows if r['status']=='implementation_error'];assert not errors,errors
 plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
 figures=[]
 for prefix,xlabel in [('load-','Users (four satellites)'),('satellites-','Satellites (16 users)'),('cpu-','CPU capacity per satellite (MIPS)'),('demand-','Demand per user (Mbps)'),('delay-','Delay limit (seconds)')]:
  data=[r for r in rows if r['case'].startswith(prefix) and r['method']=='stars-fixed'];data.sort(key=lambda r:float(r['case'][len(prefix):]))
  fig,axs=plt.subplots(1,2,figsize=(9,3.5),layout='constrained');xx=list(range(len(data)));labels=[r['case'][len(prefix):] for r in data]
  axs[0].bar(xx,[r['approved_windows'] for r in data],color=['#197e73' if r['status']=='success' else '#bc6547' for r in data]);axs[0].set(ylim=(0,3.4),ylabel='Committed windows out of 3',xlabel=xlabel,xticks=xx,xticklabels=labels)
  axs[1].bar(xx,[r['decision_seconds'] for r in data],color='#3b6684');axs[1].set(ylabel='Sum of attempted decision times (s)',xlabel=xlabel,xticks=xx,xticklabels=labels)
  name=prefix[:-1]+'.png';fig.savefig(out/name,dpi=200);plt.close(fig);figures.append((name,'Success and attempted decision cost. Failed episodes terminate early, so their timing is not full-episode runtime. Single measured run per unique input.'))
 fig,ax=plt.subplots(figsize=(8,3.7),layout='constrained');methods=['stars-fixed','mono-temporal','hier-only','mono-delay'];levels=[0,4,8,16]
 for i,m in enumerate(methods):
  subset=[next(r for r in rows if r['case']==f'handover-{n}' and r['method']==m) for n in levels]
  ax.bar([j+(i-1.5)*.2 for j in range(4)],[r['approved_windows'] for r in subset],width=.2,label=m)
 ax.set(xticks=range(4),xticklabels=levels,xlabel='Users whose access changes (16 total users)',ylabel='Committed windows out of 3',ylim=(0,4));ax.legend(fontsize=8,ncol=2);fig.savefig(out/'handover-methods.png',dpi=200);plt.close(fig);figures.append(('handover-methods.png','Completion under the same 10-second per-window budget and native initialization. These methods have different objectives; this is a method-package comparison.'))
 fig,axs=plt.subplots(1,2,figsize=(8,3.5),layout='constrained')
 for ax,family in zip(axs,['paper-inputs-v1','development-physical-v1']):
  rr=[r for r in physical if r['family']==family];ax.bar([r['seed'] for r in rr],[r['necessary_passed'] for r in rr],color='#3b6684');ax.set(ylim=(0,15),xticks=range(5),xlabel='Predetermined seed',ylabel='Passing snapshots out of 14',title=family)
 fig.savefig(out/'physical-seeds.png',dpi=200);plt.close(fig);figures.append(('physical-seeds.png','All five seeds retained per family. Necessary coverage/resource checks are not sufficient for a complete feasible deployment. Seeds are layout/load perturbations of the same geometry, not five independent orbital designs.'))
 def table(data,cols):
  return '| '+' | '.join(cols)+' |\n| '+' | '.join(['---']*len(cols))+' |\n'+'\n'.join('| '+' | '.join(str(r.get(k,'')) for k in cols)+' |' for r in data)
 md=['# Final experiment record and report-selection guide','This is a research evidence summary, not a finished submission report. All configured outcomes are retained. The code was frozen; only scenario inputs and experiment scripts were added.','## Results by scenario',table(rows,['case','method','status','approved_windows','failure_reason','J','access_switches','host_moves','max_committed_delay_ms','decision_seconds','reused_from']),'## Physical seed sweep',table(physical,['family','seed','necessary_passed','min_access_flow','max_access_flow','initial_passed','episode_status']),'## Significant findings to discuss']
 for name in ['load-4','load-8','load-16','load-24','load-32','satellites-2','satellites-4','satellites-8','satellites-12','satellites-20']:
  r=next(r for r in rows if r['case']==name and r['method']=='stars-fixed');md.append(f"- {name}: {r['approved_windows']}/3 windows committed; {r['status']}; reason={r['failure_reason'] or 'none'}; attempted decision time={r['decision_seconds']:.3f}s.")
 for filename,title in [('capacity-extension.json','Larger-population boundary cases'),('physical-prefix-results.json','Actual physical episode attempts after initial coverage passed')]:
  if (source/filename).exists():md+=['## '+title,'```json\n'+(source/filename).read_text()+'\n```']
 repetitions=source.parent/'budget-repetitions/results.json'
 if repetitions.exists():
  rr=json.loads(repetitions.read_text());md+=['## Rotated-order runtime repetitions',table(rr,['repeat','method','status','approved_windows','reason','decision_seconds']),'These repeat the same input; they measure run-to-run computational behavior rather than independent network conditions.']
 md+=['## How to select results for the report','Lead with the 16-user handover and Stage II rescue. Use native/shared-start comparisons to explain initialization. Use the handover-method matrix and one CPU/delay boundary figure for controlled stress evidence. Use the satellite sweep to explain capacity versus computation. Use the physical-seed plot to establish coverage limitations beyond seed 0. Use constructed X/Y and the aliased-state example to explain when adaptive weighting could help and when observations are insufficient. The smaller cases, complete tables and raw logs belong in appendices/archive rather than being discarded.','Do not claim universal STARS superiority. Identify cases where hierarchy-only or monolithic temporal ties STARS. Deadline outcomes are budget-specific and timings vary; repeated failure is not proof of mathematical infeasibility. Forced handovers do not establish learned-policy benefit. Native physical training and scientific held-out evaluation remain unavailable wherever readiness fails. Do not treat blocked training as completed.','J is normalized: the same four migrating users form a smaller fraction at 16 users than at eight. A smaller normalized J across population sizes is not fewer absolute migrations. Failed episodes have a penalty; observed switch and delay totals refer only to committed windows. Zero moves with zero deployments is not a stability success.','## Figures']
 for name,caption in figures:md.append(f'![{caption}]({name})\n\n{caption}')
 text='\n\n'.join(md);(out/'SUMMARY.md').write_text(text,encoding='utf8')
 body='<h1>Experiment evidence</h1><p>All cases and report-selection guidance are in SUMMARY.md and the CSV tables. No native trained-policy gain is claimed.</p>'
 for name,caption in figures:body+=f'<figure><img src="{name}" style="width:100%"><figcaption>{html.escape(caption)}</figcaption></figure>'
 body+='<h2>Complete outcomes</h2><pre style="white-space:pre-wrap">'+html.escape(text[:text.index('## Figures')])+'</pre>'
 (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Final experiment evidence</title><main style="max-width:1100px;margin:auto;font:16px/1.5 system-ui">'+body+'</main>',encoding='utf8')
 for name in ['authored-results.csv','physical-results.csv','protocol.json','status.json']:shutil.copyfile(source/name,out/name)
 evidence={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()};(out/'evidence-hashes.json').write_text(json.dumps(evidence,indent=2),encoding='utf8')
 with zipfile.ZipFile(out.parent/'final-experiment-summary.zip','w',zipfile.ZIP_DEFLATED) as z:
  for file in out.iterdir():
   if file.is_file():z.write(file,file.name)
 print(status)
if __name__=='__main__':main()
