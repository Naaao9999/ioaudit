import numpy as np
import pandas as pd

from ioaudit import AccountingConvention, IOSystem, audit


def test_labels_and_alignment():
    z = pd.DataFrame([[2.0, 1.0], [1.0, 3.0]], index=["A", "B"], columns=["A", "B"])
    x = pd.Series([8.0, 9.0], index=["A", "B"])
    report = audit(IOSystem(z, x, ["A", "B"], accounting=AccountingConvention()))
    assert report.orientation.row_labels_match_columns is True
    assert report.orientation.sector_order_consistent is True
    assert report.orientation.x_alignment is True


def test_transposed_table_detectable():
    # Y and V are constructed for Z.T, so the transposed candidate has zero
    # residual while the supplied orientation does not.
    z = np.array([[2.0, 1.0], [4.0, 3.0]])
    x = np.array([10.0, 10.0])
    y = np.array([4.0, 6.0])
    report = audit(IOSystem(z, x, ["a", "b"], Y=y, imports=np.zeros(2), accounting=AccountingConvention.japan_competitive()))
    assert report.orientation.possible_transpose is True


def test_transposed_table_indeterminate():
    z = np.array([[2.0, 1.0], [1.0, 3.0]])
    x = np.array([8.0, 9.0])
    # Symmetric evidence makes both orientations equally plausible.
    report = audit(IOSystem(z, x, ["a", "b"], Y=np.array([5.0, 5.0]), V=np.array([5.0, 5.0]), accounting=AccountingConvention.japan_competitive()))
    assert report.orientation.possible_transpose is None


def test_no_evidence_is_indeterminate(normal_io):
    io = IOSystem(normal_io.Z, normal_io.x, normal_io.sectors)
    assert audit(io).orientation.possible_transpose is None


def test_subtotal_y_is_not_reused_for_orientation_evidence():
    y = pd.DataFrame(
        [[1.0, 2.0, 3.0], [2.0, 3.0, 5.0]],
        columns=["household", "government", "total"],
    )
    report = audit(
        IOSystem(
            np.eye(2),
            np.ones(2),
            ["a", "b"],
            Y=y,
            accounting=AccountingConvention(trade_representation="embedded"),
        )
    )
    assert report.accounting.output_balance.status == "SKIPPED"
    assert report.orientation.comparison_available is False
    assert report.orientation.possible_transpose is None


def test_x_label_mismatch_fails_orientation_and_pipeline():
    z = pd.DataFrame(np.eye(2), index=["a", "b"], columns=["a", "b"])
    x = pd.Series([1.0, 1.0], index=["b", "a"])
    report = audit(IOSystem(z, x, ["a", "b"], accounting=AccountingConvention()))
    assert report.orientation.x_alignment is False
    assert report.orientation.status == "FAIL"
    assert report.passed() is False
