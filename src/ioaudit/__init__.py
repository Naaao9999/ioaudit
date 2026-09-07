"""ioaudit: transparent diagnostics for input-output tables."""

from .audit import audit
from .conventions import AccountingConvention
from .exceptions import IOAuditError, IONumericalError, IOValidationError
from .file_diagnostics import DelimitedFileReport, inspect_csv, inspect_delimited
from .model import IOSystem, TradeFlows
from .results import AuditReport
from ._version import __version__

__all__ = [
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
]
