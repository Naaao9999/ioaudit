"""Fault injection: simulate extraction mistakes in an independently balanced IO table.

These tests distinguish diagnostic evidence, a configured pipeline gate, and
mistakes that accounting identities alone cannot identify.
"""

import copy
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from ioaudit import AccountingConvention, IOSystem, TradeFlows, audit


TOLERANCE = {"absolute": .01}


def _table(*, trade=False, references=True):
    sectors = ["agriculture", "manufacturing", "transport", "services"]
    z = np.array([[12., 3., 5., 1.], [2., 18., 4., 6.],
                  [7., 1., 14., 2.], [3., 8., 2., 20.]])
    x = np.array([80., 100., 90., 120.])
    f = x - z.sum(axis=1)
    v = x - z.sum(axis=0)
    options = {}
    convention = AccountingConvention(transaction_scope="domestic",
        import_treatment="competitive", trade_representation="embedded",
        input_representation="complete")
    if trade:
        inflow = np.array([6., 7., 3., 5.])
        outflow = np.array([10., 12., 7., 9.])
        adjustment = np.array([3., 5., 2., 4.])
        f = f - outflow + inflow
        v = v - adjustment
        convention = replace(convention, trade_representation="separate",
            external_flow_scope="both", inflow_sign="positive", outflow_sign="positive",
            input_representation="adjustments_required")
        options = dict(trade=TradeFlows(
            combined_inflows=pd.Series(inflow, index=sectors),
            combined_outflows=pd.Series(outflow, index=sectors)),
            input_adjustments=pd.Series(adjustment, index=sectors))
    if references:
        a = z / x
        options.update(A_reference=pd.DataFrame(a, index=sectors, columns=sectors),
            L_reference=pd.DataFrame(np.linalg.inv(np.eye(4)-a), index=sectors, columns=sectors))
    return IOSystem(pd.DataFrame(z, index=sectors, columns=sectors),
        pd.Series(x, index=sectors), sectors,
        Y=pd.DataFrame(np.column_stack([f*.55, f*.3, f*.15]), index=sectors,
                       columns=["Households", "Government", "Investment"]),
        V=pd.DataFrame(np.vstack([v*.65, v*.35]), columns=sectors,
                       index=["Compensation", "Surplus"]),
        accounting=convention, **options)


def _run(io):
    before = copy.deepcopy(io)
    r = audit(io, accounting_tolerance=TOLERANCE)
    # Faults are deliberately left in place for the caller to investigate.
    for name in ("Z", "x", "Y", "V", "input_adjustments", "A_reference", "L_reference"):
        value, old = getattr(io, name), getattr(before, name)
        if isinstance(value, pd.DataFrame):
            pd.testing.assert_frame_equal(value, old)
        elif isinstance(value, pd.Series):
            pd.testing.assert_series_equal(value, old)
        elif value is not None:
            np.testing.assert_array_equal(value, old)
    return r


def _strict_gate(r):
    return r.passed(require_complete=True, fail_on_invalid_reference=True,
                    thresholds={"reference.A.relative_difference": 1e-8,
                                "reference.L.relative_difference": 1e-8})


@pytest.mark.parametrize("trade", [False, True])
def test_control_table_passes(trade):
    r = _run(_table(trade=trade))
    assert r.accounting.input_balance.status == "PASS"
    assert r.accounting.output_balance.status == "PASS"
    assert r.scale.total_candidates == 0
    assert _strict_gate(r)


@pytest.mark.parametrize("field", ["Z_rows", "Z_columns", "x", "Y", "V", "adjustments", "trade"])
def test_wrong_label_order_is_not_used_positionally(field):
    io = _table(trade=True)
    if field == "Z_rows": io.Z = io.Z.iloc[::-1]
    elif field == "Z_columns": io.Z = io.Z.iloc[:, ::-1]
    elif field == "x": io.x = io.x.iloc[::-1]
    elif field == "Y": io.Y = io.Y.iloc[::-1]
    elif field == "V": io.V = io.V.iloc[:, ::-1]
    elif field == "adjustments": io.input_adjustments = io.input_adjustments.iloc[::-1]
    else:
        io.trade = replace(io.trade, combined_inflows=io.trade.combined_inflows.iloc[::-1])
    r = _run(io)
    if field in {"Z_rows", "Z_columns", "x"}:
        assert r.coefficients.status == r.stability.status == "SKIPPED"
    elif field in {"Y", "trade"}:
        assert r.accounting.output_balance.status == "SKIPPED"
        assert r.accounting.input_balance.status == "PASS"
    else:
        assert r.accounting.input_balance.status == "SKIPPED"
        assert r.accounting.output_balance.status == "PASS"
    assert not _strict_gate(r)


@pytest.mark.parametrize("fault", ["extra_row", "extra_column", "NaN", "Inf", "text", "zero_output"])
@pytest.mark.filterwarnings("error::RuntimeWarning")
def test_wrong_range_or_numeric_reading_rejects_downstream_calculation(fault):
    io = _table()
    if fault == "extra_row": io.Z.loc["Total"] = io.Z.sum(axis=0)
    elif fault == "extra_column": io.Z["Total"] = io.Z.sum(axis=1)
    elif fault == "zero_output": io.x.iloc[1] = 0.
    else:
        io.Z = io.Z.astype(object)
        io.Z.iloc[0, 1] = {"NaN": np.nan, "Inf": np.inf, "text": "1,234"}[fault]
    r = _run(io)
    assert r.coefficients.status == "SKIPPED"
    assert r.stability.status == "SKIPPED"
    assert not _strict_gate(r)


@pytest.mark.parametrize("field", ["Y", "V"])
def test_rounded_total_included_with_components_skips_only_affected_side(field):
    io = _table()
    if field == "Y": io.Y["Total"] = io.Y.sum(axis=1) + .001
    else: io.V.loc["Total"] = io.V.sum(axis=0) + .001
    r = _run(io)
    assert r.components.double_count_risk
    affected = r.accounting.output_balance if field == "Y" else r.accounting.input_balance
    other = r.accounting.input_balance if field == "Y" else r.accounting.output_balance
    assert affected.status == "SKIPPED"
    assert other.status == "PASS"
    assert not _strict_gate(r)


@pytest.mark.parametrize("fault", ["transpose", "shift_x_without_labels", "swap_Y_V", "A_as_Z", "L_as_Z"])
def test_shape_correct_but_wrong_extraction_has_accounting_or_reference_evidence(fault):
    io = _table()
    if fault == "transpose": io.Z = io.Z.T
    elif fault == "shift_x_without_labels": io.x = np.roll(io.x.to_numpy(), 1)
    elif fault == "swap_Y_V": io.Y, io.V = io.V.T, io.Y.T
    elif fault == "A_as_Z": io.Z = io.A_reference.copy()
    else: io.Z = io.L_reference.copy()
    r = _run(io)
    if fault == "transpose": assert r.orientation.possible_transpose is True
    assert (r.accounting.input_balance.status == "FAIL"
            or r.accounting.output_balance.status == "FAIL")
    assert not _strict_gate(r)


@pytest.mark.parametrize("field", ["x", "Y", "V", "Z_row", "Z_column", "Z_cell"])
def test_power_of_ten_misread_produces_matching_scale_candidate(field):
    io = _table()
    if field in {"x", "Y", "V"}: setattr(io, field, getattr(io, field) * 1000.)
    elif field == "Z_row": io.Z.iloc[1, :] *= 1000.
    elif field == "Z_column": io.Z.iloc[:, 1] *= 1000.
    else: io.Z.iloc[1, 2] *= 1000.
    r = _run(io)
    if field in {"x", "Y", "V"}:
        candidates = [c for c in r.scale.possible_global_scale_mismatches if c["field"] == field]
    elif field == "Z_row":
        candidates = [c for c in r.scale.possible_row_scale_errors if c["index"] == 1]
    elif field == "Z_column":
        candidates = [c for c in r.scale.possible_column_scale_errors if c["index"] == 1]
    else:
        candidates = [c for c in r.scale.possible_cell_scale_errors
                      if c["row_index"] == 1 and c["column_index"] == 2]
    assert any(c["candidate_factor"] == .001 for c in candidates)
    assert not _strict_gate(r)


@pytest.mark.parametrize("fault", ["wrong_inflow_sign", "wrong_Y_representation", "missing_adjustments", "unknown_convention"])
def test_semantic_misread_cannot_pass_complete_gate(fault):
    io = _table(trade=True)
    if fault == "wrong_inflow_sign": io.accounting = replace(io.accounting, inflow_sign="negative")
    elif fault == "wrong_Y_representation": io.accounting = replace(io.accounting, trade_representation="embedded")
    elif fault == "missing_adjustments": io.input_adjustments = None
    else: io.accounting = AccountingConvention()
    r = _run(io)
    assert not _strict_gate(r)
    assert any(s.status in {"FAIL", "SKIPPED"} for s in
               (r.accounting.input_balance, r.accounting.output_balance))


def test_accounting_preserving_cell_errors_need_independent_reference():
    io = _table()
    io.Z.iloc[:2, :2] += np.array([[1., -1.], [-1., 1.]])
    r = _run(io)
    assert r.accounting.input_balance.status == r.accounting.output_balance.status == "PASS"
    assert r.reference.A.relative_difference > 1e-8
    assert not _strict_gate(r)
    # Numeric differences are information until the caller sets a threshold.
    assert r.passed(require_complete=True)


def test_uniform_unit_mislabel_cannot_be_identified_from_identities_or_coefficients():
    io = _table()
    for field in ("Z", "x", "Y", "V"):
        setattr(io, field, getattr(io, field) * 1000.)
    r = _run(io)
    assert r.scale.total_candidates == 0
    assert _strict_gate(r)


def test_missing_all_accounting_information_is_indeterminate_and_needs_complete_gate():
    io = _table(references=False)
    io.Y = io.V = io.accounting = None
    r = _run(io)
    assert r.orientation.possible_transpose is None
    assert r.passed()
    assert not r.passed(require_complete=True)
