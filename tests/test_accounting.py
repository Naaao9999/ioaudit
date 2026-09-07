import numpy as np
import pandas as pd

from ioaudit import AccountingConvention, IOSystem, TradeFlows, audit


def test_balanced_input_and_output(normal_io):
    report = audit(normal_io)
    assert report.accounting.status == "PASS"
    assert report.accounting.max_relative_residual == 0
    assert report.accounting.input_balance.max_absolute_residual == 0
    assert report.accounting.output_balance.max_absolute_residual == 0
    assert report.accounting.convention["import_treatment"] == "competitive"
    assert "inflow (signed)" in report.accounting.formula


def test_imbalance_and_conventions():
    z = np.eye(2)
    y = np.ones((2, 2))
    v = np.ones((2, 2))
    for treatment in ("competitive", "noncompetitive", "none"):
        report = audit(IOSystem(z, np.array([4.0, 4.0]), ["a", "b"], Y=y, V=v, accounting=AccountingConvention(transaction_scope="domestic", import_treatment=treatment, trade_representation="embedded")))
        assert report.accounting.status == "AVAILABLE"
        assert report.accounting.convention["import_treatment"] == treatment
        assert report.accounting.max_relative_residual > 0


def test_multidimensional_y_and_v(normal_io):
    z, x = normal_io.Z, normal_io.x
    y = np.array([[2.0, 3.0], [2.0, 3.0]])
    v = np.array([[2.0, 2.0], [3.0, 3.0]])
    report = audit(
        IOSystem(
            z,
            x,
            ["A", "B"],
            Y=y,
            V=v,
            trade=TradeFlows(international_imports=np.zeros(2)),
            accounting=AccountingConvention.domestic_competitive(
                inflow_sign="negative",
                trade_representation="outflows_in_Y",
                external_flow_scope="international",
                outflow_sign="positive",
                input_representation="complete",
            ),
        )
    )
    assert report.accounting.output_balance.max_absolute_residual == 0
    assert report.accounting.input_balance.max_absolute_residual == 0


def test_dataframe_input_adjustment_columns_must_match_sector_order(normal_io):
    adjustment = pd.DataFrame(
        [[1.0, 3.0], [0.0, 0.0]],
        index=["external", "tax"],
        columns=["B", "A"],
    )
    report = audit(
        IOSystem(
            normal_io.Z,
            normal_io.x,
            normal_io.sectors,
            Y=normal_io.Y,
            V=normal_io.V,
            input_adjustments=adjustment,
            accounting=AccountingConvention.domestic_competitive(
                input_representation="adjustments_required"
            ),
        )
    )
    assert report.structure.input_adjustment_labels_match is False
    assert report.structure.normalized_input_adjustment_labels_match is False
    assert report.accounting.input_balance.status == "SKIPPED"
    assert "columns do not match sectors in order" in report.accounting.input_balance.reason


def test_dataframe_input_adjustment_normalized_columns_are_used_with_warning(normal_io):
    adjustment = pd.DataFrame(
        [[0.0, 0.0], [0.0, 0.0]],
        index=["external", "tax"],
        columns=["A ", "B"],
    )
    report = audit(
        IOSystem(
            normal_io.Z,
            normal_io.x,
            normal_io.sectors,
            Y=normal_io.Y,
            V=normal_io.V,
            input_adjustments=adjustment,
            accounting=AccountingConvention.domestic_competitive(
                input_representation="adjustments_required"
            ),
        )
    )
    assert report.structure.input_adjustment_labels_match is False
    assert report.structure.normalized_input_adjustment_labels_match is True
    assert report.accounting.input_balance.status == "PASS"
    assert any("normalization" in note for note in report.accounting.notes)


def test_noncompetitive_import_accounting_uses_explicit_vectors():
    z = np.array([[2.0, 1.0], [1.0, 3.0]])
    x = np.array([8.0, 9.0])
    # x + imports = row_sum(Z) + f + exports
    y = np.array([6.0, 6.0])
    v = np.array([5.0, 5.0])
    imports = np.array([1.0, 2.0])
    exports = np.array([0.0, 1.0])
    convention = AccountingConvention(
        transaction_scope="domestic",
        import_treatment="noncompetitive",
        trade_representation="separate",
        external_flow_scope="international",
        inflow_sign="positive",
        outflow_sign="positive",
    )
    report = audit(
        IOSystem(
            z,
            x,
            ["a", "b"],
            Y=y,
            V=v,
            trade=TradeFlows(
                international_imports=imports,
                international_exports=exports,
            ),
            accounting=convention,
        )
    )
    assert set(report.accounting.output_balance.uses) == {
        "Y",
        "inflows",
        "outflows",
    }
    assert report.accounting.output_balance.max_absolute_residual == 0
    assert "inflow (international_imports)" in report.accounting.output_balance.equation


def test_competitive_import_accounting_uses_signed_import_row():
    z = np.array([[2.0, 1.0], [1.0, 3.0]])
    x = np.array([8.0, 9.0])
    # Competitive tables use the signed import adjustment: x = Z1 + f + imports.
    y = np.array([6.0, 7.0])
    v = np.array([5.0, 5.0])
    imports = np.array([-1.0, -2.0])
    report = audit(
        IOSystem(
            z,
            x,
            ["a", "b"],
            Y=y,
            V=v,
            trade=TradeFlows(international_imports=imports),
            accounting=AccountingConvention.domestic_competitive(
                inflow_sign="negative",
                trade_representation="outflows_in_Y",
                external_flow_scope="international",
                outflow_sign="positive",
                input_representation="complete",
            ),
        )
    )
    assert report.accounting.output_balance.max_absolute_residual == 0
    assert set(report.accounting.output_balance.uses) == {"Y", "inflows"}
    assert "inflow (signed)" in report.accounting.formula


def test_competitive_positive_import_accounting_subtracts_magnitude():
    z = np.array([[2.0, 1.0], [1.0, 3.0]])
    x = np.array([8.0, 9.0])
    y = np.array([7.0, 6.0])
    v = np.array([5.0, 5.0])
    imports = np.array([2.0, 1.0])
    convention = AccountingConvention(
        transaction_scope="domestic",
        import_treatment="competitive",
        inflow_sign="positive",
        trade_representation="outflows_in_Y",
        external_flow_scope="international",
        outflow_sign="positive",
    )
    report = audit(
        IOSystem(
            z,
            x,
            ["a", "b"],
            Y=y,
            V=v,
            trade=TradeFlows(international_imports=imports),
            accounting=convention,
        )
    )
    assert report.accounting.output_balance.max_absolute_residual == 0
    assert " - inflow " in report.accounting.formula


def test_competitive_unknown_import_sign_skips_output_balance():
    report = audit(
        IOSystem(
            np.eye(2),
            np.array([2.0, 2.0]),
            ["a", "b"],
            Y=np.ones(2),
            V=np.ones(2),
            trade=TradeFlows(international_imports=np.ones(2)),
            accounting=AccountingConvention(inflow_sign="unknown"),
        )
    )
    assert report.accounting.output_balance.status == "SKIPPED"
    assert report.accounting.output_balance.reason
    assert "unknown" in report.accounting.formula


def test_explicit_generalized_unknown_inflow_sign_is_not_overridden():
    convention = AccountingConvention(
        import_treatment="noncompetitive",
        trade_representation="outflows_in_Y",
        inflow_sign="unknown",
    )
    report = audit(
        IOSystem(
            np.array([[1.0]]),
            np.array([6.0]),
            ["a"],
            Y=np.array([6.0]),
            trade=TradeFlows(
                international_imports=np.array([2.0]),
                international_exports=np.array([0.0]),
            ),
            accounting=convention,
        )
    )
    assert convention.inflow_sign == "unknown"
    assert report.accounting.output_balance.status == "SKIPPED"


def test_total_transactions_rejects_non_embedded_trade_representation():
    report = audit(
        IOSystem(
            np.array([[1.0]]),
            np.array([5.0]),
            ["A"],
            Y=np.array([4.0]),
            trade=TradeFlows(
                combined_inflows=np.array([1.0]),
                combined_outflows=np.array([1.0]),
            ),
            accounting=AccountingConvention(
                transaction_scope="total",
                import_treatment="none",
                trade_representation="separate",
                external_flow_scope="international",
                inflow_sign="positive",
                outflow_sign="positive",
            ),
        )
    )
    assert report.accounting.output_balance.status == "SKIPPED"
    assert "does not support explicitly declared" in report.accounting.formula


def test_inflow_sign_is_not_applicable_for_total_scope():
    report = audit(
        IOSystem(
            np.eye(1),
            np.array([2.0]),
            ["a"],
            Y=np.array([1.0]),
            V=np.array([1.0]),
            accounting=AccountingConvention(
                "total",
                "competitive",
                trade_representation="embedded",
                external_flow_scope="international",
            ),
        )
    )
    assert "inflow_sign not applicable" in report.accounting.notes


def test_total_scope_does_not_require_trade_representation():
    report = audit(
        IOSystem(
            np.array([[1.0]]),
            np.array([3.0]),
            ["a"],
            Y=np.array([2.0]),
            accounting=AccountingConvention(
                transaction_scope="total", trade_representation="unknown"
            ),
        )
    )
    assert report.accounting.output_balance.status == "PASS"


def test_noncompetitive_without_import_vectors_skips_adjusted_side():
    report = audit(
        IOSystem(
            np.eye(2),
            np.ones(2),
            ["a", "b"],
            Y=np.ones(2),
            V=np.ones(2),
            accounting=AccountingConvention(
                "domestic", "noncompetitive", input_representation="complete"
            ),
        )
    )
    assert report.accounting.output_balance.status == "SKIPPED"
    assert report.accounting.input_balance.status == "AVAILABLE"


def test_missing_convention_skips_accounting(normal_io):
    io = IOSystem(normal_io.Z, normal_io.x, normal_io.sectors, Y=normal_io.Y, V=normal_io.V)
    report = audit(io)
    assert report.accounting.status == "SKIPPED"


def test_plain_convention_skips_semantically_ambiguous_output_check():
    report = audit(
        IOSystem(
            np.eye(2),
            np.array([2.0, 2.0]),
            ["a", "b"],
            Y=np.ones(2),
            V=np.ones(2),
            accounting=AccountingConvention(),
        )
    )
    assert report.accounting.input_balance.status == "SKIPPED"
    assert report.accounting.output_balance.status == "SKIPPED"
    assert "unknown" in report.accounting.output_balance.reason


def test_sector_count_mismatch_does_not_raise():
    io = IOSystem(
        np.eye(2),
        np.ones(2),
        ["a", "b", "extra"],
        V=np.ones(2),
        accounting=AccountingConvention(),
    )
    report = audit(io)
    assert report.structure.status == "FAIL"
    assert report.accounting.status == "SKIPPED"
    assert report.accounting.by_sector == []


def test_input_adjustments_are_required_and_aggregated_by_user():
    z = np.array([[2.0, 1.0], [1.0, 3.0]])
    x = np.array([8.0, 9.0])
    v = np.array([2.0, 3.0])
    external_inputs = np.array([[1.0, 2.0], [2.0, 0.0]])
    convention = AccountingConvention.domestic_competitive(
        trade_representation="embedded",
        input_representation="adjustments_required",
    )
    report = audit(
        IOSystem(
            z,
            x,
            ["a", "b"],
            Y=np.array([5.0, 5.0]),
            V=v,
            input_adjustments=external_inputs,
            accounting=convention,
        )
    )
    assert report.accounting.input_balance.status == "PASS"
    assert set(report.accounting.input_balance.uses) == {"V", "input_adjustments"}
    assert report.accounting.input_balance.equation.endswith("+ input_adjustment")


def test_input_adjustments_required_without_data_is_skipped():
    convention = AccountingConvention.domestic_competitive(
        trade_representation="embedded",
        input_representation="adjustments_required",
    )
    report = audit(
        IOSystem(
            np.eye(2),
            np.array([2.0, 2.0]),
            ["a", "b"],
            Y=np.ones(2),
            V=np.ones(2),
            accounting=convention,
        )
    )
    assert report.accounting.input_balance.status == "SKIPPED"
    assert "adjustment" in report.accounting.input_balance.reason


def test_two_input_adjustment_representations_are_not_added_together():
    convention = AccountingConvention.domestic_competitive(
        trade_representation="embedded",
        input_representation="complete",
    )
    report = audit(
        IOSystem(
            np.eye(1),
            np.array([3.0]),
            ["a"],
            Y=np.array([2.0]),
            V=np.array([2.0]),
            input_adjustments=np.array([1.0]),
            accounting=convention,
        )
    )
    assert report.accounting.input_balance.status == "SKIPPED"
    assert "complete" in report.accounting.input_balance.reason


def test_nonfinite_accounting_residual_is_a_failure():
    report = audit(
        IOSystem(
            np.zeros((1, 1)),
            np.array([1.0]),
            ["a"],
            Y=np.array([[1.0e308, 1.0e308]]),
            accounting=AccountingConvention.domestic_competitive(
                trade_representation="embedded"
            ),
        )
    )
    assert report.accounting.output_balance.status == "FAIL"
    assert report.accounting.output_balance.residual_class == "nonfinite"
    assert report.passed() is False
    assert report.scale.reason == "scale diagnostics require finite accounting residuals"


def test_none_import_treatment_does_not_ignore_separate_trade_declaration():
    report = audit(
        IOSystem(
            np.array([[1.0]]),
            np.array([5.0]),
            ["a"],
            Y=np.array([4.0]),
            trade=TradeFlows(
                international_imports=np.array([1.0]),
                international_exports=np.array([3.0]),
            ),
            accounting=AccountingConvention(
                transaction_scope="domestic",
                import_treatment="none",
                trade_representation="separate",
                external_flow_scope="international",
                inflow_sign="positive",
                outflow_sign="positive",
            ),
        )
    )
    assert report.accounting.output_balance.status == "SKIPPED"
    assert report.accounting.output_balance.uses == ()
    assert "incompatible" in report.accounting.output_balance.reason
    assert "does not support explicitly declared" in report.accounting.formula


def test_explicit_zero_tolerance_takes_precedence_over_machine_precision():
    report = audit(
        IOSystem(
            np.zeros((1, 1)),
            np.array([1.0]),
            ["a"],
            Y=np.array([np.nextafter(1.0, 0.0)]),
            accounting=AccountingConvention.domestic_competitive(
                trade_representation="embedded"
            ),
        ),
        accounting_tolerance={
            "absolute": 0.0,
            "relative": 0.0,
            "rounding_unit": 0.0,
        },
    )
    assert report.accounting.output_balance.status == "FAIL"
    assert report.accounting.output_balance.residual_class == "outside_tolerance"
