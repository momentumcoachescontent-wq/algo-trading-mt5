"""
tests/test_wfa_engine.py
─────────────────────────
Tests para python/research/wfa_engine.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
import pandas as pd

from python.data.extract_mt5 import generate_synthetic_ohlcv
from python.research.signals import SignalConfig
from python.research.wfa_engine import (
    WFAEngine,
    WFAResult,
    WFAWindow,
    WindowMetrics,
    generate_wfa_windows,
)


@pytest.fixture
def small_df():
    """DataFrame con suficientes barras para WFA 12m IS + 3m OOS.
    H4 = 6 barras/día × 252 días/año ≈ 1512 barras/año.
    Necesitamos ≥ 2 años para generar al menos una ventana IS 12m + OOS 3m.
    """
    return generate_synthetic_ohlcv(n_bars=4000, seed=10)


@pytest.fixture
def default_config():
    return SignalConfig()


class TestWindowMetrics:

    def test_meets_criteria_pass(self):
        m = WindowMetrics(
            profit_factor=1.25, max_dd_pct=8.0, n_trades=100
        )
        assert m.meets_criteria(pf_min=1.20, dd_max=10.0, trades_min=80)

    def test_meets_criteria_fail_pf(self):
        m = WindowMetrics(profit_factor=1.10, max_dd_pct=8.0, n_trades=100)
        assert not m.meets_criteria(pf_min=1.20)

    def test_meets_criteria_fail_dd(self):
        m = WindowMetrics(profit_factor=1.30, max_dd_pct=15.0, n_trades=100)
        assert not m.meets_criteria(dd_max=10.0)

    def test_meets_criteria_fail_trades(self):
        m = WindowMetrics(profit_factor=1.30, max_dd_pct=8.0, n_trades=50)
        assert not m.meets_criteria(trades_min=80)


class TestWFAWindow:

    def test_robustness_index_calculation(self):
        w = WFAWindow(
            window_idx=0,
            is_from=pd.Timestamp("2020-01"),
            is_to=pd.Timestamp("2022-12"),
            oos_from=pd.Timestamp("2023-01"),
            oos_to=pd.Timestamp("2023-06"),
            is_metrics=WindowMetrics(profit_factor=0.97),
            oos_metrics=WindowMetrics(profit_factor=1.21),
        )
        expected_ri = 1.21 / 0.97
        assert abs(w.robustness_index - expected_ri) < 0.001

    def test_robustness_index_zero_when_is_pf_zero(self):
        w = WFAWindow(
            window_idx=0,
            is_from=pd.Timestamp("2020-01"),
            is_to=pd.Timestamp("2022-12"),
            oos_from=pd.Timestamp("2023-01"),
            oos_to=pd.Timestamp("2023-06"),
            is_metrics=WindowMetrics(profit_factor=0.0),
            oos_metrics=WindowMetrics(profit_factor=1.21),
        )
        assert w.robustness_index == 0.0


class TestWFAResult:

    def _make_result(self) -> WFAResult:
        from python.research.signals import SignalConfig
        result = WFAResult(
            run_id="test_run",
            ea_version="v_test",
            symbol="USDJPY",
            timeframe="H4",
            config=SignalConfig(),
        )
        for i, (is_pf, oos_pf) in enumerate([
            (1.30, 1.18), (1.25, 1.12), (1.28, 1.10)
        ]):
            result.windows.append(WFAWindow(
                window_idx=i,
                is_from=pd.Timestamp("2020-01"),
                is_to=pd.Timestamp("2022-12"),
                oos_from=pd.Timestamp("2023-01"),
                oos_to=pd.Timestamp("2023-06"),
                is_metrics=WindowMetrics(
                    profit_factor=is_pf, n_trades=90, max_dd_pct=7.0
                ),
                oos_metrics=WindowMetrics(
                    profit_factor=oos_pf, n_trades=25, max_dd_pct=6.0,
                    sharpe=0.85
                ),
            ))
        return result

    def test_avg_is_pf(self):
        result = self._make_result()
        expected = np.mean([1.30, 1.25, 1.28])
        assert abs(result.avg_is_pf - expected) < 0.001

    def test_avg_oos_pf(self):
        result = self._make_result()
        expected = np.mean([1.18, 1.12, 1.10])
        assert abs(result.avg_oos_pf - expected) < 0.001

    def test_f3_criteria_pass(self):
        result = self._make_result()
        passed, checks = result.meets_f3_criteria(
            pf_is_min=1.20, pf_oos_min=1.05, ri_min=0.80,
            dd_max=10.0, trades_is_min=80,
        )
        assert passed, f"F3 debería pasar: {checks}"

    def test_f3_criteria_fail_oos_pf(self):
        result = self._make_result()
        passed, checks = result.meets_f3_criteria(pf_oos_min=1.20)
        assert not passed

    def test_total_is_trades(self):
        result = self._make_result()
        assert result.total_is_trades == 270  # 90 × 3 ventanas

    def test_to_dict_has_required_keys(self):
        result = self._make_result()
        d = result.to_dict()
        required = ["run_id", "ea_version", "symbol", "avg_is_pf",
                    "avg_oos_pf", "avg_robustness_index"]
        for key in required:
            assert key in d, f"Clave faltante en to_dict(): {key}"


class TestWFAEngineWindowGeneration:
    """
    Tests de generación de ventanas usando la función standalone.
    No requiere vectorbt.
    """

    def test_windows_generated(self, small_df):
        windows = generate_wfa_windows(small_df, is_months=12, oos_months=3, step_months=3)
        assert len(windows) > 0

    def test_window_dates_coherent(self, small_df):
        windows = generate_wfa_windows(small_df, is_months=12, oos_months=3, step_months=3)
        for is_from, is_to, oos_from, oos_to in windows:
            assert is_from < is_to
            assert is_to == oos_from
            assert oos_from < oos_to

    def test_step_advances_correctly(self, small_df):
        windows = generate_wfa_windows(small_df, is_months=12, oos_months=3, step_months=3)
        if len(windows) > 1:
            delta_days = (windows[1][0] - windows[0][0]).days
            # 3 meses ≈ 89–92 días según el mes
            assert 85 <= delta_days <= 95, f"Step esperado ~90 días, obtenido {delta_days}"

    def test_no_oos_beyond_data_end(self, small_df):
        """Ninguna ventana debe tener OOS fuera del rango de datos."""
        end = small_df.index[-1]
        windows = generate_wfa_windows(small_df, is_months=12, oos_months=3, step_months=3)
        for _, _, _, oos_to in windows:
            assert oos_to <= end + pd.DateOffset(days=1)

    def test_is_always_longer_than_oos(self, small_df):
        """IS siempre debe ser más largo que OOS."""
        windows = generate_wfa_windows(small_df, is_months=18, oos_months=3, step_months=3)
        for is_from, is_to, oos_from, oos_to in windows:
            is_duration  = (is_to - is_from).days
            oos_duration = (oos_to - oos_from).days
            assert is_duration > oos_duration

    def test_wfa_engine_requires_vectorbt(self):
        """WFAEngine levanta ImportError si vectorbt no está instalado."""
        try:
            import vectorbt
            pytest.skip("vectorbt está instalado — test no aplica")
        except ImportError:
            with pytest.raises(ImportError, match="vectorbt"):
                WFAEngine()
