"""Transactional one-episode fixed-method runs and initial-boundary replay."""
from dataclasses import asdict
import math
from pathlib import Path
import re
import shutil
import time

from stars_rl.baselines import method_spec
from stars_rl.config import deployment_from_dict
from stars_rl.metrics import change_metrics
from stars_rl.models import AccessChoice,EgressChoice
from stars_rl.optimization.repair import repair_previous
from stars_rl.optimization.stage1 import AssociationReference
from stars_rl.simulation import simulate
from stars_rl.topology.trace import load_trace,trace_to_dict
from stars_rl.validation.association import validate_association
from stars_rl.validation.deployment import validate_export
from stars_rl.validation.monolithic import validate_monolithic
from stars_rl.validation.stage2 import validate_stage2
from .manifest import (atomic_json,checked_path,compatibility_profile,diagnostic_json,digest,
                       environment,file_hash,read_json,run_lock,utc_now)


def run_directory(root,run_id,method_id):
    method_spec(method_id)
    if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',run_id) or run_id.endswith('.')
            or run_id.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'{p}{i}' for p in ('COM','LPT') for i in range(1,10)]}):
        raise ValueError('unsafe run ID')
    return Path(root).resolve()/run_id/method_id


def _rates(records,window_count):
    if records is None:return None
    if type(records) is not list:raise ValueError('radio fixture must be a list of original coefficients')
    result={k:{} for k in range(window_count)}
    for r in records:
        if type(r) is not dict or set(r)!={'window_index','user_id','satellite_id','occupancy','rate_bps'}:raise ValueError('invalid radio record')
        if type(r['window_index']) is not int or not 0<=r['window_index']<window_count or type(r['occupancy']) is not int or r['occupancy']<1:raise ValueError('invalid radio indices')
        if type(r['user_id']) is not str or type(r['satellite_id']) is not str:raise ValueError('invalid radio IDs')
        value=r['rate_bps']
        if type(value) not in (int,float) or not math.isfinite(value) or value<=0:raise ValueError('invalid radio rate')
        table=result.setdefault(r['window_index'],{});key=(r['user_id'],r['satellite_id'],r['occupancy'])
        if key in table:raise ValueError('duplicate radio coefficient')
        table[key]=value
    return result


def _boundary(settings_hash,trace,profile):
    state={'schema_version':1,'scope':'fixed_method_initial_episode_boundary','next_episode_index':0,
           'active_deployment':None,'settings_hash':settings_hash,'trace_order':[trace.content_hash],
           'group_order':[trace.scenario.metadata.scenario_group_id],
           'rng':{'policy_rng_used':False,'solver_seed':0,'reason':'fixed policies; generation seeds/draws are in trace snapshot'},
           'runtime_profile_hash':digest(profile)}
    return state | {'state_hash':digest(state)}


def _check_files(folder,hashes):
    if type(hashes) is not dict:raise ValueError('invalid artifact hash map')
    for name,expected in hashes.items():
        if file_hash(checked_path(folder,name))!=expected:raise ValueError(f'artifact hash mismatch: {name}')


def _check_boundary(folder,manifest,trace):
    state=read_json(folder/'boundary-0000.json')
    if state.get('state_hash')!=digest({k:v for k,v in state.items() if k!='state_hash'}):raise ValueError('boundary state hash mismatch')
    expected=_boundary(manifest['settings_hash'],trace,manifest['runtime_profile'])
    if state!=expected:raise ValueError('incompatible initial boundary state')


def run_experiment(trace_path,output_root,run_id,method_id='stars-fixed',*,rho=1,total_budget_seconds=None,
                   seed=0,resume=False,initial_export_path=None,radio_coefficients_path=None,
                   _fault=None,_simulate_fn=None):
    folder=run_directory(output_root,run_id,method_id)
    if not resume and trace_path is None:raise ValueError('new run requires --trace')
    if type(seed) is not int or seed!=0:raise ValueError('fixed-method solver seed is frozen at 0')
    if type(rho) not in (int,float) or rho not in (.25,.5,1,2,4):raise ValueError('invalid fixed ratio')
    if total_budget_seconds is not None and (type(total_budget_seconds) not in (int,float) or not math.isfinite(total_budget_seconds) or total_budget_seconds<=0):raise ValueError('invalid window budget')
    if not resume:folder.mkdir(parents=True,exist_ok=False)
    elif not folder.is_dir():raise ValueError('no existing run to resume')
    with run_lock(folder):
        if resume:
            manifest=read_json(folder/'manifest.json');_check_files(folder,manifest['input_hashes'])
        trace_start=time.perf_counter()
        trace=load_trace(trace_path if trace_path is not None else folder/'trace.json')
        trace_load_seconds=time.perf_counter()-trace_start
        if total_budget_seconds is None:
            total_budget_seconds=read_json(folder/'settings.json')['window_budget_seconds'] if resume else (60 if trace.scenario.orbit is not None else 10)
        generation_path=(Path(trace_path).with_name(Path(trace_path).name+'.generation.json') if trace_path is not None else folder/'generation.json')
        generation=read_json(generation_path) if generation_path.exists() else None
        if generation is not None:
            seconds=generation.get('generation_seconds')
            if (generation.get('schema_version')!=1 or generation.get('trace_artifact_hash')!=trace.artifact_hash
                    or generation.get('trace_content_hash')!=trace.content_hash or type(seconds) not in (int,float)
                    or not math.isfinite(seconds) or seconds<0):raise ValueError('invalid generation provenance')
        initial_path=initial_export_path if initial_export_path is not None else (folder/'initial_export.json' if resume and (folder/'initial_export.json').exists() else None)
        rates_path=radio_coefficients_path if radio_coefficients_path is not None else (folder/'radio_coefficients.json' if resume and (folder/'radio_coefficients.json').exists() else None)
        initial=None if initial_path is None else read_json(initial_path)
        rate_records=None if rates_path is None else read_json(rates_path);rates=_rates(rate_records,len(trace.windows))
        settings={'schema_version':1,'method_id':method_id,'rho':float(rho),'window_budget_seconds':float(total_budget_seconds),
                  'solver_seed':seed,'failure_policy':'terminate_episode','initialization_study':'native_initialization' if initial is None else 'common_initial_state',
                  'initial_export_hash':None if initial is None else digest(initial),'radio_coefficients_hash':None if rate_records is None else digest(rate_records),
                  'execution_adapter':'standard' if _simulate_fn is None else 'injected_test_adapter'}
        settings_hash=digest(settings);env=environment();profile=compatibility_profile(env)
        if resume:
            if manifest['schema_version']!=1 or manifest['run_id']!=run_id or manifest['method_id']!=method_id:raise ValueError('incompatible run identity')
            if settings_hash!=manifest['settings_hash'] or trace.artifact_hash!=manifest['trace_artifact_hash']:raise ValueError('incompatible config or trace')
            if profile!=manifest['runtime_profile']:raise ValueError('incompatible code, dependencies, solver or hardware')
            _check_boundary(folder,manifest,trace)
            if manifest['status']=='completed':validate_run(folder);return manifest
            if manifest['status']=='aborted':raise ValueError('aborted numerical/infrastructure run requires diagnosis, not automatic replay')
            if manifest['status'] not in {'running','interrupted'}:raise ValueError('invalid recovery status')
            for attempt in manifest['attempts']:
                if attempt['status'] not in {'abandoned','completed'}:
                    for prefix in ('pending','attempt'):
                        old=checked_path(folder,f'{prefix}-{attempt["index"]:04d}')
                        if old.exists():
                            new=checked_path(folder,f'abandoned-{attempt["index"]:04d}')
                            if new.exists():raise ValueError('abandoned destination already exists')
                            old.rename(new)
                    attempt['status']='abandoned';attempt['abandoned_at']=utc_now()
        else:
            atomic_json(folder/'trace.json',trace_to_dict(trace));atomic_json(folder/'settings.json',settings)
            if initial is not None:atomic_json(folder/'initial_export.json',initial)
            if rate_records is not None:atomic_json(folder/'radio_coefficients.json',rate_records)
            if generation is not None:atomic_json(folder/'generation.json',generation)
            boundary=_boundary(settings_hash,trace,profile);atomic_json(folder/'boundary-0000.json',boundary)
            sources={}
            package=Path(__file__).resolve().parents[1];repo=Path(__file__).resolve().parents[3]
            for relative,expected in env['source_files'].items():
                origin=repo/relative.removeprefix('@repo/') if relative.startswith('@repo/') else package/relative
                name='source/'+relative.removeprefix('@repo/') if relative.startswith('@repo/') else 'source/src/stars_rl/'+relative
                destination=checked_path(folder,name);destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(origin,destination)
                if file_hash(destination)!=expected:raise ValueError('source changed while snapshotting')
                sources[name]=expected
            inputs={p.name:file_hash(p) for p in (folder/'trace.json',folder/'settings.json',folder/'boundary-0000.json',
                *([folder/'initial_export.json'] if initial is not None else []),*([folder/'radio_coefficients.json'] if rate_records is not None else []),
                *([folder/'generation.json'] if generation is not None else []))}
            inputs.update(sources)
            manifest={'schema_version':1,'run_id':run_id,'method_id':method_id,'created_at':utc_now(),'status':'running',
                'settings_hash':settings_hash,'trace_content_hash':trace.content_hash,'trace_artifact_hash':trace.artifact_hash,
                'lineage':asdict(trace.scenario.metadata),'environment':env,'runtime_profile':profile,'input_hashes':inputs,'source_snapshot':sources,
                'attempts':[],'artifact_hashes':{},'active_boundary':'boundary-0000.json',
                'trace_load_offline_seconds':trace_load_seconds,'generation_timing':{'scope':'outside per-window decision budget',
                    'seconds':None if generation is None else generation['generation_seconds'],
                    'record':None if generation is None else 'generation.json','reason':'unavailable for externally supplied trace' if generation is None else 'measured authored trace preparation'},
                'scope':'one fixed-method episode; no RL/Q/RNG training checkpoint'}
        index=len(manifest['attempts']);pending=checked_path(folder,f'pending-{index:04d}');pending.mkdir()
        manifest['artifact_hashes']={};manifest['active_boundary']='boundary-0000.json';manifest.pop('active_attempt',None)
        manifest['attempts'].append({'index':index,'status':'running','started_at':utc_now()})
        manifest['status']='running';atomic_json(folder/'manifest.json',manifest)
        atomic_json(pending/'progress.json',{'episode_index':0,'status':'running','resume_from':'boundary-0000.json'})
        fault=_fault or (lambda event:None)
        try:
            fault('before_episode');started=time.perf_counter()
            result=(_simulate_fn or simulate)(trace,method_id,rho=rho,total_budget_seconds=total_budget_seconds,
                                             radio_coefficients_by_window=rates,initial_export=initial)
            elapsed=time.perf_counter()-started;fault('after_episode')
            serialization_started=time.perf_counter()
            episode=asdict(result)
            if _simulate_fn is not None:episode['runtime_adapter']='injected_test_adapter'
            if result.status in {'infrastructure_error','numerical_rejection'}:episode=diagnostic_json(episode)
            atomic_json(pending/'episode.json',episode)
            atomic_json(pending/'decisions.json',[{k:w[k] for k in ('window_index','status','reason','failure_stage','previous_committed','committed_deployment','rho')} for w in episode['windows']])
            fault('after_decisions')
            atomic_json(pending/'metrics.json',[{'window_index':w['window_index'],'metrics':w['metrics']} for w in episode['windows']])
            atomic_json(pending/'validation.json',[{'window_index':w['window_index'],'commit_validation':w['commit_validation']} for w in episode['windows']])
            atomic_json(pending/'summary.json',{'episode_status':result.status,'transition_valid':result.transition_valid,
                'committed_windows':sum(w.status=='committed' for w in result.windows),'failure_window':result.failure_window,
                'episode_wall_seconds':elapsed,'authority':'only a completed/aborted manifest publishes this attempt'})
            end={'schema_version':1,'scope':'completed_fixed_method_episode_boundary' if result.transition_valid else 'aborted_episode_no_boundary_advance',
                 'next_episode_index':1 if result.transition_valid else 0,
                 'active_deployment':None,'initial_boundary_hash':read_json(folder/'boundary-0000.json')['state_hash']}
            end['state_hash']=digest(end);atomic_json(pending/'boundary_end.json',end)
            hashes={p.name:file_hash(p) for p in pending.iterdir() if p.is_file()}
            atomic_json(pending/'transaction.json',{'schema_version':1,'files':hashes})
            fault('before_publish')
            final=checked_path(folder,f'attempt-{index:04d}');pending.rename(final)
            fault('after_directory_publish')
            manifest['artifact_hashes']={f'{final.name}/{p.name}':file_hash(p) for p in final.iterdir() if p.is_file()}
            manifest['status']='completed' if result.transition_valid else 'aborted';manifest['episode_status']=result.status
            manifest['attempts'][-1].update(status=manifest['status'],finished_at=utc_now())
            manifest['active_attempt']=final.name;manifest['active_boundary']=f'{final.name}/boundary_end.json' if result.transition_valid else 'boundary-0000.json'
            manifest['finished_at']=utc_now()
            manifest['timings']={'episode_wall_seconds':elapsed,
                'post_decision_serialization_and_hashing_seconds':time.perf_counter()-serialization_started,
                'scope':'artifact preparation; excludes final manifest publication'}
            audit_started=time.perf_counter()
            validate_run(folder,_manifest=manifest)
            manifest['timings']['offline_artifact_audit_seconds']=time.perf_counter()-audit_started
            fault('before_manifest_publish');atomic_json(folder/'manifest.json',manifest)
        except BaseException as exc:
            manifest['status']='interrupted';manifest['attempts'][-1]['status']='interrupted'
            manifest['active_boundary']='boundary-0000.json'
            manifest['artifact_hashes']={};manifest.pop('active_attempt',None)
            manifest['interruption']={'type':type(exc).__name__,'message':str(exc)}
            atomic_json(folder/'manifest.json',manifest);raise
        return manifest


def validate_run(directory,*,_manifest=None):
    """Verify snapshots/hashes, schemas and committed deployments independently."""
    folder=Path(directory).resolve();m=read_json(folder/'manifest.json') if _manifest is None else _manifest
    if m.get('schema_version')!=1 or m.get('status') not in {'completed','aborted'}:raise ValueError('run is not a published transaction')
    _check_files(folder,m['input_hashes']);_check_files(folder,m['artifact_hashes'])
    trace=load_trace(folder/'trace.json');settings=read_json(folder/'settings.json')
    method_spec(m['method_id'])
    if settings['method_id']!=m['method_id']:raise ValueError('method identity mismatch')
    if digest(settings)!=m['settings_hash'] or trace.content_hash!=m['trace_content_hash'] or trace.artifact_hash!=m['trace_artifact_hash']:raise ValueError('input identity mismatch')
    _check_boundary(folder,m,trace)
    expected_sources={('source/'+name.removeprefix('@repo/') if name.startswith('@repo/') else 'source/src/stars_rl/'+name):value for name,value in m['environment']['source_files'].items()}
    if m['source_snapshot']!=expected_sources or any(m['input_hashes'].get(k)!=v for k,v in expected_sources.items()):raise ValueError('source snapshot differs from recorded code')
    if digest(m['lineage'])!=digest(asdict(trace.scenario.metadata)):raise ValueError('group lineage mismatch')
    attempt=checked_path(folder,m['active_attempt']);transaction=read_json(attempt/'transaction.json')
    expected_boundary=f'{attempt.name}/boundary_end.json' if m['status']=='completed' else 'boundary-0000.json'
    if m['active_boundary']!=expected_boundary:raise ValueError('invalid active boundary pointer')
    _check_files(attempt,transaction['files'])
    required={'episode.json','decisions.json','metrics.json','validation.json','summary.json','boundary_end.json','progress.json'}
    if set(transaction['files'])!=required:raise ValueError('missing/unknown transaction files')
    if set(m['artifact_hashes'])!={f'{attempt.name}/{p}' for p in (*required,'transaction.json')}:raise ValueError('incomplete published artifact map')
    episode=read_json(attempt/'episode.json');decisions=read_json(attempt/'decisions.json');metrics=read_json(attempt/'metrics.json');checks=read_json(attempt/'validation.json')
    end=read_json(attempt/'boundary_end.json')
    if (end['state_hash']!=digest({k:v for k,v in end.items() if k!='state_hash'}) or end['active_deployment'] is not None or end['next_episode_index']!=(1 if episode['transition_valid'] else 0)
            or end['initial_boundary_hash']!=read_json(folder/'boundary-0000.json')['state_hash']):raise ValueError('invalid final boundary')
    if len(episode['windows'])!=len(trace.windows):raise ValueError('missing window records')
    if decisions!=[{k:w[k] for k in ('window_index','status','reason','failure_stage','previous_committed','committed_deployment','rho')} for w in episode['windows']]:raise ValueError('decision projections differ')
    if metrics!=[{'window_index':w['window_index'],'metrics':w['metrics']} for w in episode['windows']]:raise ValueError('metric projections differ')
    if checks!=[{'window_index':w['window_index'],'commit_validation':w['commit_validation']} for w in episode['windows']]:raise ValueError('validation projections differ')
    rates=_rates(read_json(folder/'radio_coefficients.json'),len(trace.windows)) if (folder/'radio_coefficients.json').exists() else None
    last=None;stopped=False;approved=0
    for w,record in zip(trace.windows,episode['windows']):
        if record['window_index']!=w.window_index:raise ValueError('window order differs')
        if record['status'] not in {'committed','failed','late','numerical_rejection','infrastructure_error','not_attempted'}:raise ValueError('unknown window status')
        if set(record['stages'])!={'stage1','stage2','monolithic'} or any(stage['stage']!=key for key,stage in record['stages'].items()):raise ValueError('invalid stage records')
        inactive=('stage1','stage2') if settings['method_id'].startswith('mono-') else ('monolithic',)
        if any(record['stages'][name]['raw_status']!='not_attempted' for name in inactive):raise ValueError('inactive stage was attempted')
        previous=None if record['previous_committed'] is None else deployment_from_dict(record['previous_committed'],trace.scenario)
        if previous!=last:raise ValueError('committed state chain differs')
        if stopped:
            if record['status']!='not_attempted' or record['committed_deployment'] is not None or record['metrics'] is not None:raise ValueError('invalid post-failure window')
            continue
        if record['status']!='committed':
            if record['committed_deployment'] is not None:raise ValueError('failed window committed state')
            stopped=True;continue
        if record['elapsed_seconds']>settings['window_budget_seconds']:raise ValueError('late deployment was committed')
        table=None if rates is None else rates[w.window_index]
        if w.window_index==0 and settings['initialization_study']=='common_initial_state':
            valid=validate_export(trace.scenario,w,record['export'],radio_coefficients=table).valid
        elif settings['method_id'].startswith('mono-'):
            mode='temporal' if settings['method_id']=='mono-temporal' and last is not None else 'Q'
            valid=validate_monolithic(trace.scenario,w,record['export'],mode=mode,previous=last,radio_coefficients=table)['valid']
        else:
            first=record['stage1_outcome'];ref=first['stage1_reference']
            reference=AssociationReference(ref['window_index'],tuple(AccessChoice(**a) for a in ref['access']),tuple(EgressChoice(**a) for a in ref['egress']))
            prior=None if settings['method_id']=='hier-only' else last
            mode='propagation' if prior is None else 'temporal'
            objective_ref=None if mode=='propagation' else repair_previous(trace.scenario,w,prior).repair_candidate
            stage=record['stages']['stage1']
            check=validate_association(trace.scenario,w,stage['values'],stage['objective'],mode=mode,reference=objective_ref,weights=(1,1))
            if not check['valid'] or not stage['has_incumbent']:raise ValueError('invalid stored Stage I')
            if {(a.user_id,a.satellite_id) for a in reference.access}!=set(map(tuple,check['access'])) or {(a.user_id,a.satellite_id,a.ground_station_id) for a in reference.egress}!=set(map(tuple,check['egress'])):raise ValueError('Stage I reference differs from raw values')
            weight=0 if settings['method_id']=='hier-only' else (.5 if last is None else settings['rho'])
            valid=validate_stage2(trace.scenario,w,record['export'],reference,prior,weights=(1,weight),radio_coefficients=table)['valid']
        if not valid:raise ValueError('independent deployment/objective validation failed')
        final=deployment_from_dict(record['export']['candidate']['deployment'],trace.scenario)
        if final!=deployment_from_dict(record['committed_deployment'],trace.scenario):raise ValueError('committed/exported deployment differs')
        actual=asdict(change_metrics(trace.scenario,last,final,previous_available=None if last is None else True))
        if record['metrics']!=actual:raise ValueError('stored change metrics differ')
        last=final;approved+=1
    if (episode['last_committed'] is None)!=(last is None) or (last is not None and deployment_from_dict(episode['last_committed'],trace.scenario)!=last):raise ValueError('final state differs')
    if episode['status']!=m['episode_status'] or (m['status']=='completed')!=episode['transition_valid']:raise ValueError('outcome/manifest differs')
    if episode['status'] not in {'success','failed','numerical_rejection','infrastructure_error'} or episode['transition_valid']!=(episode['status'] in {'success','failed'}):raise ValueError('invalid transition classification')
    failure=next((r['window_index'] for r in episode['windows'] if r['status']!='committed'),None)
    if episode['failure_window']!=failure:raise ValueError('failure index differs')
    if episode['method_id']!=settings['method_id'] or episode['initialization_study']!=settings['initialization_study']:raise ValueError('episode config differs')
    summary=read_json(attempt/'summary.json')
    if summary['episode_status']!=episode['status'] or summary['transition_valid']!=episode['transition_valid'] or summary['committed_windows']!=approved or summary['failure_window']!=episode['failure_window']:raise ValueError('summary differs from episode')
    if (episode['status']=='success')!=all(r['status']=='committed' for r in episode['windows']):raise ValueError('invalid episode success claim')
    return {'valid':True,'usable_episode':episode['transition_valid'],'episode_status':episode['status'],
            'approved_windows':approved,'trace_content_hash':trace.content_hash,'scope':'artifact integrity and independent committed-deployment checks; not solver optimality proof'}
