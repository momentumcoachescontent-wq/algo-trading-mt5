"""
python/research/regime.py
──────────────────────────
Detección de régimen de mercado.
Prepara la infraestructura para F7 (Regime Routing).

Métodos disponibles:
    1. ADX-based: simple, directo, ya validado en el EA
    2. Rolling volatility: compresión/expansión
    3. HMM (Hidden Markov Model): 2 estados ocultos via statsmodels

El régimen se etiqueta como:
    0 = TRENDING    (ADX > umbral, volatilidad normal)
    1 = RANGING     (ADX < umbral, baja volatilidad)
    2 = VOLATILE    (ADX cualquiera, alta volatilidad)

ADR: El EA solo opera en régimen TRENDING (Pilar P3).
En F7, se activará routing dinámico entre subsistemas.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional
from rich.console import Console

console = Console()

try:
    from hmmlearn import hmm
    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False


@dataclass
class RegimeConfig:
    """Parámetros para detección de régimen."""
    adx_period:         int   = 14
    adx_trending_min:   float = 25.0   # ADX ≥ 25 → trending (Pilar P10)
    adx_ranging_max:    float = 20.0   # ADX ≤ 20 → ranging
    vol_lookback:       int   = 20     # Ventana rolling volatilidad
    vol_high_percentile: float = 80.0  # Percentil para "alta volatilidad"
    vol_low_percentile:  float = 30.0  # Percentil para "baja volatilidad"
    hmm_n_components:   int   = 2      # Estados ocultos HMM


# ── Régimen ADX-based (producción) ───────────────────────────────────────

class ADXRegimeDetector:
    """
    Detector de régimen basado en ADX.
    Alineado con el filtro ADX≥25 del EA (Pilar P10).

    0 = TRENDING (ADX ≥ adx_trending_min)
    1 = RANGING  (ADX < adx_ranging_max)
    2 = TRANSITION (entre ranging y trending)
    """

    def __init__(self, cfg: Optional[RegimeConfig] = None):
        self.cfg = cfg or RegimeConfig()

    def detect(self, df: pd.DataFrame) -> pd.Series:
        """
        Detecta régimen en cada barra.

        Args:
            df: DataFrame con columna 'adx' ya calculada

        Returns:
            Series con valores 0 (trending), 1 (ranging), 2 (transition)
        """
        if "adx" not in df.columns:
            raise ValueError("DataFrame debe contener columna 'adx'")

        adx = df["adx"]
        regime = pd.Series(2, index=df.index, name="regime", dtype=int)  # default: transition
        regime[adx >= self.cfg.adx_trending_min] = 0  # trending
        regime[adx <= self.cfg.adx_ranging_max]  = 1  # ranging

        # Stats
        counts = regime.value_counts()
        total  = len(regime)
        console.print(
            f"[dim]Régimen ADX — Trending: {counts.get(0,0)/total*100:.1f}% | "
            f"Ranging: {counts.get(1,0)/total*100:.1f}% | "
            f"Transition: {counts.get(2,0)/total*100:.1f}%[/dim]"
        )

        return regime

    def filter_trending(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filtra el DataFrame para retener solo barras en régimen trending.
        Usado para comparar performance con/sin filtro de régimen.
        """
        regime = self.detect(df)
        return df[regime == 0].copy()


# ── Régimen por volatilidad ───────────────────────────────────────────────

class VolatilityRegimeDetector:
    """
    Detector de régimen basado en volatilidad rolling.

    Útil para detectar periodos de compresión (pre-expansión)
    que el TTM Squeeze captura — reservado para F7.
    """

    def __init__(self, cfg: Optional[RegimeConfig] = None):
        self.cfg = cfg or RegimeConfig()

    def detect(self, df: pd.DataFrame) -> pd.Series:
        """
        Detecta régimen por percentil de volatilidad histórica.

        Returns:
            Series: 0=normal, 1=low_vol (compresión), 2=high_vol (expansión)
        """
        if "atr" not in df.columns:
            raise ValueError("DataFrame debe contener columna 'atr'")

        # ATR normalizado como % del precio
        atr_pct = df["atr"] / df["close"] * 100

        # Percentiles rolling
        roll = atr_pct.rolling(self.cfg.vol_lookback)
        high_threshold = roll.quantile(self.cfg.vol_high_percentile / 100)
        low_threshold  = roll.quantile(self.cfg.vol_low_percentile  / 100)

        regime = pd.Series(0, index=df.index, name="vol_regime", dtype=int)
        regime[atr_pct > high_threshold] = 2   # alta volatilidad
        regime[atr_pct < low_threshold]  = 1   # compresión

        return regime


# ── Régimen HMM (F7) ──────────────────────────────────────────────────────

class HMMRegimeDetector:
    """
    Detector de régimen con Hidden Markov Model.
    2 estados ocultos: tendencia vs rango.

    RESERVADO PARA F7 — no usar en producción hasta validación.
    Requiere: pip install hmmlearn
    """

    def __init__(self, cfg: Optional[RegimeConfig] = None):
        self.cfg = cfg or RegimeConfig()
        if not HMM_AVAILABLE:
            raise ImportError(
                "hmmlearn no instalado. "
                "Ejecutar: pip install hmmlearn"
            )
        self._model = None
        self._fitted = False

    def fit(self, df: pd.DataFrame) -> "HMMRegimeDetector":
        """
        Entrena el HMM sobre la serie de retornos + volatilidad.

        Features: [return, log_vol]
        """
        returns   = df["close"].pct_change().fillna(0).values
        log_vol   = np.log(df["atr"].replace(0, np.nan).fillna(method="ffill").values)

        X = np.column_stack([returns, log_vol])

        self._model = hmm.GaussianHMM(
            n_components=self.cfg.hmm_n_components,
            covariance_type="full",
            n_iter=200,
            random_state=42,
        )
        self._model.fit(X)
        self._fitted = True

        console.print(
            f"[dim]HMM entrenado: {self.cfg.hmm_n_components} estados, "
            f"convergió={self._model.monitor_.converged}[/dim]"
        )
        return self

    def detect(self, df: pd.DataFrame) -> pd.Series:
        """
        Predice régimen en cada barra.
        Debe llamarse después de fit().

        Returns:
            Series de estados HMM (0 o 1)
        """
        if not self._fitted:
            raise RuntimeError("Modelo no entrenado. Llamar .fit() primero.")

        returns = df["close"].pct_change().fillna(0).values
        log_vol = np.log(df["atr"].replace(0, np.nan).fillna(method="ffill").values)
        X = np.column_stack([returns, log_vol])

        states = self._model.predict(X)
        return pd.Series(states, index=df.index, name="hmm_regime")

    def label_states(self, df: pd.DataFrame, states: pd.Series) -> dict:
        """
        Identifica cuál estado corresponde a trending vs ranging
        basándose en ADX promedio por estado.
        """
        if "adx" not in df.columns:
            return {0: "state_0", 1: "state_1"}

        adx_by_state = {}
        for state in states.unique():
            mask = states == state
            adx_by_state[state] = df.loc[mask, "adx"].mean()

        # Mayor ADX promedio → trending
        trending_state = max(adx_by_state, key=adx_by_state.get)
        ranging_state  = min(adx_by_state, key=adx_by_state.get)

        return {
            trending_state: "trending",
            ranging_state:  "ranging",
        }


# ── Análisis de performance por régimen ──────────────────────────────────

def analyze_performance_by_regime(
    df_with_signals: pd.DataFrame,
    regime: pd.Series,
) -> pd.DataFrame:
    """
    Compara métricas de performance por régimen.

    Args:
        df_with_signals: DataFrame con señales y trades simulados
        regime:          Series de régimen (mismo índice)

    Returns:
        DataFrame con métricas por régimen
    """
    if "signal" not in df_with_signals.columns:
        raise ValueError("DataFrame debe contener columna 'signal'")

    results = []
    for regime_val in sorted(regime.unique()):
        mask  = regime == regime_val
        df_r  = df_with_signals[mask]
        n_sig = (df_r["signal"] != 0).sum()

        results.append({
            "regime":          regime_val,
            "n_bars":          mask.sum(),
            "pct_time":        mask.mean() * 100,
            "n_signals":       n_sig,
            "signals_per_bar": n_sig / max(mask.sum(), 1) * 100,
        })

    return pd.DataFrame(results)
