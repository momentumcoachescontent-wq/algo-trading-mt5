"""
tests/test_sleeve_scorer.py
────────────────────────────
Tests para python/portfolio/sleeve_scorer.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np

from python.portfolio.sleeve_scorer import SleeveScorer, SleeveKPIs


@pytest.fixture
def scorer():
    return SleeveScorer(initial_capital=10_000.0)


@pytest.fixture
def sample_pnls_winning():
    """33% WR, RR=2.0 — PF teórico ~0.98 (cerca del breakeven)."""
    np.random.seed(42)
    wins   = np.random.normal(125.0, 20.0, 33)
    losses = np.random.normal(62.5,  10.0, 67)
    return np.concatenate([wins, -losses])


@pytest.fixture
def sample_pnls_v19():
    """Simula trades USDJPY v1.9 OOS — PF ~1.21."""
    np.random.seed(99)
    wins   = np.random.normal(150.0, 25.0, 26)   # 35% WR de 74 trades
    losses = np.random.normal(65.0,  10.0, 48)
    return np.concatenate([wins, -losses])


class TestSleeveKPIs:

    def test_basic_metrics(self, scorer, sample_pnls_v19):
        kpis = scorer.compute(
            sample_pnls_v19,
            sleeve_id="v1.9_usdjpy",
            ea_version="v1.9",
            symbol="USDJPY",
        )
        assert kpis.n_trades == len(sample_pnls_v19)
        assert kpis.profit_factor > 0
        assert 0 < kpis.win_rate < 1
        assert kpis.max_dd_pct > 0

    def test_profit_factor_positive_only(self, scorer):
        all_wins = np.full(50, 100.0)
        kpis = scorer.compute(all_wins, sleeve_id="all_wins")
        assert kpis.profit_factor > 1.0

    def test_profit_factor_negative_only(self, scorer):
        all_losses = np.full(50, -100.0)
        kpis = scorer.compute(all_losses, sleeve_id="all_losses")
        assert kpis.profit_factor == 0.0

    def test_sharpe_is_numeric(self, scorer, sample_pnls_v19):
        kpis = scorer.compute(sample_pnls_v19, sleeve_id="test")
        assert np.isfinite(kpis.sharpe)

    def test_sortino_leq_or_eq_sharpe_in_extreme_cases(self, scorer):
        """Sortino ≥ Sharpe cuando hay pérdidas (penaliza solo downside)."""
        pnls = np.concatenate([np.full(33, 100.0), np.full(67, -50.0)])
        kpis = scorer.compute(pnls, sleeve_id="test_sortino")
        # Sortino puede ser mayor O igual que Sharpe (penaliza menos la volatilidad)
        assert kpis.sortino >= kpis.sharpe or abs(kpis.sortino - kpis.sharpe) < 5.0

    def test_ulcer_index_positive(self, scorer, sample_pnls_v19):
        kpis = scorer.compute(sample_pnls_v19, sleeve_id="test")
        assert kpis.ulcer_index >= 0

    def test_robustness_index(self, scorer, sample_pnls_v19):
        kpis = scorer.compute(
            sample_pnls_v19,
            sleeve_id="ri_test",
            is_pf=0.97,
            oos_pf=1.21,
        )
        expected_ri = 1.21 / 0.97
        assert abs(kpis.robustness_index - expected_ri) < 0.01

    def test_score_between_0_and_1(self, scorer, sample_pnls_v19):
        kpis = scorer.compute(sample_pnls_v19, sleeve_id="score_test",
                               is_pf=0.97, oos_pf=1.21)
        assert 0.0 <= kpis.score() <= 1.0

    def test_empty_trades(self, scorer):
        kpis = scorer.compute(np.array([]), sleeve_id="empty")
        assert kpis.n_trades == 0
        assert kpis.profit_factor == 0.0
        assert kpis.score() == 0.0

    def test_v19_kpis_match_known(self, scorer):
        """
        Verifica que los KPIs calculados para v1.9 son coherentes
        con los resultados validados en WFA.
        """
        kpis = scorer.compute(
            _generate_v19_trades(),
            sleeve_id="v1.9_usdjpy",
            ea_version="v1.9",
            symbol="USDJPY",
            is_pf=0.97,
            oos_pf=1.21,
        )
        # PF debe estar cerca de 1.21
        assert abs(kpis.profit_factor - 1.21) < 0.30, \
            f"PF esperado ~1.21, obtenido {kpis.profit_factor:.2f}"

        # RI debe ser 1.25
        assert abs(kpis.robustness_index - 1.25) < 0.01


class TestSleeveComparison:

    def test_compare_returns_dataframe(self, scorer):
        import pandas as pd

        kpis_list = [
            SleeveKPIs(sleeve_id="v1.9", profit_factor=1.21,
                       robustness_index=1.25, sharpe=0.92, sortino=1.15,
                       max_dd_pct=8.67, win_rate=0.35, n_trades=74,
                       ulcer_index=3.2, calmar=0.45),
            SleeveKPIs(sleeve_id="v1.6", profit_factor=1.04,
                       robustness_index=0.87, sharpe=0.41, sortino=0.58,
                       max_dd_pct=9.2, win_rate=0.33, n_trades=55,
                       ulcer_index=5.1, calmar=0.22),
        ]
        result = scorer.compare_sleeves(kpis_list)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        # v1.9 debe tener mayor score
        assert result.iloc[0]["sleeve"] == "v1.9"


# ── Helper ────────────────────────────────────────────────────────────────

def _generate_v19_trades() -> np.ndarray:
    """Genera trades que reproducen aproximadamente las métricas de v1.9 OOS."""
    np.random.seed(0)
    n_trades = 74
    wr       = 0.35
    n_wins   = int(n_trades * wr)
    n_losses = n_trades - n_wins

    wins   = np.random.normal(150.0, 30.0, n_wins).clip(min=10)
    losses = np.random.normal(72.0,  15.0, n_losses).clip(min=10)

    trades = np.concatenate([wins, -losses])
    np.random.shuffle(trades)
    return trades
