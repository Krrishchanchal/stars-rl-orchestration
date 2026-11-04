"""Run a real, explicitly authored handover; write a self-contained HTML demo.

This is a demonstration of C12 APIs, not the C13 experiment/manifest runner.
No orbital generator, trained RL policy or performance comparison is implied.
"""
import argparse
from dataclasses import asdict, replace
from html import escape
import json
from pathlib import Path

from stars_rl.config import load_scenario
from stars_rl.models import AccessLink, AccessWindow
from stars_rl.simulation import simulate
from stars_rl.topology.trace import build_trace


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('runs/demo'))
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[1]
    source=load_scenario(root/'configs/toy.yaml')
    # Deliberately authored, separately named scenario. Keep original radio,
    # CPU capacities, SLA and chain. Remove ISLs to force endpoint/host moves.
    scenario=replace(source,scenario_id='demo-forced-handover-v1',family_id='demo-forced-handover-v1',family_classification='analytical_fixture',
        users=(source.users[0],),slices=(source.slices[0],),
        satellites=tuple(s for s in source.satellites if s.id!='s2'),
        instances=tuple(i for i in source.instances if i.satellite_id!='s2'),isl_links=(),
        access_schedule=tuple(AccessWindow(k,(AccessLink('u0','s0' if k==0 else 's1',500000),)) for k in range(3)),
        metadata=replace(source.metadata,scenario_group_id='demo-handover',root_lineage_id='demo-handover',
                         constellation_id='authored-disconnected-pair',layout_id='demo-layout'))
    trace=build_trace(scenario)
    result=simulate(trace,'stars-fixed',rho=.5,total_budget_seconds=10)
    (args.output/'raw_result.json').write_text(json.dumps(asdict(result),indent=2,allow_nan=False),encoding='utf-8')
    cards=[];summary=[]
    print('REAL SCIP SOLVES | authored distances + physical radio | rho=0.5 | B=10s/window')
    for w in result.windows:
        if w.status!='committed':
            cards.append(f'<section><h2>Window {w.window_index+1}</h2><p>{escape(w.status+": "+w.reason)}</p></section>')
            print(w.window_index+1,w.status,w.reason)
            continue
        d=w.committed_deployment
        access=d.access[0].satellite_id;egress=d.egress[0]
        allocations=sorted(d.allocations,key=lambda a:a.stage_index)
        report=w.commit_validation['deployment']['recomputed']['u0']
        delay_ms=report['physical_total_delay_seconds']*1000
        limit_ms=scenario.slices[0].delay_limit_seconds*1000
        m=w.metrics
        row={'window':w.window_index+1,'access':access,'egress':egress.satellite_id,
             'allocations':[{'function':a.instance.function_type_id,'instance':a.instance.instance_id,
                             'host':a.instance.satellite_id,'cpu_mips':a.cpu_mips} for a in allocations],
             'delay_ms':delay_ms,'sla_ms':limit_ms,'access_switches':m.access_switches,
             'host_changes':m.host_changes,'assignment_changes':m.assignment_changes,
             'validated':w.commit_validation['valid'],'elapsed_seconds':w.elapsed_seconds}
        summary.append(row)
        chain=' &rarr; '.join(f'{escape(a.instance.function_type_id)} @ {escape(a.instance.satellite_id)}' for a in allocations)
        resource_rows=''.join(f'<tr><td>{escape(a.instance.function_type_id)}</td><td>{escape(a.instance.instance_id)}</td><td>{escape(a.instance.satellite_id)}</td><td>{a.cpu_mips:.3f}</td></tr>' for a in allocations)
        cards.append(f'''<section><div class="eyebrow">WINDOW {w.window_index+1} / 3 · {w.window_index*60}–{(w.window_index+1)*60}s</div>
<h2>{"Initial deployment" if w.window_index==0 else "Forced handover" if w.window_index==1 else "Retain the deployment"}</h2>
<p class="route">u0 &rarr; <b>{escape(access)}</b> &rarr; {chain} &rarr; {escape(egress.satellite_id)} &rarr; g0</p>
<p>Visible access: <b>{escape(access)}</b>. The satellites have no ISL path in this authored case.</p>
<table><tr><th>Function</th><th>Instance</th><th>Host</th><th>CPU (MIPS)</th></tr>{resource_rows}</table>
<div class="stats"><div><strong>{delay_ms:.3f} ms</strong><span>recomputed E2E / {limit_ms:.0f} ms SLA</span></div><div><strong>{m.access_switches} / {m.host_changes}</strong><span>access switches / stage host changes</span></div><div><strong>VALIDATED</strong><span>full independent feasibility check</span></div></div>
<p class="muted">Measured decision time {w.elapsed_seconds:.4f}s · shared budget10s · initial setup counts as zero changes.</p></section>''')
        print(f'Window {w.window_index+1}: access={access}, chain='+','.join(a.instance.satellite_id for a in allocations)+
              f', delay={delay_ms:.3f}/{limit_ms:.0f}ms, switches={m.access_switches}, host changes={m.host_changes}, VALIDATED')
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>STARS · real optimizer handover demo</title>
<style>body{background:#edf1f5;color:#14263a;font:16px/1.6 system-ui;margin:0}main{max-width:1000px;margin:auto;padding:40px 24px}h1{font-size:40px;line-height:1.15;margin:10px 0}h2{margin:8px 0}.eyebrow{letter-spacing:2px;font-size:12px;color:#376a85;font-weight:700}section{background:white;border-radius:18px;padding:26px;margin:24px 0;box-shadow:0 3px 15px #14263a0b}.route{padding:14px;background:#edf5fc;border-radius:9px}table{border-collapse:collapse;width:100%;text-align:left}td,th{padding:9px;border-bottom:1px solid #e0e8ee}.stats{display:flex;gap:24px;flex-wrap:wrap;margin-top:24px}.stats strong{display:block;font-size:23px;color:#087b68}.stats span,.muted{font-size:13px;color:#506578}footer{font-size:14px}</style><main><div class="eyebrow">STARS + RL PROJECT · OPTIMIZATION DEMO</div>
<h1>A service chain follows a forced satellite handover.</h1><p>Three decision windows, each using both SCIP stages, continuous CPU allocation and independent validation. A successful run makes six stage solves. This is an explicitly authored two-satellite scenario with physical radio calculations, not a simulated orbital constellation.</p>
<section><h2>What to watch</h2><p>Window1: only s0 serves the user. Window2: s0 becomes invisible, and only s1 can serve the user. Because these hosts are disconnected, the optimizer must change access, egress and both function hosts. Window3 keeps the same topology, so stability penalties favor retaining those choices.</p></section>'''+''.join(cards)+'''<footer><b>Scope:</b> Working fixed-weight optimization and validation, not a trained RL policy. CPU values are solver-selected continuous allocations; tied values and timings can vary. This demonstration is not evidence of physical-scale feasibility or superiority over baselines. Raw solver outputs and residuals are in raw_result.json beside this report.</footer></main></html>'''
    (args.output/'index.html').write_text(html,encoding='utf-8')
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False),encoding='utf-8')
    print('Report:',(args.output/'index.html').resolve())
    if result.status!='success':raise SystemExit(1)


if __name__=='__main__':main()
