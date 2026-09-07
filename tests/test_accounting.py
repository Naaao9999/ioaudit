import numpy as np

from ioaudit import AccountingConvention, IOSystem, audit


def test_balanced_input_and_output(normal_io):
    report = audit(normal_io)
    assert report.accounting.status == "AVAILABLE"
    assert report.accounting.max_relative_residual == 0
    assert report.accounting.input_balance.max_absolute_residual == 0
    assert report.accounting.output_balance.max_absolute_residual == 0
    assert report.accounting.convention["import_treatment"] == "competitive"
    assert "imports (imports are signed)" in report.accounting.formula


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
    report = audit(IOSystem(z, x, ["A", "B"], Y=y, V=v, imports=np.zeros(2), accounting=AccountingConvention.domestic_competitive()))
    assert report.accounting.output_balance.max_absolute_residual == 0
    assert report.accounting.input_balance.max_absolute_residual == 0


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
    report = audit(IOSystem(z, x, ["a", "b"], Y=y, V=v, imports=imports, exports=exports, accounting=convention))
    assert report.accounting.import_adjustment_applied is True
    assert report.accounting.imports_used is True
    assert report.accounting.exports_used is True
    assert report.accounting.output_balance.max_absolute_residual == 0
    assert "inflow (international_imports)" in report.accounting.output_balance.equation


def test_competitive_import_accounting_uses_signed_import_row():
    z = np.array([[2.0, 1.0], [1.0, 3.0]])
    x = np.array([8.0, 9.0])
    # Competitive tables use the signed import adjustment: x = Z1 + f + imports.
    y = np.array([6.0, 7.0])
    v = np.array([5.0, 5.0])
    imports = np.array([-1.0, -2.0])
    report = audit(IOSystem(z, x, ["a", "b"], Y=y, V=v, imports=imports, accounting=AccountingConvention.domestic_competitive()))
    assert report.accounting.output_balance.max_absolute_residual == 0
    assert report.accounting.import_adjustment_applied is True
    assert report.accounting.imports_used is True
    assert "imports (imports are signed)" in report.accounting.formula


def test_competitive_positive_import_accounting_subtracts_magnitude():
    z = np.array([[2.0, 1.0], [1.0, 3.0]])
    x = np.array([8.0, 9.0])
    y = np.array([7.0, 6.0])
    v = np.array([5.0, 5.0])
    imports = np.array([2.0, 1.0])
    convention = AccountingConvention(
        transaction_scope="domestic",
        import_treatment="competitive",
        import_sign="positive",
        trade_representation="outflows_in_Y",
        external_flow_scope="international",
        outflow_sign="positive",
    )
    report = audit(IOSystem(z, x, ["a", "b"], Y=y, V=v, imports=imports, accounting=convention))
    assert report.accounting.output_balance.max_absolute_residual == 0
    assert " - imports " in report.accounting.formula


def test_competitive_unknown_import_sign_skips_output_balance():
    report = audit(
        IOSystem(
            np.eye(2),
            np.array([2.0, 2.0]),
            ["a", "b"],
            Y=np.ones(2),
            V=np.ones(2),
            imports=np.ones(2),
            accounting=AccountingConvention(import_sign="unknown"),
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
            imports=np.array([2.0]),
            exports=np.array([0.0]),
            accounting=convention,
        )
    )
    assert convention.inflow_sign == "unknown"
    assert report.accounting.output_balance.status == "SKIPPED"


def test_import_sign_is_not_applicable_for_total_scope():
    report = audit(
        IOSystem(
            np.eye(1),
            np.array([2.0]),
            ["a"],
            Y=np.array([1.0]),
            V=np.array([1.0]),
            imports=np.array([10.0]),
            accounting=AccountingConvention(
                "total",
                "competitive",
                "unknown",
                trade_representation="embedded",
                external_flow_scope="international",
            ),
        )
    )
    assert "import_sign not applicable" in report.accounting.notes


def test_unknown_trade_representation_skips_even_with_total_scope():
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
    assert report.accounting.output_balance.status == "SKIPPED"


def test_noncompetitive_without_import_vectors_skips_adjusted_side():
    report = audit(IOSystem(np.eye(2), np.ones(2), ["a", "b"], Y=np.ones(2), V=np.ones(2), accounting=AccountingConvention("domestic", "noncompetitive")))
    assert report.accounting.output_balance.status == "SKIPPED"
    assert report.accounting.input_balance.status == "PASS"


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
    assert report.accounting.input_balance.status == "PASS"
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
    assert report.accounting.status == "AVAILABLE"
    assert report.accounting.by_sector == []
