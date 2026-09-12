"""Regression tests for numeric and semantic boundary cases."""

from __future__ import annotations

import warnings

import numpy as np
import pytest
from scipy import sparse

from ioaudit import AccountingConvention, IOSystem, TradeFlows, audit
from ioaudit.exceptions import IOValidationError


def test_longdouble_inputs_do_not_break_provenance():
    io = IOSystem(
        np.array([[1.0]], dtype=np.longdouble),
        np.array([2.0], dtype=np.longdouble),
        ["A"],
    )

    report = audit(io)

    assert report.provenance["input_hash"]


def test_empty_table_is_not_a_successful_complete_audit():
    report = audit(
        IOSystem(
            np.empty((0, 0)),
            np.empty(0),
            [],
            Y=np.empty((0, 2)),
        )
    )

    assert report.structure.status == "FAIL"
    assert report.coefficients.status == "SKIPPED"
    assert report.stability.status == "SKIPPED"
    assert report.passed(require_complete=True) is False


def test_combined_trade_requires_both_external_flow_scope():
    report = audit(
        IOSystem(
            np.array([[1.0]]),
            np.array([2.0]),
            ["A"],
            Y=np.array([1.0]),
            trade=TradeFlows(combined_inflows=np.array([1.0])),
            accounting=AccountingConvention(
                transaction_scope="domestic",
                import_treatment="competitive",
                trade_representation="outflows_in_Y",
                external_flow_scope="international",
                inflow_sign="positive",
            ),
        )
    )

    assert report.accounting.output_balance.status == "SKIPPED"
    assert "combined interregional and international" in (
        report.accounting.output_balance.reason or ""
    )


def test_sparse_duplicate_entries_are_cancelled_before_sign_and_coefficient_checks():
    z = sparse.csr_matrix(
        (
            np.array([1.0, -1.0]),
            np.array([0, 0]),
            np.array([0, 2]),
        ),
        shape=(1, 1),
    )
    report = audit(IOSystem(z, np.array([1.0]), ["A"]))

    assert report.coefficients.status == "PASS"
    assert report.coefficients.zero_output_mask == [False]
    assert report.signs.negative_transaction_cells.count == 0


def test_trade_overflow_is_reported_without_runtime_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        report = audit(
            IOSystem(
                np.array([[1.0]]),
                np.array([1.0]),
                ["A"],
                Y=np.array([0.0]),
                trade=TradeFlows(
                    interregional_inflows=np.array([1e308]),
                    international_imports=np.array([1e308]),
                ),
                accounting=AccountingConvention(
                    transaction_scope="domestic",
                    import_treatment="competitive",
                    trade_representation="outflows_in_Y",
                    external_flow_scope="both",
                    inflow_sign="positive",
                ),
            )
        )

    assert report.accounting.output_balance.status == "SKIPPED"
    assert "non-finite" in (report.accounting.output_balance.reason or "")


def test_negative_signed_trade_equation_matches_the_calculation():
    report = audit(
        IOSystem(
            np.array([[1.0]]),
            np.array([10.0]),
            ["A"],
            Y=np.array([8.0]),
            trade=TradeFlows(
                international_imports=np.array([-2.0]),
                international_exports=np.array([-3.0]),
            ),
            accounting=AccountingConvention(
                transaction_scope="domestic",
                import_treatment="competitive",
                trade_representation="separate",
                external_flow_scope="international",
                inflow_sign="negative",
                outflow_sign="negative",
            ),
        )
    )

    equation = report.accounting.output_balance.equation
    assert report.accounting.output_balance.status == "PASS"
    assert "- outflow (international_exports, negative signed)" in equation
    assert "+ inflow (international_imports, negative signed)" in equation


def test_invalid_convention_types_raise_io_validation_error():
    with pytest.raises(IOValidationError):
        AccountingConvention(transaction_scope=[])
