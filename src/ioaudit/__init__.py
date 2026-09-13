"""ioaudit: transparent diagnostics for input-output tables."""

from .audit import audit
from .conventions import AccountingConvention
from .exceptions import IOAuditError, IONumericalError, IOValidationError
from .file_diagnostics import DelimitedFileReport, inspect_csv, inspect_delimited
from .model import IOSystem, TradeFlows
from .results import AuditReport
from .systems import MRIOAuditReport, MRIOSystem, SUTAuditReport, SUTSystem, audit_mrio, audit_sut
from ._version import __version__

__all__ = [
    "IOSystem",
    "TradeFlows",
    "AccountingConvention",
    "AuditReport",
    "audit",
    "SUTSystem",
    "MRIOSystem",
    "SUTAuditReport",
    "MRIOAuditReport",
    "audit_sut",
    "audit_mrio",
    "DelimitedFileReport",
    "inspect_csv",
    "inspect_delimited",
    "IOAuditError",
    "IOValidationError",
    "IONumericalError",
]
