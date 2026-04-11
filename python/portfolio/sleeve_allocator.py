"""
python/portfolio/sleeve_allocator.py
──────────────────────────────────────
Asignación de capital multi-sleeve usando Hierarchical Risk Parity (HRP).

HRP (Lopez de Prado, 2016) es superior a Mean-Variance para trading:
    - No requiere inversión de matriz de covarianza (singular en muchos casos)
    - Más robusto a errores de estimación
    - Diversifica por estructura jerárquica de correlaciones

Flujo:
    1. Equity curves de cada sleeve → retornos diarios
    2. Matriz de correlación
    3. Clustering jerárquico (Ward linkage)
    4. HRP → pesos de capital
    5. Filtro: excluir sleeves con correlación > 0.60 entre sí

RESERVADO PARA F8 — preparado aquí para no reescribir en el futuro.
"""

from typing import Optional
import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()

try:
    from pypfopt import HRPOpt, risk_models, expected_returns
    PYPFOPT_AVAILABLE = True
except ImportError:
    PYPFOPT_AVAILABLE = False


class SleeveAllocator:
    """
    Asigna capital entre sleeves usando HRP.

    Restricciones por defecto (ajustables):
        - Peso mínimo por sleeve: 5%
        - Peso máximo por sleeve: 60%
        - Excluir sleeves con correlación > max_correlation entre sí
        - Solo incluir sleeves con RI ≥ ri_min
    """

    def __init__(
        self,
        min_weight:      float = 0.05,
        max_weight:      float = 0.60,
        max_correlation: float = 0.60,
        ri_min:          float = 0.85,
    ):
        self.min_weight      = min_weight
        self.max_weight      = max_weight
        self.max_correlation = max_correlation
        self.ri_min          = ri_min

    def allocate(
        self,
        equity_curves: dict[str, np.ndarray],
        sleeve_kpis:   Optional[dict] = None,
    ) -> pd.Series:
        """
        Calcula pesos HRP para el portfolio de sleeves.

        Args:
            equity_curves: dict {sleeve_id: equity_array}
            sleeve_kpis:   dict {sleeve_id: SleeveKPIs} para filtros

        Returns:
            pd.Series con pesos normalizados por sleeve_id
        """
        if not PYPFOPT_AVAILABLE:
            console.print(
                "[yellow]PyPortfolioOpt no instalado. "
                "Ejecutar: pip install PyPortfolioOpt[/yellow]\n"
                "Usando equal-weight como fallback."
            )
            return self._equal_weight(list(equity_curves.keys()))

        # Filtrar sleeves por RI mínimo
        if sleeve_kpis:
            eligible = {
                sid: eq for sid, eq in equity_curves.items()
                if sleeve_kpis.get(sid) and
                   getattr(sleeve_kpis[sid], "robustness_index", 0) >= self.ri_min
            }
            excluded_ri = set(equity_curves.keys()) - set(eligible.keys())
            if excluded_ri:
                console.print(
                    f"[dim]Sleeves excluidos por RI < {self.ri_min}: {excluded_ri}[/dim]"
                )
        else:
            eligible = equity_curves

        if len(eligible) < 2:
            console.print(
                "[yellow]Menos de 2 sleeves elegibles. "
                "Equal-weight aplicado.[/yellow]"
            )
            return self._equal_weight(list(eligible.keys()))

        # Construir DataFrame de retornos
        returns_dict = {}
        min_len = min(len(eq) for eq in eligible.values())

        for sid, eq in eligible.items():
            eq_series = pd.Series(eq[-min_len:])
            returns_dict[sid] = eq_series.pct_change().dropna()

        returns_df = pd.DataFrame(returns_dict).dropna()

        if len(returns_df) < 30:
            console.print("[yellow]Datos insuficientes para HRP. Equal-weight.[/yellow]")
            return self._equal_weight(list(eligible.keys()))

        # Filtrar por correlación alta
        corr_matrix = returns_df.corr()
        eligible_after_corr = self._filter_high_correlation(
            corr_matrix, list(eligible.keys())
        )
        returns_df = returns_df[eligible_after_corr]

        # HRP via PyPortfolioOpt
        try:
            hrp = HRPOpt(returns=returns_df)
            hrp.optimize()
            weights = hrp.clean_weights(
                cutoff=self.min_weight,
                rounding=3,
            )

            # Aplicar límite máximo
            weights = pd.Series(weights)
            weights = weights.clip(upper=self.max_weight)
            weights = weights / weights.sum()  # re-normalizar

            self._print_allocation(weights, corr_matrix)
            return weights

        except Exception as e:
            console.print(f"[red]Error en HRP: {e}. Equal-weight aplicado.[/red]")
            return self._equal_weight(eligible_after_corr)

    def _filter_high_correlation(
        self, corr_matrix: pd.DataFrame, sleeves: list[str]
    ) -> list[str]:
        """
        Elimina sleeves con correlación > max_correlation entre sí.
        Estrategia greedy: mantiene el sleeve con mejor Sharpe.
        """
        filtered = list(sleeves)
        removed  = []

        for i in range(len(filtered)):
            for j in range(i + 1, len(filtered)):
                if i >= len(filtered) or j >= len(filtered):
                    break
                s1, s2 = filtered[i], filtered[j]
                if s1 not in corr_matrix.index or s2 not in corr_matrix.columns:
                    continue
                corr = abs(corr_matrix.loc[s1, s2])
                if corr > self.max_correlation:
                    # Remover el segundo (heurístico — en F8 usar Sharpe para decidir)
                    if s2 in filtered:
                        filtered.remove(s2)
                        removed.append(s2)
                        console.print(
                            f"[dim]Sleeve '{s2}' excluido por correlación "
                            f"{corr:.2f} con '{s1}'[/dim]"
                        )

        return filtered

    def _equal_weight(self, sleeves: list[str]) -> pd.Series:
        """Fallback: pesos iguales."""
        if not sleeves:
            return pd.Series()
        w = 1.0 / len(sleeves)
        return pd.Series({s: round(w, 4) for s in sleeves})

    def _print_allocation(self, weights: pd.Series, corr_matrix: pd.DataFrame):
        """Imprime asignación HRP en terminal."""
        table = Table(title="Asignación HRP Portfolio", header_style="bold green")
        table.add_column("Sleeve")
        table.add_column("Peso %", justify="right")

        for sleeve, weight in weights.sort_values(ascending=False).items():
            table.add_row(str(sleeve), f"{weight*100:.1f}%")

        console.print(table)

        # Diversificación
        hhi = (weights ** 2).sum()
        eff_n = 1 / hhi
        console.print(f"[dim]Diversificación efectiva: {eff_n:.1f} sleeves equivalentes[/dim]")
        console.print(f"[dim]HHI: {hhi:.3f} (< 0.25 = bien diversificado)[/dim]")

    def compute_portfolio_metrics(
        self,
        equity_curves: dict[str, np.ndarray],
        weights: pd.Series,
    ) -> dict:
        """
        Calcula métricas del portfolio combinado con los pesos asignados.
        """
        min_len = min(len(eq) for eq in equity_curves.values())
        portfolio_equity = np.zeros(min_len)

        for sid, weight in weights.items():
            if sid in equity_curves:
                eq = equity_curves[sid][-min_len:]
                # Normalizar a retornos y aplicar peso
                norm_returns = np.diff(eq) / eq[:-1]
                portfolio_equity += weight * norm_returns

        # Reconstruir equity
        portfolio_curve = np.cumprod(1 + portfolio_equity) * 10_000

        # Métricas
        running_max = np.maximum.accumulate(portfolio_curve)
        dd = (portfolio_curve - running_max) / running_max * 100

        returns = pd.Series(portfolio_equity)
        sharpe  = returns.mean() / returns.std() * np.sqrt(252 * 6) if returns.std() > 0 else 0

        return {
            "portfolio_total_return": (portfolio_curve[-1] / portfolio_curve[0] - 1) * 100,
            "portfolio_max_dd":       abs(dd.min()),
            "portfolio_sharpe":       sharpe,
            "portfolio_ulcer":        float(np.sqrt((dd ** 2).mean())),
            "n_sleeves":              len(weights),
        }
