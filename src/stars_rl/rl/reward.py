"""Actual-event reward, independent of the chosen optimization weights."""
import math

DISCOUNT = .95


def failure_reward(remaining, discount=DISCOUNT):
    if type(remaining) is not int or remaining < 1:
        raise ValueError('positive remaining horizon required')
    if type(discount) not in (int,float) or not math.isfinite(discount) or not 0 <= discount <= 1:
        raise ValueError('discount must be finite in [0,1]')
    return -4 * sum(discount**j for j in range(remaining))


def success_reward(metrics):
    if any(v is None or not math.isfinite(v) or not 0 <= v <= 1
           for v in (metrics.d_alpha, metrics.d_xi, metrics.d_beta)):
        raise ValueError('successful observed metrics required')
    return -(metrics.d_alpha + metrics.d_xi + metrics.d_beta)
