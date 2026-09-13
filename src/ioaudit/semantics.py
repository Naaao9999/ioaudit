"""Machine-readable semantic values shared by IO table models."""

from __future__ import annotations

from enum import Enum
from typing import Any


class PriceBasis(str, Enum):
    """Valuation basis declared for an IO table or SUT block.

    The enum is deliberately small.  It records the source table's declared
    valuation; it does not convert values between bases or infer a basis from
    the presence of taxes, margins, or trade flows.
    """

    PRODUCER = "producer"
    PURCHASER = "purchaser"
    BASIC = "basic"
    UNKNOWN = "unknown"

    @classmethod
    def parse(cls, value: Any) -> "PriceBasis | None":
        """Return a member for an exact declared value, otherwise ``None``."""

        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError:
                return None
        return None


PRICE_BASIS_VALUES = frozenset(item.value for item in PriceBasis)
