import inspect

import ioaudit
from ioaudit import AccountingConvention, AuditReport, IOSystem, TradeFlows, audit


def test_v01_public_exports_and_input_contract_are_present():
    assert {
        "IOSystem",
        "TradeFlows",
        "AccountingConvention",
        "AuditReport",
        "audit",
        "DelimitedFileReport",
        "inspect_csv",
        "inspect_delimited",
        "IOAuditError",
        "IOValidationError",
        "IONumericalError",
    } == set(ioaudit.__all__)
    assert ioaudit.__version__ == "0.1.0"

    io_parameters = inspect.signature(IOSystem).parameters
    for name in (
        "Z",
        "x",
        "sectors",
        "Y",
        "V",
        "trade",
        "input_adjustments",
        "output_adjustments",
        "A_reference",
        "L_reference",
        "metadata",
        "accounting",
    ):
        assert name in io_parameters

    audit_parameters = inspect.signature(audit).parameters
    assert set(audit_parameters) == {
        "io",
        "numerical_method",
        "accounting_tolerance",
    }


def test_v01_status_contract_is_used_by_a_report():
    report = audit(IOSystem([[0.1]], [1.0], ["A"]))
    statuses = {
        report.structure.status,
        report.orientation.status,
        report.signs.status,
        report.coefficients.status,
        report.stability.status,
        report.metadata.status,
    }
    assert statuses <= {"PASS", "AVAILABLE", "WARNING", "FAIL", "SKIPPED"}
