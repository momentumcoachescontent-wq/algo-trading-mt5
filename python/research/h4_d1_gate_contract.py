"""Canonical Stage10C H4 raw-signal to D1-filtered-signal contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class H4D1GateDecision:
    raw_signal: int
    discrete_bias: int
    filtered_signal: int
    reason: str
    snapshot_match: bool


def gate_h4_signal(
    raw_signal: int,
    discrete_bias: int,
    *,
    snapshot_match: bool = True,
) -> H4D1GateDecision:
    """Filter a raw H4 pattern through the discrete D1 execution context.

    The raw pattern remains available for Stage10D research. Only the filtered
    signal is eligible to enter the Stage10C execution waterfall.
    """

    if raw_signal not in (-1, 0, 1):
        raise ValueError("raw_signal must be -1, 0 or 1")
    if discrete_bias not in (-1, 0, 1):
        raise ValueError("discrete_bias must be -1, 0 or 1")

    if not snapshot_match:
        return H4D1GateDecision(
            raw_signal=raw_signal,
            discrete_bias=discrete_bias,
            filtered_signal=0,
            reason="d1_context_snapshot_mismatch",
            snapshot_match=False,
        )

    if raw_signal == 0:
        return H4D1GateDecision(
            raw_signal=0,
            discrete_bias=discrete_bias,
            filtered_signal=0,
            reason="no_h4_pattern",
            snapshot_match=True,
        )

    if discrete_bias == 0:
        return H4D1GateDecision(
            raw_signal=raw_signal,
            discrete_bias=0,
            filtered_signal=0,
            reason="d1_neutral_blocks_h4_signal",
            snapshot_match=True,
        )

    if raw_signal != discrete_bias:
        return H4D1GateDecision(
            raw_signal=raw_signal,
            discrete_bias=discrete_bias,
            filtered_signal=0,
            reason="d1_bias_blocks_opposite_h4_signal",
            snapshot_match=True,
        )

    return H4D1GateDecision(
        raw_signal=raw_signal,
        discrete_bias=discrete_bias,
        filtered_signal=raw_signal,
        reason="signal_ok",
        snapshot_match=True,
    )