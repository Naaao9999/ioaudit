"""Accounting identity diagnostics for a single IO table."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .conventions import AccountingConvention
from .exceptions import IOValidationError
from .structure import _all_finite, _is_sparse, _numeric_array, _shape_of


def _axis_sum(value: Any, axis: int) -> np.ndarray:
    """Sum a dense or sparse matrix along one axis without densifying input."""

    summed = value.sum(axis=axis)
    return np.asarray(summed, dtype=float).reshape(-1)


@dataclass
class BalanceDiagnostics:
    """Residuals for one accounting identity."""

    status: str = "SKIPPED"
    equation: str = ""
    sector_residual: list[float] = field(default_factory=list)
    absolute_residual: list[float] = field(default_factory=list)
    relative_residual: list[float] = field(default_factory=list)
    mae: float | None = None
    rmse: float | None = None
    max_absolute_residual: float | None = None
    max_relative_residual: float | None = None
    reason: str | None = None

    @property
    def sector_level_residual(self) -> list[float]:
        """Alias for the sector-level signed residual vector."""

        return self.sector_residual

    @property
    def MAE(self) -> float | None:
        """Upper-case alias matching the conventional metric name."""

        return self.mae

    @property
    def RMSE(self) -> float | None:
        """Upper-case alias matching the conventional metric name."""

        return self.rmse


@dataclass
class AccountingDiagnostics:
    """Input-side and output-side balance results."""

    status: str = "SKIPPED"
    convention: dict[str, str] | None = None
    formula: str | None = None
    input_balance: BalanceDiagnostics = field(default_factory=BalanceDiagnostics)
    output_balance: BalanceDiagnostics = field(default_factory=BalanceDiagnostics)
    trade_adjusted_input_balance: BalanceDiagnostics = field(default_factory=BalanceDiagnostics)
    by_sector: list[dict[str, Any]] = field(default_factory=list)
    max_relative_residual: float | None = None
    convention_required: bool = True
    import_adjustment_applied: bool = False
    input_adjustment_applied: bool = False
    external_inputs_used: bool = False
    input_adjustments_used: bool = False
    imports_used: bool = False
    exports_used: bool = False
    inflows_used: bool = False
    outflows_used: bool = False
    tolerance: dict[str, float] | None = None
    notes: list[str] = field(default_factory=list)


def _vector(value: Any, *, expected: str, n: int) -> tuple[np.ndarray | None, str | None]:
    if value is None:
        return None, f"{expected} was not supplied"
    try:
        array, bad = _numeric_array(value)
    except Exception as exc:
        return None, f"{expected} could not be read: {exc}"
    if array is None or bad or not _all_finite(array):
        return None, f"{expected} contains non-numeric or missing values"
    if expected == "Y":
        if getattr(array, "ndim", None) == 1 and array.shape == (n,):
            return np.asarray(array, dtype=float), None
        if getattr(array, "ndim", None) == 2 and array.shape[0] == n:
            return _axis_sum(array, 1), None
        return None, "Y must have shape (n,) or (n, k)"
    if expected == "V":
        if getattr(array, "ndim", None) == 1 and array.shape == (n,):
            return np.asarray(array, dtype=float), None
        if getattr(array, "ndim", None) == 2 and array.shape[1] == n:
            return _axis_sum(array, 0), None
        return None, "V must have shape (n,) or (m, n)"
    return None, f"unsupported accounting input {expected}"


def _aggregate_sector_vector(value: Any, *, name: str, n: int) -> tuple[np.ndarray | None, str | None]:
    """Read an explicit one-vector flow without guessing axes."""

    if value is None:
        return None, f"{name} was not supplied"
    try:
        array, bad = _numeric_array(value)
    except Exception as exc:
        return None, f"{name} could not be read: {exc}"
    if array is None or bad or not _all_finite(array):
        return None, f"{name} contains non-numeric or missing values"
    if getattr(array, "ndim", None) != 1 or array.shape != (n,):
        return None, f"{name} must have explicit shape (n,) for v0.1 accounting"
    return np.asarray(array, dtype=float), None


def _input_adjustment_vector(
    value: Any, *, name: str, n: int
) -> tuple[np.ndarray | None, str | None]:
    """Read signed user-specific input adjustments without guessing an axis.

    A one-dimensional value is already aggregated by user sector.  A
    two-dimensional value is interpreted as rows of external inputs and
    columns of purchasing sectors, so it is summed over rows.  Other shapes
    are deliberately rejected because v0.1 cannot infer their meaning.
    """

    if value is None:
        return None, f"{name} was not supplied"
    try:
        array, bad = _numeric_array(value)
    except Exception as exc:
        return None, f"{name} could not be read: {exc}"
    if array is None or bad or not _all_finite(array):
        return None, f"{name} contains non-numeric or missing values"
    shape = _shape_of(array)
    if len(shape) == 1 and shape == (n,):
        return np.asarray(array, dtype=float), None
    if len(shape) == 2 and shape[1] == n:
        return _axis_sum(array, 0), None
    return None, f"{name} must have shape (n,) or (m, n)"


def _resolve_input_adjustment(
    io: Any, *, n: int
) -> tuple[np.ndarray | None, str | None, str | None]:
    """Resolve one explicit input-side adjustment source.

    The two public fields are alternative representations.  Supplying both
    is ambiguous and therefore skips the affected identity instead of adding
    them and risking double counting.
    """

    external = getattr(io, "external_inputs_by_user", None)
    adjustments = getattr(io, "input_adjustments_by_user", None)
    if external is not None and adjustments is not None:
        return None, "external_inputs_by_user and input_adjustments_by_user were supplied together", "conflict"
    if adjustments is not None:
        vector, reason = _input_adjustment_vector(
            adjustments, name="input_adjustments_by_user", n=n
        )
        return vector, reason, "input_adjustments_by_user"
    if external is not None:
        vector, reason = _input_adjustment_vector(
            external, name="external_inputs_by_user", n=n
        )
        return vector, reason, "external_inputs_by_user"
    return None, "no input-side adjustment was supplied", None


def _balance(
    residual: np.ndarray,
    x: np.ndarray,
    equation: str,
    tolerance: dict[str, float] | None = None,
) -> BalanceDiagnostics:
    residual = np.asarray(residual, dtype=float)
    absolute = np.abs(residual)
    relative = np.zeros_like(absolute)
    nonzero_x = x != 0
    np.divide(absolute, np.abs(x), out=relative, where=nonzero_x)
    relative[(~nonzero_x) & (absolute != 0)] = np.inf
    finite_rel = relative[np.isfinite(relative)]
    exact = bool(
        np.all(
            absolute
            <= np.finfo(float).eps * np.maximum(1.0, np.abs(x))
        )
    )
    status = "PASS" if exact else "AVAILABLE"
    if tolerance is not None:
        absolute_limit = float(tolerance.get("absolute", 0.0))
        relative_limit = float(tolerance.get("relative", 0.0))
        rounding_unit = float(tolerance.get("rounding_unit", 0.0))
        allowed = np.maximum(
            np.maximum(absolute_limit, relative_limit * np.abs(x)), rounding_unit
        )
        within_tolerance = bool(np.all(absolute <= allowed))
        if not exact and within_tolerance:
            status = "ROUNDING_LEVEL"
        elif not within_tolerance:
            status = "FAIL"
    return BalanceDiagnostics(
        status=status,
        equation=equation,
        sector_residual=residual.tolist(),
        absolute_residual=absolute.tolist(),
        relative_residual=relative.tolist(),
        mae=float(np.mean(absolute)) if absolute.size else 0.0,
        rmse=float(np.sqrt(np.mean(residual**2))) if residual.size else 0.0,
        max_absolute_residual=float(np.max(absolute)) if absolute.size else 0.0,
        max_relative_residual=float(np.max(finite_rel))
        if finite_rel.size and not np.isinf(relative).any()
        else (float("inf") if relative.size else 0.0),
    )


def _normalize_tolerance(value: Any) -> dict[str, float] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise IOValidationError("accounting_tolerance must be a mapping or None")
    allowed = {"absolute", "relative", "rounding_unit"}
    unknown = set(value) - allowed
    if unknown:
        raise IOValidationError(
            "accounting_tolerance has unknown fields: " + ", ".join(sorted(map(str, unknown)))
        )
    normalized: dict[str, float] = {}
    for name in allowed:
        raw = value.get(name, 0.0)
        if isinstance(raw, bool):
            raise IOValidationError(f"accounting_tolerance.{name} must be finite and non-negative")
        try:
            numeric = float(raw)
        except (TypeError, ValueError) as exc:
            raise IOValidationError(f"accounting_tolerance.{name} must be numeric") from exc
        if not np.isfinite(numeric) or numeric < 0.0:
            raise IOValidationError(f"accounting_tolerance.{name} must be finite and non-negative")
        normalized[name] = numeric
    return normalized


def _trade_side(
    trade: Any,
    *,
    side: str,
    scope: str,
    n: int,
) -> tuple[np.ndarray | None, str | None, str | None]:
    """Resolve one flow side as combined or the required split components."""

    if trade is None:
        return None, f"trade.{side} was not supplied", None
    if scope not in {"international", "interregional", "both"}:
        return None, "external_flow_scope='unknown'; trade scope is not declared", None
    if side == "inflows":
        combined_name = "combined_inflows"
        components = {
            "international": (("international_imports",), "international_imports"),
            "interregional": (("interregional_inflows",), "interregional_inflows"),
            "both": (("interregional_inflows", "international_imports"), "split inflows"),
        }
    else:
        combined_name = "combined_outflows"
        components = {
            "international": (("international_exports",), "international_exports"),
            "interregional": (("interregional_outflows",), "interregional_outflows"),
            "both": (("interregional_outflows", "international_exports"), "split outflows"),
        }
    combined = getattr(trade, combined_name)
    names, label = components[scope]
    present = [getattr(trade, name) is not None for name in names]
    # A combined flow must never coexist with either of its split source
    # components.  Check both components even when the declared scope uses
    # only one of them, otherwise an accidental duplicate can be silently
    # ignored by the accounting path.
    all_split_names = (
        ("interregional_inflows", "international_imports")
        if side == "inflows"
        else ("interregional_outflows", "international_exports")
    )
    if combined is not None and any(getattr(trade, name) is not None for name in all_split_names):
        return None, f"combined and split {side} were supplied together", None
    if combined is not None:
        vector, reason = _aggregate_sector_vector(combined, name=f"trade.{combined_name}", n=n)
        return vector, reason, combined_name if vector is not None else None
    if not all(present):
        missing = [name for name, is_present in zip(names, present) if not is_present]
        return None, f"missing trade.{side} component(s): {', '.join(missing)}", None
    vectors: list[np.ndarray] = []
    for name in names:
        vector, reason = _aggregate_sector_vector(getattr(trade, name), name=f"trade.{name}", n=n)
        if vector is None:
            return None, reason, None
        vectors.append(vector)
    return np.sum(vectors, axis=0), None, label


def _legacy_or_explicit_trade(io: Any) -> tuple[Any, str | None]:
    """Return canonical trade and flag simultaneous legacy/new inputs."""

    trade = getattr(io, "trade", None)
    if getattr(io, "_trade_explicit", False) and getattr(io, "_legacy_trade_fields_supplied", False):
        return trade, "trade and legacy imports/exports were supplied together"
    return trade, None


def _inflow_adjustment(raw: np.ndarray, sign: str) -> np.ndarray | None:
    if sign == "negative":
        return raw
    if sign == "positive":
        return -raw
    return None


def _outflow_adjustment(raw: np.ndarray, sign: str) -> np.ndarray | None:
    if sign == "positive":
        return raw
    if sign == "negative":
        return -raw
    return None


def diagnose_accounting(
    z: Any,
    x: np.ndarray | None,
    io: Any,
    convention: AccountingConvention | None,
    sectors: list[Any],
    *,
    tolerance: dict[str, float] | None = None,
    components: Any = None,
) -> AccountingDiagnostics:
    """Compute declared input/output identities without inferring trade."""

    result = AccountingDiagnostics(tolerance=_normalize_tolerance(tolerance))
    if convention is None:
        result.notes.append("AccountingConvention was not supplied; accounting checks are SKIPPED")
        return result
    result.convention = convention.to_dict()
    z_shape = _shape_of(z) if z is not None else ()
    if z is None or x is None or len(z_shape) != 2 or z_shape[0] != z_shape[1] or getattr(x, "ndim", None) != 1 or len(x) != z_shape[0]:
        result.notes.append("Z and x do not have a safe square/numeric shape")
        return result
    n = z_shape[0]
    if not _all_finite(z) or not _all_finite(x):
        result.notes.append("Z or x contains NaN/Inf")
        return result

    f, y_reason = _vector(io.Y, expected="Y", n=n)
    v, v_reason = _vector(io.V, expected="V", n=n)
    component_risks = getattr(components, "double_count_risk", []) if components is not None else []
    y_subtotal_risk = any(item.get("field") == "Y" for item in component_risks)
    v_subtotal_risk = any(item.get("field") == "V" for item in component_risks)
    if y_subtotal_risk:
        result.notes.append(
            "Y subtotal/total component detected; output balance is SKIPPED rather than auto-excluding a column"
        )
    if v_subtotal_risk:
        result.notes.append(
            "V subtotal/total component detected; input balance is SKIPPED rather than auto-excluding a row"
        )
    trade, trade_conflict = _legacy_or_explicit_trade(io)
    if trade_conflict:
        result.notes.append(trade_conflict)
    row_sum = _axis_sum(z, 1)
    output_residual: np.ndarray | None = None
    output_equation = ""
    representation = convention.trade_representation
    legacy_noncompetitive = (
        not getattr(io, "_trade_explicit", False)
        and getattr(io, "_legacy_trade_fields_supplied", False)
        and convention.import_treatment == "noncompetitive"
        and getattr(io, "exports", None) is not None
        and not getattr(convention, "_inflow_sign_explicit", False)
    )
    if legacy_noncompetitive and representation == "outflows_in_Y":
        # Preserve the pre-TradeFlows call where explicit imports/exports were
        # both used as positive magnitudes.
        representation = "separate"
        result.notes.append("legacy imports/exports mapped to separate trade representation")
    if trade_conflict:
        representation = "unknown"
    inflow_sign = "positive" if legacy_noncompetitive else convention.inflow_sign

    if f is None:
        result.formula = "output: SKIPPED because Y is unavailable"
        result.output_balance.reason = y_reason
    elif y_subtotal_risk:
        result.formula = "output: SKIPPED because Y contains a possible subtotal/total component"
        result.output_balance.reason = (
            "Y contains a possible subtotal/total component; the correct component subset was not inferred"
        )
    elif representation == "unknown":
        result.formula = "output: SKIPPED because trade_representation='unknown'"
        result.output_balance.reason = "trade representation in Y is unknown; no output-side inference is performed"
    elif (
        convention.transaction_scope == "unknown"
        or convention.import_treatment == "unknown"
    ):
        result.formula = (
            "output: SKIPPED because transaction_scope or import_treatment is unknown"
        )
        result.output_balance.reason = (
            "transaction_scope/import_treatment is unknown; no output-side accounting equation is inferred"
        )
    elif convention.transaction_scope == "total" or convention.import_treatment == "none":
        result.formula = (
            "output: x = row_sum(Z) + row_sum(Y); "
            "input: x = column_sum(Z) + column_sum(V)"
        )
        output_equation = "x = row_sum(Z) + row_sum(Y)"
        output_residual = x - (row_sum + f)
        if trade is not None and trade.has_any:
            result.notes.append("trade flows were supplied but excluded by the declared scope/treatment")
        result.notes.append("import_sign not applicable")
        result.notes.append("inflow_sign not applicable")
    elif representation == "embedded":
        result.formula = (
            "output: x = row_sum(Z) + row_sum(Y) (trade embedded in Y); "
            "input: x = column_sum(Z) + column_sum(V)"
        )
        output_equation = "x = row_sum(Z) + row_sum(Y)"
        output_residual = x - (row_sum + f)
        result.notes.append("trade flows were supplied but excluded because trade_representation='embedded'") if trade is not None and trade.has_any else None
        result.notes.append("inflow_sign not applicable")
        result.notes.append("outflow_sign not applicable")
    else:
        inflows, inflow_reason, inflow_label = _trade_side(
            trade, side="inflows", scope=convention.external_flow_scope, n=n
        )
        if inflows is None:
            result.output_balance.reason = inflow_reason
        else:
            inflow_adjustment = _inflow_adjustment(inflows, inflow_sign)
            if inflow_adjustment is None:
                result.formula = "output: SKIPPED because inflow_sign='unknown'"
                result.output_balance.reason = "inflow_sign='unknown'; no sign inference is performed"
            else:
                result.inflows_used = True
                result.imports_used = True
                if representation == "outflows_in_Y":
                    if inflow_label == "international_imports" and inflow_sign == "negative":
                        output_equation = "x = row_sum(Z) + row_sum(Y) + imports (imports are signed)"
                        result.formula = (
                            "output: x = row_sum(Z) + row_sum(Y) + imports (imports are signed); "
                            "input: x = column_sum(Z) + column_sum(V)"
                        )
                    elif inflow_label == "international_imports" and inflow_sign == "positive":
                        output_equation = "x = row_sum(Z) + row_sum(Y) - imports"
                        result.formula = (
                            "output: x = row_sum(Z) + row_sum(Y) - imports (positive magnitude); "
                            "input: x = column_sum(Z) + column_sum(V)"
                        )
                    else:
                        output_equation = f"x = row_sum(Z) + row_sum(Y) - inflow ({inflow_label})"
                        result.formula = (
                            "output: x = row_sum(Z) + row_sum(Y) - inflow; "
                            "input: x = column_sum(Z) + column_sum(V)"
                        )
                    output_residual = x - (row_sum + f + inflow_adjustment)
                    result.import_adjustment_applied = True
                    result.notes.append("outflow_sign not applicable")
                else:
                    outflows, outflow_reason, outflow_label = _trade_side(
                        trade, side="outflows", scope=convention.external_flow_scope, n=n
                    )
                    if outflows is None:
                        result.output_balance.reason = outflow_reason
                    else:
                        outflow_adjustment = _outflow_adjustment(outflows, convention.outflow_sign)
                        if outflow_adjustment is None:
                            result.formula = "output: SKIPPED because outflow_sign='unknown'"
                            result.output_balance.reason = "outflow_sign='unknown'; no sign inference is performed"
                        else:
                            result.outflows_used = True
                            result.exports_used = True
                            output_equation = (
                                "x + imports = row_sum(Z) + row_sum(Y) + exports"
                                if legacy_noncompetitive
                                else f"x = row_sum(Z) + row_sum(Y) + outflow ({outflow_label}) - inflow ({inflow_label})"
                            )
                            output_residual = x - (row_sum + f + outflow_adjustment + inflow_adjustment)
                            result.formula = (
                                "output: x = row_sum(Z) + row_sum(Y) + outflow - inflow; "
                                "input: x = column_sum(Z) + column_sum(V)"
                            )
                            result.import_adjustment_applied = True
    if result.formula is None:
        result.formula = "output: x = row_sum(Z) + row_sum(Y)"
    if output_residual is not None:
        result.output_balance = _balance(
            output_residual, x, output_equation, result.tolerance
        )

    input_adjustment, input_adjustment_reason, input_adjustment_source = (
        _resolve_input_adjustment(io, n=n)
    )
    input_equation = "input: SKIPPED"
    if v_subtotal_risk:
        result.input_balance.reason = (
            "V contains a possible subtotal/total component; the correct component subset was not inferred"
        )
        input_equation = "input: SKIPPED because V contains a possible subtotal/total component"
    elif v is None:
        result.input_balance.reason = v_reason
        input_equation = "input: SKIPPED because V is unavailable"
    elif convention.input_representation == "unknown":
        result.input_balance.reason = (
            "input_representation='unknown'; the completeness of V and any input-side adjustments is not declared"
        )
        input_equation = "input: SKIPPED because input_representation='unknown'"
    elif convention.input_representation == "complete":
        if input_adjustment_source is not None:
            result.input_balance.reason = (
                "input-side adjustment was supplied but input_representation='complete'; "
                "the adjustment's relationship to V is ambiguous"
            )
            input_equation = "input: SKIPPED because a complete V conflicts with supplied input adjustment"
        else:
            input_equation = "input: x = column_sum(Z) + column_sum(V)"
            result.input_balance = _balance(
                x - (_axis_sum(z, 0) + v),
                x,
                "x = column_sum(Z) + column_sum(V)",
                result.tolerance,
            )
    elif convention.input_representation == "adjustments_required":
        if input_adjustment is None:
            result.input_balance.reason = (
                "input_representation='adjustments_required' but no valid signed "
                "external input adjustment was supplied"
            )
            input_equation = "input: SKIPPED because input-side adjustment is unavailable"
        else:
            result.input_adjustment_applied = True
            result.input_adjustments_used = input_adjustment_source == "input_adjustments_by_user"
            result.external_inputs_used = input_adjustment_source == "external_inputs_by_user"
            input_equation = (
                "input: x = column_sum(Z) + column_sum(V) + input_adjustment"
            )
            result.input_balance = _balance(
                x - (_axis_sum(z, 0) + v + input_adjustment),
                x,
                "x = column_sum(Z) + column_sum(V) + input_adjustment",
                result.tolerance,
            )
    else:
        result.input_balance.reason = (
            f"unsupported input_representation={convention.input_representation!r}"
        )
        input_equation = "input: SKIPPED because input_representation is unsupported"

    if input_adjustment_reason and input_adjustment_source is not None:
        result.notes.append(input_adjustment_reason)
    if input_adjustment_source is not None and input_adjustment is None:
        result.input_balance.reason = input_adjustment_reason
    if "input:" in result.formula:
        output_formula = result.formula.split("; input:", 1)[0]
    else:
        output_formula = result.formula
    result.formula = f"{output_formula}; {input_equation}"
    result.trade_adjusted_input_balance.reason = (
        "SKIPPED: product/commodity inflows are not reused as user-specific inputs; "
        "use input_representation='adjustments_required' with an explicit input-side adjustment"
    )

    balances = [result.input_balance, result.output_balance]
    available = [balance for balance in balances if balance.status != "SKIPPED"]
    if not available:
        result.notes.append("Neither an auditable Y nor V was available")
        return result
    result.status = "AVAILABLE"
    residuals = [balance.max_relative_residual for balance in available if balance.max_relative_residual is not None]
    result.max_relative_residual = max(residuals) if residuals else None
    if len(sectors) != n:
        result.notes.append("by_sector omitted because sector IDs are not aligned with Z")
        return result
    for index, sector in enumerate(sectors):
        row: dict[str, Any] = {"sector": sector}
        if result.input_balance.status != "SKIPPED":
            row["input_residual"] = result.input_balance.sector_residual[index]
            row["input_absolute_residual"] = result.input_balance.absolute_residual[index]
            row["input_relative_residual"] = result.input_balance.relative_residual[index]
        if result.output_balance.status != "SKIPPED":
            row["output_residual"] = result.output_balance.sector_residual[index]
            row["output_absolute_residual"] = result.output_balance.absolute_residual[index]
            row["output_relative_residual"] = result.output_balance.relative_residual[index]
        result.by_sector.append(row)
    return result
