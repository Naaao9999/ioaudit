import numpy as np
import pandas as pd

from ioaudit import AccountingConvention, IOSystem, audit


def test_structure_passes(normal_io):
    report = audit(normal_io)
    assert report.structure.status == "PASS"
    assert report.structure.z_is_2d == "PASS"
    assert report.structure.z_is_square == "PASS"


def test_non_square_is_reported_and_downstream_skipped():
    io = IOSystem(np.ones((2, 3)), np.ones(2), ["a", "b"])
    report = audit(io)
    assert report.structure.z_is_square == "FAIL"
    assert report.coefficients.status == "SKIPPED"
    assert report.stability.status == "SKIPPED"


def test_nan_inf_and_nonnumeric():
    nan_report = audit(IOSystem(np.array([[1.0, np.nan], [0.0, 1.0]]), np.ones(2), ["a", "b"]))
    assert nan_report.structure.nan_exists is True
    inf_report = audit(IOSystem(np.array([[1.0, np.inf], [0.0, 1.0]]), np.ones(2), ["a", "b"]))
    assert inf_report.structure.inf_exists is True
    text_report = audit(IOSystem(pd.DataFrame([[1.0, "bad"], [0.0, 1.0]]), np.ones(2), ["a", "b"]))
    assert text_report.structure.non_numeric is True


def test_invalid_employment_does_not_fail_core_structure():
    report = audit(
        IOSystem(
            np.eye(2) * 0.1,
            np.ones(2),
            ["a", "b"],
            employment=["bad", None],
        )
    )
    assert report.structure.status == "PASS"
    assert report.structure.auxiliary_status == "FAIL"
    assert report.structure.auxiliary_non_numeric_fields == ["employment"]
    assert any("auxiliary data" in warning for warning in report.warnings)
    assert report.passed() is True


def test_invalid_satellites_do_not_fail_core_structure():
    report = audit(
        IOSystem(
            np.eye(2) * 0.1,
            np.ones(2),
            ["a", "b"],
            satellites=np.array([[1.0, np.nan]]),
        )
    )
    assert report.structure.status == "PASS"
    assert report.structure.auxiliary_status == "FAIL"
    assert report.structure.auxiliary_nan_fields == ["satellites"]
    assert report.passed() is True


def test_duplicate_sector_ids():
    report = audit(IOSystem(np.eye(2), np.ones(2), ["a", "a"]))
    assert report.structure.duplicate_sector_ids is True


def test_auxiliary_sector_labels_are_checked():
    z = pd.DataFrame(
        [[0.1, 0.0], [0.0, 0.1]], index=["a", "b"], columns=["a", "b"]
    )
    y = pd.Series([3.0, 8.0], index=["b", "a"])
    report = audit(
        IOSystem(
            z,
            np.array([3.1, 8.1]),
            ["a", "b"],
            Y=y,
            V=np.array([3.0, 8.0]),
            accounting=AccountingConvention(trade_representation="embedded"),
        )
    )
    assert report.structure.y_labels_match is False
    assert report.structure.status == "FAIL"


def test_named_output_vector_is_reported_as_possible_total():
    x = pd.Series([1.0, 2.0], index=["a", "b"], name="Total")
    report = audit(IOSystem(np.eye(2), x, ["a", "b"]))
    assert report.structure.possible_total_vector[0]["label"] == "Total"


def test_unlabelled_numeric_total_row_and_column_are_reported():
    z = pd.DataFrame(
        [[1.0, 2.0, 3.0], [4.0, 5.0, 9.0], [5.0, 7.0, 12.0]],
        index=["A", "B", "C"],
        columns=["A", "B", "C"],
    )
    report = audit(IOSystem(z, np.ones(3), ["A", "B", "C"]))
    row_candidate = next(
        item for item in report.structure.possible_total_rows if item["index"] == 2
    )
    column_candidate = next(
        item for item in report.structure.possible_total_columns if item["index"] == 2
    )
    assert row_candidate["label_evidence"] is False
    assert row_candidate["sum_similarity"] == 1.0
    assert column_candidate["label_evidence"] is False
    assert column_candidate["sum_similarity"] == 1.0
