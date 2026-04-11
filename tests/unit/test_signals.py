"""
tests/test_signals.py
──────────────────────
Tests unitarios para python/research/signals.py

Valida:
    1. Paridad con lógica MQL5 (shift=1 en todos los indicadores)
    2. Condiciones de señal correctas
    3. Cálculo de SL/TP desde ATR
    4. Sin data leakage (shift correcto)
    5. Generación de señales sintéticas con datos controlados
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
import pandas as pd

from python.data.extract_mt5 import generate_synthetic_ohlcv
from python.research.signals import (
    SignalConfig,
    compute_indicators,
    generate_signals,
    compute_sl_tp,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def default_config():
    return SignalConfig()


@pytest.fixture
def v19_config():
    """Configuración exacta de v1.9."""
    return SignalConfig(
        ema_period=21, adx_period=14, adx_min=25.0,
        atr_period=14, atr_sl_mult=1.5, atr_tp_mult=2.0,
        body_threshold=0.40,
    )


@pytest.fixture
def v23_config():
    """Configuración exacta de v2.3."""
    return SignalConfig(
        ema_period=21, adx_period=14, adx_min=25.0,
        atr_period=14, atr_sl_mult=1.5, atr_tp_mult=2.5,
        body_threshold=0.40,
    )


@pytest.fixture
def synthetic_df():
    return generate_synthetic_ohlcv(n_bars=1000, seed=42)


# ── Tests: compute_indicators ─────────────────────────────────────────────

class TestComputeIndicators:

    def test_returns_dataframe(self, synthetic_df, default_config):
        result = compute_indicators(synthetic_df, default_config)
        assert isinstance(result, pd.DataFrame)

    def test_required_columns_present(self, synthetic_df, default_config):
        result = compute_indicators(synthetic_df, default_config)
        required = ["ema21", "atr", "adx", "+di", "-di", "body_ratio", "hh_hl"]
        for col in required:
            assert col in result.columns, f"Columna faltante: {col}"

    def test_ema_not_nan_after_warmup(self, synthetic_df, default_config):
        result = compute_indicators(synthetic_df, default_config)
        # Después de ema_period barras, EMA no debe ser NaN
        warmup = default_config.ema_period + 1
        assert not result["ema21"].iloc[warmup:].isna().any()

    def test_adx_range(self, synthetic_df, default_config):
        result = compute_indicators(synthetic_df, default_config)
        # ADX debe estar entre 0 y 100
        valid = result["adx"].dropna()
        assert (valid >= 0).all(), "ADX tiene valores negativos"
        assert (valid <= 100).all(), "ADX supera 100"

    def test_atr_positive(self, synthetic_df, default_config):
        result = compute_indicators(synthetic_df, default_config)
        valid = result["atr"].dropna()
        assert (valid > 0).all(), "ATR tiene valores ≤ 0"

    def test_body_ratio_range(self, synthetic_df, default_config):
        result = compute_indicators(synthetic_df, default_config)
        valid = result["body_ratio"].dropna()
        assert (valid >= 0).all(), "Body ratio negativo"
        assert (valid <= 1.0001).all(), "Body ratio > 1"

    def test_hh_hl_is_boolean(self, synthetic_df, default_config):
        result = compute_indicators(synthetic_df, default_config)
        unique_vals = result["hh_hl"].dropna().unique()
        assert set(unique_vals).issubset({True, False, 0, 1})

    def test_no_data_leakage_ema(self, synthetic_df, default_config):
        """
        Verifica que generate_signals usa shift=1 (no mira el futuro).
        Truncar la última barra y verificar que las señales no cambian.
        """
        df_full = generate_signals(synthetic_df, default_config)
        df_trunc = generate_signals(synthetic_df.iloc[:-1], default_config)

        # Señales en t-2 deben ser idénticas (la última barra no debe afectar las anteriores)
        signals_full  = df_full["signal"].iloc[:-2]
        signals_trunc = df_trunc["signal"].iloc[:-1]
        common_index  = signals_full.index.intersection(signals_trunc.index)

        pd.testing.assert_series_equal(
            signals_full.loc[common_index],
            signals_trunc.loc[common_index],
            check_names=False,
        )


# ── Tests: generate_signals ───────────────────────────────────────────────

class TestGenerateSignals:

    def test_signal_column_exists(self, synthetic_df, default_config):
        result = generate_signals(synthetic_df, default_config)
        assert "signal" in result.columns

    def test_signal_values_valid(self, synthetic_df, default_config):
        result = generate_signals(synthetic_df, default_config)
        valid_values = {-1, 0, 1}
        assert set(result["signal"].unique()).issubset(valid_values)

    def test_no_simultaneous_long_short(self, synthetic_df, default_config):
        """No puede haber long y short en la misma barra."""
        result = generate_signals(synthetic_df, default_config)
        # Por construcción esto es imposible, pero verificamos
        assert (result["signal"].abs() <= 1).all()

    def test_signals_generated(self, synthetic_df):
        """Con 1000 barras y ADX bajo debe haber señales."""
        # Usar ADX mínimo bajo para garantizar señales en datos GBM sintéticos
        cfg_relaxed = SignalConfig(adx_min=5.0, body_threshold=0.05)
        result = generate_signals(synthetic_df, cfg_relaxed)
        n_signals = (result["signal"] != 0).sum()
        assert n_signals > 0, "No se generaron señales incluso con filtros relajados"

    def test_v19_vs_v23_trade_count(self, synthetic_df, v19_config, v23_config):
        """v1.9 y v2.3 deben generar el mismo número de señales (mismo filtro, distinto TP)."""
        result_v19 = generate_signals(synthetic_df, v19_config)
        result_v23 = generate_signals(synthetic_df, v23_config)

        n_v19 = (result_v19["signal"] != 0).sum()
        n_v23 = (result_v23["signal"] != 0).sum()

        # Mismo número de entradas (el TP no afecta las señales de entrada)
        assert n_v19 == n_v23, (
            f"v1.9 ({n_v19} señales) ≠ v2.3 ({n_v23} señales). "
            "Solo el TP difiere, las entradas deben ser idénticas."
        )

    def test_adx_filter_active(self, synthetic_df):
        """ADX min alto debe reducir señales."""
        cfg_low_adx  = SignalConfig(adx_min=5.0)
        cfg_high_adx = SignalConfig(adx_min=45.0)

        result_low  = generate_signals(synthetic_df, cfg_low_adx)
        result_high = generate_signals(synthetic_df, cfg_high_adx)

        n_low  = (result_low["signal"] != 0).sum()
        n_high = (result_high["signal"] != 0).sum()

        assert n_high <= n_low, "ADX alto no redujo las señales"

    def test_body_threshold_filter(self, synthetic_df):
        """Body threshold alto debe reducir señales."""
        cfg_low  = SignalConfig(body_threshold=0.10)
        cfg_high = SignalConfig(body_threshold=0.80)

        result_low  = generate_signals(synthetic_df, cfg_low)
        result_high = generate_signals(synthetic_df, cfg_high)

        n_low  = (result_low["signal"] != 0).sum()
        n_high = (result_high["signal"] != 0).sum()

        assert n_high <= n_low, "Body threshold alto no redujo las señales"


# ── Tests: compute_sl_tp ──────────────────────────────────────────────────

class TestComputeSlTp:

    def test_long_sl_below_entry(self):
        cfg = SignalConfig(atr_sl_mult=1.5, atr_tp_mult=2.0)
        sl, tp = compute_sl_tp(150.0, 1, atr=0.5, cfg=cfg)
        assert sl < 150.0, f"SL LONG debe ser menor que entrada: {sl}"
        assert tp > 150.0, f"TP LONG debe ser mayor que entrada: {tp}"

    def test_short_sl_above_entry(self):
        cfg = SignalConfig(atr_sl_mult=1.5, atr_tp_mult=2.0)
        sl, tp = compute_sl_tp(150.0, -1, atr=0.5, cfg=cfg)
        assert sl > 150.0, f"SL SHORT debe ser mayor que entrada: {sl}"
        assert tp < 150.0, f"TP SHORT debe ser menor que entrada: {tp}"

    def test_rr_ratio_v19(self):
        """v1.9: TP/SL debe ser 2.0 (RR=2.0)."""
        cfg = SignalConfig(atr_sl_mult=1.5, atr_tp_mult=2.0 * 1.5)  # TP=3.0×ATR → RR=2.0
        entry = 150.0
        atr   = 0.50
        sl, tp = compute_sl_tp(entry, 1, atr=atr, cfg=cfg)

        sl_dist = abs(entry - sl)
        tp_dist = abs(tp - entry)
        actual_rr = tp_dist / sl_dist

        assert abs(actual_rr - 2.0) < 0.01, f"RR v1.9 esperado 2.0, obtenido {actual_rr:.2f}"

    def test_rr_ratio_v23(self):
        """v2.3: RR debe ser 2.5 (atr_tp_mult = 2.5 × atr_sl_mult = 1.5)."""
        # atr_tp_mult = 2.5 × 1.5 = 3.75 × ATR (TP)
        # atr_sl_mult = 1.5 × ATR (SL)
        # RR = 3.75 / 1.5 = 2.5
        cfg = SignalConfig(atr_sl_mult=1.5, atr_tp_mult=2.5 * 1.5)
        entry = 150.0
        atr   = 0.50
        sl, tp = compute_sl_tp(entry, 1, atr=atr, cfg=cfg)

        sl_dist = abs(entry - sl)
        tp_dist = abs(tp - entry)
        actual_rr = tp_dist / sl_dist

        assert abs(actual_rr - 2.5) < 0.01, f"RR v2.3 esperado 2.5, obtenido {actual_rr:.2f}"

    def test_atr_zero_returns_valid(self):
        """ATR=0 no debe causar división por cero."""
        cfg = SignalConfig()
        sl, tp = compute_sl_tp(150.0, 1, atr=0.0, cfg=cfg)
        assert sl == 150.0
        assert tp == 150.0


# ── Tests: Monte Carlo ────────────────────────────────────────────────────

class TestMonteCarlo:

    def test_basic_mc_runs(self):
        from python.research.monte_carlo import MonteCarlo, MCConfig
        import numpy as np

        pnls = np.concatenate([
            np.full(30, 125.0),   # 30 wins
            np.full(70, -62.5),   # 70 losses
        ])
        mc = MonteCarlo(MCConfig(n_simulations=100, seed=42))
        results = mc.run(pnls, run_id="test_001")

        assert results.pf_p50 > 0
        assert 0 <= results.prob_pf_gt_1 <= 1
        assert results.dd_p95 > 0

    def test_mc_median_approx_base(self):
        """La mediana de MC debe estar cercana al PF base."""
        from python.research.monte_carlo import MonteCarlo, MCConfig
        import numpy as np

        pnls = np.concatenate([np.full(33, 100.0), np.full(67, -50.0)])
        mc = MonteCarlo(MCConfig(n_simulations=500, seed=42))
        results = mc.run(pnls, run_id="test_coherence")

        deviation = abs(results.pf_p50 - results.base_pf) / results.base_pf
        assert deviation < 0.15, (
            f"Mediana ({results.pf_p50:.2f}) diverge del base ({results.base_pf:.2f}) "
            f"en {deviation*100:.0f}%"
        )


# ── Tests: WFA Engine (smoke tests) ───────────────────────────────────────

class TestWFAEngineSmokeTest:

    def test_wfa_runs_without_crash(self):
        """Smoke test: el WFA debe correr sin excepciones con datos sintéticos."""
        try:
            import vectorbt as vbt
        except ImportError:
            pytest.skip("vectorbt no instalado")

        from python.research.wfa_engine import WFAEngine
        from python.data.store import ResultsStore

        # H4: ~6 bars/día → 24 meses ≈ 4380 bars; usar 5000 para garantizar ventanas
        df  = generate_synthetic_ohlcv(n_bars=5000, seed=42)
        cfg = SignalConfig()
        engine = WFAEngine()

        result = engine.run_wfa(
            df=df, config=cfg,
            run_id="smoke_test",
            ea_version="test_v0",
            symbol="USDJPY",
            timeframe="H4",
            is_months=18,
            oos_months=6,
            step_months=6,
        )

        assert len(result.windows) > 0
        assert result.run_id == "smoke_test"
