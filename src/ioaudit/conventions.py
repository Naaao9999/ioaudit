"""Accounting conventions used by an IO audit."""

from dataclasses import dataclass

from .exceptions import IOValidationError


TRANSACTION_SCOPES = frozenset({"domestic", "total", "unknown"})
IMPORT_TREATMENTS = frozenset({"competitive", "noncompetitive", "none", "unknown"})
FLOW_SIGNS = frozenset({"negative", "positive", "unknown"})
TRADE_REPRESENTATIONS = frozenset({"embedded", "outflows_in_Y", "separate", "unknown"})
EXTERNAL_FLOW_SCOPES = frozenset({"international", "interregional", "both", "unknown"})
INPUT_REPRESENTATIONS = frozenset({"complete", "adjustments_required", "unknown"})
OUTPUT_REPRESENTATIONS = frozenset({"complete", "adjustments_required", "unknown"})


def _validate_choice(value: object, allowed: frozenset[str], message: str) -> None:
    """Raise the public validation error for a malformed choice value."""

    if not isinstance(value, str) or value not in allowed:
        raise IOValidationError(message)


@dataclass(frozen=True)
class AccountingConvention:
    """Declare the accounting interpretation of a supplied IO table.

    ``ioaudit`` records this declaration and never infers import treatment
    merely from the presence of an imports vector.  The plain constructor is
    deliberately conservative: omitted semantic fields become ``"unknown"``
    and affected accounting checks are skipped.  The
    ``output_representation`` default of ``"complete"`` preserves the
    existing convention that no separate output-adjustment block is declared;
    use ``"unknown"`` when that relationship is not known.  For a domestic table,
    competitive imports are interpreted according to ``inflow_sign``:
    ``negative`` means the supplied vector is ``-M`` and is added to the
    output identity, ``positive`` means it is ``M`` and is subtracted, and
    ``unknown`` disables that adjusted check.  ``input_representation``
    declares whether ``V`` is complete, requires an explicit user-specific
    adjustment, or is unknown.  ``output_representation`` declares whether
    no separate signed row-side adjustment is expected, or whether an
    explicit ``IOSystem.output_adjustments`` block is required.
    Noncompetitive treatment requires explicit sector vectors for both
    imports and exports.  Missing or unspecified information causes the
    affected check to be SKIPPED rather than guessed.
    """

    transaction_scope: str = "unknown"
    import_treatment: str = "unknown"
    trade_representation: str = "unknown"
    external_flow_scope: str = "unknown"
    inflow_sign: str = "unknown"
    outflow_sign: str = "unknown"
    input_representation: str = "unknown"
    output_representation: str = "complete"

    def __post_init__(self) -> None:
        _validate_choice(
            self.transaction_scope,
            TRANSACTION_SCOPES,
            "transaction_scope must be 'domestic', 'total', or 'unknown'",
        )
        _validate_choice(
            self.import_treatment,
            IMPORT_TREATMENTS,
            "import_treatment must be 'competitive', 'noncompetitive', 'none', or 'unknown'",
        )
        _validate_choice(
            self.trade_representation,
            TRADE_REPRESENTATIONS,
            "trade_representation must be 'embedded', 'outflows_in_Y', 'separate', or 'unknown'",
        )
        _validate_choice(
            self.external_flow_scope,
            EXTERNAL_FLOW_SCOPES,
            "external_flow_scope must be 'international', 'interregional', 'both', or 'unknown'",
        )
        _validate_choice(
            self.inflow_sign,
            FLOW_SIGNS,
            "inflow_sign must be 'negative', 'positive', or 'unknown'",
        )
        _validate_choice(
            self.outflow_sign,
            FLOW_SIGNS,
            "outflow_sign must be 'negative', 'positive', or 'unknown'",
        )
        _validate_choice(
            self.input_representation,
            INPUT_REPRESENTATIONS,
            "input_representation must be 'complete', 'adjustments_required', or 'unknown'",
        )
        _validate_choice(
            self.output_representation,
            OUTPUT_REPRESENTATIONS,
            "output_representation must be 'complete', 'adjustments_required', or 'unknown'",
        )

    @property
    def name(self) -> str:
        """Return a stable human-readable convention name."""

        return f"{self.transaction_scope}/{self.import_treatment}"

    @classmethod
    def domestic_competitive(
        cls,
        *,
        inflow_sign: str = "unknown",
        trade_representation: str = "unknown",
        external_flow_scope: str = "unknown",
        outflow_sign: str = "unknown",
        input_representation: str = "unknown",
        output_representation: str = "complete",
    ) -> "AccountingConvention":
        """Return a domestic competitive-import convention.

        The preset fixes only the semantics guaranteed by its name:
        ``transaction_scope="domestic"`` and
        ``import_treatment="competitive"``.  Trade representation, signs,
        and input completeness remain ``"unknown"`` unless explicitly
        declared by the caller.
        """

        return cls(
            transaction_scope="domestic",
            import_treatment="competitive",
            trade_representation=trade_representation,
            external_flow_scope=external_flow_scope,
            inflow_sign=inflow_sign,
            outflow_sign=outflow_sign,
            input_representation=input_representation,
            output_representation=output_representation,
        )

    @classmethod
    def domestic_noncompetitive(
        cls,
        *,
        trade_representation: str = "unknown",
        external_flow_scope: str = "unknown",
        inflow_sign: str = "unknown",
        outflow_sign: str = "unknown",
        input_representation: str = "unknown",
        output_representation: str = "complete",
    ) -> "AccountingConvention":
        """Return a domestic noncompetitive-import convention.

        Only the domestic transaction scope and noncompetitive import
        treatment are fixed by this preset.  All other semantic fields must
        be declared when they are known from the source table.
        """

        return cls(
            transaction_scope="domestic",
            import_treatment="noncompetitive",
            trade_representation=trade_representation,
            external_flow_scope=external_flow_scope,
            inflow_sign=inflow_sign,
            outflow_sign=outflow_sign,
            input_representation=input_representation,
            output_representation=output_representation,
        )

    @classmethod
    def total_transactions(cls) -> "AccountingConvention":
        """Return a total-transactions convention with input completeness unspecified.

        The table scope and absence of a separate import treatment are fixed
        by the preset name.  Whether the supplied value-added block closes the
        input identity remains source-table metadata and is therefore left
        as ``"unknown"``.  Callers must declare completeness explicitly when
        they want the input-side identity to be evaluated.
        """

        return cls(
            transaction_scope="total",
            import_treatment="none",
            trade_representation="embedded",
            external_flow_scope="unknown",
            inflow_sign="unknown",
            outflow_sign="unknown",
            input_representation="unknown",
            output_representation="complete",
        )

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-compatible representation."""

        return {
            "transaction_scope": self.transaction_scope,
            "import_treatment": self.import_treatment,
            "trade_representation": self.trade_representation,
            "external_flow_scope": self.external_flow_scope,
            "inflow_sign": self.inflow_sign,
            "outflow_sign": self.outflow_sign,
            "input_representation": self.input_representation,
            "output_representation": self.output_representation,
            "name": self.name,
        }
