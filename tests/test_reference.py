import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from ioaudit import IOAuditError, IOSystem, audit


def test_reference_matrices(normal_io):
    a = normal_io.Z / normal_io.x[np.newaxis, :]
    l = np.linalg.inv(np.eye(2) - a)
    report = audit(IOSystem(normal_io.Z, normal_io.x, normal_io.sectors, A_reference=a, L_reference=l))
    assert report.reference.status == "PASS"
    assert report.reference.A.max_absolute_difference == 0
    assert report.reference.L.rmse == 0
    assert report.reference.A.shape_consistency is True


def test_reference_shape_and_labels(normal_io):
    wrong_shape = np.ones((3, 3))
    wrong_labels = pd.DataFrame(np.eye(2), index=["B", "A"], columns=["B", "A"])
    report = audit(IOSystem(normal_io.Z, normal_io.x, normal_io.sectors, A_reference=wrong_shape, L_reference=wrong_labels))
    assert report.reference.A.shape_consistency is False
    assert report.reference.L.label_consistency is False
    assert report.reference.status == "FAIL"


def test_missing_reference_is_skipped(normal_io):
    report = audit(normal_io)
    assert report.reference.status == "SKIPPED"
    assert report.reference.A.status == "SKIPPED"


def test_sparse_reference_comparison_uses_dense_numeric_values():
    z = np.eye(2) * 0.1
    report = audit(
        IOSystem(z, np.ones(2), ["a", "b"], A_reference=sparse.eye(2) * 0.1)
    )
    assert report.reference.A.status == "PASS"
    assert report.reference.A.relative_difference == 0


def test_invalid_optional_reference_does_not_fail_core_structure_or_stop_audit(normal_io):
    report = audit(
        IOSystem(
            normal_io.Z,
            normal_io.x,
            normal_io.sectors,
            Y=normal_io.Y,
            V=normal_io.V,
            accounting=normal_io.accounting,
            L_reference=pd.DataFrame([["..", 0.0], [0.0, 1.0]]),
        )
    )
    assert report.structure.status == "PASS"
    assert report.reference.status == "FAIL"
    assert report.coefficients.status == "PASS"
    assert report.stability.status == "PASS"
    assert report.accounting.status == "AVAILABLE"
    assert report.passed() is True
    assert report.passed(fail_on_invalid_reference=True) is False
    with pytest.raises(IOAuditError):
        report.raise_for_status(fail_on_invalid_reference=True)


def test_scale_does_not_use_reference_with_mismatched_labels(normal_io):
    reference = pd.DataFrame(
        normal_io.Z / normal_io.x[np.newaxis, :],
        index=["B", "A"],
        columns=["B", "A"],
    )
    report = audit(
        IOSystem(
            normal_io.Z,
            normal_io.x,
            normal_io.sectors,
            Y=normal_io.Y,
            V=normal_io.V,
            accounting=normal_io.accounting,
            A_reference=reference,
        )
    )
    assert report.reference.A.status == "FAIL"
    assert report.scale.reference_evidence_used is False
    assert report.scale.reference_evidence_reason
    assert all("reference_evidence" not in item for item in report.scale.possible_cell_scale_errors)
