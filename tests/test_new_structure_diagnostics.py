import numpy as np
import pandas as pd

from ioaudit import IOSystem, audit


def test_normalized_label_match_is_reported_separately_from_exact_match():
    z = pd.DataFrame(
        [[1.0, 0.0], [0.0, 1.0]],
        index=["A", "B"],
        columns=["A ", "B　"],
    )
    x = pd.Series([1.0, 1.0], index=["A", "B　"])
    report = audit(IOSystem(z, x, ["A", "B"]))
    assert report.structure.row_column_labels_match is False
    assert report.structure.normalized_row_column_labels_match is True
    assert report.structure.x_labels_match is False
    assert report.structure.normalized_x_labels_match is True


def test_nonsector_labels_are_warnings_and_not_auto_removed():
    labels = ["A", "輸入"]
    report = audit(IOSystem(pd.DataFrame(np.eye(2), index=labels, columns=labels), np.ones(2), labels))
    assert report.structure.possible_nonsector_rows[0]["label"] == "輸入"
    assert report.structure.possible_nonsector_columns[0]["label"] == "輸入"
    assert report.structure.status == "PASS"


def test_exact_duplicate_rows_and_columns_are_reported():
    z = np.array([[1.0, 1.0], [1.0, 1.0]])
    report = audit(IOSystem(z, np.ones(2), ["A", "B"]))
    assert report.structure.possible_duplicate_rows
    assert report.structure.possible_duplicate_columns
    assert report.structure.possible_duplicate_rows[0]["first_index"] == 0
