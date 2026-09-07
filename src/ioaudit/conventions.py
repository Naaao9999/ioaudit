"""Accounting conventions used by an IO audit."""

from dataclasses import dataclass

from .exceptions import IOValidationError


TRANSACTION_SCOPES = frozenset({"domestic", "total"})
IMPORT_TREATMENTS = frozenset({"competitive", "noncompetitive", "none"})
IMPORT_SIGNS = frozenset({"negative", "positive", "unknown"})
TRADE_REPRESENTATIONS = frozenset({"embedded", "outflows_in_Y", "separate", "unknown"})
EXTERNAL_FLOW_SCOPES = frozenset({"international", "interregional", "both"})


@dataclass(frozen=True)
class AccountingConvention:
    """Declare the accounting interpretation of a supplied IO table.

    ``ioaudit`` records this declaration and never infers import treatment
    merely from the presence of an imports vector.  For a domestic table,
    competitive imports are interpreted according to ``inflow_sign``:
    ``negative`` means the supplied vector is ``-M`` and is added to the
    output identity, ``positive`` means it is ``M`` and is subtracted, and
    ``unknown`` disables that adjusted check.  Noncompetitive treatment
    requires explicit sector vectors for both imports and exports.  Missing
    or unspecified information causes the affected check to be SKIPPED rather
    than guessed.
    """

    transaction_scope: str = "domestic"
    import_treatment: str = "competitive"
    # Kept as a compatibility alias for the pre-TradeFlows API.  New code
    # should use inflow_sign, which also covers interregional inflows.
    import_sign: str | None = None
    trade_representation: str = "outflows_in_Y"
    external_flow_scope: str = "international"
    # ``None`` means the field was omitted.  It is normalized to the legacy
    # default below, while still allowing us to distinguish an explicit
    # ``inflow_sign="unknown"`` from an omitted value.
    inflow_sign: str | None = None
    outflow_sign: str = "positive"

    def __post_init__(self) -> None:
        supplied_import_sign = self.import_sign
        supplied_inflow_sign = self.inflow_sign
        if self.transaction_scope not in TRANSACTION_SCOPES:
            raise IOValidationError(
                "transaction_scope must be 'domestic' or 'total'"
            )
        if self.import_treatment not in IMPORT_TREATMENTS:
            raise IOValidationError(
                "import_treatment must be 'competitive', 'noncompetitive', or 'none'"
            )
        if supplied_import_sign is not None and supplied_import_sign not in IMPORT_SIGNS:
            raise IOValidationError(
                "import_sign must be 'negative', 'positive', or 'unknown'"
            )
        if self.trade_representation not in TRADE_REPRESENTATIONS:
            raise IOValidationError(
                "trade_representation must be 'embedded', 'outflows_in_Y', 'separate', or 'unknown'"
            )
        if self.external_flow_scope not in EXTERNAL_FLOW_SCOPES:
            raise IOValidationError(
                "external_flow_scope must be 'international', 'interregional', or 'both'"
            )
        if supplied_inflow_sign is not None and supplied_inflow_sign not in IMPORT_SIGNS:
            raise IOValidationError(
                "inflow_sign must be 'negative', 'positive', or 'unknown'"
            )
        if self.outflow_sign not in IMPORT_SIGNS:
            raise IOValidationError(
                "outflow_sign must be 'negative', 'positive', or 'unknown'"
            )
        if supplied_import_sign is not None:
            if supplied_inflow_sign not in {None, "negative", supplied_import_sign}:
                raise IOValidationError(
                    "import_sign and inflow_sign specify conflicting signs"
                )
        effective_inflow_sign = supplied_import_sign or supplied_inflow_sign or "negative"
        object.__setattr__(self, "inflow_sign", effective_inflow_sign)
        object.__setattr__(self, "_import_sign_explicit", supplied_import_sign is not None)
        object.__setattr__(
            self,
            "_inflow_sign_explicit",
            supplied_import_sign is not None or supplied_inflow_sign is not None,
        )
        # Keep the old attribute readable as the effective generalized sign.
        object.__setattr__(self, "import_sign", self.inflow_sign)

    @property
    def name(self) -> str:
        """Return a stable human-readable convention name."""

        return f"{self.transaction_scope}/{self.import_treatment}"

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-compatible representation."""

        return {
            "transaction_scope": self.transaction_scope,
            "import_treatment": self.import_treatment,
            "trade_representation": self.trade_representation,
            "external_flow_scope": self.external_flow_scope,
            "inflow_sign": self.inflow_sign,
            "outflow_sign": self.outflow_sign,
            # Compatibility field; it reflects the generalized inflow sign.
            "import_sign": self.inflow_sign,
            "name": self.name,
        }
