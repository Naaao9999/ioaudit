import numpy as np
import pandas as pd
import pytest

from ioaudit import AccountingConvention, IOSystem, TradeFlows, audit
from ioaudit.exceptions import IOValidationError


def test_model_copies_inputs(normal_data):
    z, x, sectors, y, v, convention = normal_data
    io = IOSystem(z, x, sectors, y, v, accounting=convention)
    z[0, 0] = 999
    x[0] = 999
    assert io.Z[0, 0] == 2
    assert io.x[0] == 8


def test_model_deep_copies_nested_sequence_inputs():
    source = [[1.0, 2.0], [3.0, 4.0]]
    io = IOSystem(source, [5.0, 6.0], ["A", "B"])
    source[0][0] = 999.0
    assert io.Z[0][0] == 1.0


def test_model_deep_copies_nested_metadata():
    metadata = {"source": {"name": "table"}, "tags": ["official"]}
    io = IOSystem(
        np.eye(2),
        np.ones(2),
        ["A", "B"],
        metadata=metadata,
    )
    metadata["source"]["name"] = "changed"
    metadata["tags"].append("changed")
    assert io.metadata == {"source": {"name": "table"}, "tags": ["official"]}


def test_country_sector_tuple_identifiers_are_supported():
    sectors = [("JPN", "Agriculture"), ("CHN", "Agriculture")]
    z = np.array([[1.0, 0.2], [0.1, 2.0]])
    x = np.array([2.0, 3.0])
    io = IOSystem(
        pd.DataFrame(z, index=sectors, columns=sectors),
        pd.Series(x, index=sectors),
        sectors,
        Y=pd.DataFrame([[0.8], [0.9]], index=sectors, columns=["final demand"]),
        V=pd.DataFrame([[0.9, 0.8]], index=["value added"], columns=sectors),
        accounting=AccountingConvention(
            transaction_scope="domestic",
            import_treatment="none",
            trade_representation="embedded",
            input_representation="complete",
        ),
    )
    report = audit(io)
    assert report.structure.status == "PASS"
    assert report.structure.z_row_labels_match_sectors is True
    assert report.structure.z_column_labels_match_sectors is True
    assert report.structure.x_labels_match is True
    assert report.coefficients.status == "PASS"


def test_tradeflows_and_audit_do_not_mutate_source_arrays(normal_data):
    from ioaudit import audit

    z, x, sectors, y, v, convention = normal_data
    imports = np.array([-1.0, 0.0])
    z_before = z.copy()
    x_before = x.copy()
    y_before = y.copy()
    v_before = v.copy()
    imports_before = imports.copy()
    io = IOSystem(
        z,
        x,
        sectors,
        y,
        v,
        trade=TradeFlows(international_imports=imports),
        accounting=convention,
    )
    audit(io)
    np.testing.assert_array_equal(z, z_before)
    np.testing.assert_array_equal(x, x_before)
    np.testing.assert_array_equal(y, y_before)
    np.testing.assert_array_equal(v, v_before)
    np.testing.assert_array_equal(imports, imports_before)


def test_convention_validation():
    with pytest.raises(IOValidationError):
        AccountingConvention(transaction_scope="unsupported")
    with pytest.raises(IOValidationError):
        IOSystem(np.eye(2), np.ones(2), ["a", "b"], accounting="domestic")
    with pytest.raises(TypeError):
        AccountingConvention(import_sign="signed")


def test_convention_serializes_inflow_sign():
    convention = AccountingConvention(inflow_sign="positive")
    assert convention.to_dict()["inflow_sign"] == "positive"


def test_plain_convention_is_conservative_and_structural_presets_are_explicit():
    plain = AccountingConvention()
    assert plain.transaction_scope == "unknown"
    assert plain.import_treatment == "unknown"
    assert plain.trade_representation == "unknown"
    assert plain.external_flow_scope == "unknown"
    assert plain.inflow_sign == "unknown"
    assert plain.outflow_sign == "unknown"
    assert plain.input_representation == "unknown"

    competitive = AccountingConvention.domestic_competitive()
    assert competitive.transaction_scope == "domestic"
    assert competitive.import_treatment == "competitive"
    assert competitive.trade_representation == "unknown"
    assert competitive.external_flow_scope == "unknown"
    assert competitive.inflow_sign == "unknown"
    assert competitive.outflow_sign == "unknown"
    assert competitive.input_representation == "unknown"

    noncompetitive = AccountingConvention.domestic_noncompetitive()
    assert noncompetitive.transaction_scope == "domestic"
    assert noncompetitive.import_treatment == "noncompetitive"
    assert noncompetitive.trade_representation == "unknown"
    assert noncompetitive.external_flow_scope == "unknown"
    assert noncompetitive.inflow_sign == "unknown"
    assert noncompetitive.outflow_sign == "unknown"
    assert noncompetitive.input_representation == "unknown"

    total = AccountingConvention.total_transactions()
    assert total.transaction_scope == "total"
    assert total.import_treatment == "none"
    assert total.trade_representation == "embedded"


def test_structural_preset_without_semantic_fields_skips_affected_accounting():
    from ioaudit import audit

    report = audit(
        IOSystem(
            np.array([[0.1]]),
            np.array([1.0]),
            ["A"],
            Y=np.array([0.9]),
            V=np.array([0.9]),
            accounting=AccountingConvention.domestic_competitive(),
        )
    )
    assert report.accounting.output_balance.status == "SKIPPED"
    assert report.accounting.input_balance.status == "SKIPPED"
