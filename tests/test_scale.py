import numpy as np

from ioaudit import AccountingConvention, IOSystem, audit


def test_global_x_scale_candidate_uses_accounting_residuals():
    z = np.diag([2.0, 3.0])
    original_x = np.array([10.0, 10.0])
    io = IOSystem(
        z,
        original_x * 1000.0,
        ["A", "B"],
        Y=np.array([8.0, 7.0]),
        V=np.array([8.0, 7.0]),
        accounting=AccountingConvention(transaction_scope="domestic", import_treatment="competitive", trade_representation="embedded", input_representation="complete"),
    )
    report = audit(io)
    candidate = next(
        item
        for item in report.scale.possible_global_scale_mismatches
        if item["field"] == "x" and item["candidate_factor"] == 0.001
    )
    assert candidate["improvement"] == 1.0
    assert candidate["evidence_level"] == "strong"


def test_global_y_and_v_candidates_use_only_their_affected_balance():
    z = np.diag([2.0, 3.0])
    report = audit(
        IOSystem(
            z,
            np.array([10.0, 10.0]),
            ["A", "B"],
            Y=np.array([8000.0, 7000.0]),
            V=np.array([8000.0, 7000.0]),
            accounting=AccountingConvention(transaction_scope="domestic", import_treatment="competitive", trade_representation="embedded", input_representation="complete"),
        )
    )
    y_candidate = next(
        item
        for item in report.scale.possible_global_scale_mismatches
        if item["field"] == "Y" and item["candidate_factor"] == 0.001
    )
    v_candidate = next(
        item
        for item in report.scale.possible_global_scale_mismatches
        if item["field"] == "V" and item["candidate_factor"] == 0.001
    )
    assert y_candidate["affected_balances"] == ["output"]
    assert v_candidate["affected_balances"] == ["input"]


def test_row_and_column_scale_candidates_are_reported():
    z = np.array([[1.0, 2.0], [3.0, 4.0]])
    x = np.array([13.0, 17.0])
    y = np.array([10.0, 10.0])
    v = np.array([9.0, 11.0])
    bad_z = z.copy()
    bad_z[0, 1] *= 1000.0
    report = audit(
        IOSystem(
            bad_z,
            x,
            ["A", "B"],
            Y=y,
            V=v,
                accounting=AccountingConvention(transaction_scope="domestic", import_treatment="competitive", trade_representation="embedded", input_representation="complete"),
        )
    )
    row = next(
        item
        for item in report.scale.possible_row_scale_errors
        if item["index"] == 0 and item["candidate_factor"] == 0.001
    )
    column = next(
        item
        for item in report.scale.possible_column_scale_errors
        if item["index"] == 1 and item["candidate_factor"] == 0.001
    )
    assert row["evidence_level"] == "strong"
    assert column["evidence_level"] == "strong"


def test_cell_scale_candidate_requires_both_accounting_sides():
    z = np.array([[1.0, 2.0], [3.0, 4.0]])
    bad_z = z.copy()
    bad_z[0, 1] *= 1000.0
    report = audit(
        IOSystem(
            bad_z,
            np.array([13.0, 17.0]),
            ["A", "B"],
            Y=np.array([10.0, 10.0]),
            V=np.array([9.0, 11.0]),
            A_reference=z / np.array([13.0, 17.0])[np.newaxis, :],
            accounting=AccountingConvention(transaction_scope="domestic", import_treatment="competitive", trade_representation="embedded", input_representation="complete"),
        ),
        accounting_tolerance={"absolute": 1.0},
    )
    candidate = next(
        item
        for item in report.scale.possible_cell_scale_errors
        if item["row_index"] == 0
        and item["column_index"] == 1
        and item["candidate_factor"] == 0.001
    )
    assert candidate["candidate_value"] == 2.0
    assert candidate["output_residual_improvement"] == 1.0
    assert candidate["input_residual_improvement"] == 1.0
    assert candidate["reference_evidence"] == "A_reference also improves"


def test_cell_scale_is_skipped_without_rounding_context():
    report = audit(
        IOSystem(
            np.array([[1.0, 2000.0], [3.0, 4.0]]),
            np.array([13.0, 17.0]),
            ["A", "B"],
            Y=np.array([10.0, 10.0]),
            V=np.array([9.0, 11.0]),
            accounting=AccountingConvention(
                transaction_scope="domestic",
                import_treatment="competitive",
                trade_representation="embedded",
                input_representation="complete",
            ),
        )
    )
    assert report.scale.cell_status == "SKIPPED"
    assert report.scale.cell_reason == "rounding context unavailable"
    assert report.scale.possible_cell_scale_errors == []
    assert any("rounding context unavailable" in warning for warning in report.warnings)


def test_balanced_table_has_available_but_empty_scale_candidates(normal_io):
    report = audit(normal_io)
    assert report.scale.status == "AVAILABLE"
    assert report.scale.total_candidates == 0


def test_one_sided_scale_candidates_are_marked_as_one_sided():
    report = audit(
        IOSystem(
            np.array([[1000.0, 0.0], [0.0, 1.0]]),
            np.array([2.0, 2.0]),
            ["A", "B"],
            Y=np.array([1.0, 1.0]),
            accounting=AccountingConvention(transaction_scope="domestic", import_treatment="competitive", trade_representation="embedded", input_representation="complete"),
        )
    )
    candidate = next(
        item
        for item in report.scale.possible_row_scale_errors
        if item["index"] == 0 and item["candidate_factor"] == 0.001
    )
    assert candidate["opposite_balance_available"] is False
    assert candidate["evidence_level"] == "one_sided"
