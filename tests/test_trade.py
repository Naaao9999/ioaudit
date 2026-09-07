import numpy as np
import pandas as pd

from ioaudit import AccountingConvention, IOSystem, TradeFlows, audit


def _trade_data():
    z = np.eye(2)
    f = np.array([100.0, 100.0])
    v = np.array([99.0, 99.0])
    inflow = np.array([15.0, 27.0])
    outflow = np.array([3.0, 4.0])
    x = np.array([89.0, 78.0])
    convention = AccountingConvention(
        transaction_scope="domestic",
        import_treatment="competitive",
        trade_representation="separate",
        external_flow_scope="both",
        inflow_sign="positive",
        outflow_sign="positive",
    )
    return z, x, f, v, inflow, outflow, convention


def test_split_and_combined_trade_representations_match():
    z, x, f, v, inflow, outflow, convention = _trade_data()
    split = TradeFlows(
        interregional_inflows=np.array([10.0, 20.0]),
        international_imports=np.array([5.0, 7.0]),
        interregional_outflows=np.array([1.0, 2.0]),
        international_exports=np.array([2.0, 2.0]),
    )
    combined = TradeFlows(combined_inflows=inflow, combined_outflows=outflow)
    split_report = audit(IOSystem(z, x, ["a", "b"], Y=f, V=v, trade=split, accounting=convention))
    combined_report = audit(IOSystem(z, x, ["a", "b"], Y=f, V=v, trade=combined, accounting=convention))
    assert split_report.accounting.output_balance.max_relative_residual == 0
    assert combined_report.accounting.output_balance.max_relative_residual == 0
    assert split_report.accounting.output_balance.sector_residual == combined_report.accounting.output_balance.sector_residual


def test_outflows_in_y_uses_only_inflows():
    z, _, f, v, inflow, _, _ = _trade_data()
    x = np.array([86.0, 74.0])
    convention = AccountingConvention(
        transaction_scope="domestic",
        import_treatment="competitive",
        trade_representation="outflows_in_Y",
        external_flow_scope="both",
        inflow_sign="positive",
    )
    report = audit(IOSystem(z, x, ["a", "b"], Y=f, V=v, trade=TradeFlows(combined_inflows=inflow), accounting=convention))
    assert report.accounting.output_balance.max_relative_residual == 0
    assert report.accounting.outflows_used is False


def test_unknown_trade_representation_skips_output_balance():
    report = audit(
        IOSystem(
            np.eye(1),
            np.array([2.0]),
            ["a"],
            Y=np.array([1.0]),
            V=np.array([1.0]),
            trade=TradeFlows(combined_inflows=np.array([1.0]), combined_outflows=np.array([1.0])),
            accounting=AccountingConvention(trade_representation="unknown"),
        )
    )
    assert report.accounting.output_balance.status == "SKIPPED"


def test_combined_and_split_trade_is_not_double_counted():
    trade = TradeFlows(combined_inflows=np.array([2.0]), international_imports=np.array([2.0]))
    report = audit(
        IOSystem(
            np.eye(1),
            np.array([1.0]),
            ["a"],
            Y=np.array([1.0]),
            V=np.array([0.0]),
            trade=trade,
            accounting=AccountingConvention(trade_representation="outflows_in_Y", inflow_sign="positive"),
        )
    )
    assert report.structure.trade_representation_conflicts == ["inflows"]
    assert report.accounting.output_balance.status == "SKIPPED"
    assert report.passed() is False


def test_combined_split_conflict_is_checked_even_when_scope_uses_other_component():
    report = audit(
        IOSystem(
            np.eye(1),
            np.array([1.0]),
            ["a"],
            Y=np.array([1.0]),
            trade=TradeFlows(
                combined_inflows=np.array([2.0]),
                interregional_inflows=np.array([2.0]),
            ),
            accounting=AccountingConvention(
                trade_representation="outflows_in_Y",
                external_flow_scope="international",
                inflow_sign="positive",
            ),
        )
    )
    assert report.structure.trade_representation_conflicts == ["inflows"]
    assert report.accounting.output_balance.status == "SKIPPED"


def test_trade_source_legacy_conflict_is_reported():
    report = audit(
        IOSystem(
            np.eye(1),
            np.array([1.0]),
            ["a"],
            Y=np.array([1.0]),
            V=np.array([0.0]),
            imports=np.array([0.0]),
            trade=TradeFlows(combined_inflows=np.array([0.0])),
            accounting=AccountingConvention(),
        )
    )
    assert report.structure.status == "FAIL"
    assert report.accounting.output_balance.status == "SKIPPED"


def test_total_label_is_reported_without_removal():
    z = pd.DataFrame(
        [[1.0, 2.0, 3.0], [4.0, 5.0, 9.0], [5.0, 7.0, 12.0]],
        index=["A", "B", "合計"],
        columns=["A", "B", "合計"],
    )
    report = audit(IOSystem(z, np.ones(3), ["A", "B", "合計"]))
    assert report.structure.possible_total_rows[0]["label_evidence"] is True
    assert report.structure.possible_total_columns[0]["label_evidence"] is True
    assert report.structure.status == "PASS"
