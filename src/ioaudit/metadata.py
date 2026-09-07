"""Semantic metadata completeness diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetadataDiagnostics:
    """Record whether the table carries enough semantic context to reproduce use."""

    status: str = "WARNING"
    values: dict[str, Any] = field(default_factory=dict)
    required_fields: list[str] = field(
        default_factory=lambda: ["year", "unit", "price_basis"]
    )
    recommended_fields: list[str] = field(
        default_factory=lambda: ["currency", "valuation"]
    )
    missing_required: list[str] = field(default_factory=list)
    missing_recommended: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def diagnose_metadata(metadata: Any) -> MetadataDiagnostics:
    """Report missing semantic metadata without inferring any values."""

    result = MetadataDiagnostics()
    if not isinstance(metadata, dict):
        result.missing_required = list(result.required_fields)
        result.missing_recommended = list(result.recommended_fields)
        result.notes.append("metadata was not supplied")
        return result
    result.values = dict(metadata)

    def _missing(name: str) -> bool:
        value = metadata.get(name)
        return value is None or (isinstance(value, str) and not value.strip())

    result.missing_required = [name for name in result.required_fields if _missing(name)]
    result.missing_recommended = [name for name in result.recommended_fields if _missing(name)]
    if result.missing_required:
        result.notes.append("missing required semantic metadata: " + ", ".join(result.missing_required))
    if result.missing_recommended:
        result.notes.append("missing recommended semantic metadata: " + ", ".join(result.missing_recommended))
    result.status = "PASS" if not result.missing_required else "WARNING"
    return result
