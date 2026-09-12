import numpy as np
import pandas as pd

from ioaudit import AccountingConvention, IOSystem, TradeFlows, audit


def _base(convention, *, output_adjustments=None, trade=None):
    z = np.array([[1.0, 0.0], [0.0, 2.0]])
    x = np.array([10.0, 20.0])
    return IOSystem(
        z,
        x,
        ["A", "B"],
        Y=np.array([8.0, 16.0]),
        output_adjustments=output_adjustments,
        trade=trade,
        accounting=convention,
    )


def _embedded_adjustments(**kwargs):
    return AccountingConvention.domestic_competitive(
        trade_representation="embedded",
        output_representation="adjustments_required",
        **kwargs,
    )


def test_signed_output_adjustment_is_added_to_output_identity():
    report = audit(
        _base(
            _embedded_adjustments(),
            output_adjustments=np.array([1.0, 2.0]),
        )
    )
    balance = report.accounting.output_balance
    assert balance.status == "PASS"
    assert balance.max_absolute_residual == 0.0
    assert set(balance.uses) == {"Y", "output_adjustments"}
    assert "+ output_adjustments (signed)" in balance.equation


def test_output_adjustment_dataframe_sums_components_and_checks_row_labels():
    adjustments = pd.DataFrame(
        [[0.5, 0.5], [1.0, 1.0]],
        index=["A", "B"],
        columns=["Net Import Duties", "Trade Margin"],
    )
    report = audit(
        _base(_embedded_adjustments(), output_adjustments=adjustments)
    )
    assert report.structure.output_adjustment_shape == "PASS"
    assert report.structure.output_adjustment_labels_match is True
    assert report.accounting.output_balance.status == "PASS"
    assert report.accounting.output_balance.max_absolute_residual == 0.0


def test_output_adjustments_required_without_data_is_skipped():
    report = audit(_base(_embedded_adjustments()))
    balance = report.accounting.output_balance
    assert balance.status == "SKIPPED"
    assert "required" in balance.reason


def test_complete_output_representation_rejects_supplied_adjustment():
    convention = AccountingConvention.domestic_competitive(
        trade_representation="embedded",
        output_representation="complete",
    )
    report = audit(
        _base(convention, output_adjustments=np.array([1.0, 2.0]))
    )
    assert report.accounting.output_balance.status == "SKIPPED"
    assert "complete" in report.accounting.output_balance.reason


def test_trade_and_labelled_nontrade_output_adjustments_can_coexist():
    adjustments = pd.DataFrame(
        [[0.0, 0.0], [0.0, 0.0]],
        index=["A", "B"],
        columns=["Net Import Duties", "Trade Margin"],
    )
    convention = AccountingConvention.domestic_competitive(
        inflow_sign="positive",
        trade_representation="outflows_in_Y",
        external_flow_scope="international",
        output_representation="adjustments_required",
    )
    io = IOSystem(
        np.array([[1.0, 0.0], [0.0, 2.0]]),
        np.array([10.0, 20.0]),
        ["A", "B"],
        Y=np.array([11.0, 21.0]),
        trade=TradeFlows(international_imports=np.array([2.0, 3.0])),
        output_adjustments=adjustments,
        accounting=convention,
    )
    report = audit(io)
    assert report.accounting.output_balance.status == "PASS"
    assert set(report.accounting.output_balance.uses) == {
        "Y",
        "inflows",
        "output_adjustments",
    }


def test_unlabelled_output_adjustment_with_trade_is_skipped_as_ambiguous():
    convention = AccountingConvention.domestic_competitive(
        inflow_sign="positive",
        trade_representation="outflows_in_Y",
        external_flow_scope="international",
        output_representation="adjustments_required",
    )
    report = audit(
        _base(
            convention,
            output_adjustments=np.zeros(2),
            trade=TradeFlows(international_imports=np.zeros(2)),
        )
    )
    assert report.accounting.output_balance.status == "SKIPPED"
    assert "double-counting" in report.accounting.output_balance.reason


def test_output_adjustment_trade_label_overlap_is_skipped():
    adjustments = pd.DataFrame(
        [[1.0], [2.0]], index=["A", "B"], columns=["Imports"]
    )
    convention = AccountingConvention.domestic_competitive(
        inflow_sign="positive",
        trade_representation="outflows_in_Y",
        external_flow_scope="international",
        output_representation="adjustments_required",
    )
    report = audit(
        _base(
            convention,
            output_adjustments=adjustments,
            trade=TradeFlows(international_imports=np.zeros(2)),
        )
    )
    assert report.accounting.output_balance.status == "SKIPPED"
    assert "overlap" in report.accounting.output_balance.reason


def test_output_adjustment_label_mismatch_is_local_to_supporting_input():
    adjustments = pd.DataFrame(
        [[1.0], [2.0]], index=["B", "A"], columns=["Trade Margin"]
    )
    report = audit(
        _base(_embedded_adjustments(), output_adjustments=adjustments)
    )
    assert report.structure.status == "PASS"
    assert report.structure.supporting_status == "FAIL"
    assert report.accounting.output_balance.status == "SKIPPED"
    assert "do not match sectors" in report.accounting.output_balance.reason


def test_output_adjustment_subtotal_is_detected_and_not_used():
    adjustments = pd.DataFrame(
        [[1.0, 2.0, 3.0], [2.0, 1.0, 3.0]],
        index=["A", "B"],
        columns=["Duties", "Margins", "Total"],
    )
    report = audit(
        _base(_embedded_adjustments(), output_adjustments=adjustments)
    )
    assert report.components.status == "WARNING"
    assert any(
        item["field"] == "output_adjustments"
        for item in report.components.subtotal_candidates
    )
    assert report.accounting.output_balance.status == "SKIPPED"


def test_output_adjustment_is_included_in_input_hash():
    convention = _embedded_adjustments()
    first = audit(_base(convention, output_adjustments=np.array([1.0, 2.0])))
    second = audit(_base(convention, output_adjustments=np.array([1.0, 3.0])))
    assert first.provenance["input_hash"] != second.provenance["input_hash"]
