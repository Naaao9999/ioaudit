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
