"""Canonical D1 context semantics for Stage10C/Stage10D research.

This module is intentionally pure Python and dependency-free. It provides a
reference contract for diagnosing the live MQL5 implementation and for keeping
research/backtest semantics aligned with the EA.

It does not authorize order execution and it does not replace the production
MQL5 modules.
"""

from __future__ import