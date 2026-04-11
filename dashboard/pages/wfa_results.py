"""
dashboard/pages/wfa_results.py
────────────────────────────────
Página WFA Results: equity curves, tabla de ventanas, métricas detalladas.
"""

import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


def render():
    st.title("📈 Walk-Forward Analysis")
    st.markdown("---")

    results_store = _get_store()

    # ── Selector de run ───────────────────────────────────────────────────
    try:
        runs_df = results_store.list_runs()
    except Exception:
        runs_df = pd.DataFrame()

    if runs_df.empty:
        st.warning("No hay runs en DuckDB. Ejecutar el pipeline primero.")
        results_store.close()
        return

    col1, col2 = st.columns([3, 1])
    with col1:
        run_options = runs_df["run_id"].tolist()
        run_labels  = [
            f"{row['ea_version']} / {row['symbol']} — {row['created_at']}"
            for _, row in runs_df.iterrows()
        ]
        selected_idx = st.selectbox(
            "Seleccionar Run",
            options=range(len(run_options)),
            format_func=lambda i: run_labels[i],
        )
        selected_run_id = run_options[selected_idx]

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Refrescar", use_container_width=True):
            st.rerun()

    # ── Cargar run ────────────────────────────────────────────────────────
    try:
        run     = results_store.load_run(selected_run_id)
        windows = results_store.load_wfa_windows(selected_run_id)
    except Exception as e:
        st.error(f"Error cargando run: {e}")
        results_store.close()
        return

    metrics = run["metrics"]

    # ── Métricas agregadas ────────────────────────────────────────────────
    st.markdown("### Resumen Agregado")
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    avg_is_pf  = metrics.get("avg_is_pf", 0)
    avg_oos_pf = metrics.get("avg_oos_pf", 0)
    ri         = metrics.get("avg_robustness_index", 0)
    max_dd     = metrics.get("max_oos_dd", 0)
    trades_is  = metrics.get("total_is_trades", 0)
    sharpe     = metrics.get("avg_oos_sharpe", 0)

    passed_f3 = (avg_is_pf >= 1.20 and avg_oos_pf >= 1.10 and
                 ri >= 0.90 and max_dd <= 10.0 and trades_is >= 80)

    c1.metric("PF IS avg",   f"{avg_is_pf:.2f}",  delta="≥1.20" if avg_is_pf >= 1.20 else "<1.20")
    c2.metric("PF OOS avg",  f"{avg_oos_pf:.2f}", delta="≥1.10" if avg_oos_pf >= 1.10 else "<1.10")
    c3.metric("Rob. Index",  f"{ri:.2f}",          delta="≥0.90" if ri >= 0.90 else "<0.90")
    c4.metric("Max DD OOS",  f"{max_dd:.1f}%",     delta="≤10%" if max_dd <= 10 else ">10%", delta_color="inverse")
    c5.metric("Trades IS",   str(trades_is),        delta="≥80" if trades_is >= 80 else "<80")
    c6.metric("Sharpe OOS",  f"{sharpe:.2f}")

    status_color = "#3fb950" if passed_f3 else "#f85149"
    status_text  = "✅ CRITERIOS F3 CUMPLIDOS" if passed_f3 else "❌ CRITERIOS F3 NO CUMPLIDOS"
    st.markdown(
        f'<div style="background:#161b22; border:2px solid {status_color}; '
        f'border-radius:8px; padding:12px; text-align:center; '
        f'font-weight:700; color:{status_color}; font-size:16px;">'
        f'{status_text}</div>',
        unsafe_allow_html=True
    )

    st.markdown("---")

    # ── Tabla de ventanas ─────────────────────────────────────────────────
    st.markdown("### Detalle por Ventana IS/OOS")

    if windows:
        rows = []
        for w in windows:
            is_m  = w.get("is_metrics", {})
            oos_m = w.get("oos_metrics", {})
            ri_w  = (oos_m.get("profit_factor", 0) / is_m.get("profit_factor", 1)
                     if is_m.get("profit_factor", 0) > 0 else 0)
            rows.append({
                "Ventana":      f"{w.get('window_idx',0)+1}",
                "IS Período":   f"{_fmt_date(w.get('is_from'))} → {_fmt_date(w.get('is_to'))}",
                "OOS Período":  f"{_fmt_date(w.get('oos_from'))} → {_fmt_date(w.get('oos_to'))}",
                "IS PF":        round(is_m.get("profit_factor", 0), 2),
                "IS Trades":    is_m.get("n_trades", 0),
                "OOS PF":       round(oos_m.get("profit_factor", 0), 2),
                "OOS WR%":      round(oos_m.get("win_rate", 0) * 100, 1),
                "OOS DD%":      round(oos_m.get("max_dd_pct", 0), 1),
                "OOS Sharpe":   round(oos_m.get("sharpe", 0), 2),
                "RI":           round(ri_w, 2),
            })

        df_windows = pd.DataFrame(rows)

        # Colorear RI
        def highlight_ri(val):
            if isinstance(val, float):
                if val >= 0.90: return "background-color: #1a4731; color: #3fb950"
                if val >= 0.70: return "background-color: #3d2f00; color: #d29922"
                return "background-color: #3d0c0c; color: #f85149"
            return ""

        styled = df_windows.style.applymap(
            highlight_ri, subset=["RI"]
        ).format({
            "IS PF": "{:.2f}", "OOS PF": "{:.2f}",
            "OOS WR%": "{:.1f}%", "OOS DD%": "{:.1f}%",
            "OOS Sharpe": "{:.2f}", "RI": "{:.2f}",
        })
        st.dataframe(styled, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── Charts ────────────────────────────────────────────────────────────
    st.markdown("### Visualizaciones")
    tab1, tab2, tab3 = st.tabs(["PF por Ventana", "IS vs OOS PF", "Robustness Index"])

    with tab1:
        if windows:
            fig = _chart_pf_by_window(windows)
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        if windows:
            fig = _chart_is_vs_oos(windows)
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        if windows:
            fig = _chart_robustness(windows)
            st.plotly_chart(fig, use_container_width=True)

    results_store.close()


# ── Chart helpers ─────────────────────────────────────────────────────────

def _chart_pf_by_window(windows: list) -> go.Figure:
    labels  = [f"W{w['window_idx']+1}" for w in windows]
    is_pfs  = [w.get("is_metrics", {}).get("profit_factor", 0) for w in windows]
    oos_pfs = [w.get("oos_metrics", {}).get("profit_factor", 0) for w in windows]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="IS PF", x=labels, y=is_pfs,
        marker_color="#58a6ff", opacity=0.7,
    ))
    fig.add_trace(go.Bar(
        name="OOS PF", x=labels, y=oos_pfs,
        marker_color="#3fb950",
    ))
    fig.add_hline(y=1.0, line_dash="dot", line_color="#f85149", annotation_text="PF=1.0")
    fig.add_hline(y=1.20, line_dash="dash", line_color="#d29922", annotation_text="Target IS")
    fig.add_hline(y=1.10, line_dash="dash", line_color="#3fb950", annotation_text="Target OOS")

    fig.update_layout(
        **_dark_layout(),
        title="Profit Factor por Ventana WFA",
        barmode="group",
        yaxis_title="Profit Factor",
        xaxis_title="Ventana",
    )
    return fig


def _chart_is_vs_oos(windows: list) -> go.Figure:
    is_pfs  = [w.get("is_metrics", {}).get("profit_factor", 0) for w in windows]
    oos_pfs = [w.get("oos_metrics", {}).get("profit_factor", 0) for w in windows]
    labels  = [f"W{w['window_idx']+1}" for w in windows]

    # Color por RI
    ris    = [o/i if i > 0 else 0 for i, o in zip(is_pfs, oos_pfs)]
    colors = ["#3fb950" if r >= 0.90 else "#d29922" if r >= 0.70 else "#f85149" for r in ris]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=is_pfs, y=oos_pfs,
        mode="markers+text",
        text=labels,
        textposition="top center",
        marker=dict(size=14, color=colors, line=dict(color="#e6edf3", width=1)),
        name="Ventanas",
    ))

    # Línea diagonal RI=1.0
    max_val = max(max(is_pfs), max(oos_pfs)) * 1.1
    fig.add_trace(go.Scatter(
        x=[0, max_val], y=[0, max_val],
        mode="lines", name="RI=1.0",
        line=dict(dash="dot", color="#58a6ff", width=1),
    ))

    fig.add_hline(y=1.10, line_dash="dash", line_color="#3fb950",
                  annotation_text="Target OOS")
    fig.add_vline(x=1.20, line_dash="dash", line_color="#d29922",
                  annotation_text="Target IS")

    fig.update_layout(
        **_dark_layout(),
        title="IS PF vs OOS PF (color = RI)",
        xaxis_title="IS Profit Factor",
        yaxis_title="OOS Profit Factor",
    )
    return fig


def _chart_robustness(windows: list) -> go.Figure:
    labels = [f"W{w['window_idx']+1}" for w in windows]
    ris    = []
    for w in windows:
        is_pf  = w.get("is_metrics", {}).get("profit_factor", 0)
        oos_pf = w.get("oos_metrics", {}).get("profit_factor", 0)
        ris.append(oos_pf / is_pf if is_pf > 0 else 0)

    colors = ["#3fb950" if r >= 0.90 else "#d29922" if r >= 0.70 else "#f85149" for r in ris]

    fig = go.Figure(go.Bar(
        x=labels, y=ris, marker_color=colors, name="RI",
    ))
    fig.add_hline(y=0.90, line_dash="dash", line_color="#3fb950",
                  annotation_text="RI mínimo F3 = 0.90")
    fig.add_hline(y=1.0, line_dash="dot", line_color="#58a6ff",
                  annotation_text="RI=1.0 (OOS=IS)")

    fig.update_layout(
        **_dark_layout(),
        title="Robustness Index por Ventana (OOS PF / IS PF)",
        yaxis_title="Robustness Index",
        xaxis_title="Ventana",
    )
    return fig


# ── Utils ──────────────────────────────────────────────────────────────────

def _dark_layout() -> dict:
    return dict(
        plot_bgcolor="#0d1117",
        paper_bgcolor="#0d1117",
        font=dict(color="#c9d1d9", family="Inter"),
        legend=dict(bgcolor="#161b22", bordercolor="#30363d"),
        margin=dict(t=50, b=40, l=50, r=30),
    )


def _fmt_date(ts) -> str:
    if ts is None:
        return "N/A"
    try:
        return str(ts)[:7]  # YYYY-MM
    except Exception:
        return str(ts)


def _get_store():
    from python.data.store import ResultsStore
    return ResultsStore()
