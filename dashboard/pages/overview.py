"""
dashboard/pages/overview.py
────────────────────────────
Página Overview: estado del proyecto, runs recientes, métricas clave.
"""

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime


def render():
    st.title("📊 algo-trading Research Platform")
    st.markdown(
        '<span class="badge-blue">F3 → F4</span> &nbsp; '
        '<span class="badge-green">v1.9 VALIDADO</span> &nbsp; '
        '<span class="badge-yellow">v2.3 EN TEST</span>',
        unsafe_allow_html=True
    )
    st.markdown("---")

    # ── Roadmap cards ─────────────────────────────────────────────────────
    st.markdown("### Roadmap")
    cols = st.columns(8)
    phases = [
        ("F0", "Foundation",    "✅"),
        ("F1", "Sandbox",       "✅"),
        ("F2", "Alpha",         "✅"),
        ("F3", "WFA",           "🔄"),
        ("F4", "Forward",       "⏳"),
        ("F5", "Hardening",     "⏳"),
        ("F6", "Live",          "⏳"),
        ("F7", "Optimize",      "⏳"),
    ]
    for col, (phase, label, status) in zip(cols, phases):
        bg = "#1a4731" if status == "✅" else "#3d2f00" if status == "🔄" else "#161b22"
        border = "#3fb950" if status == "✅" else "#d29922" if status == "🔄" else "#30363d"
        col.markdown(
            f"""<div style="background:{bg}; border:1px solid {border};
                border-radius:8px; padding:10px; text-align:center;">
                <div style="font-size:18px">{status}</div>
                <div style="font-weight:700; color:#e6edf3">{phase}</div>
                <div style="font-size:11px; color:#8b949e">{label}</div>
            </div>""",
            unsafe_allow_html=True
        )

    st.markdown("---")

    # ── Versiones validadas ───────────────────────────────────────────────
    st.markdown("### EA Versions")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        <div style="background:#161b22; border:1px solid #3fb950; border-radius:8px; padding:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:700; font-size:16px; color:#e6edf3">v1.9</span>
                <span class="badge-green">VALIDADO F3</span>
            </div>
            <div style="color:#8b949e; font-size:12px; margin-top:4px;">USDJPY H4 · ATR 1.5× · RR=2.0 · Body 40%</div>
            <hr style="border-color:#30363d; margin:10px 0">
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:13px;">
                <div><span style="color:#8b949e">IS PF:</span> <span style="color:#e6edf3">0.97</span></div>
                <div><span style="color:#8b949e">OOS PF:</span> <span style="color:#3fb950; font-weight:700">1.21</span></div>
                <div><span style="color:#8b949e">RI:</span> <span style="color:#3fb950; font-weight:700">1.25</span></div>
                <div><span style="color:#8b949e">OOS DD:</span> <span style="color:#e6edf3">8.67%</span></div>
                <div><span style="color:#8b949e">OOS Sharpe:</span> <span style="color:#e6edf3">0.92</span></div>
                <div><span style="color:#8b949e">Net OOS:</span> <span style="color:#3fb950">+$903</span></div>
            </div>
            <div style="margin-top:10px; padding:8px; background:#0d2340; border-radius:4px; font-size:12px; color:#58a6ff;">
                🎯 Candidato principal F4 Forward Testing
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div style="background:#161b22; border:1px solid #d29922; border-radius:8px; padding:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:700; font-size:16px; color:#e6edf3">v2.3</span>
                <span class="badge-yellow">EN TEST</span>
            </div>
            <div style="color:#8b949e; font-size:12px; margin-top:4px;">USDJPY H4 · ATR 1.5× · RR=2.5 · Body 40%</div>
            <hr style="border-color:#30363d; margin:10px 0">
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:13px;">
                <div><span style="color:#8b949e">Prior PF:</span> <span style="color:#e6edf3">1.17 (v2.2)</span></div>
                <div><span style="color:#8b949e">Target PF:</span> <span style="color:#e6edf3">1.23</span></div>
                <div><span style="color:#8b949e">WR:</span> <span style="color:#e6edf3">33% (techo)</span></div>
                <div><span style="color:#8b949e">W/L:</span> <span style="color:#e6edf3">1.9× típico</span></div>
            </div>
            <div style="margin-top:10px; padding:8px; background:#3d2f00; border-radius:4px; font-size:12px; color:#d29922;">
                🔬 Hipótesis: WR=33% + RR=2.5 → PF=1.23
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Runs recientes ────────────────────────────────────────────────────
    st.markdown("### Runs Recientes")

    try:
        results_store = _get_results_store()
        runs_df = results_store.list_runs()
        results_store.close()

        if runs_df.empty:
            st.info("No hay runs en DuckDB. Ejecutar el pipeline primero.")
            _show_quickstart()
        else:
            # Colorear passed_f3
            def style_row(row):
                return ['background-color: #1a4731' if row.get('passed_f3') else '' for _ in row]

            st.dataframe(
                runs_df,
                use_container_width=True,
                hide_index=True,
            )
    except Exception as e:
        st.info("Base de datos local no inicializada.")
        _show_quickstart()

    # ── Lecciones clave ───────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Lecciones Clave Documentadas")

    lessons = [
        ("L-06", "WR techo estructural ~33% en family pullback EMA21+body"),
        ("L-10", "ATR SL 1.5× óptimo para USDJPY H4 — 2.0× colapsa WR"),
        ("L-14", "Trailing stop destruye avg_win — TP fijo es prioridad"),
        ("L-16", "body=0.40 óptimo — NO iterar threshold"),
        ("P-10", "ADX ≥ 25 requerido para DMI signal validation"),
        ("P-04", "Martingala hard-coded OFF — ruina matemática garantizada"),
    ]

    cols = st.columns(3)
    for i, (code, lesson) in enumerate(lessons):
        cols[i % 3].markdown(
            f"""<div style="background:#161b22; border:1px solid #30363d;
                border-radius:6px; padding:10px; margin-bottom:8px;">
                <span style="font-family:monospace; color:#58a6ff; font-size:11px">{code}</span>
                <div style="color:#c9d1d9; font-size:13px; margin-top:4px">{lesson}</div>
            </div>""",
            unsafe_allow_html=True
        )


def _show_quickstart():
    st.markdown("""
    ```bash
    # 1. Extraer datos (MT5 abierto)
    python -m python.pipeline.run_backtest extract \\
      --symbol USDJPY --timeframe H4 --from 2020-01-01

    # O con datos sintéticos (sin MT5)
    python -m python.pipeline.run_backtest extract \\
      --symbol USDJPY --timeframe H4 --synthetic

    # 2. Correr WFA
    python -m python.pipeline.run_backtest wfa \\
      --config configs/v2_3.yaml --symbol USDJPY

    # 3. Monte Carlo
    python -m python.pipeline.run_backtest monte-carlo \\
      --run-id <run_id> --n 1000
    ```
    """)


def _get_results_store():
    from python.data.store import ResultsStore
    return ResultsStore()
