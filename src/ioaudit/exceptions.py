"""Exceptions raised by :mod:`ioaudit`."""


class IOAuditError(Exception):
    """Base exception for audit and validation failures."""


class IOValidationError(IOAuditError):
    """Raised when an input cannot be represented as an IO system."""


class IONumericalError(IOAuditError):
    """Raised when a requested numerical calculation cannot be completed."""
