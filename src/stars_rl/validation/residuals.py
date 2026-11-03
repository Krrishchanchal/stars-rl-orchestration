"""Original-unit acceptance registry from execution contract section8."""
from dataclasses import dataclass
import math


FAMILIES={
    "binary":("dimensionless",1e-8,0),"counts":("count",1e-8,0),"logic":("count",0,0),
    "cpu":("MIPS",1e-6,1e-8),"throughput":("bits/s",1e-3,1e-9),
    "reciprocal":("dimensionless",1e-8,0),"processing":("seconds",5e-8,0),
    "reconstruction":("seconds",2.5e-8,0),"raw_delay":("seconds",2.5e-8,0),
    "e2e":("seconds",1e-7,0),"total_error":("seconds",1e-7,0),
}


def finite(value, label="number") -> float:
    try:
        if type(value) not in (int,float) or not math.isfinite(value):
            raise ValueError(f"{label}: finite numeric data required")
        return float(value)
    except OverflowError as exc:
        raise ValueError(f"{label}: outside float range") from exc


@dataclass(frozen=True,slots=True)
class Residual:
    family: str
    row_id: str
    units: str
    violation: float
    threshold: float
    normalized_violation: float | None
    passed: bool
    severity: str="error"


class Residuals:
    def __init__(self):self.rows=[]

    def add(self,family,row_id,violation,*,reference=0) -> Residual:
        if family not in FAMILIES:raise ValueError(f"unregistered residual family: {family}")
        v=finite(violation,"violation");ref=finite(reference,"reference")
        if v<0 or ref<0:raise ValueError("violations and references must be nonnegative")
        units,absolute,relative=FAMILIES[family];threshold=max(absolute,relative*ref)
        ratio=v/threshold if threshold else (0 if v==0 else None)
        if ratio is not None and not math.isfinite(ratio):ratio=None
        row=Residual(family,row_id,units,v,threshold,ratio,v<=threshold)
        self.rows.append(row);return row

    def eq(self,family,row_id,actual,expected,*,reference=0):
        return self.add(family,row_id,abs(finite(actual)-finite(expected)),reference=reference)

    def le(self,family,row_id,actual,upper,*,reference=0):
        return self.add(family,row_id,max(0,finite(actual)-finite(upper)),reference=reference)

    def ge(self,family,row_id,actual,lower,*,reference=0):
        return self.add(family,row_id,max(0,finite(lower)-finite(actual)),reference=reference)

    def logic(self,row_id,condition):return self.add("logic",row_id,0 if condition else 1)


def processing_error(terms) -> float | None:
    """Sum all selected |t-A/G| and all unselected |t|; undefined at selected G<=0.
    Each term is (decoded_beta, original_G_MIPS, A_seconds_MIPS, original_t_seconds).
    """
    errors=[]
    for selected,cpu,amplitude,delay in terms:
        g=finite(cpu);a=finite(amplitude);t=finite(delay)
        if selected:
            if g<=0:return None
            errors.append(abs(t-a/g))
        else:errors.append(abs(t))
    return math.fsum(errors)
