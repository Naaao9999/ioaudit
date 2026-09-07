import numpy as np
import pandas as pd
from scipy import sparse

from ioaudit import IOSystem, audit


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
