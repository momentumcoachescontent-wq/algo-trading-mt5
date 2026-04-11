"""
dashboard/pages/monte_carlo_page.py
─────────────────────────────────────
Página Monte Carlo: distribuciones de PF y DD, percentiles, probabilidades.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def render():
    st.title("🎲 Monte Carlo Analysis")
    st.markdown("""
    Permutación aleatoria del orden de trades OOS.
    Responde: *"Si el orden de mis trades hubiese sido diferente, ¿cuál sería el rango de resultados?"*
    """)
    st.markdown("---")

    # ── Panel de configuración ────────────────────────────────────────────
    with st.expander("⚙️ Configurar y Ejecutar Monte Carlo", expanded=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            n_sims = st.slider("N° Simulaciones", 100, 5000, 1000, 100)
            seed   = st.number_input("Seed", value=42, min_value=0)

        with col2:
            # Inputs de trades manuales (hasta que el pipeline persista trades individuales)
            st.markdown("**Trades OOS (estadísticas)**")
            n_trades = st.number_input("N° Trades", value=74, min_value=10)
            wr       = st.slider("Win Rate %", 20.0, 60.0, 33.0, 0.5) / 100

        with col3:
            avg_win  = st.number_input("Avg Win ($)", value=125.0, min_value=1.0)
            avg_loss = st.number_input("Avg Loss ($)", value=62.5, min_value=1.0)
            capital  = st.number_input("Capital ($)", value=10000, min_value=1000)

        run_mc = st.button("▶ Correr Monte Carlo", type="primary", use_container_width=True)

    if run_mc or st.session_state.get("mc_results"):
        if run_mc:
            # Generar trades sintéticos desde estadísticas
            rng = np.random.default_rng(seed)
            n_wins   = int(n_trades * wr)
            n_losses = n_trades - n_wins
            wins     = rng.normal(avg_win,  avg_win * 0.3,  n_wins).clip(min=0.01)
            losses   = rng.normal(avg_loss, avg_loss * 0.3, n_losses).clip(min=0.01)
            pnls     = np.concatenate([wins, -losses])

            # Correr MC
            with st.spinner(f"Corriendo {n_sims:,} permutaciones..."):
                mc_results = _run_mc_simulation(pnls, n_sims, capital, seed)
                st.session_state["mc_results"] = mc_results
                st.session_state["mc_pnls"]    = pnls

        mc_results = st.session_state["mc_results"]
        pnls       = st.session_state.get("mc_pnls", np.array([]))

        # ── Métricas clave ─────────────────────────────────────────────
        st.markdown("### Distribución de Resultados")

        base_pf = mc_results["base_pf"]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Base PF",  f"{base_pf:.2f}")
        c2.metric("P5 (peor 5%)", f"{mc_results['pf_p5']:.2f}",
                  delta=f"{mc_results['pf_p5']-base_pf:+.2f}")
        c3.metric("P50 Mediana", f"{mc_results['pf_p50']:.2f}")
        c4.metric("P95 (mejor 5%)", f"{mc_results['pf_p95']:.2f}",
                  delta=f"{mc_results['pf_p95']-base_pf:+.2f}")
        c5.metric("Prob PF > 1.0", f"{mc_results['prob_gt_1']*100:.1f}%")

        # Coherencia
        coherence = abs(mc_results["pf_p50"] - base_pf) / base_pf
        if coherence < 0.10:
            st.success(f"✅ Sistema coherente: mediana ({mc_results['pf_p50']:.2f}) ≈ base ({base_pf:.2f})")
        else:
            st.warning(f"⚠️ Divergencia {coherence*100:.0f}%: mediana vs base — varianza alta, pocos trades")

        # ── Charts ─────────────────────────────────────────────────────
        tab1, tab2 = st.tabs(["Distribución PF", "Distribución Max DD"])

        with tab1:
            fig = _chart_pf_distribution(mc_results, base_pf)
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            fig = _chart_dd_distribution(mc_results)
            st.plotly_chart(fig, use_container_width=True)

        # ── Tabla de percentiles ───────────────────────────────────────
        st.markdown("### Tabla de Percentiles")
        percentile_data = {
            "Percentil": ["P5 (peor 5%)", "P10", "P25", "P50 (mediana)",
                          "P75", "P90", "P95 (mejor 5%)"],
            "PF":  [
                f"{np.percentile(mc_results['pf_dist'], p):.3f}"
                for p in [5, 10, 25, 50, 75, 90, 95]
            ],
            "Max DD%": [
                f"{np.percentile(mc_results['dd_dist'], p):.1f}%"
                for p in [5, 10, 25, 50, 75, 90, 95]
            ],
        }
        st.dataframe(
            pd.DataFrame(percentile_data),
            use_container_width=True,
            hide_index=True,
        )

        # ── Probabilidades ─────────────────────────────────────────────
        st.markdown("### Probabilidades")
        col1, col2, col3 = st.columns(3)

        prob_gt1    = mc_results["prob_gt_1"]
        prob_gt1_2  = mc_results["prob_gt_1_2"]
        prob_ruin   = mc_results["prob_ruin"]

        with col1:
            color = "normal" if prob_gt1 >= 0.80 else "inverse"
            col1.metric("P(PF > 1.0)", f"{prob_gt1*100:.1f}%",
                        delta="✅ Robusto" if prob_gt1 >= 0.80 else "⚠️ Borderline",
                        delta_color=color)
        with col2:
            col2.metric("P(PF > 1.2)", f"{prob_gt1_2*100:.1f}%")
        with col3:
            ruin_color = "inverse" if prob_ruin > 0.05 else "normal"
            col3.metric("P(Ruina DD>20%)", f"{prob_ruin*100:.1f}%",
                        delta="✅ Seguro" if prob_ruin <= 0.05 else "⚠️ Riesgo",
                        delta_color=ruin_color)


# ── Simulación ─────────────────────────────────────────────────────────────

def _run_mc_simulation(
    pnls: np.ndarray,
    n_sims: int,
    capital: float,
    seed: int,
) -> dict:
    rng = np.random.default_rng(seed)

    pf_dist  = np.zeros(n_sims)
    dd_dist  = np.zeros(n_sims)
    pnl_dist = np.zeros(n_sims)

    for i in range(n_sims):
        perm = rng.permutation(pnls)
        pf_dist[i]  = _compute_pf(perm)
        dd_dist[i]  = _compute_max_dd(perm, capital)
        pnl_dist[i] = perm.sum()

    base_pf = _compute_pf(pnls)
    base_dd = _compute_max_dd(pnls, capital)

    return {
        "base_pf":     base_pf,
        "base_dd":     base_dd,
        "pf_dist":     pf_dist,
        "dd_dist":     dd_dist,
        "pnl_dist":    pnl_dist,
        "pf_p5":       float(np.percentile(pf_dist, 5)),
        "pf_p25":      float(np.percentile(pf_dist, 25)),
        "pf_p50":      float(np.percentile(pf_dist, 50)),
        "pf_p75":      float(np.percentile(pf_dist, 75)),
        "pf_p95":      float(np.percentile(pf_dist, 95)),
        "prob_gt_1":   float((pf_dist > 1.0).mean()),
        "prob_gt_1_2": float((pf_dist > 1.2).mean()),
        "prob_ruin":   float((dd_dist > 20.0).mean()),
    }


def _compute_pf(pnl: np.ndarray) -> float:
    gp = pnl[pnl > 0].sum()
    gl = abs(pnl[pnl < 0].sum())
    return float(gp / gl) if gl > 0 else (1.5 if gp > 0 else 0.0)


def _compute_max_dd(pnl: np.ndarray, capital: float) -> float:
    eq  = capital + np.cumsum(pnl)
    eq  = np.insert(eq, 0, capital)
    rmax = np.maximum.accumulate(eq)
    dd   = (eq - rmax) / rmax * 100
    return float(abs(dd.min()))


# ── Charts ─────────────────────────────────────────────────────────────────

def _chart_pf_distribution(mc: dict, base_pf: float) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=mc["pf_dist"],
        nbinsx=50,
        name="PF simulado",
        marker_color="#58a6ff",
        opacity=0.7,
    ))

    for pct, val, color, label in [
        (5,  mc["pf_p5"],  "#f85149", "P5"),
        (50, mc["pf_p50"], "#d29922", "P50"),
        (95, mc["pf_p95"], "#3fb950", "P95"),
    ]:
        fig.add_vline(x=val, line_color=color, line_dash="dash",
                      annotation_text=f"{label}={val:.2f}", annotation_font_color=color)

    fig.add_vline(x=base_pf, line_color="#e6edf3", line_width=2,
                  annotation_text=f"Base={base_pf:.2f}", annotation_font_color="#e6edf3")
    fig.add_vline(x=1.0, line_color="#f85149", line_dash="dot",
                  annotation_text="PF=1.0")

    fig.update_layout(
        **_dark_layout(),
        title="Distribución de Profit Factor — Monte Carlo",
        xaxis_title="Profit Factor",
        yaxis_title="Frecuencia",
    )
    return fig


def _chart_dd_distribution(mc: dict) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=mc["dd_dist"],
        nbinsx=40,
        name="Max DD% simulado",
        marker_color="#f85149",
        opacity=0.7,
    ))

    dd_p50 = float(np.percentile(mc["dd_dist"], 50))
    dd_p95 = float(np.percentile(mc["dd_dist"], 95))

    fig.add_vline(x=dd_p50, line_color="#d29922", line_dash="dash",
                  annotation_text=f"P50={dd_p50:.1f}%")
    fig.add_vline(x=dd_p95, line_color="#f85149", line_dash="dash",
                  annotation_text=f"P95={dd_p95:.1f}%")
    fig.add_vline(x=10.0, line_color="#3fb950", line_dash="dot",
                  annotation_text="Límite F3=10%")
    fig.add_vline(x=20.0, line_color="#f85149", line_dash="solid",
                  annotation_text="Umbral ruina=20%")

    fig.update_layout(
        **_dark_layout(),
        title="Distribución de Max Drawdown% — Monte Carlo",
        xaxis_title="Max Drawdown %",
        yaxis_title="Frecuencia",
    )
    return fig


def _dark_layout() -> dict:
    return dict(
        plot_bgcolor="#0d1117",
        paper_bgcolor="#0d1117",
        font=dict(color="#c9d1d9", family="Inter"),
        legend=dict(bgcolor="#161b22", bordercolor="#30363d"),
        margin=dict(t=50, b=40, l=50, r=30),
    )
