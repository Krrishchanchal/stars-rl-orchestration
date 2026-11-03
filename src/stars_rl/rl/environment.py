"""Plain Python reset/step API; immutable input and transactional solver state."""
from copy import deepcopy

from stars_rl.simulation import advance_window
from stars_rl.topology.trace import NetworkTrace
from .actions import DEFAULT_ACTION, ratio
from .reward import failure_reward, success_reward
from .state import observation


class TransitionError(RuntimeError):
    """Implementation/infrastructure errors must never become learned rewards."""


class StarsEnvironment:
    def __init__(self, trace, *, total_budget_seconds=None, radio_coefficients_by_window=None, services=None, initial_export=None):
        if not isinstance(trace,NetworkTrace):
            raise ValueError('validated immutable NetworkTrace required')
        self._trace = trace
        self._options = dict(total_budget_seconds=total_budget_seconds,
                             radio_coefficients_by_window=deepcopy(radio_coefficients_by_window),services=services,
                             initial_export=deepcopy(initial_export))
        self._done = True
        self._records = []

    @property
    def trace(self):
        return self._trace

    @property
    def records(self):
        return tuple(deepcopy(self._records))

    def reset(self):
        self._index = 0
        self._previous = None
        self._churn = 0
        self._records = []
        self._done = False
        return observation(self.trace,0), {'initialization_forced':True}

    def fork(self):
        """Replay actions from the identical committed state, with no solver replay.

        Solver RNG configuration remains the core's frozen seed zero. Injected
        service clocks may be stateful; callers must supply isolated test clocks.
        """
        if self._done:
            raise RuntimeError('only active environments can be forked')
        other = StarsEnvironment(self.trace,**self._options)
        other._index,other._previous,other._churn = self._index,self._previous,self._churn
        other._records = deepcopy(self._records)
        other._done = False
        return other

    def step(self, action):
        chosen = ratio(action)
        if self._done:
            raise RuntimeError('reset required before stepping a terminated environment')
        initial = self._previous is None
        effective = DEFAULT_ACTION if initial else action
        result = advance_window(self.trace,self._index,self._previous,rho=ratio(effective),**self._options)
        record = result.windows[0]
        self._records.append(record)
        if not result.transition_valid:
            self._done = True
            raise TransitionError(f'{record.status}: {record.reason}')
        remaining = len(self.trace.windows)-self._index
        failed = record.status != 'committed'
        reward = failure_reward(remaining) if failed else success_reward(record.metrics)
        self._index += 1
        self._done = failed or self._index == len(self.trace.windows)
        if not failed:
            self._previous = record.committed_deployment
            self._churn = -reward
        next_state = None if self._done else observation(self.trace,self._index,self._previous,self._churn)
        return next_state, reward, self._done, False, dict(
            requested_action=action, requested_ratio=chosen,effective_action=effective, rho=ratio(effective),
            learning_eligible=not initial, failure=failed, status=record.status, reason=record.reason,
            remaining_before=remaining)
