import numpy as np

from ioaudit import IOSystem, audit


def test_abnormal_zero_structure_and_isolated_sector_are_reported():
    z = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    report = audit(
        IOSystem(
            z,
            np.array([1.0, 2.0, 1.0]),
            ["A", "B", "C"],
            Y=np.array([0.0, 0.0, 0.0]),
            V=np.array([0.0, 0.0, 0.0]),
        )
    )
    assert report.zero_structure.all_zero_rows == ["B"]
    assert report.zero_structure.all_zero_columns == ["B"]
    assert report.zero_structure.all_zero_rows_with_positive_output == ["B"]
    assert report.zero_structure.all_zero_columns_with_positive_output == ["B"]
    assert report.zero_structure.isolated_sectors == ["B"]


def test_zero_structure_records_final_demand_and_value_added_evidence():
    z = np.zeros((2, 2))
    report = audit(
        IOSystem(
            z,
            np.array([5.0, 0.0]),
            ["A", "B"],
            Y=np.array([5.0, 0.0]),
            V=np.array([0.0, 2.0]),
        )
    )
    assert report.zero_structure.all_zero_rows_with_positive_output == ["A"]
    assert report.zero_structure.all_zero_rows_with_positive_final_demand == ["A"]
    assert report.zero_structure.all_zero_columns_with_positive_value_added == ["B"]
