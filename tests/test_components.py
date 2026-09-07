import numpy as np
import pandas as pd

from ioaudit import AccountingConvention, IOSystem, audit


def test_y_subtotal_column_and_v_subtotal_row_are_double_count_risks():
    y = pd.DataFrame(
        [[1.0, 2.0, 3.0], [2.0, 3.0, 5.0]],
        index=["A", "B"],
        columns=["家計消費", "政府消費", "最終需要計"],
    )
    v = pd.DataFrame(
        [[1.0, 2.0], [2.0, 3.0], [3.0, 5.0]],
        index=["雇用者所得", "営業余剰", "付加価値計"],
        columns=["A", "B"],
    )
    report = audit(
        IOSystem(
            np.eye(2),
            np.array([4.0, 6.0]),
            ["A", "B"],
            Y=y,
            V=v,
            accounting=AccountingConvention(),
        )
    )
    assert any(item["label"] == "最終需要計" for item in report.components.possible_subtotal_columns)
    assert any(item["label"] == "付加価値計" for item in report.components.possible_subtotal_rows)
    assert len(report.components.double_count_risk) == 2
    assert any("double-count" in warning for warning in report.warnings)
    assert report.accounting.output_balance.status == "SKIPPED"
    assert report.accounting.input_balance.status == "SKIPPED"


def test_single_component_y_and_v_do_not_create_subtotal_candidates():
    report = audit(
        IOSystem(
            np.eye(2),
            np.ones(2),
            ["A", "B"],
            Y=np.ones((2, 1)),
            V=np.ones((1, 2)),
        )
    )
    assert report.components.possible_subtotal_columns == []
    assert report.components.possible_subtotal_rows == []


def test_numeric_only_two_components_are_not_called_subtotals():
    y = np.ones((2, 2))
    v = np.ones((2, 2))
    report = audit(IOSystem(np.eye(2), np.ones(2), ["A", "B"], Y=y, V=v))
    assert report.components.possible_subtotal_columns == []
    assert report.components.possible_subtotal_rows == []


def test_geography_qualified_subtotal_labels_are_label_evidence():
    y = pd.DataFrame(
        [[1.0, 2.0], [3.0, 4.0]],
        index=["A", "B"],
        columns=["家計消費", "都内最終需要計"],
    )
    v = pd.DataFrame(
        [[1.0, 3.0], [2.0, 3.0]],
        index=["雇用者所得", "粗付加価値部門計"],
        columns=["A", "B"],
    )
    report = audit(IOSystem(np.eye(2), np.ones(2), ["A", "B"], Y=y, V=v))
    assert report.components.possible_subtotal_columns[0]["label_evidence"] is True
    assert report.components.possible_subtotal_rows[0]["label_evidence"] is True


def test_partial_subset_subtotal_is_reported_with_subset_members():
    y = pd.DataFrame(
        [[10.0, 2.0, 3.0, 5.0, 7.0], [20.0, 4.0, 6.0, 10.0, 9.0]],
        index=["A", "B"],
        columns=["P3 S1", "P3 S13", "P3 S14", "P3 S15", "投資"],
    )
    report = audit(IOSystem(np.eye(2), np.ones(2), ["A", "B"], Y=y))
    candidate = next(
        item for item in report.components.possible_subtotal_columns
        if item["index"] == 0
    )
    assert candidate["aggregation_type"] == "subset_sum"
    assert candidate["subset_indices"] == [1, 2, 3]
    assert candidate["subset_labels"] == ["P3 S13", "P3 S14", "P3 S15"]
    assert candidate["sum_similarity"] == 1.0
    assert report.accounting.output_balance.status == "SKIPPED"
