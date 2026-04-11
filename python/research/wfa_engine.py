"""
python/research/wfa_engine.py
──────────────────────────────
Walk-Forward Analysis vectorizado con vectorbt.

Genera ventanas IS/OOS deslizantes y calcula métricas completas
por ventana. Aplica criterios de aceptación F3 automáticamente.

Métricas calculadas:
    - Profit Factor (PF)
    - Win Rate (WR)
    - Average Win / Average Loss (W/L ratio)
    - Max Drawdown (DD%)
    - Sharpe Ratio
    - Sortino Ratio
    - Ulcer Index
    - Robustness Index (RI = PF_OOS / PF_IS)
    - Expectancy (por trade)
    - Total trades
"""

import warnings
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

# vectorbt puede generar warnings de numba/numpy — suprimir en backtesting
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

try:
    import vectorbt as vbt
    VBT_AVAILABLE = True
except ImportError:
    VBT_AVAILABLE = False

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from python.research.signals import SignalConfig, generate_signals

console = Console()


# ── Métricas de un run ────────────────────────────────────────────────────

@dataclass
class WindowMetrics:
    """Métricas calculadas para una ventana IS u OOS."""
    n_trades:      int   = 0
    profit_factor: float = 0.0
    win_rate:      float = 0.0
    avg_win:       float = 0.0
    avg_loss:      float = 0.0
    wl_ratio:      float = 0.0
    max_dd_pct:    float = 0.0
    sharpe:        float = 0.0
    sortino:       float = 0.0
    ulcer_index:   float = 0.0
    expectancy:    float = 0.0
    net_pnl:       float = 0.0
    total_return:  float = 0.0

    def meets_criteria(
        self,
        pf_min: float = 1.20,
        dd_max: float = 10.0,
        trades_min: int = 80,
    ) -> bool:
        """Verifica criterios de aceptación IS."""
        return (
            self.profit_factor >= pf_min and
            self.max_dd_pct <= dd_max and
            self.n_trades >= trades_min
        )


@dataclass
class WFAWindow:
    """Ventana completa IS + OOS con sus métricas."""
    window_idx: int
    is_from:    datetime
    is_to:      datetime
    oos_from:   datetime
    oos_to:     datetime
    is_metrics: WindowMetrics = field(default_factory=WindowMetrics)
    oos_metrics: WindowMetrics = field(default_factory=WindowMetrics)

    @property
    def robustness_index(self) -> float:
        """RI = PF_OOS / PF_IS. > 0.85 = robusto."""
        if self.is_metrics.profit_factor == 0:
            return 0.0
        return self.oos_metrics.profit_factor / self.is_metrics.profit_factor


@dataclass
class WFAResult:
    """Resultado completo del WFA (todas las ventanas)."""
    run_id:       str
    ea_version:   str
    symbol:       str
    timeframe:    str
    config:       SignalConfig
    windows:      list[WFAWindow] = field(default_factory=list)

    # Métricas agregadas (promedio ponderado por trades)
    @property
    def avg_is_pf(self) -> float:
        pfs = [w.is_metrics.profit_factor for w in self.windows if w.is_metrics.n_trades > 0]
        return float(np.mean(pfs)) if pfs else 0.0

    @property
    def avg_oos_pf(self) -> float:
        pfs = [w.oos_metrics.profit_factor for w in self.windows if w.oos_metrics.n_trades > 0]
        return float(np.mean(pfs)) if pfs else 0.0

    @property
    def avg_robustness_index(self) -> float:
        ris = [w.robustness_index for w in self.windows]
        return float(np.mean(ris)) if ris else 0.0

    @property
    def max_oos_dd(self) -> float:
        dds = [w.oos_metrics.max_dd_pct for w in self.windows]
        return float(max(dds)) if dds else 0.0

    @property
    def total_is_trades(self) -> int:
        return sum(w.is_metrics.n_trades for w in self.windows)

    @property
    def avg_oos_sharpe(self) -> float:
        sharpes = [w.oos_metrics.sharpe for w in self.windows if w.oos_metrics.n_trades > 0]
        return float(np.mean(sharpes)) if sharpes else 0.0

    def meets_f3_criteria(
        self,
        pf_is_min: float = 1.20,
        pf_oos_min: float = 1.10,
        ri_min: float = 0.90,
        dd_max: float = 10.0,
        trades_is_min: int = 80,
    ) -> tuple[bool, dict]:
        """
        Evalúa si el WFA cumple todos los criterios de aceptación F3.
        Returns: (passed: bool, details: dict)
        """
        checks = {
            "pf_is":    (self.avg_is_pf >= pf_is_min,   f"{self.avg_is_pf:.2f} ≥ {pf_is_min}"),
            "pf_oos":   (self.avg_oos_pf >= pf_oos_min,  f"{self.avg_oos_pf:.2f} ≥ {pf_oos_min}"),
            "ri":       (self.avg_robustness_index >= ri_min, f"{self.avg_robustness_index:.2f} ≥ {ri_min}"),
            "dd":       (self.max_oos_dd <= dd_max,       f"{self.max_oos_dd:.1f}% ≤ {dd_max}%"),
            "trades":   (self.total_is_trades >= trades_is_min, f"{self.total_is_trades} ≥ {trades_is_min}"),
        }
        passed = all(v[0] for v in checks.values())
        return passed, checks

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "ea_version": self.ea_version,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "avg_is_pf": self.avg_is_pf,
            "avg_oos_pf": self.avg_oos_pf,
            "avg_robustness_index": self.avg_robustness_index,
            "max_oos_dd": self.max_oos_dd,
            "total_is_trades": self.total_is_trades,
            "avg_oos_sharpe": self.avg_oos_sharpe,
            "n_windows": len(self.windows),
        }


# ── Motor principal ───────────────────────────────────────────────────────

def generate_wfa_windows(
    df: pd.DataFrame,
    is_months: int,
    oos_months: int,
    step_months: int,
) -> list[tuple]:
    """
    Genera lista de ventanas IS/OOS deslizantes.
    Función standalone — no requiere vectorbt.

    Returns: lista de (is_from, is_to, oos_from, oos_to)
    """
    windows = []
    start = df.index[0]
    end   = df.index[-1]

    current = start
    while True:
        is_from  = current
        is_to    = is_from + pd.DateOffset(months=is_months)
        oos_from = is_to
        oos_to   = oos_from + pd.DateOffset(months=oos_months)

        if oos_to > end:
            break

        windows.append((is_from, is_to, oos_from, oos_to))
        current = current + pd.DateOffset(months=step_months)

    return windows


class WFAEngine:
    """
    Motor de Walk-Forward Analysis.

    Genera ventanas IS/OOS deslizantes, corre backtest vectorizado
    con vectorbt y calcula métricas completas por ventana.
    """

    def __init__(
        self,
        initial_capital: float = 10_000.0,
        commission_pct:  float = 0.0001,   # 1 pip típico en forex
        slippage_pct:    float = 0.0001,   # 1 pip slippage
    ):
        if not VBT_AVAILABLE:
            raise ImportError(
                "vectorbt no instalado. Ejecutar: pip install vectorbt"
            )
        self.initial_capital = initial_capital
        self.commission_pct  = commission_pct
        self.slippage_pct    = slippage_pct

    # ── WFA principal ─────────────────────────────────────────────────────

    def run_wfa(
        self,
        df: pd.DataFrame,
        config: SignalConfig,
        run_id: str,
        ea_version: str,
        symbol: str,
        timeframe: str = "H4",
        is_months: int  = 36,
        oos_months: int = 6,
        step_months: int = 6,
    ) -> WFAResult:
        """
        Ejecuta Walk-Forward Analysis completo.

        Args:
            df:          DataFrame OHLCV con DatetimeIndex UTC
            config:      Parámetros de la señal
            run_id:      Identificador del run
            ea_version:  Versión del EA (ej: "v2.3")
            symbol:      Símbolo (ej: "USDJPY")
            timeframe:   Timeframe (ej: "H4")
            is_months:   Meses de In-Sample por ventana
            oos_months:  Meses de Out-of-Sample por ventana
            step_months: Avance de la ventana en meses

        Returns:
            WFAResult con todas las ventanas y métricas agregadas
        """
        result = WFAResult(
            run_id=run_id,
            ea_version=ea_version,
            symbol=symbol,
            timeframe=timeframe,
            config=config,
        )

        windows = self._generate_windows(df, is_months, oos_months, step_months)
        console.print(
            f"\n[bold cyan]═══ WFA: {ea_version} / {symbol} {timeframe} ═══[/bold cyan]"
        )
        console.print(f"Run ID: [dim]{run_id}[/dim]")
        console.print(f"Ventanas: {len(windows)} | IS: {is_months}m | OOS: {oos_months}m\n")

        # Calcular señales sobre datos completos (más eficiente)
        df_signals = generate_signals(df, config)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Corriendo ventanas...", total=len(windows))

            for i, (is_from, is_to, oos_from, oos_to) in enumerate(windows):
                # Slices IS y OOS
                is_data  = df_signals.loc[is_from:is_to]
                oos_data = df_signals.loc[oos_from:oos_to]

                is_metrics  = self._run_single(is_data,  config)
                oos_metrics = self._run_single(oos_data, config)

                window = WFAWindow(
                    window_idx=i,
                    is_from=is_from, is_to=is_to,
                    oos_from=oos_from, oos_to=oos_to,
                    is_metrics=is_metrics,
                    oos_metrics=oos_metrics,
                )
                result.windows.append(window)

                progress.update(task, advance=1,
                    description=f"Ventana {i+1}/{len(windows)} — OOS PF: {oos_metrics.profit_factor:.2f}")

        self._print_wfa_summary(result)
        return result

    # ── Single backtest ───────────────────────────────────────────────────

    def _run_single(
        self, df: pd.DataFrame, config: SignalConfig
    ) -> WindowMetrics:
        """
        Corre un backtest simple sobre un slice de datos.
        Usa vectorbt para vectorización completa.
        """
        if len(df) < config.lookback * 2 + 50:
            return WindowMetrics()  # Datos insuficientes

        signal = df["signal"] if "signal" in df.columns else pd.Series(0, index=df.index)
        atr    = df["atr"]    if "atr" in df.columns    else pd.Series(0.001, index=df.index)

        # Construir entries/exits por trade
        entries_long  = signal == 1
        entries_short = signal == -1

        # SL/TP dinámico por ATR — simplificado para vectorización
        # En vectorbt usamos sl_stop y tp_stop como fracciones del precio
        sl_frac = (config.atr_sl_mult * atr / df["close"]).clip(0.001, 0.10)
        tp_frac = (config.atr_tp_mult * atr / df["close"]).clip(0.001, 0.20)

        try:
            # Portfolio vectorbt — longs
            pf_long = vbt.Portfolio.from_signals(
                close       = df["close"],
                entries     = entries_long,
                exits       = pd.Series(False, index=df.index),
                sl_stop     = sl_frac,
                tp_stop     = tp_frac,
                init_cash   = self.initial_capital,
                fees        = self.commission_pct,
                slippage    = self.slippage_pct,
                freq        = "4h",
            )

            # Portfolio vectorbt — shorts
            pf_short = vbt.Portfolio.from_signals(
                close       = df["close"],
                short_entries = entries_short,
                short_exits   = pd.Series(False, index=df.index),
                sl_stop     = sl_frac,
                tp_stop     = tp_frac,
                init_cash   = self.initial_capital,
                fees        = self.commission_pct,
                slippage    = self.slippage_pct,
                freq        = "4h",
            )

            # Combinar trades
            trades_long  = pf_long.trades.records_readable
            trades_short = pf_short.trades.records_readable
            all_trades   = pd.concat([trades_long, trades_short], ignore_index=True)

            return self._compute_metrics(all_trades, pf_long, pf_short)

        except Exception as e:
            console.print(f"[yellow]⚠ Error en backtest: {e}[/yellow]")
            return WindowMetrics()

    # ── Métricas ──────────────────────────────────────────────────────────

    def _compute_metrics(
        self,
        trades: pd.DataFrame,
        pf_long,
        pf_short,
    ) -> WindowMetrics:
        """Calcula todas las métricas de performance."""
        if trades.empty or len(trades) == 0:
            return WindowMetrics()

        # PnL por trade (columna "PnL" en vectorbt)
        pnl_col = next(
            (c for c in trades.columns if "pnl" in c.lower() or "profit" in c.lower()),
            None
        )
        if pnl_col is None:
            return WindowMetrics()

        pnl = trades[pnl_col].values

        wins  = pnl[pnl > 0]
        losses = pnl[pnl < 0]

        n_trades = len(pnl)
        n_wins   = len(wins)

        # Profit Factor
        gross_profit = wins.sum()  if len(wins)   > 0 else 0
        gross_loss   = abs(losses.sum()) if len(losses) > 0 else 0
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (
            1.5 if gross_profit > 0 else 0.0
        )

        # Win Rate
        wr = n_wins / n_trades if n_trades > 0 else 0

        # Avg Win / Avg Loss
        avg_win  = wins.mean()   if len(wins)   > 0 else 0
        avg_loss = abs(losses.mean()) if len(losses) > 0 else 0
        wl_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0

        # Expectancy
        expectancy = (wr * avg_win) - ((1 - wr) * avg_loss)

        # Net PnL
        net_pnl = pnl.sum()

        # Max Drawdown — usar equity curve del portfolio long (dominante)
        try:
            eq = pf_long.value()
            if len(eq) > 0:
                running_max = eq.cummax()
                drawdown = (eq - running_max) / running_max * 100
                max_dd = abs(drawdown.min())
            else:
                max_dd = 0.0
        except Exception:
            max_dd = 0.0

        # Sharpe / Sortino — sobre retornos diarios
        try:
            returns = pf_long.returns()
            if len(returns) > 5:
                sharpe  = returns.mean() / returns.std() * np.sqrt(252 * 6) if returns.std() > 0 else 0
                neg_ret = returns[returns < 0]
                sortino = returns.mean() / neg_ret.std() * np.sqrt(252 * 6) if (len(neg_ret) > 0 and neg_ret.std() > 0) else 0
            else:
                sharpe = sortino = 0.0
        except Exception:
            sharpe = sortino = 0.0

        # Ulcer Index — penaliza profundidad Y duración del drawdown
        ulcer = self._compute_ulcer_index(pf_long)

        return WindowMetrics(
            n_trades      = n_trades,
            profit_factor = round(pf, 4),
            win_rate      = round(wr, 4),
            avg_win       = round(avg_win, 4),
            avg_loss      = round(avg_loss, 4),
            wl_ratio      = round(wl_ratio, 4),
            max_dd_pct    = round(max_dd, 2),
            sharpe        = round(sharpe, 4),
            sortino       = round(sortino, 4),
            ulcer_index   = round(ulcer, 4),
            expectancy    = round(expectancy, 4),
            net_pnl       = round(net_pnl, 2),
            total_return  = round(net_pnl / self.initial_capital * 100, 2),
        )

    def _compute_ulcer_index(self, portfolio) -> float:
        """
        Ulcer Index = sqrt(mean(drawdown^2))
        Penaliza duración Y profundidad del drawdown (Pilar 9 del blueprint).
        """
        try:
            eq = portfolio.value()
            running_max = eq.cummax()
            pct_drawdown = ((eq - running_max) / running_max * 100).fillna(0)
            return float(np.sqrt((pct_drawdown ** 2).mean()))
        except Exception:
            return 0.0

    # ── Generación de ventanas ─────────────────────────────────────────────

    def _generate_windows(
        self,
        df: pd.DataFrame,
        is_months: int,
        oos_months: int,
        step_months: int,
    ) -> list[tuple]:
        """Delegación a función standalone (testeable sin vectorbt)."""
        return generate_wfa_windows(df, is_months, oos_months, step_months)

    # ── Print summary ──────────────────────────────────────────────────────

    def _print_wfa_summary(self, result: WFAResult):
        """Imprime tabla de resumen WFA en terminal."""
        table = Table(
            title=f"WFA: {result.ea_version} / {result.symbol}",
            show_header=True,
            header_style="bold magenta"
        )
        table.add_column("Ventana", style="dim")
        table.add_column("IS PF",   justify="right")
        table.add_column("IS Trades", justify="right")
        table.add_column("OOS PF",  justify="right")
        table.add_column("OOS WR",  justify="right")
        table.add_column("OOS DD%", justify="right")
        table.add_column("RI",      justify="right")

        for w in result.windows:
            ri_color = "green" if w.robustness_index >= 0.90 else "yellow"
            table.add_row(
                f"{w.is_from.strftime('%Y-%m')}→{w.oos_to.strftime('%Y-%m')}",
                f"{w.is_metrics.profit_factor:.2f}",
                str(w.is_metrics.n_trades),
                f"{w.oos_metrics.profit_factor:.2f}",
                f"{w.oos_metrics.win_rate*100:.1f}%",
                f"{w.oos_metrics.max_dd_pct:.1f}%",
                f"[{ri_color}]{w.robustness_index:.2f}[/{ri_color}]",
            )

        console.print(table)

        # Resumen agregado
        passed, checks = result.meets_f3_criteria()
        status_color = "green" if passed else "red"
        status_text  = "✓ CRITERIOS F3 CUMPLIDOS" if passed else "✗ CRITERIOS F3 NO CUMPLIDOS"

        console.print(f"\n[bold]Resumen Agregado:[/bold]")
        console.print(f"  PF IS promedio:   {result.avg_is_pf:.2f}")
        console.print(f"  PF OOS promedio:  {result.avg_oos_pf:.2f}")
        console.print(f"  Robustness Index: {result.avg_robustness_index:.2f}")
        console.print(f"  Max DD OOS:       {result.max_oos_dd:.1f}%")
        console.print(f"  Total trades IS:  {result.total_is_trades}")
        console.print(f"  Sharpe OOS avg:   {result.avg_oos_sharpe:.2f}")
        console.print(f"\n[bold {status_color}]{status_text}[/bold {status_color}]")

        if not passed:
            console.print("\n[yellow]Detalle de checks:[/yellow]")
            for k, (ok, detail) in checks.items():
                icon = "✓" if ok else "✗"
                color = "green" if ok else "red"
                console.print(f"  [{color}]{icon}[/{color}] {k}: {detail}")
