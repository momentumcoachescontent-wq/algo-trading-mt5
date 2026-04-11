"""
dashboard/pages/sleeve_compare.py
───────────────────────────────────
Página Sleeve Comparison: tabla de KPIs, scatter Sharpe vs DD,
radar chart de métricas normalizadas.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px


# ── Datos hardcoded para los sleeves ya validados ─────────────────────────
# Estos se reemplazarán con datos de DuckDB cuando haya runs suficientes.

KNOWN_SLEEVES = {
    "v1.9 / USDJPY H4": {
        "ea_version": "v1.9", "symbol": "USDJPY", "timeframe": "H4",
        "n_trades": 74, "profit_factor": 1.21, "win_rate": 0.35,
        "avg_win": 125.0, "avg_loss": 62.5, "wl_ratio": 2.0,
        "sharpe": 0.92, "sortino": 1.15, "calmar": 0.45,
        "ulcer_index": 3.2, "max_dd_pct": 8.67,
        "robustness_index": 1.25, "is_pf": 0.97, "oos_pf": 1.21,
        "status": "VALIDADO_F3",
    },
    "v1.6 / EURUSD H4": {
        "ea_version": "v1.6", "symbol": "EURUSD", "timeframe": "H4",
        "n_trades": 0, "profit_factor": 1.04, "win_rate": 0.33,
        "avg_win": 100.0, "avg_loss": 55.0, "wl_ratio": 1.82,
        "sharpe": 0.41, "sortino": 0.58, "calmar": 0.22,
        "ulcer_index": 5.1, "max_dd_pct": 9.2,
        "robustness_index": 0.87, "is_pf": 1.20, "oos_pf": 1.04,
        "status": "VALIDADO_F3",
    },
    "v2.2 / USDJPY H4": {
        "ea_version": "v2.2", "symbol": "USDJPY", "timeframe": "H4",
        "n_trades": 0, "profit_factor": 1.17, "win_rate": 0.33,
        "avg_win": 108.0, "avg_loss": 62.5, "wl_ratio": 1.73,
        "sharpe": 0.78, "sortino": 0.95, "calmar": 0.38,
        "ulcer_index": 4.0, "max_dd_pct": 9.1,
        "robustness_index": 0.93, "is_pf": 1.26, "oos_pf": 1.17,
        "status": "REFERENCIA",
    },
}


def render():
    st.title("⚖️ Sleeve Comparison")
    st.markdown("Comparación de KPIs institucionales entre versiones del EA.")
    st.markdown("---")

    # ── Selector de sleeves ───────────────────────────────────────────────
    all_sleeves = list(KNOWN_SLEEVES.keys())
    selected = st.multiselect(
        "Seleccionar sleeves para comparar",
        options=all_sleeves,
        default=all_sleeves,
    )

    if not selected:
        st.info("Selecciona al menos un sleeve.")
        return

    sleeves_data = {k: KNOWN_SLEEVES[k] for k in selected}

    # ── Tabla KPIs ────────────────────────────────────────────────────────
    st.markdown("### KPIs Institucionales")

    rows = []
    for name, s in sleeves_data.items():
        score = _compute_score(s)
        rows.append({
            "Sleeve":   name,
            "PF OOS":   s["profit_factor"],
            "WR%":      round(s["win_rate"] * 100, 1),
            "W/L":      s["wl_ratio"],
            "Sharpe":   s["sharpe"],
            "Sortino":  s["sortino"],
            "Calmar":   s["calmar"],
            "Ulcer":    s["ulcer_index"],
            "Max DD%":  s["max_dd_pct"],
            "RI":       s["robustness_index"],
            "Score":    round(score, 3),
            "Status":   s["status"],
        })

    df = pd.DataFrame(rows).sort_values("Score", ascending=False)

    def color_ri(val):
        if val >= 0.90: return "background-color:#1a4731; color:#3fb950"
        if val >= 0.70: return "background-color:#3d2f00; color:#d29922"
        return "background-color:#3d0c0c; color:#f85149"

    def color_score(val):
        if val >= 0.6: return "background-color:#1a4731; color:#3fb950; font-weight:700"
        if val >= 0.4: return "background-color:#3d2f00; color:#d29922"
        return "background-color:#3d0c0c; color:#f85149"

    styled = (
        df.style
        .applymap(color_ri, subset=["RI"])
        .applymap(color_score, subset=["Score"])
        .format({
            "PF OOS": "{:.2f}", "WR%": "{:.1f}%", "W/L": "{:.2f}",
            "Sharpe": "{:.2f}", "Sortino": "{:.2f}", "Calmar": "{:.2f}",
            "Ulcer": "{:.2f}", "Max DD%": "{:.1f}%",
            "RI": "{:.2f}", "Score": "{:.3f}",
        })
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── Charts ────────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Sharpe vs Max Drawdown")
        fig = _chart_sharpe_vs_dd(sleeves_data)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("### Radar — Métricas Normalizadas")
        fig = _chart_radar(sleeves_data)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ── Bar chart PF IS vs OOS ────────────────────────────────────────────
    st.markdown("### IS PF vs OOS PF (Robustness)")
    fig = _chart_is_oos_bars(sleeves_data)
    st.plotly_chart(fig, use_container_width=True)

    # ── Nota metodológica ─────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("📐 Metodología del Score Compuesto"):
        st.markdown("""
        El **Composite Score** es una ponderación cualitativa calibrada para
        estrategias pullback H4. **No optimizar los pesos** — son juicios de
        diseño, no objetivos a maximizar.

        | Componente | Peso | Normalización |
        |---|---|---|
        | Profit Factor | 25% | PF/1.5 (1.5 = máx esperado) |
        | Robustness Index | 20% | RI/1.0 |
        | Max Drawdown | 20% | 1 - DD/20% |
        | Sortino Ratio | 15% | Sortino/2.0 |
        | Ulcer Index | 10% | 1 - Ulcer/10 |
        | Win Rate | 10% | WR/50% |

        **Fuente:** Pilar 9 del Blueprint Institucional — Métricas de Viabilidad.
        """)


# ── Helpers ────────────────────────────────────────────────────────────────

def _compute_score(s: dict) -> float:
    return (
        0.25 * min(s["profit_factor"] / 1.5, 1.0) +
        0.20 * min(s["robustness_index"] / 1.0, 1.0) +
        0.20 * max(0, 1 - s["max_dd_pct"] / 20.0) +
        0.15 * min(max(s["sortino"], 0) / 2.0, 1.0) +
        0.10 * max(0, 1 - s["ulcer_index"] / 10.0) +
        0.10 * min(s["win_rate"] / 0.50, 1.0)
    )


def _chart_sharpe_vs_dd(sleeves: dict) -> go.Figure:
    fig = go.Figure()

    colors = ["#3fb950", "#58a6ff", "#d29922", "#f85149", "#bc8cff"]
    for i, (name, s) in enumerate(sleeves.items()):
        score = _compute_score(s)
        fig.add_trace(go.Scatter(
            x=[s["max_dd_pct"]], y=[s["sharpe"]],
            mode="markers+text",
            name=name,
            text=[name.split("/")[0].strip()],
            textposition="top center",
            marker=dict(
                size=16 + score * 20,
                color=colors[i % len(colors)],
                line=dict(color="#e6edf3", width=1),
            ),
        ))

    fig.add_vline(x=10.0, line_dash="dash", line_color="#f85149",
                  annotation_text="DD límite F3")

    fig.update_layout(
        **_dark_layout(),
        xaxis_title="Max Drawdown %",
        yaxis_title="Sharpe Ratio",
        showlegend=False,
    )
    return fig


def _chart_radar(sleeves: dict) -> go.Figure:
    categories = ["PF OOS", "Sharpe", "Sortino", "RI", "1-DD%", "WR%"]
    colors = ["#3fb950", "#58a6ff", "#d29922"]
    fig = go.Figure()

    for i, (name, s) in enumerate(sleeves.items()):
        values = [
            min(s["profit_factor"] / 1.5, 1.0),
            min(max(s["sharpe"], 0) / 2.0, 1.0),
            min(max(s["sortino"], 0) / 2.0, 1.0),
            min(s["robustness_index"] / 1.5, 1.0),
            max(0, 1 - s["max_dd_pct"] / 20.0),
            min(s["win_rate"] / 0.50, 1.0),
        ]
        fig.add_trace(go.Scatterpolar(
            r=values + [values[0]],
            theta=categories + [categories[0]],
            fill="toself",
            name=name.split("/")[0].strip(),
            line_color=colors[i % len(colors)],
            opacity=0.7,
        ))

    fig.update_layout(
        **_dark_layout(),
        polar=dict(
            bgcolor="#161b22",
            radialaxis=dict(visible=True, range=[0, 1], color="#8b949e"),
            angularaxis=dict(color="#8b949e"),
        ),
        showlegend=True,
    )
    return fig


def _chart_is_oos_bars(sleeves: dict) -> go.Figure:
    names  = [s.split("/")[0].strip() for s in sleeves.keys()]
    is_pfs = [s["is_pf"] for s in sleeves.values()]
    oos_pfs = [s["oos_pf"] for s in sleeves.values()]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="IS PF",  x=names, y=is_pfs,  marker_color="#58a6ff", opacity=0.7))
    fig.add_trace(go.Bar(name="OOS PF", x=names, y=oos_pfs, marker_color="#3fb950"))

    fig.add_hline(y=1.0,  line_dash="dot",  line_color="#f85149", annotation_text="PF=1.0")
    fig.add_hline(y=1.20, line_dash="dash", line_color="#d29922", annotation_text="Target IS")
    fig.add_hline(y=1.10, line_dash="dash", line_color="#3fb950", annotation_text="Target OOS")

    fig.update_layout(
        **_dark_layout(),
        barmode="group",
        yaxis_title="Profit Factor",
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
