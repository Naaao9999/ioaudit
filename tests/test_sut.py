import numpy as np
import pandas as pd
import pytest

from ioaudit import IOValidationError, SUTSystem, audit_sut


def _valid_sut() -> SUTSystem:
    products = ["p1", "p2"]
    industries = ["i1", "i2"]
    use = pd.DataFrame([[2.0, 1.0], [1.0, 3.0]], index=products, columns=industries)
    final_demand = pd.DataFrame(
        [[3.0, 1.0], [2.0, 2.0]],
        index=products,
        columns=["households", "investment"],
    )
    value_added = pd.DataFrame(
        [[3.0, 3.0], [1.0, 1.0]],
        index=["compensation", "operating_surplus"],
        columns=industries,
    )
    output_by_product = np.array([7.0, 8.0])
    output_by_industry = np.array([7.0, 8.0])
    make = pd.DataFrame([[3.0, 4.0], [4.0, 4.0]], index=products, columns=industries)
    return SUTSystem(
        use=use,
        products=products,
        industries=industries,
        make=make,
        final_demand=final_demand,
        value_added=value_added,
        output_by_product=output_by_product,
        output_by_industry=output_by_industry,
        output_by_product_scope="domestic_output",
        metadata={"year": 2020, "unit": "million", "price_basis": "producer"},
    )


def test_sut_audits_use_make_and_multidimensional_components():
    report = audit_sut(_valid_sut())

    assert report.structure.status == "PASS"
    assert report.accounting.status == "PASS"
    assert report.accounting.commodity_balance.status == "PASS"
    assert report.accounting.industry_balance.status == "PASS"
    assert report.accounting.make_product_balance.status == "PASS"
    assert report.accounting.make_industry_balance.status == "PASS"
    assert report.passed(require_complete=True)


def test_sut_does_not_accept_a_terminal_row_or_column_as_use():
    sut = _valid_sut()
    sut.use = np.zeros((3, 3))

    report = audit_sut(sut)

    assert report.structure.status == "FAIL"
    assert report.accounting.commodity_balance.status == "SKIPPED"
    assert report.accounting.industry_balance.status == "SKIPPED"


def test_sut_label_mismatch_skips_only_affected_identity():
    sut = _valid_sut()
    sut.final_demand = pd.DataFrame(
        [[3.0, 1.0], [2.0, 2.0]],
        index=["p2", "p1"],
        columns=["households", "investment"],
    )

    report = audit_sut(sut)

    assert report.structure.status == "FAIL"
    assert report.accounting.commodity_balance.status == "SKIPPED"
    assert report.accounting.industry_balance.status == "PASS"


def test_sut_report_serializes_without_siot_conversion():
    report = audit_sut(_valid_sut())

    payload = report.to_dict()
    assert payload["system_type"] == "SUT"
    assert "no automatic SUT-to-SIOT transformation" in report.to_json()
    assert not report.to_dataframe().empty


def test_sut_does_not_compare_make_with_total_supply():
    sut = _valid_sut()
    sut.output_by_product_scope = "total_supply"

    report = audit_sut(sut)

    assert report.accounting.commodity_balance.status == "PASS"
    assert report.accounting.make_product_balance.status == "SKIPPED"
    assert "total_supply" in report.accounting.make_product_balance.reason


def test_sut_rejects_unknown_output_scope_values():
    with pytest.raises(IOValidationError):
        SUTSystem(
            use=np.eye(1),
            products=["p"],
            industries=["i"],
            output_by_product_scope="supply_like",
        )
