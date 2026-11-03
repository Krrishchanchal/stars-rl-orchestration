"""Frozen ratio grid and deterministic evaluation convention."""
import math

RATIOS = (.25, .5, 1., 2., 4.)
DEFAULT_ACTION = 1


def ratio(action):
    if type(action) is not int or not 0 <= action < len(RATIOS):
        raise ValueError('action must be an integer in 0..4')
    return RATIOS[action]


def greedy_action(values=None):
    if values is None:
        return DEFAULT_ACTION
    if len(values) != 5 or any(not math.isfinite(v) for v in values):
        raise ValueError('five finite Q values required')
    best = max(values)
    ties = [i for i,v in enumerate(values) if abs(v-best) <= 1e-12]
    return DEFAULT_ACTION if DEFAULT_ACTION in ties else min(ties)
