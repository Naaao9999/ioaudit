"""Regression tests for gate consistency, missing labels and sparse values."""

import copy

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from ioaudit import AccountingConvention, IOAuditError, IOSystem, audit


@pytest.mark.parametrize("method", ["dense", "iterative"])
@pytest.mark.parametrize("reference", [
    np.eye(3),
    np.array([[np.nan, 0.], [0., 1.]]),
    np.array([[np.inf, 0.], [0., 1.]]),
    pd.DataFrame(np.eye(2), index=["B", "A"], columns=["B", "A"]),
    pd.DataFrame(np.eye(2), index=["A", pd.NA], columns=["A", "B"]),
])
def test_invalid_reference_is_rejected_without_requiring_inverse(method, reference):
    r = audit(IOSystem(np.eye(2) * .2, [1., 1.], ["A", "B"],
                       L_reference=reference), numerical_method=method)
    assert r.structure.status == "PASS"
    assert r.coefficients.status == "PASS"
    assert r.stability.status == "PASS"
    assert r.reference.L.status == "FAIL"
    assert r.reference.L.reason
    assert r.passed()
    assert not r.passed(fail_on_invalid_reference=True)
    with pytest.raises(IOAuditError):
        r.raise_for_status(fail_on_invalid_reference=True)


def test_valid_iterative_reference_has_structure_results_but_no_comparison():
    r = audit(IOSystem(np.eye(2) * .2, [1., 1.], ["A", "B"],
                       L_reference=pd.DataFrame(np.eye(2) * 1.25,
                                                index=["A", "B"], columns=["A", "B"])),
              numerical_method="iterative")
    assert r.reference.L.status == "SKIPPED"
    assert r.reference.L.shape_consistency is True
    assert r.reference.L.label_consistency is True
    assert r.reference.L.relative_difference is None
    assert r.passed(fail_on_invalid_reference=True)
    assert not r.passed(require_available=["reference.L"])


def test_saved_spectral_gate_remains_active_until_explicitly_overridden():
    r = audit(IOSystem(np.array([[.8]]), [1.], ["A"]))
    with pytest.raises(IOAuditError):
        r.raise_for_status(max_spectral_radius=.5)
    before = copy.deepcopy(r.to_dict())
    assert not r.passed()
    assert r.passed(max_spectral_radius=1.)
    assert r.passed(max_spectral_radius=None)
    assert not r.passed({"stability.spectral_radius": .5}, max_spectral_radius=1.)
    assert r.to_dict() == before
    with pytest.raises(IOAuditError):
        r.raise_for_status()
    assert r.thresholds["stability.spectral_radius"] == .5
    assert r.provenance["thresholds"]["stability.spectral_radius"] == .5
    r.raise_for_status(max_spectral_radius=1.)
    assert r.passed()
    r.raise_for_status(max_spectral_radius=None)
    assert "stability.spectral_radius" not in r.thresholds
    assert "stability.spectral_radius" not in r.provenance["thresholds"]


@pytest.mark.parametrize("missing", [pd.NA, None, np.nan, pd.NaT])
@pytest.mark.parametrize("labelled", [True, False])
def test_missing_sector_identifiers_fail_safely(missing, labelled):
    labels = ["A", missing]
    z = np.eye(2) * .2
    if labelled:
        z = pd.DataFrame(z, index=labels, columns=labels)
    r = audit(IOSystem(z, [1., 1.], labels))
    assert r.structure.status == "FAIL"
    assert r.structure.details["missing_sector_id_indices"] == [1]
    assert r.coefficients.status == "SKIPPED"
    assert r.stability.status == "SKIPPED"
    assert not r.passed()


def test_missing_y_sector_label_only_skips_output_accounting():
    r = audit(IOSystem(np.eye(2) * .2, [1., 1.], ["A", "B"],
                       Y=pd.Series([.8, .8], index=["A", pd.NA]), V=[.8, .8],
                       accounting=AccountingConvention(
                           transaction_scope="total", input_representation="complete")))
    assert r.coefficients.status == "PASS"
    assert r.accounting.input_balance.status == "PASS"
    assert r.accounting.output_balance.status == "SKIPPED"


def test_explicit_sparse_zeros_have_same_zero_structure_without_mutation():
    z = sparse.csr_matrix(([0., .2], ([0, 1], [0, 1])), shape=(2, 2))
    io = IOSystem(z, [0., 1.], ["A", "B"], Y=[0., .8], V=[0., .8])
    before = io.Z.copy()
    r = audit(io)
    dense = audit(IOSystem(z.toarray(), [0., 1.], ["A", "B"], Y=[0., .8], V=[0., .8]))
    assert r.zero_structure == dense.zero_structure
    assert r.zero_structure.all_zero_rows == ["A"]
    assert r.zero_structure.isolated_sectors == ["A"]
    np.testing.assert_array_equal(io.Z.data, before.data)
    np.testing.assert_array_equal(io.Z.indices, before.indices)
    assert z.nnz == io.Z.nnz == 2


@pytest.mark.parametrize("values", [
    [[.1, .1], [.1, .1]],
    [[-.1, -.1], [-.1, -.1]],
    [[0., .1], [.1, .2]],
    [[0., 0.], [0., 0.]],
])
def test_sparse_distribution_matches_dense(values):
    dense = audit(IOSystem(np.array(values), [1., 1.], ["A", "B"]))
    compressed = audit(IOSystem(sparse.csr_matrix(values), [1., 1.], ["A", "B"]))
    assert compressed.coefficients.distribution == pytest.approx(dense.coefficients.distribution)


def test_sparse_coefficient_division_does_not_form_overflowing_reciprocal():
    z = np.array([[1e-310, 0.], [0., 0.]])
    x = [1e-309, 0.]
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        dense = audit(IOSystem(z, x, ["A", "B"]))
        compressed = audit(IOSystem(sparse.csr_matrix(z), x, ["A", "B"]))
    assert dense.coefficients.status == compressed.coefficients.status == "PASS"
    np.testing.assert_array_equal(dense.coefficients.A, compressed.coefficients.A.toarray())
    assert dense.passed() == compressed.passed() is True
