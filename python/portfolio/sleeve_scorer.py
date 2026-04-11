"""
python/portfolio/sleeve_scorer.py
──────────────────────────────────
Calcula KPIs institucionales por sleeve (versión de EA / activo).

Un "sleeve" es una combinación EA_version × symbol × timeframe.
Ejemplo: sleeve("v1.9", "USDJPY", "H4")

KPIs calculados (Pilares 9 del Blueprint):
    - Profit Factor
    - Win Rate
    - W/L Ratio
    - Sharpe Ratio
    - Sortino Ratio     (penaliza solo volatilidad negativa)
    - Ulcer Index       (penaliza profundidad Y duración del DD)
    - Calmar Ratio      (retorno anual / max DD)
    - Robustness Index  (PF_OOS / PF_IS)
    - Max Drawdown %
    - Expectancy por trade
"""

from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()

# Períodos anualizados para H4 (6 velas/día × 252 días)
ANNUAL_PERIODS_H4 = 6 * 252


@dataclass
class SleeveKPIs:
    """KPIs completos de un sleeve."""
    sleeve_id:      str   = ""
    ea_version:     str   = ""
    symbol:         str   = ""
    timeframe:      str   = "H4"

    # Trade metrics
    n_trades:       int   = 0
    profit_factor:  float = 0.0
    win_rate:       float = 0.0
    avg_win:        float = 0.0
    avg_loss:       float = 0.0
    wl_ratio:       float = 0.0
    expectancy:     float = 0.0

    # Risk-adjusted
    sharpe:         float = 0.0
    sortino:        float = 0.0
    calmar:         float = 0.0
    ulcer_index:    float = 0.0

    # Drawdown
    max_dd_pct:     float = 0.0
    avg_dd_pct:     float = 0.0
    max_dd_duration_bars: int = 0

    # WFA
    robustness_index: float = 0.0
    is_pf:          float = 0.0
    oos_pf:         float = 0.0

    # Returns
    total_return_pct: float = 0.0
    annual_return_pct: float = 0.0
    net_pnl:        float = 0.0

    def score(self) -> float:
        """
        Score compuesto para ranking de sleeves.
        Ponderación calibrada para estrategia pullback H4.

        No optimizar los pesos — son juicios cualitativos, no objetivos.
        """
        if self.n_trades < 10:
            return 0.0

        score = (
            0.25 * min(self.profit_factor / 1.5, 1.0) +   # PF normalizado (1.5 = máx esperado)
            0.20 * min(self.robustness_index / 1.0, 1.0) + # RI normalizado
            0.20 * max(0, 1 - self.max_dd_pct / 20.0) +   # penaliza DD > 20%
            0.15 * min(max(self.sortino, 0) / 2.0, 1.0) +  # Sortino normalizado
            0.10 * max(0, 1 - self.ulcer_index / 10.0) +   # penaliza Ulcer alto
            0.10 * min(self.win_rate / 0.50, 1.0)          # WR normalizado (50% = máx esperado)
        )
        return round(score, 4)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["composite_score"] = self.score()
        return d


class SleeveScorer:
    """
    Calcula KPIs institucionales para un sleeve dado su equity curve
    y lista de trades.
    """

    def __init__(self, initial_capital: float = 10_000.0):
        self.initial_capital = initial_capital

    def compute(
        self,
        trade_pnls:   np.ndarray,
        equity_curve: Optional[np.ndarray] = None,
        sleeve_id:    str = "",
        ea_version:   str = "",
        symbol:       str = "",
        timeframe:    str = "H4",
        is_pf:        float = 0.0,
        oos_pf:       float = 0.0,
    ) -> SleeveKPIs:
        """
        Calcula todos los KPIs de un sleeve.

        Args:
            trade_pnls:   Array de PnL por trade (positivo=win, negativo=loss)
            equity_curve: Array de equity (opcional, si ya disponible)
            sleeve_id:    Identificador único del sleeve
            ea_version:   Versión del EA
            symbol:       Símbolo
            timeframe:    Timeframe
            is_pf:        PF In-Sample (para Robustness Index)
            oos_pf:       PF Out-of-Sample

        Returns:
            SleeveKPIs con todos los KPIs calculados
        """
        kpis = SleeveKPIs(
            sleeve_id  = sleeve_id or f"{ea_version}_{symbol}_{timeframe}",
            ea_version = ea_version,
            symbol     = symbol,
            timeframe  = timeframe,
            is_pf      = is_pf,
            oos_pf     = oos_pf,
        )

        if len(trade_pnls) == 0:
            return kpis

        pnl = trade_pnls

        # ── Trade metrics ─────────────────────────────────────────────────
        wins   = pnl[pnl > 0]
        losses = pnl[pnl < 0]

        kpis.n_trades = len(pnl)

        gross_profit = wins.sum()  if len(wins)   > 0 else 0.0
        gross_loss   = abs(losses.sum()) if len(losses) > 0 else 0.0

        kpis.profit_factor = (
            gross_profit / gross_loss if gross_loss > 0
            else (1.5 if gross_profit > 0 else 0.0)
        )
        kpis.win_rate    = len(wins) / kpis.n_trades
        kpis.avg_win     = float(wins.mean())   if len(wins)   > 0 else 0.0
        kpis.avg_loss    = float(abs(losses.mean())) if len(losses) > 0 else 0.0
        kpis.wl_ratio    = kpis.avg_win / kpis.avg_loss if kpis.avg_loss > 0 else 0.0
        kpis.expectancy  = (kpis.win_rate * kpis.avg_win) - ((1 - kpis.win_rate) * kpis.avg_loss)
        kpis.net_pnl     = float(pnl.sum())

        # ── Equity curve ──────────────────────────────────────────────────
        if equity_curve is None:
            equity_curve = self.initial_capital + np.cumsum(pnl)
            equity_curve = np.insert(equity_curve, 0, self.initial_capital)

        kpis.total_return_pct = (equity_curve[-1] - equity_curve[0]) / equity_curve[0] * 100

        # ── Drawdown ──────────────────────────────────────────────────────
        running_max = np.maximum.accumulate(equity_curve)
        dd_series   = (equity_curve - running_max) / running_max * 100

        kpis.max_dd_pct = float(abs(dd_series.min()))
        kpis.avg_dd_pct = float(abs(dd_series[dd_series < 0].mean())) if (dd_series < 0).any() else 0.0

        # Duración máxima del drawdown en barras
        in_dd = dd_series < 0
        if in_dd.any():
            max_dur = 0
            cur_dur = 0
            for val in in_dd:
                if val:
                    cur_dur += 1
                    max_dur = max(max_dur, cur_dur)
                else:
                    cur_dur = 0
            kpis.max_dd_duration_bars = max_dur

        # ── Sharpe ────────────────────────────────────────────────────────
        returns = pd.Series(equity_curve).pct_change().dropna()
        if len(returns) > 2 and returns.std() > 0:
            kpis.sharpe = float(
                returns.mean() / returns.std() * np.sqrt(ANNUAL_PERIODS_H4)
            )

        # ── Sortino ───────────────────────────────────────────────────────
        neg_returns = returns[returns < 0]
        if len(neg_returns) > 2 and neg_returns.std() > 0:
            kpis.sortino = float(
                returns.mean() / neg_returns.std() * np.sqrt(ANNUAL_PERIODS_H4)
            )

        # ── Calmar ────────────────────────────────────────────────────────
        n_years = kpis.n_trades / (252 * 6 / 20)  # estimación: ~20 trades/mes
        kpis.annual_return_pct = kpis.total_return_pct / max(n_years, 0.1)
        kpis.calmar = kpis.annual_return_pct / kpis.max_dd_pct if kpis.max_dd_pct > 0 else 0.0

        # ── Ulcer Index ───────────────────────────────────────────────────
        kpis.ulcer_index = float(np.sqrt((dd_series ** 2).mean()))

        # ── Robustness Index ──────────────────────────────────────────────
        kpis.robustness_index = oos_pf / is_pf if is_pf > 0 else 0.0

        return kpis

    def compare_sleeves(self, sleeves: list[SleeveKPIs]) -> pd.DataFrame:
        """
        Genera tabla comparativa de múltiples sleeves.
        Ordenado por composite score.
        """
        records = []
        for s in sleeves:
            records.append({
                "sleeve":    s.sleeve_id,
                "trades":    s.n_trades,
                "PF":        round(s.profit_factor, 2),
                "WR%":       round(s.win_rate * 100, 1),
                "W/L":       round(s.wl_ratio, 2),
                "Sharpe":    round(s.sharpe, 2),
                "Sortino":   round(s.sortino, 2),
                "Ulcer":     round(s.ulcer_index, 2),
                "Calmar":    round(s.calmar, 2),
                "MaxDD%":    round(s.max_dd_pct, 1),
                "RI":        round(s.robustness_index, 2),
                "Score":     round(s.score(), 3),
            })

        df = pd.DataFrame(records).sort_values("Score", ascending=False)
        self._print_comparison(df)
        return df

    def _print_comparison(self, df: pd.DataFrame):
        """Imprime tabla comparativa en terminal."""
        table = Table(
            title="Comparación de Sleeves",
            show_header=True,
            header_style="bold cyan"
        )
        for col in df.columns:
            table.add_column(col, justify="right" if col != "sleeve" else "left")

        for _, row in df.iterrows():
            score_color = (
                "green"  if row["Score"] > 0.6 else
                "yellow" if row["Score"] > 0.4 else
                "red"
            )
            ri_color = (
                "green"  if row["RI"] >= 0.90 else
                "yellow" if row["RI"] >= 0.70 else
                "red"
            )
            table.add_row(
                str(row["sleeve"]),
                str(row["trades"]),
                str(row["PF"]),
                f"{row['WR%']}%",
                str(row["W/L"]),
                str(row["Sharpe"]),
                str(row["Sortino"]),
                str(row["Ulcer"]),
                str(row["Calmar"]),
                f"{row['MaxDD%']}%",
                f"[{ri_color}]{row['RI']}[/{ri_color}]",
                f"[{score_color}]{row['Score']}[/{score_color}]",
            )

        console.print(table)
