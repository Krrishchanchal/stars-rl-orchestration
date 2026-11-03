"""Frozen C12 method packages; descriptive independent baseline names."""
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class MethodSpec:
    method_id: str
    stages: int
    initial_objective: str
    later_objective: str
    prior_start: bool


METHODS = MappingProxyType({s.method_id:s for s in (
    MethodSpec('mono-delay',1,'Q','Q',False),
    MethodSpec('mono-temporal',1,'Q','D_alpha+D_xi+D_beta_original',True),
    MethodSpec('hier-only',2,'propagation_then_H','propagation_then_H',False),
    MethodSpec('stars-fixed',2,'propagation_then_H','repaired_associations_then_H+rho_D_beta',True),
)})


def method_spec(method_id):
    if method_id not in METHODS:
        raise ValueError('unsupported C12 method; stars-random/stars-q require later policy implementation')
    return METHODS[method_id]
