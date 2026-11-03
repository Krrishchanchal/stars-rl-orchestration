"""C02 row-level calibration, not the future independent deployment validator.

Literal physical thresholds below come from execution_contract section 8.
Injected cases exercise SCIP checkSol on the original rows: 0.5/2 times
the *physical* threshold are both outside SCIP's tighter 1e-9 target.
Their future validator acceptance differs; that gate remains C07/C08.
"""
import json
import math

import pytest

from stars_rl.optimization.backend import create_model, solve

pytestmark = pytest.mark.solver


def test_residual_family_calibration(tmp_path):
    records = []
    # family, original-unit reference, row divisor, physical threshold
    families = [
        ("association", 1., 1., 1e-8),
        ("occupancy", 1., 1., 1e-8),
        ("activation", 1., 1., 1e-8),
        ("endpoint_product", 1., 1., 1e-8),
        ("internal_product", 1., 1., 1e-8),
        ("deviation", 1., 1., 1e-8),
        ("cpu_zero_host", 0., 1., 1e-6),
        ("cpu_minimum", 1800., 2000., 2e-5),
        ("cpu_gate", 2000., 2000., 2e-5),
        ("cpu_overhead", 2000., 2000., 2e-5),
        ("throughput_low", 2e6, 2e6, .002),
        ("throughput_high", 20e6, 20e6, .02),
        ("qhat_definition", 1., 1., 1e-8),
        ("qhat_bound", 1., 1., 1e-8),
        ("raw_c16", .035, .035, 2.5e-8),
        ("other_delay_reconstruction", .035, 1., 2.5e-8),
    ]
    for family, reference, divisor, threshold in families:
        m = create_model(family)
        x = m.addVar("physical", lb=0, ub=max(2*reference, 1))
        m.addCons(x/divisor == reference/divisor)
        result = solve(m, stage="calibration", objective_name=family, objective_units="original")
        raw = result.values["physical"]
        error = abs(raw-reference)
        assert error <= threshold
        checks = []
        for multiple in [.5, 2]:
            sol = m.createOrigSol()
            m.setSolVal(sol, x, reference + multiple*threshold)
            feasible = bool(m.checkSol(sol, original=True, completely=True, printreason=False))
            m.freeSol(sol)
            # Diagnostic only: SCIP checks scaled rows, not physical budgets.
            checks.append({"injected_physical_residual": multiple*threshold,
                           "normalized_physical_violation": multiple,
                           "solver_check_feasible": feasible,
                           "future_physical_row_expected_pass": multiple == .5})
        records.append({"family": family, "raw_value": raw, "residual": error,
                        "target": threshold, "ratio": error/threshold, "injections": checks})

    # Binary boundary candidates are deliberately raw, never rounded into feasibility.
    m = create_model("binary_calibration")
    b = m.addVar("b", vtype="B")
    binary_checks = []
    for raw in [5e-9, 2e-8, 1-5e-9, 1-2e-8]:
        sol = m.createOrigSol()
        m.setSolVal(sol, b, raw)
        feasible = bool(m.checkSol(sol, original=True, completely=True, printreason=False))
        m.freeSol(sol)
        binary_checks.append({"raw": raw, "solver_check_feasible": feasible,
                              "future_decode_expected_pass": raw in [5e-9, 1-5e-9]})

    # Independent O-SCALE: tau=1/2+epsilon, qhat=g=2 gives
    # t-A/G = (A/L)*epsilon. Four small errors must be summed.
    epsilon = 2e-6
    errors = [abs((.5+epsilon)*.008 - .004) for _ in range(4)]
    assert all(e < 5e-8 for e in errors)
    assert sum(errors) > 5e-8
    # Inactive candidates matter even when every selected delay is exact.
    assert sum([0., 3e-8, 3e-8]) > 5e-8
    assert not math.isfinite(float("nan"))
    report = {"rows": records, "binary_injections": binary_checks,
              "aggregate_processing_error": sum(errors),
              "scope": "row-level backend calibration; full raw/decoded validation pending C07/C08"}
    (tmp_path / "residual_calibration.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
