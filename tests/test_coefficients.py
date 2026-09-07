import numpy as np

from ioaudit import IOSystem, audit


def test_known_a(normal_io):
    report = audit(normal_io)
    expected = normal_io.Z / normal_io.x[np.newaxis, :]
    np.testing.assert_allclose(report.coefficients.A, expected)
    assert report.coefficients.finite_coefficients is True
    assert report.coefficients.column_sums == list(expected.sum(axis=0))
    assert report.coefficients.negative_coefficients["count"] == 0
