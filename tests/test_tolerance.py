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
        accounting=AccountingConvention(),
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


def test_rounding_aware_accounting_marks_large_residual_as_fail():
    report = audit(
        _io_with_output_residual(2.0),
        accounting_tolerance={"absolute": 1.0},
    )
    assert report.accounting.output_balance.status == "FAIL"
    assert report.passed() is False
    with pytest.raises(IOAuditError):
        report.raise_for_status()
