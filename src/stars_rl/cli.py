"""Command-line entry point for STARS-RL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from collections.abc import Sequence

from stars_rl import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the public command-line parser."""
    parser = argparse.ArgumentParser(
        prog="stars-rl",
        description="Optimization-based STARS orchestration with RL weight selection.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")
    doctor = commands.add_parser("doctor", help="Check the installed optimization backend")
    doctor.add_argument("--solver", action="store_true", required=True)
    generate=commands.add_parser('generate',help='Materialize an authored scenario trace (physical generator is later work)')
    source=generate.add_mutually_exclusive_group(required=True)
    source.add_argument('--scenario',type=Path)
    source.add_argument('--physical-config',type=Path)
    generate.add_argument('--output',required=True,type=Path)
    simulate=commands.add_parser('simulate',help='Run one fixed-method episode transactionally')
    simulate.add_argument('--trace',type=Path)
    simulate.add_argument('--output-root',type=Path,default=Path('runs'))
    simulate.add_argument('--run-id',required=True)
    simulate.add_argument('--method',choices=('stars-fixed','mono-delay','mono-temporal','hier-only'))
    simulate.add_argument('--rho',type=float)
    simulate.add_argument('--budget',type=float)
    simulate.add_argument('--seed',type=int)
    simulate.add_argument('--config',type=Path,help='JSON/YAML method/rho/window_budget_seconds/solver_seed settings')
    simulate.add_argument('--initial-export',type=Path)
    simulate.add_argument('--radio-coefficients',type=Path)
    simulate.add_argument('--resume',action='store_true')
    validate=commands.add_parser('validate',help='Check a saved trace or a published run and its deployments')
    target=validate.add_mutually_exclusive_group(required=True)
    target.add_argument('--trace',type=Path)
    target.add_argument('--run-dir',type=Path)
    audit=commands.add_parser('audit',help='Coverage, matching certificates, connectivity and physical cap bound')
    audit.add_argument('--trace',required=True,type=Path)
    audit.add_argument('--output',required=True,type=Path)
    benchmark=commands.add_parser('benchmark',help='Start a supervised authored single-window size ladder')
    benchmark.add_argument('--output',required=True,type=Path)
    benchmark.add_argument('--sizes',nargs='+',default=['2:1','4:2','8:4'])
    benchmark.add_argument('--budget',type=float,default=10)
    sensitivity=commands.add_parser('action-sensitivity',help='Replay all five objective ratios without training')
    sensitivity_source=sensitivity.add_mutually_exclusive_group(required=True)
    sensitivity_source.add_argument('--trace',type=Path)
    sensitivity_source.add_argument('--constructed',action='store_true')
    sensitivity.add_argument('--output',required=True,type=Path)
    sensitivity.add_argument('--budget',type=float,default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return its success status."""
    args = build_parser().parse_args(argv)
    try:
        if args.command=='action-sensitivity':
            from stars_rl.experiments.manifest import atomic_json
            if args.output.exists():raise ValueError('sensitivity output exists; choose a new path')
            if args.constructed:
                from stars_rl.rl.fixtures import constructed_report
                report=constructed_report(10 if args.budget is None else args.budget)
            else:
                from stars_rl.topology.trace import load_trace
                from stars_rl.rl.sensitivity import measure_trace
                report=measure_trace(load_trace(args.trace),total_budget_seconds=args.budget)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            atomic_json(args.output,report)
            print(json.dumps({'output':str(args.output.resolve()),'constructed_gate_passed':report.get('constructed_gate_passed'),
                              'training_gate':report.get('training_gate','physical readiness remains OPEN')}))
            return 0 if report.get('constructed_gate_passed',True) else 1
        if args.command == "doctor":
            from stars_rl.optimization.doctor import diagnose
            report = diagnose()
            print(json.dumps(report, indent=2, allow_nan=False))
            return 0 if report["passed"] else 1
        if args.command=='generate':
            from stars_rl.config import load_scenario
            from stars_rl.topology.trace import build_trace,trace_to_dict
            from stars_rl.experiments.manifest import atomic_json,file_hash,utc_now,environment
            output=args.output.resolve();sidecar=output.with_name(output.name+'.generation.json')
            failed=output.with_name(output.name+'.generation-failed.json')
            if output.exists() or sidecar.exists() or failed.exists():raise ValueError('generation output already exists; choose a new path')
            output.parent.mkdir(parents=True,exist_ok=True)
            started=time.perf_counter();sampling=None
            if args.physical_config is not None:
                from stars_rl.topology.physical import load_physical_config
                try:trace,sampling=load_physical_config(args.physical_config)
                except ValueError as exc:
                    if hasattr(exc,'diagnostics'):
                        atomic_json(failed,{'schema_version':1,'status':'generation_failed','diagnostics':exc.diagnostics,'generated_at':utc_now()})
                    raise
            else:trace=build_trace(load_scenario(args.scenario))
            elapsed=time.perf_counter()-started
            atomic_json(output,trace_to_dict(trace))
            atomic_json(sidecar,{'schema_version':1,'generated_at':utc_now(),'generation_seconds':elapsed,
                'scope':'offline trace preparation, outside decision budget','trace_content_hash':trace.content_hash,
                'trace_artifact_hash':trace.artifact_hash,'scenario_source_sha256':file_hash(args.physical_config or args.scenario),
                'sampling':sampling,'environment':environment()})
            print(json.dumps({'trace':str(output),'generation_record':str(sidecar),'trace_content_hash':trace.content_hash}))
        if args.command=='simulate':
            import yaml
            from stars_rl.experiments.runner import run_experiment,run_directory
            from stars_rl.experiments.manifest import read_json
            config={}
            if args.config is not None:
                config=read_json(args.config) if args.config.suffix.lower()=='.json' else yaml.safe_load(args.config.read_text(encoding='utf-8'))
                if type(config) is not dict or not set(config)<={'method_id','rho','window_budget_seconds','solver_seed'}:raise ValueError('unknown config fields')
            method=args.method or config.get('method_id','stars-fixed')
            folder=run_directory(args.output_root,args.run_id,method)
            if args.resume:
                saved=read_json(folder/'settings.json')
                defaults={'rho':saved['rho'],'window_budget_seconds':saved['window_budget_seconds'],'solver_seed':saved['solver_seed']}
            else:defaults={'rho':1,'window_budget_seconds':None,'solver_seed':0}
            config=defaults|config
            result=run_experiment(args.trace,args.output_root,args.run_id,method,
                rho=config['rho'] if args.rho is None else args.rho,
                total_budget_seconds=config['window_budget_seconds'] if args.budget is None else args.budget,
                seed=config['solver_seed'] if args.seed is None else args.seed,resume=args.resume,
                initial_export_path=args.initial_export,radio_coefficients_path=args.radio_coefficients)
            print(json.dumps({'run_dir':str(folder),'status':result['status'],'episode_status':result['episode_status']}))
            return 0 if result['status']=='completed' and result['episode_status']=='success' else 1
        if args.command=='validate':
            if args.trace is not None:
                from stars_rl.topology.trace import load_trace
                trace=load_trace(args.trace)
                report={'valid':True,'trace_content_hash':trace.content_hash,'trace_artifact_hash':trace.artifact_hash,'windows':len(trace.windows)}
            else:
                from stars_rl.experiments.runner import validate_run
                report=validate_run(args.run_dir)
            print(json.dumps(report,indent=2,allow_nan=False))
            return 0 if report['valid'] and report.get('usable_episode',True) else 1
        if args.command=='audit':
            from stars_rl.topology.trace import load_trace
            from stars_rl.topology.audit import audit_trace
            from stars_rl.experiments.manifest import atomic_json
            if args.output.exists():raise ValueError('audit output exists; choose a new path')
            report=audit_trace(load_trace(args.trace));args.output.parent.mkdir(parents=True,exist_ok=True)
            atomic_json(args.output,report)
            print(json.dumps({'audit':str(args.output.resolve()),'all_windows_necessary_passed':report['all_windows_necessary_passed'],
                              'scope':'necessary conditions only; failed coverage is retained'}))
        if args.command=='benchmark':
            from stars_rl.topology.benchmark import benchmark_ladder
            result=benchmark_ladder(args.output,tuple(tuple(map(int,value.split(':'))) for value in args.sizes),args.budget)
            print(json.dumps(result,indent=2,allow_nan=False))
            return 0 if all(row['status']=='success' for row in result['records']) else 1
    except (OSError,ValueError,KeyError,TypeError,RuntimeError) as exc:
        print(json.dumps({'error':str(exc),'type':type(exc).__name__}),file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

