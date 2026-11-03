"""O-RESIDUALFAMILY: independent literal thresholds and normalized violations."""
import pytest

from stars_rl.validation.residuals import Residuals, processing_error


@pytest.mark.parametrize("family,reference,threshold",[
    ("binary",0,1e-8),("counts",0,1e-8),("cpu",0,1e-6),("cpu",2000,2e-5),
    ("throughput",2e6,.002),("throughput",20e6,.02),("reciprocal",0,1e-8),
    ("processing",0,5e-8),("reconstruction",0,2.5e-8),("raw_delay",0,2.5e-8),
    ("e2e",0,1e-7),("total_error",0,1e-7),
])
def test_each_original_unit_boundary(family,reference,threshold):
    for factor,expected in [(.5,True),(2,False)]:
        rows=Residuals();row=rows.add(family,"injected",factor*threshold,reference=reference)
        assert row.threshold==pytest.approx(threshold,rel=1e-15)
        assert row.passed==expected
        assert row.normalized_violation==pytest.approx(factor)


def test_exact_logic_unknown_family_and_nonfinite():
    rows=Residuals()
    assert rows.logic("true",True).passed
    assert not rows.logic("false",False).passed
    assert rows.rows[-1].normalized_violation is None
    for family,value in [("unregistered",0),("cpu",float("nan")),("counts",float("inf"))]:
        with pytest.raises(ValueError):rows.add(family,"invalid",value)


@pytest.mark.parametrize("cpus,expected_delay",[((3,6),1),((4,5),1.05)])
def test_alloc2_processing_independent_of_c04(cpus,expected_delay):
    # Literal algebraic A=(1,4), C9, not physical inputs or a local-NLP oracle.
    times=(1/cpus[0],4/cpus[1])
    assert sum(times)==pytest.approx(expected_delay)
    terms=[(1,cpus[0],1,times[0]),(1,cpus[1],4,times[1])]
    assert processing_error(terms)==0
    assert processing_error([(1,cpus[0]+1,1,times[0]),terms[1]])>5e-8
    rows=Residuals();assert rows.add("cpu","C14",max(0,sum(cpus)-9),reference=9).passed
    assert not rows.add("cpu","C14-corrupt",.01,reference=9).passed


def test_inactive_and_mixed_budget_constants():
    inactive=[(0,0,1.08,1.08e-10)]*476
    assert processing_error(inactive)==pytest.approx(5.1408e-8,rel=1e-14,abs=0)
    assert not Residuals().add("processing","sum",processing_error(inactive)).passed
    assert processing_error([(1,0,1,0)]) is None
