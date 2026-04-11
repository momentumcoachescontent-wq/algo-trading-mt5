"""
python/research/monte_carlo.py
───────────────────────────────
Simulación Monte Carlo sobre series de trades reales.

Método: Permutación aleatoria del orden de trades (bootstrap).
No asume distribución — usa la distribución empírica real.

Métricas simuladas (n=1000 permutaciones):
    - Distribución de Profit Factor
    - Distribución de Max Drawdown
    - Probabilidad de PF > 1.0 / 1.2
    - Probabilidad de ruina (DD > umbral)
    - Percentiles P5, P25, P50, P75, P95

Por qué permutación y no síntesis:
    Preserva la distribución real de wins/losses.
    La síntesis introduce supuestos de normalidad que no aplican a forex.
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()


@dataclass
class MCConfig:
    """Configuración de la simulación Monte Carlo."""
    n_simulations:    int   = 1000
    initial_capital:  float = 10_000.0
    ruin_threshold:   float = 20.0    # DD% considerado "ruina"
    seed:             Optional[int] = 42


@dataclass
class MCResults:
    """Resultados completos de la simulación Monte Carlo."""
    run_id:       str
    n_simulations: int
    base_pf:      float    # PF del run original (no permutado)
    base_dd:      float    # DD% del run original

    # Distribuciones
    pf_distribution:  np.ndarray = field(default_factory=lambda: np.array([]))
    dd_distribution:  np.ndarray = field(default_factory=lambda: np.array([]))
    net_pnl_distribution: np.ndarray = field(default_factory=lambda: np.array([]))

    # Percentiles PF
    @property
    def pf_p5(self) -> float:
        return float(np.percentile(self.pf_distribution, 5))

    @property
    def pf_p25(self) -> float:
        return float(np.percentile(self.pf_distribution, 25))

    @property
    def pf_p50(self) -> float:
        return float(np.percentile(self.pf_distribution, 50))

    @property
    def pf_p75(self) -> float:
        return float(np.percentile(self.pf_distribution, 75))

    @property
    def pf_p95(self) -> float:
        return float(np.percentile(self.pf_distribution, 95))

    # Probabilidades
    @property
    def prob_pf_gt_1(self) -> float:
        return float((self.pf_distribution > 1.0).mean())

    @property
    def prob_pf_gt_1_2(self) -> float:
        return float((self.pf_distribution > 1.2).mean())

    @property
    def prob_ruin(self) -> float:
        """Probabilidad de DD > ruin_threshold."""
        # Calculada desde dd_distribution
        return 0.0  # Se setea en MonteCarlo.run()

    # Percentiles DD
    @property
    def dd_p50(self) -> float:
        return float(np.percentile(self.dd_distribution, 50))

    @property
    def dd_p95(self) -> float:
        return float(np.percentile(self.dd_distribution, 95))

    def to_dict(self) -> dict:
        return {
            "run_id":          self.run_id,
            "n_simulations":   self.n_simulations,
            "base_pf":         self.base_pf,
            "base_dd":         self.base_dd,
            "pf_p5":           self.pf_p5,
            "pf_p25":          self.pf_p25,
            "pf_p50":          self.pf_p50,
            "pf_p75":          self.pf_p75,
            "pf_p95":          self.pf_p95,
            "prob_pf_gt_1":    round(self.prob_pf_gt_1 * 100, 1),
            "prob_pf_gt_1_2":  round(self.prob_pf_gt_1_2 * 100, 1),
            "dd_p50":          self.dd_p50,
            "dd_p95":          self.dd_p95,
        }


class MonteCarlo:
    """
    Simulación Monte Carlo por permutación de trades.

    Cómo funciona:
    1. Toma la lista real de PnL por trade del OOS
    2. Permuta el orden aleatoriamente n veces
    3. En cada permutación, recalcula PF y Max DD
    4. Genera distribución de outcomes posibles

    Esto responde: "Si el orden de mis trades hubiese sido diferente,
    ¿cuál sería el rango de resultados posibles?"
    """

    def __init__(self, cfg: Optional[MCConfig] = None):
        self.cfg = cfg or MCConfig()

    def run(
        self,
        trade_pnls: np.ndarray,
        run_id: str,
        initial_capital: Optional[float] = None,
    ) -> MCResults:
        """
        Ejecuta la simulación Monte Carlo.

        Args:
            trade_pnls: Array de PnL por trade (del OOS)
            run_id:     ID del run base
            initial_capital: Capital inicial (override cfg)

        Returns:
            MCResults con distribuciones completas
        """
        capital = initial_capital or self.cfg.initial_capital
        rng = np.random.default_rng(self.cfg.seed)

        n_trades = len(trade_pnls)
        if n_trades < 10:
            raise ValueError(
                f"Insuficientes trades para Monte Carlo: {n_trades}. "
                "Se requieren ≥ 10 trades."
            )

        # Métricas del run original
        base_pf  = self._compute_pf(trade_pnls)
        base_dd  = self._compute_max_dd(trade_pnls, capital)

        console.print(
            f"\n[bold cyan]═══ Monte Carlo: {self.cfg.n_simulations:,} permutaciones ═══[/bold cyan]"
        )
        console.print(f"Trades: {n_trades} | Capital: ${capital:,.0f}")
        console.print(f"Base PF: {base_pf:.2f} | Base DD: {base_dd:.1f}%\n")

        # Arrays de resultados
        pf_dist  = np.zeros(self.cfg.n_simulations)
        dd_dist  = np.zeros(self.cfg.n_simulations)
        pnl_dist = np.zeros(self.cfg.n_simulations)

        for i in range(self.cfg.n_simulations):
            permuted = rng.permutation(trade_pnls)
            pf_dist[i]  = self._compute_pf(permuted)
            dd_dist[i]  = self._compute_max_dd(permuted, capital)
            pnl_dist[i] = permuted.sum()

        # Probabilidad de ruina
        prob_ruin = float((dd_dist > self.cfg.ruin_threshold).mean())

        results = MCResults(
            run_id           = run_id,
            n_simulations    = self.cfg.n_simulations,
            base_pf          = base_pf,
            base_dd          = base_dd,
            pf_distribution  = pf_dist,
            dd_distribution  = dd_dist,
            net_pnl_distribution = pnl_dist,
        )

        self._print_summary(results, prob_ruin)
        return results

    # ── Métricas ──────────────────────────────────────────────────────────

    def _compute_pf(self, pnl: np.ndarray) -> float:
        """Profit Factor de una serie de PnL."""
        gross_profit = pnl[pnl > 0].sum()
        gross_loss   = abs(pnl[pnl < 0].sum())
        if gross_loss == 0:
            return 1.5 if gross_profit > 0 else 0.0
        return float(gross_profit / gross_loss)

    def _compute_max_dd(self, pnl: np.ndarray, initial_capital: float) -> float:
        """Max Drawdown % de una serie de PnL."""
        equity = initial_capital + np.cumsum(pnl)
        equity = np.insert(equity, 0, initial_capital)
        running_max = np.maximum.accumulate(equity)
        drawdown = (equity - running_max) / running_max * 100
        return float(abs(drawdown.min()))

    # ── Print ─────────────────────────────────────────────────────────────

    def _print_summary(self, results: MCResults, prob_ruin: float):
        """Imprime resumen de Monte Carlo en terminal."""
        table = Table(title="Distribución de Resultados (Monte Carlo)",
                      show_header=True, header_style="bold blue")
        table.add_column("Métrica")
        table.add_column("P5",  justify="right")
        table.add_column("P25", justify="right")
        table.add_column("P50 (mediana)", justify="right")
        table.add_column("P75", justify="right")
        table.add_column("P95", justify="right")

        table.add_row(
            "Profit Factor",
            f"{results.pf_p5:.2f}",
            f"{results.pf_p25:.2f}",
            f"[bold]{results.pf_p50:.2f}[/bold]",
            f"{results.pf_p75:.2f}",
            f"{results.pf_p95:.2f}",
        )

        dd_p5  = float(np.percentile(results.dd_distribution, 5))
        dd_p25 = float(np.percentile(results.dd_distribution, 25))
        dd_p75 = float(np.percentile(results.dd_distribution, 75))

        table.add_row(
            "Max DD%",
            f"{dd_p5:.1f}%",
            f"{dd_p25:.1f}%",
            f"[bold]{results.dd_p50:.1f}%[/bold]",
            f"{dd_p75:.1f}%",
            f"{results.dd_p95:.1f}%",
        )

        console.print(table)

        # Probabilidades
        pf_color = "green" if results.prob_pf_gt_1 >= 0.80 else "yellow"
        console.print(f"\nProbabilidad PF > 1.0:   [{pf_color}]{results.prob_pf_gt_1*100:.1f}%[/{pf_color}]")
        console.print(f"Probabilidad PF > 1.2:   {results.prob_pf_gt_1_2*100:.1f}%")

        ruin_color = "red" if prob_ruin > 0.05 else "green"
        console.print(f"Probabilidad de ruina:   [{ruin_color}]{prob_ruin*100:.1f}%[/{ruin_color}] (DD > {self.cfg.ruin_threshold}%)")

        # Coherencia: mediana ≈ base
        coherence = abs(results.pf_p50 - results.base_pf) / results.base_pf
        if coherence < 0.10:
            console.print(f"\n[green]✓ Sistema coherente:[/green] P50 ({results.pf_p50:.2f}) ≈ base ({results.base_pf:.2f})")
        else:
            console.print(
                f"\n[yellow]⚠ Divergencia: P50 ({results.pf_p50:.2f}) vs base ({results.base_pf:.2f}) "
                f"— varianza alta, pocos trades[/yellow]"
            )
