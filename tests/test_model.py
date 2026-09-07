import numpy as np
import pytest

from ioaudit import AccountingConvention, IOSystem
from ioaudit.exceptions import IOValidationError


def test_model_copies_inputs(normal_data):
    z, x, sectors, y, v, convention = normal_data
    io = IOSystem(z, x, sectors, y, v, accounting=convention)
    z[0, 0] = 999
    x[0] = 999
    assert io.Z[0, 0] == 2
    assert io.x[0] == 8


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
        imports=imports,
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
    with pytest.raises(IOValidationError):
        AccountingConvention(import_sign="signed")


def test_convention_serializes_import_sign():
    convention = AccountingConvention(import_sign="positive")
    assert convention.to_dict()["import_sign"] == "positive"


def test_plain_convention_is_conservative_and_japan_preset_is_explicit():
    plain = AccountingConvention()
    assert plain.transaction_scope == "unknown"
    assert plain.import_treatment == "unknown"
    assert plain.trade_representation == "unknown"
    assert plain.external_flow_scope == "unknown"
    assert plain.inflow_sign == "unknown"
    assert plain.outflow_sign == "unknown"

    japan = AccountingConvention.japan_competitive()
    assert japan.transaction_scope == "domestic"
    assert japan.import_treatment == "competitive"
    assert japan.trade_representation == "outflows_in_Y"
    assert japan.external_flow_scope == "international"
    assert japan.inflow_sign == "negative"
    assert japan.outflow_sign == "positive"
