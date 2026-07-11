"""Canonical D1 context semantics for Stage10C/Stage10D research.

This module is intentionally pure Python and dependency-free. It provides a
reference contract for diagnosing the live MQL5 implementation and for keeping
research/backtest semantics aligned with the EA.

It does not authorize order execution and it does not replace the production
MQL5 modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class D1Alignment(str, Enum):
    """Normalized relationship between structure and directional components."""

    ALIGNED = "aligned"
    PARTIALLY_ALIGNED = "partially_aligned"
    CONFLICT = "conflict"
    NEUTRAL = "neutral"
    INVALID = "invalid"


class D1Reason(str, Enum):
    """Specific, stable reason codes for D1 context decisions."""

    BULL_ALIGNED = "d1_bull_aligned"
    BULL_WITHOUT_STRUCTURE = "d1_bull_without_structure"
    BEAR_ALIGNED = "d1_bear_aligned"
    BEAR_WITHOUT_STRUCTURE = "d1_bear_without_structure"
    BEAR_STRUCTURE_CONFLICTS_BULL_TREND = "d1_bear_structure_conflicts_bull_trend"
    BULL_STRUCTURE_CONFLICTS_BEAR_TREND = "d1_bull_structure_conflicts_bear_trend"
    COMPONENTS_MIXED = "d1_components_mixed"
    DATA_INVALID = "d1_context_data_invalid"


@dataclass(frozen=True)
class D1ContextSnapshot:
    """Immutable D1 context snapshot consumed by one H4 evaluation.

    ``discrete_bias`` is intentionally derived from the primitive components
    instead of being accepted as an independent mutable input. The live EA
    should create one equivalent immutable snapshot per evaluation and pass it
    to every downstream stage.
    """

    symbol: str
    d1_bar: str
    structure: int
    has_structure: bool
    ema_rising: bool
    ema_falling: bool
    d1_above_ema: bool
    d1_below_ema: bool
    h4_above_ema: bool
    h4_below_ema: bool
    data_valid: bool = True
    weighted_bias: Optional[float] = None
    ema_component: Optional[float] = None
    donchian_component: Optional[float] = None

    def __post_init__(self) -> None:
        if self.structure not in (-1, 0, 1):
            raise ValueError("structure must be -1, 0 or 1")
        if not self.symbol:
            raise ValueError("symbol is required")
        if not self.d1_bar:
            raise ValueError("d1_bar is required")

    @property
    def bullish_components(self) -> bool:
        return self.ema_rising and self.d1_above_ema and self.h4_above_ema

    @property
    def bearish_components(self) -> bool:
        return self.ema_falling and self.d1_below_ema and self.h4_below_ema

    @property
    def discrete_bias(self) -> int:
        """Resolve the binary execution bias observed in the Stage10C logs.

        A neutral structure does not veto otherwise aligned directional
        components. An explicitly opposite structure does veto them and
        resolves to zero. This reproduces the July 2026 evidence:

        * structure=0 + bullish components -> +1
        * structure=-1 + bullish components -> 0
        * structure=+1 + bullish components -> +1
        """

        if not self.data_valid:
            return 0
        if self.bullish_components and self.structure != -1:
            return 1
        if self.bearish_components and self.structure != 1:
            return -1
        return 0

    @property
    def reason(self) -> D1Reason:
        if not self.data_valid:
            return D1Reason.DATA_INVALID
        if self.bullish_components:
            if self.structure == -1:
                return D1Reason.BEAR_STRUCTURE_CONFLICTS_BULL_TREND
            if self.structure == 1:
                return D1Reason.BULL_ALIGNED
            return D1Reason.BULL_WITHOUT_STRUCTURE
        if self.bearish_components:
            if self.structure == 1:
                return D1Reason.BULL_STRUCTURE_CONFLICTS_BEAR_TREND
            if self.structure == -1:
                return D1Reason.BEAR_ALIGNED
            return D1Reason.BEAR_WITHOUT_STRUCTURE
        return D1Reason.COMPONENTS_MIXED

    @property
    def alignment(self) -> D1Alignment:
        if not self.data_valid:
            return D1Alignment.INVALID
        if self.reason in (D1Reason.BULL_ALIGNED, D1Reason.BEAR_ALIGNED):
            return D1Alignment.ALIGNED
        if self.reason in (D1Reason.BULL_WITHOUT_STRUCTURE, D1Reason.BEAR_WITHOUT_STRUCTURE):
            return D1Alignment.PARTIALLY_ALIGNED
        if self.reason in (
            D1Reason.BEAR_STRUCTURE_CONFLICTS_BULL_TREND,
            D1Reason.BULL_STRUCTURE_CONFLICTS_BEAR_TREND,
        ):
            return D1Alignment.CONFLICT
        return D1Alignment.NEUTRAL

    @property
    def snapshot_id(self) -> str:
        """Deterministic identity used to detect stale downstream state."""

        flags = (
            int(self.ema_rising),
            int(self.ema_falling),
            int(self.d1_above_ema),
            int(self.d1_below_ema),
            int(self.h4_above_ema),
            int(self.h4_below_ema),
            int(self.data_valid),
        )
        return (
            f"{self.symbol}|{self.d1_bar}|s={self.structure}|hs={int(self.has_structure)}|"
            f"f={''.join(map(str, flags))}|b={self.discrete_bias}|r={self.reason.value}"
        )


@dataclass(frozen=True)
class BiasSynchronizationCheck:
    """Result of comparing downstream H4 state with the current D1 snapshot."""

    expected_bias: int
    observed_bias: int
    stale: bool
    reason: str


def check_bias_synchronization(
    snapshot: D1ContextSnapshot,
    observed_h4_bias: int,
) -> BiasSynchronizationCheck:
    """Detect whether H4 evaluated with a stale D1 bias."""

    if observed_h4_bias not in (-1, 0, 1):
        raise ValueError("observed_h4_bias must be -1, 0 or 1")

    expected = snapshot.discrete_bias
    stale = observed_h4_bias != expected
    reason = (
        "h4_bias_matches_current_d1_snapshot"
        if not stale
        else "h4_bias_stale_vs_current_d1_snapshot"
    )
    return BiasSynchronizationCheck(
        expected_bias=expected,
        observed_bias=observed_h4_bias,
        stale=stale,
        reason=reason,
    )


def candidate_direction_bias(direction: str) -> int:
    normalized = direction.strip().lower()
    if normalized == "buy":
        return 1
    if normalized == "sell":
        return -1
    if normalized in ("none", "", "null"):
        return 0
    raise ValueError(f"unsupported direction: {direction}")


def specific_block_reason(snapshot: D1ContextSnapshot) -> str:
    """Return the exact D1 block reason expected in signal telemetry."""

    if snapshot.discrete_bias != 0:
        return ""
    return snapshot.reason.value
