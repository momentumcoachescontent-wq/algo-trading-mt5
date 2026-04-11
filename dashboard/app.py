"""
dashboard/app.py
─────────────────
Entry point del dashboard Streamlit.
Ejecutar: streamlit run dashboard/app.py

Páginas:
    1. Overview       — Estado del proyecto, runs recientes
    2. WFA Results    — Equity curves, métricas por ventana
    3. Monte Carlo    — Distribución de outcomes
    4. Sleeve Compare — Tabla comparativa de versiones
    5. Portfolio      — HRP allocation (F8)
"""

import sys
from pathlib import Path

# Asegurar que el root esté en el path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

# ── Config de página ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="algo-trading Research",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS global ────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Tipografía */
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    code, pre, .stCode {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Sidebar */
    .css-1d391kg { background-color: #0d1117; }

    /* Métricas */
    [data-testid="metric-container"] {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 12px 16px;
    }
    [data-testid="metric-container"] label {
        color: #8b949e !important;
        font-size: 12px !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* Headers */
    h1 { color: #e6edf3; font-weight: 700; }
    h2 { color: #c9d1d9; font-weight: 600; }
    h3 { color: #8b949e; font-weight: 600; font-size: 14px; text-transform: uppercase; letter-spacing: 0.08em; }

    /* Status badges */
    .badge-green  { background:#1a4731; color:#3fb950; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }
    .badge-yellow { background:#3d2f00; color:#d29922; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }
    .badge-red    { background:#3d0c0c; color:#f85149; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }
    .badge-blue   { background:#0d2340; color:#58a6ff; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }
</style>
""", unsafe_allow_html=True)

# ── Imports internos ──────────────────────────────────────────────────────
from python.data.store import MarketDataStore, ResultsStore

# ── Sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📊 Research Platform")
    st.markdown("---")

    page = st.radio(
        "Navegación",
        options=[
            "🏠 Overview",
            "📈 WFA Results",
            "🎲 Monte Carlo",
            "⚖️ Sleeve Compare",
            "🗂️ Portfolio",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown("**Fase actual:** F3 → F4")
    st.markdown("**EA activo:** v2.3 (en test)")
    st.markdown("**Candidato F4:** v1.9 ✅")

# ── Routing ───────────────────────────────────────────────────────────────
if page == "🏠 Overview":
    from dashboard.pages import overview
    overview.render()

elif page == "📈 WFA Results":
    from dashboard.pages import wfa_results
    wfa_results.render()

elif page == "🎲 Monte Carlo":
    from dashboard.pages import monte_carlo_page
    monte_carlo_page.render()

elif page == "⚖️ Sleeve Compare":
    from dashboard.pages import sleeve_compare
    sleeve_compare.render()

elif page == "🗂️ Portfolio":
    from dashboard.pages import portfolio_page
    portfolio_page.render()
