"""Per-window solve/check/commit orchestration with episode-local state.

Every failed decision terminates the episode. Remaining windows are explicitly
not attempted. Infrastructure/numerical failures are not modeled transitions.
Artifact persistence/manifests/resume belong to C13, not this in-memory runner.
"""
from copy import deepcopy
from dataclasses import dataclass, field
import math
import time

from .baselines import method_spec
from .config import deployment_from_dict
from .metrics import change_metrics
from .optimization.baselines import run_monolithic
from .optimization.result import StageResult
from .optimization.stage1 import run_stage1
from .optimization.stage2 import run_stage2
from .topology.trace import NetworkTrace
from .validation.deployment import validate_export
from .validation.monolithic import validate_monolithic
from .validation.stage2 import validate_stage2


@dataclass(frozen=True)
class RuntimeServices:
    stage1: object=run_stage1
    stage2: object=run_stage2
    monolithic: object=run_monolithic
    clock: object=time.perf_counter


def _stages():
    return {name:StageResult(name,'not_attempted','not_attempted') for name in ('stage1','stage2','monolithic')}


@dataclass
class WindowRecord:
    window_index: int
    status: str='not_attempted'
    reason: str='not_attempted'
    failure_stage: str | None=None
    previous_committed: object=None
    committed_deployment: object=None
    stages: dict=field(default_factory=_stages)
    stage1_outcome: object=None
    final_outcome: object=None
    export: dict | None=None
    commit_validation: dict=field(default_factory=dict)
    metrics: object=None
    rho: float | None=None
    elapsed_seconds: float=0
    error: dict | None=None
    timings: dict=field(default_factory=dict)


@dataclass
class EpisodeResult:
    method_id: str
    initialization_study: str
    total_budget_seconds: float
    runtime_adapter: str
    status: str='success'
    transition_valid: bool=True
    failure_window: int | None=None
    windows: tuple=()
    last_committed: object=None


def simulate(trace: NetworkTrace, method_id='stars-fixed', *, rho=1,
             total_budget_seconds=10, radio_coefficients_by_window=None,
             initial_export=None, services=None) -> EpisodeResult:
    """Run one isolated method/episode; commit only checked on-time final choices.

    Common-initial-state studies accept a saved base full-model export for window0
    and independently check it within that window budget. Native objectives are
    bypassed only in that separately labeled study. Injected services are labeled
    test adapters, never silently described as standard solver measurements.
    """
    if not isinstance(trace,NetworkTrace):raise ValueError('validated NetworkTrace required')
    spec=method_spec(method_id)
    if type(total_budget_seconds) not in (int,float) or not math.isfinite(total_budget_seconds) or total_budget_seconds<=0:
        raise ValueError('positive finite window budget required')
    if type(rho) not in (int,float) or rho not in (.25,.5,1,2,4):raise ValueError('rho must belong to the frozen ratio grid')
    runtime=RuntimeServices() if services is None else services
    episode=EpisodeResult(method_id,'native_initialization' if initial_export is None else 'common_initial_state',
                          total_budget_seconds,'standard' if services is None else 'injected_test_adapter')
    records=[];committed=None;stopped=False
    scenario=trace.scenario
    for w in trace.windows:
        record=WindowRecord(w.window_index,previous_committed=committed)
        records.append(record)
        if stopped:
            record.reason=f'episode_terminated_after_window_{episode.failure_window}'
            continue
        t0=runtime.clock();deadline=t0+total_budget_seconds
        active='initialization'
        try:
            rates=None if radio_coefficients_by_window is None else radio_coefficients_by_window[w.window_index]
            candidate=None
            if w.window_index==0 and initial_export is not None:
                record.export=deepcopy(initial_export)
                if runtime.clock()>=deadline:
                    record.status='late';record.reason='deadline_before_initial_validation'
                else:
                    record.commit_validation=validate_export(scenario,w,record.export,radio_coefficients=rates).to_dict()
                    if not record.commit_validation['valid']:
                        record.status='infrastructure_error';record.reason='invalid_common_initial_state'
                    else:
                        candidate=deployment_from_dict(record.export['candidate']['deployment'],scenario)
                        record.reason='externally_validated_common_initial_state'
            else:
                if spec.stages==2:
                    hierarchy_only=method_id=='hier-only'
                    objective_previous=None if hierarchy_only else committed
                    active='stage1'
                    first=runtime.stage1(scenario,w,objective_previous,started_at=t0,total_budget_seconds=total_budget_seconds,
                                        objective_mode='propagation' if hierarchy_only else None,
                                        warm=not hierarchy_only,clock=runtime.clock)
                    record.stage1_outcome=first;record.stages['stage1']=first.stage_result
                    if first.status!='reference_ready':
                        record.status='numerical_rejection' if first.reason=='association_validation_rejected' else 'failed'
                        record.reason='stage1_no_reference:'+first.reason;record.failure_stage='stage1'
                        if record.status=='numerical_rejection':episode.transition_valid=False
                        final=None
                    else:
                        active='stage2'
                        effective_rho=0 if hierarchy_only else (.5 if committed is None else rho)
                        record.rho=None if hierarchy_only else effective_rho
                        final=runtime.stage2(scenario,w,first,objective_previous,started_at=t0,total_budget_seconds=total_budget_seconds,
                                             weights=(1,effective_rho),radio_coefficients=rates,clock=runtime.clock)
                        record.stages['stage2']=final.stage_result
                else:
                    active='monolithic'
                    final=runtime.monolithic(scenario,w,method_id,committed,started_at=t0,
                                            total_budget_seconds=total_budget_seconds,radio_coefficients=rates,clock=runtime.clock)
                    record.stages['monolithic']=final.stage_result
                if final is not None:
                    record.final_outcome=final;record.export=final.export
                    if final.status=='late':record.status='late';record.reason=final.reason
                    elif final.status!='validated':
                        record.status='numerical_rejection' if final.reason=='deployment_validation_rejected' else 'failed'
                        record.reason=final.reason
                        if record.status=='numerical_rejection':episode.transition_valid=False
                    elif runtime.clock()>=deadline:
                        record.status='late';record.reason='deadline_before_commit_validation'
                    else:
                        # The state boundary independently checks the original raw
                        # export again; a stale/forged runner report cannot commit.
                        validation_started=runtime.clock()
                        if validation_started>=deadline:
                            record.status='late';record.reason='deadline_before_commit_validation'
                        else:
                            if spec.stages==2:
                                checked=validate_stage2(scenario,w,final.export,first.stage1_reference,objective_previous,
                                                        weights=(1,effective_rho),radio_coefficients=rates)
                            else:
                                mode='temporal' if method_id=='mono-temporal' and committed is not None else 'Q'
                                checked=validate_monolithic(scenario,w,final.export,mode=mode,previous=committed,radio_coefficients=rates)
                            record.timings['commit_validation_wall_seconds']=runtime.clock()-validation_started
                            record.commit_validation=checked
                            if not checked['valid']:
                                record.status='infrastructure_error' if checked['status'] in {'schema_error','input_error'} else 'numerical_rejection'
                                record.reason='commit_validation_rejected';episode.transition_valid=False
                            else:
                                candidate=deployment_from_dict(final.export['candidate']['deployment'],scenario)
                                if candidate!=final.final_deployment:raise ValueError('runner final state differs from validated export')
                                record.reason='validated_on_time'
                    if candidate is None:record.failure_stage=active
            if candidate is not None and runtime.clock()>deadline:
                candidate=None;record.status='late';record.reason='window_deadline_exceeded'
            if candidate is not None:
                metrics=change_metrics(scenario,committed,candidate,previous_available=None if committed is None else True)
                record.elapsed_seconds=max(0,runtime.clock()-t0)
                if record.elapsed_seconds>total_budget_seconds:
                    record.status='late';record.reason='window_deadline_exceeded'
                else:
                    committed=candidate;record.committed_deployment=candidate;record.metrics=metrics;record.status='committed'
            else:
                record.elapsed_seconds=max(0,runtime.clock()-t0)
                if record.elapsed_seconds>total_budget_seconds and record.status not in {'infrastructure_error','numerical_rejection'}:
                    record.status='late';record.reason='window_deadline_exceeded'
        except Exception as exc:
            record.status='infrastructure_error';record.reason='execution_error';record.failure_stage=active
            record.error={'type':type(exc).__name__,'message':str(exc)}
            if record.stages.get(active) is not None and record.stages[active].raw_status=='not_attempted':
                record.stages[active]=StageResult(active,'unknown_after_error','unknown',raw_status='infrastructure_error',outcome='model_error')
            record.elapsed_seconds=max(0,runtime.clock()-t0);episode.transition_valid=False
        if record.status!='committed':
            if record.failure_stage is None:record.failure_stage=active
            stopped=True;episode.failure_window=w.window_index
            episode.status=record.status if record.status in {'infrastructure_error','numerical_rejection'} else 'failed'
            if record.status in {'infrastructure_error','numerical_rejection'}:episode.transition_valid=False
            else:record.metrics=change_metrics(scenario,committed,None,previous_available=None if committed is None else True)
        record.timings['decision_wall_seconds']=record.elapsed_seconds
    episode.windows=tuple(records);episode.last_committed=committed
    return episode
