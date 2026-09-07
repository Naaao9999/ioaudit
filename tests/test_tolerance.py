import numpy as np
import pytest

from ioaudit import AccountingConvention, IOAuditError, IOSystem, audit


def _io_with_output_residual(residual):
    return IOSystem(
        np.array([[2.0, 1.0], [1.0, 3.0]]),
        np.array([8.0, 9.0]),
        ["A", "B"],
        Y=np.array([5.0 + residual, 5.0]),
        V=np.array([5.0, 5.0]),
        imports=np.zeros(2),
        accounting=AccountingConvention.domestic_competitive(),
    )


def test_rounding_aware_accounting_marks_small_nonzero_residual():
    report = audit(
        _io_with_output_residual(0.5),
        accounting_tolerance={"absolute": 1.0, "relative": 0.0, "rounding_unit": 1.0},
    )
    assert report.accounting.output_balance.status == "ROUNDING_LEVEL"
    assert report.passed() is True
    assert report.accounting.tolerance["rounding_unit"] == 1.0
    report.raise_for_status()


def test_nonzero_residual_without_tolerance_is_available_not_pass():
    report = audit(_io_with_output_residual(0.5))
    assert report.accounting.output_balance.status == "AVAILABLE"
    assert report.accounting.output_balance.max_absolute_residual == 0.5
    assert report.passed() is True


def test_rounding_aware_accounting_marks_large_residual_as_fail():
    report = audit(
        _io_with_output_residual(2.0),
        accounting_tolerance={"absolute": 1.0},
    )
    assert report.accounting.output_balance.status == "FAIL"
    assert report.passed() is False
    with pytest.raises(IOAuditError):
        report.raise_for_status()


def test_scale_ignores_residuals_inside_declared_rounding_envelope():
    report = audit(
        IOSystem(
            np.diag([2.0, 3.0]),
            np.array([10.0, 10.0]),
            ["A", "B"],
            Y=np.array([8.5, 7.0]),
            V=np.array([8.0, 7.0]),
            accounting=AccountingConvention(
                transaction_scope="domestic",
                import_treatment="competitive",
                trade_representation="embedded",
            ),
        ),
        accounting_tolerance={
            "absolute": 1.0,
            "relative": 0.0,
            "rounding_unit": 1.0,
        },
    )
    assert report.accounting.output_balance.status == "ROUNDING_LEVEL"
    assert report.accounting.output_balance.max_absolute_residual == 0.5
    assert report.scale.rounding_context_available is True
    assert report.scale.possible_global_scale_mismatches == []
    assert report.scale.possible_cell_scale_errors == []
