"""Data model for a single input-output system."""

from __future__ import annotations

from collections.abc import Sequence
import copy
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .conventions import AccountingConvention
from .exceptions import IOValidationError


def _copy_value(value: Any, name: str, *, allow_none: bool = True) -> Any:
    if value is None and allow_none:
        return None
    if isinstance(value, pd.DataFrame):
        return value.copy(deep=True)
    if isinstance(value, pd.Series):
        return value.copy(deep=True)
    try:
        # scipy sparse matrices expose copy() and are useful for the iterative
        # route.  Import scipy lazily so the model remains easy to inspect.
        from scipy import sparse

        if sparse.issparse(value):
            return value.copy()
    except Exception:
        pass
    if isinstance(value, np.ndarray):
        return value.copy()
    if isinstance(value, (list, tuple)):
        return copy.deepcopy(list(value))
    raise IOValidationError(
        f"{name} must be a numpy.ndarray, pandas object, sparse matrix, or sequence"
    )


@dataclass(frozen=True)
class TradeFlows:
    """External and interregional flows for one IO system.

    Each side may be supplied either as a combined vector or as the two
    explicit components.  The audit never adds a combined and split
    representation together; conflicting representations are reported and
    the affected accounting check is skipped.
    """

    interregional_inflows: Any = None
    international_imports: Any = None
    interregional_outflows: Any = None
    international_exports: Any = None
    combined_inflows: Any = None
    combined_outflows: Any = None

    def __post_init__(self) -> None:
        for name in (
            "interregional_inflows",
            "international_imports",
            "interregional_outflows",
            "international_exports",
            "combined_inflows",
            "combined_outflows",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _copy_value(value, name))

    @property
    def representation_conflicts(self) -> list[str]:
        """Return sides where combined and split values coexist."""

        conflicts: list[str] = []
        if self.combined_inflows is not None and (
            self.interregional_inflows is not None or self.international_imports is not None
        ):
            conflicts.append("inflows")
        if self.combined_outflows is not None and (
            self.interregional_outflows is not None or self.international_exports is not None
        ):
            conflicts.append("outflows")
        return conflicts

    @property
    def has_any(self) -> bool:
        """Whether at least one flow vector was supplied."""

        return any(
            getattr(self, name) is not None
            for name in (
                "interregional_inflows",
                "international_imports",
                "interregional_outflows",
                "international_exports",
                "combined_inflows",
                "combined_outflows",
            )
        )


class IOSystem:
    """Container for one IO table and its optional supporting data.

    The constructor copies array-like inputs.  The original objects therefore
    remain unchanged when an audit computes coefficients or numerical results.
    Structural validation is intentionally performed by :func:`ioaudit.audit`
    so malformed shapes can be reported as diagnostics.
    """

    def __init__(
        self,
        Z: Any,
        x: Any,
        sectors: Sequence[Any],
        Y: Any = None,
        V: Any = None,
        *,
        trade: TradeFlows | None = None,
        input_adjustments: Any = None,
        A_reference: Any = None,
        L_reference: Any = None,
        metadata: dict[str, Any] | None = None,
        accounting: AccountingConvention | None = None,
    ) -> None:
        if Z is None:
            raise IOValidationError("Z is required")
        if x is None:
            raise IOValidationError("x is required")
        if sectors is None:
            raise IOValidationError("sectors is required")
        if accounting is not None and not isinstance(accounting, AccountingConvention):
            raise IOValidationError("accounting must be an AccountingConvention or None")
        if trade is not None and not isinstance(trade, TradeFlows):
            raise IOValidationError("trade must be a TradeFlows instance or None")

        self.Z = _copy_value(Z, "Z", allow_none=False)
        self.x = _copy_value(x, "x", allow_none=False)
        try:
            self.sectors = list(sectors)
        except Exception as exc:
            raise IOValidationError("sectors must be a finite sequence") from exc
        self.Y = _copy_value(Y, "Y")
        self.V = _copy_value(V, "V")
        self.input_adjustments = _copy_value(input_adjustments, "input_adjustments")
        self.A_reference = _copy_value(A_reference, "A_reference")
        self.L_reference = _copy_value(L_reference, "L_reference")
        self.trade = TradeFlows(**trade.__dict__) if trade is not None else None
        if metadata is None:
            self.metadata = {}
        else:
            try:
                self.metadata = dict(metadata)
            except (TypeError, ValueError) as exc:
                raise IOValidationError("metadata must be a mapping") from exc
        self.accounting = accounting

    def __repr__(self) -> str:
        return (
            f"IOSystem(n_sectors={len(self.sectors)}, "
            f"has_Y={self.Y is not None}, has_V={self.V is not None})"
        )
