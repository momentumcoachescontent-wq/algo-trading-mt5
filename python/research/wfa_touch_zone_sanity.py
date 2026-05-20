"""
python/research/wfa_touch_zone_sanity.py
─────────────────────────────────────────
WFA Sanity Check: touch_zone_binary vs touch_zone_soft (umbral 0.50 ATR).

Compara Profit Factor OOS promedio con:
  - touch_zone_binary : gate duro en 0.50 ATR (comportamiento actual)
  - touch_zone_soft   : gate extendido en 0.75 ATR (incluye zona soft adicional)

Gate de aceptación (por cada símbolo):
  PF(soft) >= PF(binary) × (1 - DROP_GATE)

Si PF cae >10% en cualquier símbolo → EXIT(1) y reporte detallado.

Pares evaluados: GBPUSD, EURUSD
Datos: CSV en data/ o sintéticos con WARNING.

Backtest: walk-forward ligero (numpy/pandas, sin vectorbt).
  - IS  = 36 meses | OOS = 6 meses | step = 6 meses
  - SL  = 1.5 × ATR | TP = 2.5 × ATR
  - Trade simulado en cierre de barra siguiente a la señal
  - PF = gross_profit / gross_loss sobre trades OOS

Uso:
    python -m python.research.wfa_touch_zone_sanity
    python -m python.research.wfa_touch_zone_sanity --data-dir /ruta/a/csvs
"""

import sys
import argparse
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

from python.research.signals import SignalConfig, generate_signals

# ── Configuración ─────────────────────────────────────────────────────────

TOUCH_BINARY: float = 0.50   # gate actual (touch_zone_binary)
TOUCH_SOFT:   float = 0.75   # gate extendido (touch_zone_soft)
PF_DROP_GATE: float = 0.10   # si PF cae >10% → STOP

SYMBOLS     = ["GBPUSD", "EURUSD"]
DEFAULT_DATA_DIR = Path("data")

# WFA params (espejo v2.3.yaml)
IS_MONTHS   = 36
OOS_MONTHS  = 6
STEP_MONTHS = 6

# Risk params (idénticos a v2.3)
ATR_SL_MULT  = 1.5
ATR_TP_MULT  = 2.5
COMMISSION   = 0.0001   # 1 pip simulado


# ── Generación de datos sintéticos ────────────────────────────────────────

def _generate_synthetic_ohlcv(symbol: str, n_bars: int = 15_000) -> pd.DataFrame:
    """
    Genera OHLCV sintético con características realistas del par.
    15000 barras H4 ≈ 10 años de datos de trading — suficiente para 5-6 ventanas WFA.
    (IS=36m ≈ 6500 barras, OOS=6m ≈ 1100 barras, step=6m)
    """
    seed = {"GBPUSD": 42, "EURUSD": 43}.get(symbol, 44)
    rng  = np.random.default_rng(seed)

    base  = {"GBPUSD": 1.2700, "EURUSD": 1.0800}.get(symbol, 1.1500)
    vol   = {"GBPUSD": 0.0008, "EURUSD": 0.0006}.get(symbol, 0.0007)
    dates = pd.date_range("2014-01-06", periods=n_bars, freq="4h")

    ret   = rng.normal(0, vol, n_bars)
    price = base * np.exp(np.cumsum(ret))

    bar_spread = rng.uniform(0.3, 1.8, n_bars) * vol
    high  = price * (1 + bar_spread * rng.uniform(0.4, 1.0, n_bars))
    low   = price * (1 - bar_spread * rng.uniform(0.4, 1.0, n_bars))
    open_ = price * (1 + rng.normal(0, vol * 0.3, n_bars))

    high  = np.maximum(high,  np.maximum(price, open_))
    low   = np.minimum(low,   np.minimum(price, open_))

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": price,
         "volume": rng.integers(1_000, 15_000, n_bars)},
        index=dates,
    )


def _load_or_generate(symbol: str, data_dir: Path) -> tuple[pd.DataFrame, bool]:
    """Intenta cargar CSV; genera sintético si no existe."""
    for suffix in [".csv", "_H4.csv", "_h4.csv", f"_{symbol}.csv"]:
        path = data_dir / f"{symbol}{suffix}"
        if path.exists():
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            df.columns = [c.lower() for c in df.columns]
            if {"open", "high", "low", "close"}.issubset(df.columns):
                print(f"  [DATA] {symbol}: cargado desde {path} ({len(df)} barras)")
                return df, False

    print(f"  [DATA] {symbol}: CSV no encontrado en {data_dir} — usando datos SINTÉTICOS")
    return _generate_synthetic_ohlcv(symbol), True


# ── Backtest ligero (sin vectorbt) ────────────────────────────────────────

def _simulate_trades(df_signals: pd.DataFrame) -> list[float]:
    """
    Simula trades con SL/TP fijo en ATR sobre el DataFrame con señales.
    Entrada en close de la barra siguiente a la señal.
    Retorna lista de PnL% por trade (positivo=ganancia, negativo=pérdida).
    """
    signals = df_signals["signal"].values
    closes  = df_signals["close"].values
    atrs    = df_signals["atr"].values
    n       = len(df_signals)

    pnls     = []
    in_trade = False
    entry_px = 0.0
    sl_px    = 0.0
    tp_px    = 0.0
    direction = 0

    for i in range(1, n):
        if in_trade:
            # Check SL/TP hit on current bar
            hi = df_signals["high"].values[i]
            lo = df_signals["low"].values[i]
            cl = closes[i]

            hit_tp = (direction == 1 and hi >= tp_px) or (direction == -1 and lo <= tp_px)
            hit_sl = (direction == 1 and lo <= sl_px) or (direction == -1 and hi >= sl_px)

            if hit_tp and not hit_sl:
                pnl_pct = direction * (tp_px - entry_px) / entry_px - COMMISSION
                pnls.append(pnl_pct)
                in_trade = False
            elif hit_sl:
                pnl_pct = direction * (sl_px - entry_px) / entry_px - COMMISSION
                pnls.append(pnl_pct)
                in_trade = False
            elif i == n - 1:
                pnl_pct = direction * (cl - entry_px) / entry_px - COMMISSION
                pnls.append(pnl_pct)
                in_trade = False
        else:
            sig = signals[i - 1]   # señal en barra anterior (shift=1)
            if sig != 0:
                atr_val   = atrs[i - 1]
                entry_px  = closes[i]   # entrada en cierre de barra i
                direction = int(sig)
                sl_px     = entry_px - direction * ATR_SL_MULT * atr_val
                tp_px     = entry_px + direction * ATR_TP_MULT * atr_val
                in_trade  = True

    return pnls


def _profit_factor(pnls: list[float]) -> float:
    if not pnls:
        return 0.0
    wins   = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]
    if not losses:
        return 1.5 if wins else 0.0
    return sum(wins) / sum(losses)


def _wfa_windows(df: pd.DataFrame) -> list[tuple]:
    """Genera ventanas IS/OOS deslizantes."""
    windows = []
    start   = df.index[0]
    end     = df.index[-1]
    current = start
    while True:
        is_from  = current
        is_to    = is_from + pd.DateOffset(months=IS_MONTHS)
        oos_from = is_to
        oos_to   = oos_from + pd.DateOffset(months=OOS_MONTHS)
        if oos_to > end:
            break
        windows.append((is_from, is_to, oos_from, oos_to))
        current = current + pd.DateOffset(months=STEP_MONTHS)
    return windows


def _run_wfa(df: pd.DataFrame, symbol: str, mode: str, touch_mult: float) -> float:
    """Corre WFA ligero. Retorna avg OOS Profit Factor."""
    cfg    = SignalConfig(touch_mult=touch_mult)
    df_sig = generate_signals(df, cfg)
    wins   = _wfa_windows(df_sig)

    if not wins:
        print(f"  [WARN] {symbol}/{mode}: no hay ventanas WFA suficientes ({len(df)} barras)")
        return 0.0

    oos_pfs = []
    for is_from, is_to, oos_from, oos_to in wins:
        oos_data = df_sig.loc[oos_from:oos_to]
        if len(oos_data) < 50:
            continue
        trades_oos = _simulate_trades(oos_data)
        oos_pfs.append(_profit_factor(trades_oos))

    avg_pf = float(np.mean(oos_pfs)) if oos_pfs else 0.0
    total_wins = sum(1 for w in wins)
    print(f"    {symbol}/{mode}: {len(oos_pfs)}/{total_wins} ventanas OOS | avg PF OOS = {avg_pf:.4f}")
    return avg_pf


# ── Sanity Check principal ────────────────────────────────────────────────

def run_sanity_check(data_dir: Path = DEFAULT_DATA_DIR) -> bool:
    """
    Ejecuta la comparación WFA binary vs soft para todos los símbolos.
    Retorna True si el check pasa, False si hay caída >10% de PF.
    """
    print("\n" + "═" * 62)
    print("[WFA_TOUCH_SANITY] Iniciando comparación touch_zone_binary vs soft")
    print(f"  touch_binary = {TOUCH_BINARY} ATR | touch_soft = {TOUCH_SOFT} ATR")
    print(f"  Gate: PF(soft) >= PF(binary) × {1 - PF_DROP_GATE:.2f}  (caída máx {PF_DROP_GATE*100:.0f}%)")
    print(f"  WFA: IS={IS_MONTHS}m OOS={OOS_MONTHS}m step={STEP_MONTHS}m | SL={ATR_SL_MULT}×ATR TP={ATR_TP_MULT}×ATR")
    print("═" * 62)

    symbol_results: dict[str, dict] = {}
    any_synthetic = False

    for symbol in SYMBOLS:
        print(f"\n[WFA_TOUCH_SANITY] {symbol}")
        df, is_synthetic = _load_or_generate(symbol, data_dir)
        if is_synthetic:
            any_synthetic = True

        pf_binary = _run_wfa(df, symbol, "binary", TOUCH_BINARY)
        pf_soft   = _run_wfa(df, symbol, "soft",   TOUCH_SOFT)

        drop_abs  = pf_binary - pf_soft
        drop_pct  = drop_abs / pf_binary if pf_binary > 0 else 0.0
        gate_ok   = drop_pct <= PF_DROP_GATE

        symbol_results[symbol] = {
            "pf_binary": pf_binary,
            "pf_soft":   pf_soft,
            "drop_pct":  drop_pct,
            "gate_ok":   gate_ok,
        }

    # ── Reporte final ────────────────────────────────────────────────────
    print("\n" + "═" * 62)
    print("[WFA_TOUCH_SANITY] Resultados finales")
    print("─" * 62)
    print(f"  {'Símbolo':<10} {'PF binary':>10} {'PF soft':>10} {'Caída%':>8} {'Gate':>12}")
    print("─" * 62)

    all_pass = True
    for sym, r in symbol_results.items():
        status = "PASS" if r["gate_ok"] else "FAIL ← STOP"
        print(
            f"  {sym:<10} {r['pf_binary']:>10.4f} {r['pf_soft']:>10.4f}"
            f" {r['drop_pct']*100:>7.1f}% {status:>12}"
        )
        if not r["gate_ok"]:
            all_pass = False

    print("─" * 62)

    if any_synthetic:
        print()
        print("  ADVERTENCIA: resultados basados en datos SINTÉTICOS.")
        print("  Proveer CSVs reales en data/ antes de tomar decisiones.")

    print()
    if all_pass:
        print("  GATE PASS: PF(soft) dentro del umbral de tolerancia (<= 10% caída)")
        print("  Seguro proceder con v4321 TouchZoneEngine")
    else:
        print("  GATE FAIL: PF(soft) cae >10% en uno o mas simbolos")
        print("  DETENER: No desplegar v4321 con zona soft extendida")
        print("  Investigar que pares degradan el PF antes de continuar")
    print("═" * 62 + "\n")

    return all_pass


# ── Entry point ───────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="WFA Touch Zone Sanity Check")
    p.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR,
        help="Directorio con CSV OHLCV (default: data/)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args   = _parse_args()
    passed = run_sanity_check(data_dir=args.data_dir)
    sys.exit(0 if passed else 1)
