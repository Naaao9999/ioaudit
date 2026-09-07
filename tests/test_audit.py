import json

import pytest

from ioaudit import IOAuditError, audit


def test_summary_and_serialization(normal_io):
    report = audit(normal_io)
    summary = report.summary()
    assert "IO Audit Report" in summary
    payload = report.to_dict()
    assert payload["structure"]["status"] == "PASS"
    assert json.loads(report.to_json())["methods"]["numerical_method"] == "dense"
    frame = report.to_dataframe()
    assert set(["path", "value"]) == set(frame.columns)


def test_raise_for_status_and_passed(normal_io):
    report = audit(normal_io)
    report.raise_for_status(max_relative_residual=1e-4)
    assert report.thresholds["accounting.max_relative_residual"] == 1e-4
    assert report.passed({"accounting.max_relative_residual": 1e-4}) is True

    imbalanced = normal_io
    imbalanced.Y[0, 0] += 1
    bad = audit(imbalanced)
    assert bad.passed({"accounting.max_relative_residual": 1e-4}) is False
    with pytest.raises(IOAuditError):
        bad.raise_for_status()
    with pytest.raises(IOAuditError):
        bad.raise_for_status(max_relative_residual=1e-4)


def test_signs_do_not_fail_boolean_gate():
    from ioaudit import AccountingConvention, IOSystem
    import numpy as np

    io = IOSystem(np.array([[-1.0]]), np.array([1.0]), ["a"], accounting=AccountingConvention())
    report = audit(io)
    assert report.passed() is True


def test_invalid_thresholds_are_not_silently_ignored(normal_io):
    report = audit(normal_io)
    assert report.passed({"stability.spectral_raduis": 1.0}) is False
    assert report.passed({"stability.spectral_radius": float("nan")}) is False
    with pytest.raises(IOAuditError):
        report.raise_for_status(max_spectral_radius=float("nan"))


def test_invalid_y_shape_is_a_boolean_failure():
    import numpy as np
    from ioaudit import AccountingConvention, IOSystem

    report = audit(
        IOSystem(
            np.eye(2),
            np.ones(2),
            ["a", "b"],
            Y=np.ones(3),
            accounting=AccountingConvention(),
        )
    )
    assert report.structure.y_shape == "FAIL"
    assert report.passed() is False


def test_explicit_threshold_fails_when_accounting_metric_is_unavailable():
    import numpy as np
    from ioaudit import AccountingConvention, IOSystem

    report = audit(
        IOSystem(
            np.array([[0.1]]),
            np.ones(1),
            ["a"],
            accounting=AccountingConvention(trade_representation="embedded"),
        )
    )
    assert report.accounting.max_relative_residual is None
    assert report.passed({"accounting.max_relative_residual": 1e-4}) is False
    with pytest.raises(IOAuditError):
        report.raise_for_status(max_relative_residual=1e-4)
