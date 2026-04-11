"""
python/research/signals.py
──────────────────────────
Espejo Python de la lógica de señales del EA MQL5 v2.x.

CRÍTICO: Este módulo debe mantenerse en paridad exacta con el EA.
Cualquier cambio en la lógica MQL5 debe reflejarse aquí.
Los tests en tests/test_signals.py validan esta paridad.

Estrategia v2.x:
    - EMA21 como referencia de tendencia (Touch & Reject)
    - ADX ≥ 25 como filtro de tendencia (Pilar P10)
    - Body confirmation ≥ 40% (ADR-008: techo WR estructural)
    - ATR SL/TP dinámico (Pilar P8)
    - HH/HL market structure (ventana de comparación)
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional


# ── Configuración de señal ────────────────────────────────────────────────

@dataclass
class SignalConfig:
    """Parámetros de la estrategia. Refleja exactamente los inputs del EA."""
    ema_period:      int   = 21
    adx_period:      int   = 14
    adx_min:         float = 25.0
    atr_period:      int   = 14
    atr_sl_mult:     float = 1.5
    atr_tp_mult:     float = 2.5    # v2.3: 2.5x (v2.2 era 2.0x)
    body_threshold:  float = 0.40   # body ≥ 40% del rango total
    lookback:        int   = 50     # ventana HH/HL


# ── Cálculo de indicadores ────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame, cfg: SignalConfig) -> pd.DataFrame:
    """
    Calcula todos los indicadores requeridos por la estrategia.

    Input:  DataFrame OHLCV con DatetimeIndex
    Output: DataFrame con columnas adicionales de indicadores

    Implementación usa shift=1 (vela cerrada) en todos los indicadores,
    exactamente como el EA MQL5 usa shift=1 en CopyBuffer().
    """
    out = df.copy()

    # ── EMA 21 ──────────────────────────────────────────────────────────
    out["ema21"] = out["close"].ewm(span=cfg.ema_period, adjust=False).mean()

    # ── ATR (True Range) ────────────────────────────────────────────────
    high_low = out["high"] - out["low"]
    high_prev_close = (out["high"] - out["close"].shift(1)).abs()
    low_prev_close  = (out["low"]  - out["close"].shift(1)).abs()
    true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    out["atr"] = true_range.ewm(span=cfg.atr_period, adjust=False).mean()

    # ── ADX / DMI ────────────────────────────────────────────────────────
    # +DM y -DM — mantener índice del DataFrame en todo momento
    up_move   = out["high"].diff()
    down_move = -out["low"].diff()

    # Usar pd.Series con índice explícito para evitar desalineación
    pos_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=out.index,
    )
    neg_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=out.index,
    )

    smoothed_tr  = true_range.ewm(span=cfg.adx_period, adjust=False).mean()
    smoothed_pdm = pos_dm.ewm(span=cfg.adx_period, adjust=False).mean()
    smoothed_ndm = neg_dm.ewm(span=cfg.adx_period, adjust=False).mean()

    out["+di"] = 100 * smoothed_pdm / smoothed_tr.replace(0, np.nan)
    out["-di"] = 100 * smoothed_ndm / smoothed_tr.replace(0, np.nan)

    dx_denom = out["+di"] + out["-di"]
    dx = 100 * (out["+di"] - out["-di"]).abs() / dx_denom.replace(0, np.nan)
    out["adx"] = dx.ewm(span=cfg.adx_period, adjust=False).mean()

    # ── Body ratio ───────────────────────────────────────────────────────
    candle_range = out["high"] - out["low"]
    body_size = (out["close"] - out["open"]).abs()
    out["body_ratio"] = body_size / candle_range.replace(0, np.nan)

    # ── HH/HL Market Structure ───────────────────────────────────────────
    out["hh_hl"] = _compute_hhhl(out, cfg.lookback)

    return out


def _compute_hhhl(df: pd.DataFrame, lookback: int) -> pd.Series:
    """
    Detecta estructura Higher High / Higher Low usando comparación de ventanas.
    Implementación directa del algoritmo MQL5 (ADR-006).

    Retorna: Series booleana — True donde hay estructura HH/HL alcista.
    """
    highs  = df["high"].values
    lows   = df["low"].values
    n      = len(df)
    result = np.zeros(n, dtype=bool)

    for i in range(lookback * 2, n):
        # Ventana actual vs ventana anterior
        curr_high = highs[i - lookback : i].max()
        curr_low  = lows[i - lookback : i].min()
        prev_high = highs[i - lookback * 2 : i - lookback].max()
        prev_low  = lows[i - lookback * 2 : i - lookback].min()

        result[i] = (curr_high > prev_high) and (curr_low > prev_low)

    return pd.Series(result, index=df.index, name="hh_hl")


# ── Generación de señales ─────────────────────────────────────────────────

def generate_signals(df: pd.DataFrame, cfg: SignalConfig) -> pd.DataFrame:
    """
    Genera señales de entrada LONG/SHORT.

    Condiciones LONG (shift=1 — vela anterior ya cerrada):
        1. HH/HL = True (estructura alcista)
        2. close[1] > ema21[1] (precio sobre EMA)
        3. |close[1] - ema21[1]| / atr[1] ≤ 0.5 (touch de EMA)
        4. ADX[1] ≥ adx_min (tendencia fuerte)
        5. +DI[1] > -DI[1] (dirección alcista del DMI — Pilar P10)
        6. body_ratio[1] ≥ body_threshold (confirmación de cuerpo)
        7. close[1] > open[1] (vela alcista)

    Condiciones SHORT: espejo inverso.

    Returns:
        DataFrame con columna 'signal': 1=LONG, -1=SHORT, 0=FLAT
    """
    out = compute_indicators(df, cfg)

    # Usar shift=1 (vela cerrada, exactamente como MQL5 shift=1)
    close_1       = out["close"].shift(1)
    open_1        = out["open"].shift(1)
    ema21_1       = out["ema21"].shift(1)
    atr_1         = out["atr"].shift(1)
    adx_1         = out["adx"].shift(1)
    pdi_1         = out["+di"].shift(1)
    ndi_1         = out["-di"].shift(1)
    body_ratio_1  = out["body_ratio"].shift(1)
    hh_hl_1       = out["hh_hl"].shift(1)

    # Touch & Reject: precio cerca de EMA (≤ 0.5 × ATR)
    touch_long  = (close_1 - ema21_1).abs() / atr_1.replace(0, np.nan) <= 0.5
    touch_short = (close_1 - ema21_1).abs() / atr_1.replace(0, np.nan) <= 0.5

    # LONG conditions
    long_signal = (
        hh_hl_1.fillna(False) &                        # estructura HH/HL
        (close_1 > ema21_1) &                           # sobre EMA
        touch_long &                                    # touch de EMA
        (adx_1 >= cfg.adx_min) &                        # ADX filtro
        (pdi_1 > ndi_1) &                               # DMI alcista
        (body_ratio_1 >= cfg.body_threshold) &          # body confirmation
        (close_1 > open_1)                              # vela alcista
    )

    # SHORT conditions (espejo)
    short_signal = (
        ~hh_hl_1.fillna(True) &                        # estructura LL/LH
        (close_1 < ema21_1) &                           # bajo EMA
        touch_short &                                   # touch de EMA
        (adx_1 >= cfg.adx_min) &                        # ADX filtro
        (ndi_1 > pdi_1) &                               # DMI bajista
        (body_ratio_1 >= cfg.body_threshold) &          # body confirmation
        (close_1 < open_1)                              # vela bajista
    )

    # Combinar señales (sin señal simultánea long+short por construcción)
    signal = pd.Series(0, index=out.index, name="signal", dtype=int)
    signal[long_signal]  = 1
    signal[short_signal] = -1

    out["signal"] = signal
    return out


# ── Cálculo de SL/TP ─────────────────────────────────────────────────────

def compute_sl_tp(
    entry_price: float,
    direction: int,
    atr: float,
    cfg: SignalConfig,
    digits: int = 3,
) -> tuple[float, float]:
    """
    Calcula SL y TP basado en ATR.
    Espejo exacto de CalculateSLTP() en el EA MQL5.

    Args:
        entry_price: Precio de entrada
        direction:   1=LONG, -1=SHORT
        atr:         Valor del ATR en la barra de entrada
        cfg:         Configuración de la señal
        digits:      Decimales del símbolo (USDJPY=3, EURUSD=5)

    Returns:
        (sl_price, tp_price)
    """
    sl_dist = atr * cfg.atr_sl_mult
    tp_dist = atr * cfg.atr_tp_mult

    if direction == 1:  # LONG
        sl = round(entry_price - sl_dist, digits)
        tp = round(entry_price + tp_dist, digits)
    else:               # SHORT
        sl = round(entry_price + sl_dist, digits)
        tp = round(entry_price - tp_dist, digits)

    return sl, tp
