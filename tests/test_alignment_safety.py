import numpy as np
import pandas as pd

from ioaudit import AccountingConvention, IOSystem, TradeFlows, audit


def _convention(**kwargs):
    values = {
        "transaction_scope": "domestic",
        "import_treatment": "competitive",
        "trade_representation": "embedded",
        "input_representation": "complete",
    }
    values.update(kwargs)
    return AccountingConvention(**values)


def test_reversed_x_labels_skip_all_position_dependent_math():
    z = pd.DataFrame(np.eye(2), index=["A", "B"], columns=["A", "B"])
    x = pd.Series([1.0, 1.0], index=["B", "A"])
    report = audit(
        IOSystem(
            z,
            x,
            ["A", "B"],
            Y=np.ones(2),
            V=np.zeros(2),
            accounting=_convention(),
        )
    )
    assert report.structure.x_labels_match is False
    assert report.structure.normalized_x_labels_match is False
    assert report.coefficients.status == "SKIPPED"
    assert report.stability.status == "SKIPPED"
    assert report.accounting.status == "SKIPPED"


def test_z_sector_order_mismatch_skips_position_dependent_math():
    z = pd.DataFrame(np.eye(2), index=["B", "A"], columns=["B", "A"])
    report = audit(
        IOSystem(
            z,
            np.ones(2),
            ["A", "B"],
            Y=np.ones(2),
            V=np.zeros(2),
            accounting=_convention(),
        )
    )
    assert report.structure.z_row_labels_match_sectors is False
    assert report.structure.z_column_labels_match_sectors is False
    assert report.coefficients.status == "SKIPPED"
    assert report.stability.status == "SKIPPED"
    assert report.accounting.status == "SKIPPED"


def test_reversed_y_labels_only_skip_output_accounting():
    z = pd.DataFrame(np.eye(2) * 0.1, index=["A", "B"], columns=["A", "B"])
    y = pd.Series([1.0, 1.0], index=["B", "A"])
    report = audit(
        IOSystem(
            z,
            np.ones(2),
            ["A", "B"],
            Y=y,
            V=np.full(2, 0.9),
            accounting=_convention(),
        )
    )
    assert report.structure.status == "FAIL"
    assert report.coefficients.status == "PASS"
    assert report.stability.status == "PASS"
    assert report.accounting.output_balance.status == "SKIPPED"
    assert report.accounting.input_balance.status == "PASS"


def test_reversed_v_labels_only_skip_input_accounting():
    z = pd.DataFrame(np.eye(2) * 0.1, index=["A", "B"], columns=["A", "B"])
    v = pd.Series([0.9, 0.9], index=["B", "A"])
    report = audit(
        IOSystem(
            z,
            np.ones(2),
            ["A", "B"],
            Y=np.full(2, 0.9),
            V=v,
            accounting=_convention(),
        )
    )
    assert report.structure.status == "FAIL"
    assert report.coefficients.status == "PASS"
    assert report.accounting.output_balance.status == "PASS"
    assert report.accounting.input_balance.status == "SKIPPED"


def test_normalized_labels_are_used_with_warning():
    z = pd.DataFrame(np.eye(2) * 0.1, index=["A ", "B"], columns=["A", "B"])
    x = pd.Series([1.0, 1.0], index=["A", "B"])
    report = audit(
        IOSystem(
            z,
            x,
            ["A", "B"],
            Y=np.zeros(2),
            V=np.zeros(2),
            accounting=_convention(),
        )
    )
    assert report.structure.status == "PASS"
    assert report.coefficients.status == "PASS"
    assert any("normalization" in warning for warning in report.warnings)


def test_normalized_duplicate_core_labels_fail_structure():
    z = pd.DataFrame(
        np.eye(2) * 0.1,
        index=["A", "A "],
        columns=["A", "A "],
    )
    report = audit(IOSystem(z, np.ones(2), ["A", "A "]))
    assert report.structure.status == "FAIL"
    assert report.structure.details["core_normalized_duplicates"]
    assert report.coefficients.status == "SKIPPED"


def test_trade_label_mismatch_is_supporting_failure_only():
    z = np.eye(2) * 0.1
    report = audit(
        IOSystem(
            z,
            np.ones(2),
            ["A", "B"],
            Y=np.full(2, 0.9),
            V=np.full(2, 0.9),
            trade=TradeFlows(
                combined_inflows=pd.Series([0.0, 0.0], index=["B", "A"])
            ),
            accounting=_convention(
                trade_representation="outflows_in_Y",
                external_flow_scope="international",
                inflow_sign="positive",
            ),
        )
    )
    assert report.structure.status == "PASS"
    assert report.structure.supporting_status == "FAIL"
    assert report.coefficients.status == "PASS"
    assert report.accounting.output_balance.status == "SKIPPED"


def test_total_transactions_does_not_assume_complete_value_added():
    convention = AccountingConvention.total_transactions()
    assert convention.input_representation == "unknown"
