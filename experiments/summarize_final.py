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
 notes=['# Experiment results','Saved measurements only. No solver calls are made by this plotting script.','Failed cases are retained in the complete CSV tables.']
 for name,caption in figures:notes.append(f'![{caption}]({name})\n\n{caption}')
 (out/'README.md').write_text('\n\n'.join(notes),encoding='utf8')
 for name in ['authored-results.csv','physical-results.csv','protocol.json','status.json']:shutil.copyfile(source/name,out/name)
 evidence={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()};(out/'evidence-hashes.json').write_text(json.dumps(evidence,indent=2),encoding='utf8')
 with zipfile.ZipFile(out.parent/'experiment-plots.zip','w',zipfile.ZIP_DEFLATED) as z:
  for file in out.iterdir():
   if file.is_file():z.write(file,file.name)
 print(status)
if __name__=='__main__':main()
