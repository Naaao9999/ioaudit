import numpy as np

from ioaudit import AccountingConvention, IOSystem, TradeFlows, audit


def test_negative_signed_entries_are_informational():
    io = IOSystem(
        [[-1.0, 0.0], [0.0, 1.0]],
        np.array([1.0, 1.0]),
        ["a", "b"],
        Y=np.array([[-1.0], [1.0]]),
        V=np.array([[-1.0, 1.0]]),
        trade=TradeFlows(
            international_imports=np.array([-2.0, 0.0]),
            international_exports=np.array([-3.0, 0.0]),
        ),
        accounting=AccountingConvention(),
    )
    report = audit(io)
    assert report.signs.negative_transaction_cells.count == 1
    assert report.signs.negative_final_demand.count == 1
    assert report.signs.negative_value_added.count == 1
    assert report.signs.negative_inflows.count == 1
    assert report.signs.negative_outflows.count == 1
    assert report.signs.status == "AVAILABLE"


def test_negative_tradeflows_are_reported_and_list_y_is_safe():
    report = audit(
        IOSystem(
            [[1.0]],
            np.array([1.0]),
            ["a"],
            Y=[1.0],
            trade=TradeFlows(
                combined_inflows=np.array([-2.0]),
                combined_outflows=np.array([-3.0]),
            ),
        )
    )
    assert report.signs.negative_inflows.count == 1
    assert report.signs.negative_outflows.count == 1
