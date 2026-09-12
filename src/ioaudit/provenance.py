"""Deterministic input fingerprints and audit provenance."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import platform
import sys
from typing import Any

import numpy as np
import pandas as pd

from ._version import __version__
from .model import _TRADE_FLOW_FIELDS


def _canonical(value: Any) -> Any:
    """Convert supported IO inputs to stable JSON-compatible structures."""

    try:
        from scipy import sparse

        if sparse.issparse(value):
            matrix = value.tocoo(copy=True)
            matrix.sum_duplicates()
            entries = sorted(
                (
                    int(row),
                    int(column),
                    _canonical(item),
                )
                for row, column, item in zip(matrix.row, matrix.col, matrix.data)
            )
            return {"type": "sparse", "shape": list(matrix.shape), "entries": entries}
    except Exception:
        pass
    if isinstance(value, pd.DataFrame):
        return {
            "type": "DataFrame",
            "index": _canonical(value.index.tolist()),
            "columns": _canonical(value.columns.tolist()),
            "values": _canonical(value.to_numpy(copy=True)),
        }
    if isinstance(value, pd.Series):
        return {
            "type": "Series",
            "name": _canonical(value.name),
            "index": _canonical(value.index.tolist()),
            "values": _canonical(value.to_numpy(copy=True)),
        }
    if isinstance(value, np.ndarray):
        return {
            "type": "ndarray",
            "shape": list(value.shape),
            "values": _canonical(value.tolist()),
        }
    if isinstance(value, dict):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, np.generic):
        # ``longdouble.item()`` may return another NumPy scalar rather than a
        # Python scalar.  Recursing through ``item()`` therefore never reaches
        # the JSON-compatible branches on some NumPy versions.  Explicitly
        # normalize numeric scalar families instead.
        if np.issubdtype(value.dtype, np.bool_):
            return bool(value)
        if np.issubdtype(value.dtype, np.integer):
            return int(value)
        if np.issubdtype(value.dtype, np.floating):
            if value.dtype.itemsize > np.dtype(float).itemsize:
                return {"dtype": str(value.dtype), "value": str(value)}
            return _canonical(float(value))
        if np.issubdtype(value.dtype, np.complexfloating):
            return str(value)
        item = value.item()
        return item if not isinstance(item, np.generic) else str(value)
    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def input_hash(io: Any) -> str:
    """Return a SHA-256 fingerprint of all supplied IOSystem inputs."""

    trade = getattr(io, "trade", None)
    trade_payload = None
    if trade is not None:
        trade_payload = {
            name: _canonical(getattr(trade, name))
            for name in _TRADE_FLOW_FIELDS
        }
    payload = {
        "Z": _canonical(io.Z),
        "x": _canonical(io.x),
        "sectors": _canonical(io.sectors),
        "Y": _canonical(io.Y),
        "V": _canonical(io.V),
        "A_reference": _canonical(getattr(io, "A_reference", None)),
        "L_reference": _canonical(getattr(io, "L_reference", None)),
        "input_adjustments": _canonical(getattr(io, "input_adjustments", None)),
        "output_adjustments": _canonical(getattr(io, "output_adjustments", None)),
        "trade": trade_payload,
        "metadata": _canonical(getattr(io, "metadata", None)),
        "accounting": _canonical(
            io.accounting.to_dict() if getattr(io, "accounting", None) is not None else None
        ),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_provenance(
    io: Any,
    methods: Any,
    *,
    requested_numerical_method: str | None = None,
    accounting_tolerance: dict[str, float] | None = None,
    scale: Any = None,
    version: str = __version__,
) -> dict[str, Any]:
    """Build an audit manifest; the timestamp records when the audit ran."""

    scale_manifest = None
    if scale is not None:
        scale_manifest = {
            "candidate_factors": _canonical(getattr(scale, "candidate_factors", [])),
            "minimum_improvement": getattr(scale, "minimum_improvement", None),
            "minimum_global_coverage": getattr(scale, "minimum_global_coverage", None),
            "maximum_opposite_side_degradation": getattr(
                scale, "maximum_opposite_side_degradation", None
            ),
            "tolerance": _canonical(getattr(scale, "tolerance", None)),
            "rounding_context_available": getattr(
                scale, "rounding_context_available", False
            ),
            "cell_status": getattr(scale, "cell_status", None),
            "cell_reason": getattr(scale, "cell_reason", None),
            "reference_evidence_used": getattr(scale, "reference_evidence_used", False),
            "reference_evidence_reason": getattr(scale, "reference_evidence_reason", None),
        }
    selected_method = getattr(methods, "numerical_method", None)
    try:
        import scipy
    except Exception:
        scipy_version = None
    else:
        scipy_version = scipy.__version__
    return {
        "ioaudit_version": version,
        "input_hash": input_hash(io),
        "thresholds": {},
        "numerical_method": selected_method,
        "requested_numerical_method": requested_numerical_method,
        "selected_numerical_method": selected_method,
        "accounting_tolerance": _canonical(accounting_tolerance),
        "scale": scale_manifest,
        "environment": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "numpy_version": np.__version__,
            "pandas_version": pd.__version__,
            "scipy_version": scipy_version,
            "platform": sys.platform,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
