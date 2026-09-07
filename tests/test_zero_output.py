import numpy as np

from ioaudit import IOSystem, audit


def test_consistent_zero_output_is_safe():
    z = np.array([[1.0, 0.0], [2.0, 0.0]])
    x = np.array([4.0, 0.0])
    report = audit(IOSystem(z, x, ["a", "b"]))
    assert report.zero_structure.consistent_sectors == ["b"]
    assert report.zero_structure.inconsistent_sectors == []
    assert np.isfinite(report.coefficients.A).all()
    assert np.all(report.coefficients.A[:, 1] == 0)


def test_inconsistent_zero_output_is_flagged_without_nan_inf():
    z = np.array([[1.0, 1.0], [2.0, 0.0]])
    x = np.array([4.0, 0.0])
    report = audit(IOSystem(z, x, ["a", "b"]))
    assert report.zero_structure.inconsistent_sectors == ["b"]
    assert report.coefficients.status == "SKIPPED"
    assert report.coefficients.A is None
    assert report.stability.status == "SKIPPED"
