import numpy as np
import pandas as pd
from scipy import sparse

from ioaudit import MRIOSystem, audit_mrio


def _valid_mrio(labelled: bool = True) -> MRIOSystem:
    regions = ["JPN", "USA"]
    sectors = ["agriculture", "manufacturing"]
    labels = [(region, sector) for region in regions for sector in sectors]
    z = np.array(
        [
            [0.10, 0.02, 0.01, 0.00],
            [0.03, 0.10, 0.00, 0.01],
            [0.00, 0.02, 0.10, 0.01],
            [0.01, 0.00, 0.03, 0.10],
        ]
    )
    y = np.array([[3.0, 0.0], [2.0, 0.0], [4.0, 0.0], [2.0, 0.0]])
    x = z.sum(axis=1) + y.sum(axis=1)
    v = x - z.sum(axis=0)
    if labelled:
        index = pd.MultiIndex.from_tuples(labels, names=["region", "sector"])
        z = pd.DataFrame(z, index=index, columns=index)
        x = pd.Series(x, index=index)
        y = pd.DataFrame(y, index=index, columns=["households", "investment"])
        v = pd.DataFrame([v], index=["value_added"], columns=index)
    return MRIOSystem(
        Z=z,
        x=x,
        regions=regions,
        sectors=sectors,
        Y=y,
        V=v,
        metadata={
            "year": 2020,
            "unit": "million_eur",
            "price_basis": "producer",
            "symmetric_dimension": "industry",
        },
    )


def test_mrio_supports_tuple_labels_and_embedded_accounting():
    report = audit_mrio(_valid_mrio())

    assert report.structure.status == "PASS"
    assert report.structure.expected_labels == [
        ("JPN", "agriculture"),
        ("JPN", "manufacturing"),
        ("USA", "agriculture"),
        ("USA", "manufacturing"),
    ]
    assert report.structure.block_structure["region_block_count"] == 4
    assert report.accounting.output_balance.status == "PASS"
    assert report.accounting.input_balance.status == "PASS"
    assert report.coefficients.status == "PASS"
    assert report.stability.status == "PASS"
    assert report.passed(require_complete=True)


def test_mrio_label_order_mismatch_does_not_reach_coefficients():
    mrio = _valid_mrio()
    mrio.x = pd.Series(
        mrio.x.to_numpy(),
        index=pd.MultiIndex.from_tuples(
            [("JPN", "manufacturing"), ("JPN", "agriculture"),
             ("USA", "agriculture"), ("USA", "manufacturing")]
        ),
    )

    report = audit_mrio(mrio)

    assert report.structure.status == "FAIL"
    assert report.coefficients.status == "SKIPPED"
    assert report.stability.status == "SKIPPED"


def test_invalid_supporting_y_does_not_stop_core_mrio_diagnostics():
    mrio = _valid_mrio()
    mrio.Y = pd.DataFrame(
        [["not numeric"], ["not numeric"], ["not numeric"], ["not numeric"]],
        index=mrio.x.index,
        columns=["households"],
    )

    report = audit_mrio(mrio)

    assert report.structure.status == "PASS"
    assert report.structure.supporting_status == "FAIL"
    assert report.accounting.output_balance.status == "SKIPPED"
    assert report.accounting.input_balance.status == "PASS"
    assert report.coefficients.status == "PASS"
    assert report.stability.status == "PASS"
    assert report.passed() is True
    assert report.passed(require_complete=True) is False


def test_mrio_iterative_route_accepts_sparse_expanded_matrix():
    mrio = _valid_mrio(labelled=False)
    mrio.Z = sparse.csr_matrix(mrio.Z)

    report = audit_mrio(mrio, numerical_method="iterative")

    assert report.methods["numerical_method"] == "iterative"
    assert report.structure.status == "PASS"
    assert report.coefficients.status == "PASS"
    assert report.stability.invertible is True


def test_mrio_report_is_serializable():
    report = audit_mrio(_valid_mrio())

    assert report.to_dict()["system_type"] == "MRIO"
    assert "MRIO Audit Report" in report.summary()
    assert not report.to_dataframe().empty


def test_mrio_report_uses_the_default_spectral_radius_gate():
    report = audit_mrio(
        MRIOSystem(
            Z=np.array([[1.1]]),
            x=np.array([1.0]),
            regions=["R"],
            sectors=["S"],
            Y=np.array([[-0.1]]),
            V=np.array([[-0.1]]),
        )
    )

    assert report.stability.spectral_radius == 1.1
    assert report.stability.invertible is True
    assert report.passed() is False
