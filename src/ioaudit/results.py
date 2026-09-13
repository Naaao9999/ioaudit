"""Serializable result objects and CI-oriented status helpers."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import pandas as pd

from .exceptions import IOAuditError
from ._report_utils import (
    MISSING as _MISSING,
    get_report_path as _get_report_path,
    report_to_dataframe as _report_to_dataframe,
    report_to_dict as _report_to_dict,
    report_to_json as _report_to_json,
)


_AUDIT_REPORT_FIELDS = (
    "structure", "orientation", "accounting", "signs", "zero_structure",
    "coefficients", "stability", "reference", "scale", "components",
    "metadata", "methods", "provenance", "thresholds", "warnings", "errors",
)

_SYSTEM_REPORT_FIELDS = (
    "system_type", "structure", "accounting", "coefficients", "stability",
    "reference", "metadata", "methods", "provenance", "thresholds",
    "warnings", "errors",
)


class AuditReport:
    """Complete, deterministic result of :func:`ioaudit.audit`."""

    def __init__(
        self,
        *,
        structure: Any,
        orientation: Any,
        accounting: Any,
        signs: Any,
        zero_structure: Any,
        coefficients: Any,
        stability: Any,
        reference: Any,
        methods: Any,
        scale: Any = None,
        components: Any = None,
        metadata: Any = None,
        provenance: dict[str, Any] | None = None,
        thresholds: dict[str, float] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        self.structure = structure
        self.orientation = orientation
        self.accounting = accounting
        self.signs = signs
        self.zero_structure = zero_structure
        self.coefficients = coefficients
        self.stability = stability
        self.reference = reference
        self.scale = scale
        self.components = components
        self.metadata = metadata
        self.methods = methods
        self.provenance = dict(provenance or {})
        self.thresholds = dict(thresholds or {})
        self.warnings = list(warnings or [])
        self.errors = list(errors or [])

    def to_dict(self) -> dict[str, Any]:
        """Return the entire report as a JSON-compatible dictionary."""

        return _report_to_dict(self, _AUDIT_REPORT_FIELDS)

    def to_json(self, **kwargs: Any) -> str:
        """Serialize the report to JSON."""

        return _report_to_json(self, _AUDIT_REPORT_FIELDS, **kwargs)

    def to_dataframe(self) -> pd.DataFrame:
        """Return one flattened ``path``/``value`` row per report value."""

        return _report_to_dataframe(self, _AUDIT_REPORT_FIELDS)

    def _boolean_failures(self, *, include_reference: bool = False) -> list[str]:
        failures: list[str] = []
        if getattr(self.structure, "status", None) == "FAIL":
            failures.append("structure.status")
        if getattr(self.orientation, "status", None) == "FAIL":
            failures.append("orientation.status")
        if getattr(self.orientation, "possible_transpose", None) is True:
            failures.append("orientation.possible_transpose")
        if getattr(self.zero_structure, "inconsistent_sectors", []):
            failures.append("zero_structure.inconsistent_sectors")
        for name in ("input_balance", "output_balance"):
            if getattr(getattr(self.accounting, name, None), "status", None) == "FAIL":
                failures.append(f"accounting.{name}.status")
        if getattr(self.coefficients, "finite_coefficients", None) is False:
            failures.append("coefficients.finite_coefficients")
        if getattr(self.coefficients, "status", None) == "FAIL":
            failures.append("coefficients.status")
        if getattr(self.stability, "invertible", None) is False:
            failures.append("stability.invertible")
        if getattr(self.stability, "leontief_inverse_finite", None) is False:
            failures.append("stability.leontief_inverse_finite")
        if getattr(self.stability, "status", None) == "FAIL":
            failures.append("stability.status")
        if include_reference and getattr(self.reference, "status", None) == "FAIL":
            failures.append("reference.status")
        return failures

    def _completeness_failures(self) -> list[str]:
        """Return checks that are unavailable for a complete-audit gate."""

        failures: list[str] = []
        if getattr(self.accounting, "status", None) == "SKIPPED":
            failures.append("accounting.status")
        for name in ("input_balance", "output_balance"):
            if getattr(getattr(self.accounting, name, None), "status", None) == "SKIPPED":
                failures.append(f"accounting.{name}.status")
        if getattr(self.coefficients, "status", None) == "SKIPPED":
            failures.append("coefficients.status")
        if getattr(self.stability, "status", None) == "SKIPPED":
            failures.append("stability.status")
        return failures

    def _availability_failures(self, paths: Iterable[str] | None) -> list[str]:
        """Return requested report paths that are unavailable or skipped."""

        failures: list[str] = []
        if paths is None:
            return failures
        if isinstance(paths, str):
            requested = [paths]
        else:
            try:
                requested = list(paths)
            except TypeError as exc:
                raise IOAuditError("require_available must be an iterable of report paths") from exc
        for path in requested:
            if not isinstance(path, str) or not path.strip():
                failures.append(f"invalid required-available path: {path!r}")
                continue
            value = self._get_path(self, path)
            if value is _MISSING or value is None:
                failures.append(f"required report path unavailable: {path}")
                continue
            status = getattr(value, "status", None)
            if status == "SKIPPED":
                failures.append(f"required report path skipped: {path}")
            elif status == "FAIL":
                failures.append(f"required report path failed: {path}")
        return failures

    def _sync_provenance(self) -> None:
        """Keep manifest thresholds in sync after a CI gate is configured."""

        if self.provenance:
            self.provenance["thresholds"] = dict(self.thresholds)
            self.provenance["numerical_method"] = getattr(
                self.methods, "numerical_method", None
            )

    @staticmethod
    def _get_path(root: Any, path: str) -> Any:
        return _get_report_path(root, path)

    def _threshold_failures(
        self,
        thresholds: dict[str, float],
        *,
        raise_invalid: bool = False,
    ) -> list[str]:
        failures: list[str] = []
        for path, threshold in thresholds.items():
            try:
                limit = float(threshold)
            except (TypeError, ValueError) as exc:
                message = f"threshold for {path} must be numeric"
                if raise_invalid:
                    raise IOAuditError(message) from exc
                failures.append(message)
                continue
            if isinstance(threshold, bool) or not math.isfinite(limit):
                message = f"threshold for {path} must be finite"
                if raise_invalid:
                    raise IOAuditError(message)
                failures.append(message)
                continue
            value = self._get_path(self, path)
            if value is _MISSING:
                message = f"unknown threshold path: {path}"
                if raise_invalid:
                    raise IOAuditError(message)
                failures.append(message)
                continue
            if value is None:
                message = f"threshold path unavailable: {path}"
                if raise_invalid:
                    raise IOAuditError(message)
                failures.append(message)
                continue
            try:
                if isinstance(value, bool):
                    raise TypeError
                numeric = float(value)
            except (TypeError, ValueError):
                message = f"threshold path is not numeric: {path}"
                if raise_invalid:
                    raise IOAuditError(message)
                failures.append(message)
                continue
            if math.isnan(numeric):
                message = f"threshold path is NaN: {path}"
                if raise_invalid:
                    raise IOAuditError(message)
                failures.append(message)
                continue
            # A Leontief spectral-radius bound is strict: rho=1 is the
            # boundary of the usual convergent series.
            violated = numeric >= limit if path == "stability.spectral_radius" else numeric > limit
            if violated:
                failures.append(f"{path}={numeric} exceeds threshold {limit}")
        return failures

    def _gate_failures(
        self,
        *,
        thresholds: dict[str, float] | None = None,
        fail_on_boolean: bool = True,
        max_relative_residual: float | None = None,
        max_spectral_radius: float | None | object = _MISSING,
        require_complete: bool = False,
        require_available: Iterable[str] | None = None,
        fail_on_invalid_reference: bool = False,
        raise_invalid: bool = False,
    ) -> tuple[list[str], dict[str, float]]:
        """Evaluate all CI gate rules and return failures plus active limits."""

        active = dict(self.thresholds)
        supplied = dict(thresholds or {})
        active.update(supplied)
        if "stability.spectral_radius" not in supplied:
            if max_spectral_radius is _MISSING:
                active.setdefault("stability.spectral_radius", 1.0)
            elif max_spectral_radius is None:
                active.pop("stability.spectral_radius", None)
            else:
                active["stability.spectral_radius"] = max_spectral_radius
        if max_relative_residual is not None:
            active["accounting.max_relative_residual"] = max_relative_residual

        failures: list[str] = []
        if fail_on_boolean:
            failures.extend(
                self._boolean_failures(include_reference=fail_on_invalid_reference)
            )
        if require_complete:
            failures.extend(self._completeness_failures())
        failures.extend(self._availability_failures(require_available))
        failures.extend(self._threshold_failures(active, raise_invalid=raise_invalid))
        return failures, active

    def raise_for_status(
        self,
        fail_on_boolean: bool = True,
        max_relative_residual: float | None = None,
        max_spectral_radius: float | None | object = _MISSING,
        require_complete: bool = False,
        require_available: Iterable[str] | None = None,
        fail_on_invalid_reference: bool = False,
    ) -> None:
        """Raise :class:`IOAuditError` when configured checks fail.

        ``require_complete=True`` additionally rejects audits where the
        accounting, coefficient, or stability checks are unavailable.  The
        default remains permissive because Y, V, references, and conventions
        are optional in the v0.1 API.

        ``fail_on_invalid_reference=True`` explicitly includes an invalid
        optional reference matrix in the boolean gate.

        An omitted spectral bound uses the saved bound, or 1.0 when none is
        saved. An explicit value overrides it; None disables that bound.
        """

        failures, thresholds = self._gate_failures(
            fail_on_boolean=fail_on_boolean,
            max_relative_residual=max_relative_residual,
            max_spectral_radius=max_spectral_radius,
            require_complete=require_complete,
            require_available=require_available,
            fail_on_invalid_reference=fail_on_invalid_reference,
            raise_invalid=True,
        )
        self.thresholds = dict(thresholds)
        self._sync_provenance()
        if failures:
            raise IOAuditError("IO audit failed: " + "; ".join(failures))

    def passed(
        self,
        thresholds: dict[str, float] | None = None,
        *,
        fail_on_boolean: bool = True,
        max_relative_residual: float | None = None,
        max_spectral_radius: float | None | object = _MISSING,
        require_complete: bool = False,
        require_available: Iterable[str] | None = None,
        fail_on_invalid_reference: bool = False,
    ) -> bool:
        """Return whether checks and supplied thresholds pass.

        By default, optional or unavailable diagnostics do not fail this
        boolean gate.  Set ``require_complete=True`` when both accounting
        sides and downstream numerical diagnostics must be available.
        Set ``fail_on_invalid_reference=True`` to include an invalid optional
        reference matrix in the boolean gate.

        Spectral bounds take precedence in this order: ``thresholds`` entries,
        explicit arguments, saved bounds, then the default 1.0. None explicitly
        disables the spectral bound. This predicate does not change the report.
        """

        failures, _ = self._gate_failures(
            thresholds=thresholds,
            fail_on_boolean=fail_on_boolean,
            max_relative_residual=max_relative_residual,
            max_spectral_radius=max_spectral_radius,
            require_complete=require_complete,
            require_available=require_available,
            fail_on_invalid_reference=fail_on_invalid_reference,
        )
        return not failures

    def summary(self) -> str:
        """Return a short human-readable audit summary."""

        structure_status = getattr(self.structure, "status", "SKIPPED")
        supporting_status = getattr(self.structure, "supporting_status", "SKIPPED")
        orientation_status = getattr(self.orientation, "status", "SKIPPED")
        accounting_status = getattr(self.accounting, "status", "SKIPPED")
        invertible = getattr(self.stability, "invertible", None)
        leontief_label = "SOLVABLE" if invertible is True else ("UNSOLVABLE" if invertible is False else "SKIPPED")
        rho = getattr(self.stability, "spectral_radius", None)
        cond = getattr(self.stability, "condition_number", None)
        negative_count = getattr(self.signs, "total_negative_entries", 0)
        zero_count = len(getattr(self.zero_structure, "zero_output_indices", []))
        scale_count = getattr(self.scale, "total_candidates", 0) if self.scale is not None else 0
        component_count = len(getattr(self.components, "double_count_risk", [])) if self.components is not None else 0
        metadata_status = getattr(self.metadata, "status", "SKIPPED") if self.metadata is not None else "SKIPPED"
        lines = [
            "IO Audit Report",
            "===============",
            f"Structure                {structure_status}",
            f"Supporting inputs       {supporting_status}",
            f"Orientation              {orientation_status}",
            f"Accounting               {accounting_status}",
            f"Signs                    {negative_count} negative entries",
            f"Zero-output sectors      {zero_count}",
            f"Scale candidates         {scale_count}",
            f"Component double-count  {component_count} risk(s)",
            f"Metadata                {metadata_status}",
            f"Leontief system          {leontief_label}",
            f"Spectral radius          {rho:.6g}" if rho is not None else "Spectral radius          SKIPPED",
            f"Condition number         {cond:.6g}" if cond is not None else "Condition number         SKIPPED",
            "Diagnostics",
            "-----------",
        ]
        for label, balance in (
            ("Input balance max rel. residual", getattr(self.accounting, "input_balance", None)),
            ("Output balance max rel. residual", getattr(self.accounting, "output_balance", None)),
        ):
            status = getattr(balance, "status", None)
            if status is not None:
                lines.append(f"{label.replace(' max rel. residual', ' status')}: {status}")
            value = getattr(balance, "max_relative_residual", None)
            if value is not None:
                lines.append(f"{label}: {value:.6g}")
        return "\n".join(lines)


class SystemAuditReport:
    """Common serializable report for the v0.2 SUT and MRIO audits.

    SUT and MRIO have different accounting identities from a single SIOT,
    so they deliberately use a separate report type rather than pretending
    to be an :class:`AuditReport`.  The report nevertheless exposes the same
    small operational surface: ``summary``, serialization, and CI gating.
    """

    def __init__(
        self,
        *,
        system_type: str,
        structure: Any,
        accounting: Any,
        coefficients: Any = None,
        stability: Any = None,
        reference: Any = None,
        metadata: Any = None,
        methods: Any = None,
        provenance: dict[str, Any] | None = None,
        thresholds: dict[str, float] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        self.system_type = system_type
        self.structure = structure
        self.accounting = accounting
        self.coefficients = coefficients
        self.stability = stability
        self.reference = reference
        self.metadata = metadata
        self.methods = methods if methods is not None else {}
        self.provenance = dict(provenance or {})
        self.thresholds = dict(thresholds or {})
        self.warnings = list(warnings or [])
        self.errors = list(errors or [])

    def to_dict(self) -> dict[str, Any]:
        """Return the report as JSON-compatible data."""

        return _report_to_dict(self, _SYSTEM_REPORT_FIELDS)

    def to_json(self, **kwargs: Any) -> str:
        """Serialize the report to JSON."""

        return _report_to_json(self, _SYSTEM_REPORT_FIELDS, **kwargs)

    def to_dataframe(self) -> pd.DataFrame:
        """Return flattened report values as a DataFrame."""

        return _report_to_dataframe(self, _SYSTEM_REPORT_FIELDS)

    @staticmethod
    def _get_path(root: Any, path: str) -> Any:
        return _get_report_path(root, path)

    def _failures(
        self,
        *,
        thresholds: dict[str, float] | None = None,
        require_complete: bool = False,
        fail_on_boolean: bool = True,
    ) -> list[str]:
        failures: list[str] = []
        if fail_on_boolean and getattr(self.structure, "status", None) == "FAIL":
            failures.append("structure.status")
        if fail_on_boolean and getattr(self.accounting, "status", None) == "FAIL":
            failures.append("accounting.status")
        if fail_on_boolean:
            for name in ("input_balance", "output_balance"):
                check = getattr(self.accounting, name, None)
                if getattr(check, "status", None) == "FAIL":
                    failures.append(f"accounting.{name}.status")
        if fail_on_boolean:
            if getattr(self.coefficients, "status", None) == "FAIL":
                failures.append("coefficients.status")
            if getattr(self.stability, "invertible", None) is False:
                failures.append("stability.invertible")
            if getattr(self.stability, "status", None) == "FAIL":
                failures.append("stability.status")
        if require_complete:
            for name in ("input_balance", "output_balance"):
                if getattr(getattr(self.accounting, name, None), "status", None) == "SKIPPED":
                    failures.append(f"accounting.{name}.status")
            if getattr(self.accounting, "status", None) == "SKIPPED":
                failures.append("accounting.status")
            for name in ("coefficients", "stability"):
                if getattr(getattr(self, name, None), "status", None) == "SKIPPED":
                    failures.append(f"{name}.status")
        active_thresholds = dict(thresholds or {})
        if self.stability is not None:
            active_thresholds.setdefault("stability.spectral_radius", 1.0)
        for path, threshold in active_thresholds.items():
            value = self._get_path(self, path)
            if value is _MISSING or value is None:
                failures.append(f"threshold path unavailable: {path}")
                continue
            try:
                limit = float(threshold)
                numeric = float(value)
            except (TypeError, ValueError):
                failures.append(f"threshold path is not numeric: {path}")
                continue
            if not math.isfinite(limit) or not math.isfinite(numeric):
                failures.append(f"threshold path is non-finite: {path}")
                continue
            violated = (
                numeric >= limit
                if path.endswith("spectral_radius")
                else numeric > limit
            )
            if violated:
                failures.append(f"{path}={numeric} exceeds threshold {limit}")
        return failures

    def passed(
        self,
        thresholds: dict[str, float] | None = None,
        *,
        require_complete: bool = False,
        fail_on_boolean: bool = True,
    ) -> bool:
        """Return whether this SUT/MRIO report passes the selected gate."""

        return not self._failures(
            thresholds=thresholds,
            require_complete=require_complete,
            fail_on_boolean=fail_on_boolean,
        )

    def raise_for_status(
        self,
        *,
        thresholds: dict[str, float] | None = None,
        require_complete: bool = False,
        fail_on_boolean: bool = True,
    ) -> None:
        """Raise :class:`IOAuditError` when the selected gate fails."""

        failures = self._failures(
            thresholds=thresholds,
            require_complete=require_complete,
            fail_on_boolean=fail_on_boolean,
        )
        if failures:
            raise IOAuditError("IO system audit failed: " + "; ".join(failures))

    def summary(self) -> str:
        """Return a compact summary suitable for interactive inspection."""

        lines = [
            f"{self.system_type} Audit Report",
            "===========================",
            f"Structure                {getattr(self.structure, 'status', 'SKIPPED')}",
            f"Supporting inputs       {getattr(self.structure, 'supporting_status', 'SKIPPED')}",
            f"Accounting               {getattr(self.accounting, 'status', 'SKIPPED')}",
        ]
        for label, name in (("Input balance", "input_balance"), ("Output balance", "output_balance")):
            check = getattr(self.accounting, name, None)
            if check is None:
                continue
            lines.append(f"{label:<24} {getattr(check, 'status', 'SKIPPED')}")
            maximum = getattr(check, "max_relative_residual", None)
            if maximum is not None:
                lines.append(f"{label} max rel. residual {maximum:.6g}")
        if self.coefficients is not None:
            lines.append(f"Coefficients             {getattr(self.coefficients, 'status', 'SKIPPED')}")
        if self.stability is not None:
            lines.append(f"Stability                {getattr(self.stability, 'status', 'SKIPPED')}")
            rho = getattr(self.stability, "spectral_radius", None)
            if rho is not None:
                lines.append(f"Spectral radius          {rho:.6g}")
        if self.warnings:
            lines.append(f"Warnings                 {len(self.warnings)}")
        return "\n".join(lines)
