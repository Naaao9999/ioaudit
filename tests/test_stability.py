import numpy as np
from scipy import sparse

from ioaudit import IOSystem, audit


def test_known_l_and_dense_route(normal_io):
    report = audit(normal_io, numerical_method="dense")
    expected_a = normal_io.Z / normal_io.x[np.newaxis, :]
    expected_l = np.linalg.inv(np.eye(2) - expected_a)
    np.testing.assert_allclose(report.stability.leontief_inverse, expected_l)
    assert report.stability.invertible is True
    assert report.methods.numerical_method == "dense"
    assert report.methods.condition_number == "dense"


def test_singular_i_minus_a():
    report = audit(IOSystem(np.eye(2), np.ones(2), ["a", "b"]), numerical_method="dense")
    assert report.stability.invertible is False
    assert report.stability.condition_number == float("inf")


def test_spectral_radius_at_least_one():
    report = audit(IOSystem(np.diag([1.0, 0.5]), np.ones(2), ["a", "b"]))
    assert report.stability.spectral_radius >= 1.0


def test_iterative_route():
    report = audit(IOSystem(np.array([[0.1, 0.0], [0.0, 0.2]]), np.ones(2), ["a", "b"]), numerical_method="iterative")
    assert report.methods.numerical_method == "iterative"
    assert report.methods.spectral_radius == "iterative"
    assert report.stability.spectral_radius == 0.2
    assert report.stability.invertible is True


def test_iterative_condition_estimate_failure_does_not_imply_singularity(monkeypatch):
    import ioaudit.stability as stability

    def fail_estimator(*args, **kwargs):
        raise RuntimeError("estimator unavailable")

    monkeypatch.setattr(stability.spla, "onenormest", fail_estimator)
    report = audit(
        IOSystem(sparse.eye(3, format="csr") * 0.1, np.ones(3), ["a", "b", "c"]),
        numerical_method="iterative",
    )
    assert report.stability.invertible is True
    assert report.stability.condition_number is None
    assert report.stability.leontief_inverse_finite is True


def test_iterative_sparse_route_keeps_sparse_system():
    report = audit(
        IOSystem(sparse.eye(3, format="csr") * 0.1, np.ones(3), ["a", "b", "c"]),
        numerical_method="iterative",
    )
    assert sparse.issparse(report.coefficients.A)
    assert sparse.issparse(report.stability.B)


def test_auto_route_selects_iterative_for_sparse_input():
    report = audit(IOSystem(sparse.eye(2, format="csr") * 0.1, np.ones(2), ["a", "b"]))
    assert report.methods.numerical_method == "iterative"


def test_iterative_spectral_radius_failure_is_not_underestimated(monkeypatch):
    import ioaudit.stability as stability

    def fail_eigs(*args, **kwargs):
        raise RuntimeError("eigensolver unavailable")

    monkeypatch.setattr(stability.spla, "eigs", fail_eigs)
    coefficient_matrix = np.diag([1.2, 0.2, 0.1])
    report = audit(
        IOSystem(coefficient_matrix, np.ones(3), ["a", "b", "c"]),
        numerical_method="iterative",
    )
    assert report.stability.spectral_radius is None
    assert report.passed({"stability.spectral_radius": 1.0}) is False
