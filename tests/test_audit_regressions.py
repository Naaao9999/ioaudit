"""Regression coverage for subtotal, sparse storage and reference safety."""

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from ioaudit import AccountingConvention, IOSystem, audit
from ioaudit.components import diagnose_components
from ioaudit.reference import _compare


def test_zero_component_does_not_turn_equal_components_into_subtotals():
    z = np.array([[1., .2], [.3, 1.]])
    y = np.array([[3., 3., 0.], [4., 4., 0.]])
    v = np.array([[2.95, 4.05], [2.95, 4.05], [0., 0.]])
    convention = AccountingConvention(
        transaction_scope="total", import_treatment="none",
        trade_representation="embedded", input_representation="complete",
    )
    io = IOSystem(z, [7.2, 9.3], ["A", "B"], Y=y, V=v, accounting=convention)
    report = audit(io)
    assert report.components.subtotal_candidates == []
    assert report.accounting.input_balance.status == "PASS"
    assert report.accounting.output_balance.status == "PASS"
    np.testing.assert_array_equal(io.Y, y)
    np.testing.assert_array_equal(io.V, v)


def test_genuine_subtotal_with_zero_component_is_still_detected():
    io = IOSystem(np.eye(2), [1, 1], ["A", "B"],
                  Y=np.array([[1., 2., 3., 0.], [2., 5., 7., 0.]]))
    candidates = diagnose_components(io).subtotal_candidates
    assert any(c["index"] == 2 and c["subset_indices"] == [0, 1] for c in candidates)


def test_explicit_total_label_still_warns_with_zero_components():
    io = IOSystem(np.eye(2), [1, 1], ["A", "B"],
                  Y=pd.DataFrame([[3., 3., 0.], [4., 4., 0.]],
                                 columns=["Total", "demand", "zero"]))
    assert any(c["label_evidence"] for c in diagnose_components(io).subtotal_candidates)


@pytest.mark.parametrize("factory", [
    sparse.csr_matrix, sparse.csc_matrix, sparse.coo_matrix,
    sparse.lil_matrix, sparse.dok_matrix, sparse.dia_matrix,
    sparse.bsr_matrix, sparse.csr_array, sparse.coo_array,
])
@pytest.mark.parametrize("method", ["dense", "iterative"])
def test_sparse_storage_formats_are_safe_and_source_is_unchanged(factory, method):
    dense = np.array([[.2, .1], [.05, .3]])
    source = factory(dense)
    io = IOSystem(source, [1., 1.], ["A", "B"])
    report = audit(io, numerical_method=method)
    assert report.structure.status == "PASS"
    assert report.stability.status == "PASS"
    np.testing.assert_array_equal(source.toarray(), dense)
    np.testing.assert_array_equal(io.Z.toarray(), dense)
    # The canonical representation must not alias caller-owned storage.
    io.Z.data[:] = 0
    np.testing.assert_array_equal(source.toarray(), dense)


@pytest.mark.parametrize("magnitude", [1e200, 1e-200, 1e308])
def test_reference_metrics_do_not_overflow_or_underflow_in_intermediate_steps(magnitude):
    reference = np.eye(2) * magnitude
    calculated = reference * .2
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        result = _compare(calculated, reference, np.eye(2), ["A", "B"])
    assert result.relative_difference == pytest.approx(.8)
    assert result.rmse / magnitude == pytest.approx(.8 / np.sqrt(2))
    assert result.mean_absolute_difference / magnitude == pytest.approx(.4)


def test_unrepresentable_reference_difference_has_explicit_failure_reason():
    result = _compare(np.array([[1e308]]), np.array([[-1e308]]), None, ["A"])
    assert result.status == "FAIL"
    assert "floating-point range" in result.reason


def test_zero_reference_keeps_defined_relative_difference_semantics():
    assert _compare(np.zeros((1, 1)), np.zeros((1, 1)), None, ["A"]).relative_difference == 0
    assert _compare(np.ones((1, 1)), np.zeros((1, 1)), None, ["A"]).relative_difference == np.inf
