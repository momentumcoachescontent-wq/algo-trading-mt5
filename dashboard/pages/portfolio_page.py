"""
dashboard/pages/portfolio_page.py
───────────────────────────────────
Página Portfolio: HRP allocation, correlaciones, métricas combinadas.
Activada completamente en F8.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.figure_factory as ff


def render():
    st.title("🗂️ Portfolio Allocation")
    st.markdown(
        '<span class="badge-blue">F8 — Preparado, no activo</span>',
        unsafe_allow_html=True
    )
    st.markdown("""
    Asignación de capital multi-sleeve usando **Hierarchical Risk Parity (HRP)**.
    Esta página estará completamente activa en F8 con datos reales de forward testing.
    """)
    st.markdown("---")

    # ── Simulación educativa con datos conocidos ──────────────────────────
    st.markdown("### Simulación HRP con sleeves validados")
    st.info("📌 Los pesos mostrados son ilustrativos — basados en equity curves simuladas desde las estadísticas WFA.")

    # Generar equity curves sintéticas desde estadísticas conocidas
    np.random.seed(42)
    n = 500

    sleeve_stats = {
        "v1.9 USDJPY": {"mu": 0.0008, "sigma": 0.008, "sharpe": 0.92},
        "v1.6 EURUSD": {"mu": 0.0003, "sigma": 0.010, "sharpe": 0.41},
        "v2.2 USDJPY": {"mu": 0.0006, "sigma": 0.009, "sharpe": 0.78},
    }

    returns_dict = {}
    equity_dict  = {}

    for name, stats in sleeve_stats.items():
        ret = np.random.normal(stats["mu"], stats["sigma"], n)
        eq  = 10_000 * np.cumprod(1 + ret)
        returns_dict[name] = ret
        equity_dict[name]  = eq

    returns_df = pd.DataFrame(returns_dict)

    # ── Matriz de correlación ─────────────────────────────────────────────
    corr_matrix = returns_df.corr()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Matriz de Correlación")
        fig = _chart_correlation(corr_matrix)
        st.plotly_chart(fig, use_container_width=True)

        # Advertencia si correlación alta
        for i in range(len(corr_matrix)):
            for j in range(i+1, len(corr_matrix)):
                corr_val = abs(corr_matrix.iloc[i,j])
                if corr_val > 0.60:
                    st.warning(
                        f"⚠️ Correlación alta ({corr_val:.2f}) entre "
                        f"{corr_matrix.index[i]} y {corr_matrix.columns[j]}"
                    )

    with col2:
        st.markdown("#### Asignación HRP (simulada)")
        # Weights HRP simplificado (inverso de volatilidad)
        vols    = returns_df.std()
        inv_vol = 1.0 / vols
        weights = inv_vol / inv_vol.sum()

        fig = _chart_weights(weights)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("**Pesos calculados:**")
        for name, w in weights.items():
            st.markdown(f"- **{name}:** {w*100:.1f}%")

        hhi = (weights**2).sum()
        eff_n = 1 / hhi
        st.markdown(f"\n*Diversificación efectiva: **{eff_n:.1f}** sleeves equivalentes*")

    st.markdown("---")

    # ── Equity curves comparadas ──────────────────────────────────────────
    st.markdown("### Equity Curves individuales vs Portfolio")
    fig = _chart_equity_curves(equity_dict, weights)
    st.plotly_chart(fig, use_container_width=True)

    # ── Métricas del portfolio combinado ─────────────────────────────────
    st.markdown("### Métricas del Portfolio Combinado")

    portfolio_returns = sum(
        weights[name] * returns_dict[name]
        for name in weights.index
    )
    portfolio_equity = 10_000 * np.cumprod(1 + portfolio_returns)

    running_max = np.maximum.accumulate(portfolio_equity)
    dd_series   = (portfolio_equity - running_max) / running_max * 100
    max_dd      = abs(dd_series.min())
    sharpe      = portfolio_returns.mean() / portfolio_returns.std() * np.sqrt(252 * 6)
    total_ret   = (portfolio_equity[-1] / 10_000 - 1) * 100

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Return Total",  f"{total_ret:.1f}%")
    c2.metric("Sharpe",        f"{sharpe:.2f}")
    c3.metric("Max DD",        f"{max_dd:.1f}%")
    c4.metric("Sleeves",       str(len(weights)))

    st.markdown("---")

    # ── Nota F8 ──────────────────────────────────────────────────────────
    with st.expander("🗓️ Plan F8 — Portfolio Multi-Sleeve"):
        st.markdown("""
        **Activación en F8:**
        1. ≥ 2 sleeves con 3+ meses de forward testing cada uno
        2. Correlación verificada con datos reales (no simulados)
        3. HRP via `PyPortfolioOpt` con equity curves reales
        4. Rebalanceo mensual con tracking de drift

        **Restricciones de diseño (ADR):**
        - Correlación máxima entre sleeves: 0.60
        - RI mínimo para inclusión: 0.85
        - Peso mínimo: 5% / Peso máximo: 60%
        - Excluir GBPUSD y USDCAD (2 regímenes detectados)

        **Ecosistema Python preparado:**
        - `python/portfolio/sleeve_allocator.py` ← HRP listo
        - `python/portfolio/sleeve_scorer.py` ← KPIs listos
        - `infra/supabase/migrations/003_research_runs.sql` ← tabla sleeve_kpis lista
        """)


# ── Charts ─────────────────────────────────────────────────────────────────

def _chart_correlation(corr: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Heatmap(
        z=corr.values,
        x=corr.columns.tolist(),
        y=corr.index.tolist(),
        colorscale="RdYlGn",
        zmin=-1, zmax=1,
        text=np.round(corr.values, 2),
        texttemplate="%{text}",
        showscale=True,
    ))
    fig.update_layout(
        **_dark_layout(),
        height=300,
        margin=dict(t=20, b=20, l=20, r=20),
    )
    return fig


def _chart_weights(weights: pd.Series) -> go.Figure:
    colors = ["#3fb950", "#58a6ff", "#d29922", "#f85149", "#bc8cff"]
    fig = go.Figure(go.Pie(
        labels=weights.index.tolist(),
        values=weights.values.tolist(),
        marker_colors=colors[:len(weights)],
        hole=0.4,
        textinfo="label+percent",
    ))
    fig.update_layout(
        **_dark_layout(),
        height=300,
        showlegend=False,
        margin=dict(t=20, b=20, l=20, r=20),
    )
    return fig


def _chart_equity_curves(equity_dict: dict, weights: pd.Series) -> go.Figure:
    portfolio_returns = None
    colors = ["#58a6ff", "#d29922", "#bc8cff"]

    fig = go.Figure()

    for i, (name, eq) in enumerate(equity_dict.items()):
        fig.add_trace(go.Scatter(
            x=list(range(len(eq))), y=eq,
            name=name, line=dict(color=colors[i % len(colors)], width=1.5),
            opacity=0.6,
        ))

    # Portfolio combinado
    np.random.seed(42)
    n = len(list(equity_dict.values())[0])
    all_rets = {name: np.diff(np.log(eq)) for name, eq in equity_dict.items()}
    port_ret = sum(weights[name] * all_rets[name] for name in weights.index if name in all_rets)
    port_eq  = 10_000 * np.cumprod(1 + port_ret)
    port_eq  = np.insert(port_eq, 0, 10_000)

    fig.add_trace(go.Scatter(
        x=list(range(len(port_eq))), y=port_eq,
        name="Portfolio HRP",
        line=dict(color="#3fb950", width=3),
    ))

    fig.add_hline(y=10_000, line_dash="dot", line_color="#8b949e")
    fig.update_layout(
        **_dark_layout(),
        yaxis_title="Capital ($)",
        xaxis_title="Barra",
    )
    return fig


def _dark_layout() -> dict:
    return dict(
        plot_bgcolor="#0d1117",
        paper_bgcolor="#0d1117",
        font=dict(color="#c9d1d9", family="Inter"),
        legend=dict(bgcolor="#161b22", bordercolor="#30363d"),
        margin=dict(t=40, b=40, l=50, r=30),
    )
