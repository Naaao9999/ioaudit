import numpy as np
import pytest

from ioaudit import IOAuditError, MRIOSystem, audit_mrio


def _small_mrio(*, with_supporting_blocks: bool = True) -> MRIOSystem:
    z = np.array([[0.1, 0.02], [0.03, 0.1]])
    x = np.array([10.0, 12.0])
    kwargs = {}
    if with_supporting_blocks:
        y = np.array([9.88, 11.87])
        v = x - z.sum(axis=0)
        kwargs.update(Y=y, V=v)
    return MRIOSystem(
        Z=z,
        x=x,
        regions=["R"],
        sectors=["A", "B"],
        metadata={"year": 2020, "unit": "million", "price_basis": "producer"},
        **kwargs,
    )


def test_v02_report_exposes_the_fixed_status_and_gate_surface():
    report = audit_mrio(_small_mrio())

    statuses = {
        report.structure.status,
        report.structure.supporting_status,
        report.accounting.status,
        report.accounting.input_balance.status,
        report.accounting.output_balance.status,
        report.coefficients.status,
        report.stability.status,
    }
    assert statuses <= {"PASS", "AVAILABLE", "WARNING", "FAIL", "SKIPPED"}
    assert report.passed(require_complete=True)
    report.raise_for_status(require_complete=True)


def test_v02_passed_and_raise_for_status_share_the_same_gate():
    report = audit_mrio(
        MRIOSystem(
            Z=np.array([[1.1]]),
            x=np.array([1.0]),
            regions=["R"],
            sectors=["A"],
        )
    )

    assert report.passed() is False
    with pytest.raises(IOAuditError):
        report.raise_for_status()
    assert report.passed(fail_on_boolean=False) is False


def test_v02_require_complete_only_rejects_unavailable_optional_checks():
    report = audit_mrio(_small_mrio(with_supporting_blocks=False))

    assert report.passed() is True
    assert report.passed(require_complete=True) is False
    with pytest.raises(IOAuditError):
        report.raise_for_status(require_complete=True)
