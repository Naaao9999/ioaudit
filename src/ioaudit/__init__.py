"""ioaudit: transparent diagnostics for input-output tables."""

from .audit import audit
from .conventions import AccountingConvention
from .exceptions import IOAuditError, IONumericalError, IOValidationError
from .file_diagnostics import CSVInspectionReport, inspect_csv, inspect_delimited
from .model import IOSystem, TradeFlows
from .results import AuditReport

__all__ = [
    "IOSystem",
    "TradeFlows",
    "AccountingConvention",
    "AuditReport",
    "audit",
    "CSVInspectionReport",
    "inspect_csv",
    "inspect_delimited",
    "IOAuditError",
    "IOValidationError",
    "IONumericalError",
]

__version__ = "0.1.0"
