"""
python/pipeline/run_backtest.py
────────────────────────────────
CLI principal del pipeline de research.

Comandos:
    extract     — Extrae datos históricos de MT5
    verify      — Verifica datos en DuckDB
    wfa         — Corre Walk-Forward Analysis
    monte-carlo — Corre Monte Carlo sobre un run existente
    compare     — Compara múltiples sleeves
    portfolio   — Calcula asignación HRP multi-sleeve

Uso:
    python -m python.pipeline.run_backtest --help
    python -m python.pipeline.run_backtest wfa --config configs/v2_3.yaml --symbol USDJPY
"""

import os
import sys
import json
from pathlib import Path
from dataclasses import asdict

import click
import yaml
from rich.console import Console
from rich.panel import Panel

# Agregar root al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from python.data.store import MarketDataStore, ResultsStore
from python.research.signals import SignalConfig
from python.research.wfa_engine import WFAEngine
from python.research.monte_carlo import MonteCarlo, MCConfig

console = Console()

# ── Helpers ───────────────────────────────────────────────────────────────

def load_config(config_path: str) -> dict:
    """Carga configuración desde YAML."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config no encontrado: {config_path}")
    with open(path) as f:
        return yaml.safe_load(f)


def config_to_signal_config(cfg: dict) -> SignalConfig:
    """Convierte dict YAML a SignalConfig."""
    return SignalConfig(
        ema_period     = cfg.get("ema_period", 21),
        adx_period     = cfg.get("adx_period", 14),
        adx_min        = cfg.get("adx_min", 25.0),
        atr_period     = cfg.get("atr_period", 14),
        atr_sl_mult    = cfg.get("atr_sl_mult", 1.5),
        atr_tp_mult    = cfg.get("atr_tp_mult", 2.5),
        body_threshold = cfg.get("body_threshold", 0.40),
        lookback       = cfg.get("lookback", 50),
    )


def get_supabase_client():
    """Inicializa cliente Supabase (opcional)."""
    try:
        from python.infra.supabase_client import ResearchSupabaseClient
        return ResearchSupabaseClient()
    except Exception as e:
        console.print(f"[dim yellow]Supabase no disponible: {e}[/dim yellow]")
        return None


# ── CLI ───────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """
    \b
    ╔═══════════════════════════════════════╗
    ║  algo-trading Research Pipeline CLI  ║
    ╚═══════════════════════════════════════╝
    """
    pass


# ── EXTRACT ──────────────────────────────────────────────────────────────

@cli.command()
@click.option("--symbol",    required=True, help="Símbolo MT5 (ej: USDJPY)")
@click.option("--timeframe", default="H4", show_default=True)
@click.option("--from",      "date_from", default="2020-01-01", show_default=True)
@click.option("--to",        "date_to",   default=None)
@click.option("--synthetic", is_flag=True, help="Usar datos sintéticos (sin MT5)")
def extract(symbol, timeframe, date_from, date_to, synthetic):
    """Extrae datos OHLCV de MT5 y los guarda en DuckDB."""

    console.print(Panel(
        f"[bold]Extracción:[/bold] {symbol} {timeframe} desde {date_from}",
        border_style="blue"
    ))

    if synthetic:
        console.print("[yellow]Modo sintético — generando datos GBM[/yellow]")
        from python.data.extract_mt5 import generate_synthetic_ohlcv
        df = generate_synthetic_ohlcv(symbol=symbol, timeframe=timeframe)
    else:
        from python.data.extract_mt5 import MT5Extractor
        with MT5Extractor() as extractor:
            df = extractor.fetch_ohlcv(symbol, timeframe, date_from, date_to)

    with MarketDataStore() as store:
        store.upsert_ohlcv(df, symbol, timeframe)
        meta = store.get_metadata(symbol, timeframe)

    console.print(f"\n[green]✓ Extracción completa[/green]")
    console.print(f"  Barras: {meta.get('bar_count', 0):,}")
    console.print(f"  Desde:  {meta.get('date_from', 'N/A')}")
    console.print(f"  Hasta:  {meta.get('date_to', 'N/A')}")


# ── VERIFY ────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--symbol", required=True)
@click.option("--timeframe", default="H4")
def verify(symbol, timeframe):
    """Verifica datos disponibles en DuckDB."""
    with MarketDataStore() as store:
        available = store.list_available()
        if available.empty:
            console.print("[yellow]No hay datos en DuckDB. Ejecutar 'extract' primero.[/yellow]")
            return

        console.print("\n[bold]Datos disponibles:[/bold]")
        console.print(available.to_string(index=False))


# ── WFA ───────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--config",   required=True, help="Path al YAML de configuración")
@click.option("--symbol",   default=None,  help="Override símbolo del config")
@click.option("--save-to-supabase", is_flag=True, default=True, show_default=True)
@click.option("--no-supabase", is_flag=True, help="Desactivar persistencia Supabase")
def wfa(config, symbol, save_to_supabase, no_supabase):
    """Corre Walk-Forward Analysis completo."""

    cfg_dict  = load_config(config)
    ea_version = cfg_dict["ea_version"]
    sym        = symbol or cfg_dict["symbol"]
    timeframe  = cfg_dict.get("timeframe", "H4")
    wfa_cfg    = cfg_dict.get("wfa", {})
    acceptance = cfg_dict.get("acceptance", {})

    signal_config = config_to_signal_config(cfg_dict)

    console.print(Panel(
        f"[bold]WFA:[/bold] {ea_version} / {sym} {timeframe}",
        border_style="cyan"
    ))

    # Cargar datos
    with MarketDataStore() as store:
        df = store.load_ohlcv(sym, timeframe)

    # Generar run_id
    results_store = ResultsStore()
    run_id = ResultsStore.generate_run_id(
        ea_version, sym,
        {k: v for k, v in cfg_dict.items() if k not in ("wfa", "acceptance")}
    )
    console.print(f"Run ID: [dim]{run_id}[/dim]")

    # Correr WFA
    engine = WFAEngine()
    result = engine.run_wfa(
        df          = df,
        config      = signal_config,
        run_id      = run_id,
        ea_version  = ea_version,
        symbol      = sym,
        timeframe   = timeframe,
        is_months   = wfa_cfg.get("is_months", 36),
        oos_months  = wfa_cfg.get("oos_months", 6),
        step_months = wfa_cfg.get("step_months", 6),
    )

    # Evaluar criterios F3
    passed, checks = result.meets_f3_criteria(
        pf_is_min    = acceptance.get("pf_is_min", 1.20),
        pf_oos_min   = acceptance.get("pf_oos_min", 1.10),
        ri_min       = acceptance.get("robustness_index_min", 0.90),
        dd_max       = acceptance.get("max_dd_pct", 10.0),
        trades_is_min = acceptance.get("min_trades_is", 80),
    )

    # Guardar resultados localmente
    windows_data = []
    for w in result.windows:
        windows_data.append({
            "window_idx": w.window_idx,
            "is_from": str(w.is_from),
            "is_to":   str(w.is_to),
            "oos_from": str(w.oos_from),
            "oos_to":   str(w.oos_to),
            "is_metrics":  asdict(w.is_metrics),
            "oos_metrics": asdict(w.oos_metrics),
        })

    results_store.save_run(
        run_id=run_id,
        ea_version=ea_version,
        symbol=sym,
        timeframe=timeframe,
        params={k: v for k, v in cfg_dict.items() if k not in ("wfa", "acceptance")},
        metrics=result.to_dict(),
        run_type="wfa",
    )
    results_store.save_wfa_windows(run_id, windows_data)

    # Persistir en Supabase (si no desactivado)
    if save_to_supabase and not no_supabase:
        sb = get_supabase_client()
        if sb:
            sb.save_run(
                run_id=run_id,
                ea_version=ea_version,
                symbol=sym,
                timeframe=timeframe,
                params=cfg_dict,
                metrics=result.to_dict(),
                passed_f3=passed,
            )
            sb.save_wfa_windows(run_id, windows_data)

    results_store.close()

    return run_id


# ── MONTE CARLO ───────────────────────────────────────────────────────────

@cli.command("monte-carlo")
@click.option("--run-id",   required=True, help="Run ID del WFA base")
@click.option("--n",        default=1000,  show_default=True, help="Número de simulaciones")
@click.option("--seed",     default=42,    show_default=True)
@click.option("--save-to-supabase", is_flag=True, default=True)
def monte_carlo(run_id, n, seed, save_to_supabase):
    """Corre Monte Carlo sobre los trades OOS de un run WFA."""

    console.print(Panel(
        f"[bold]Monte Carlo:[/bold] run_id={run_id} n={n:,}",
        border_style="magenta"
    ))

    # Cargar windows del run
    results_store = ResultsStore()
    try:
        windows = results_store.load_wfa_windows(run_id)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    # Extraer todos los trade PnLs OOS de todas las ventanas
    import numpy as np
    all_pnls = []
    for w in windows:
        oos = w.get("oos_metrics", {})
        net_pnl = oos.get("net_pnl", 0)
        n_trades = oos.get("n_trades", 0)
        wr       = oos.get("win_rate", 0.33)
        avg_win  = oos.get("avg_win", 50)
        avg_loss = oos.get("avg_loss", 25)

        # Reconstruir trades sintéticos desde estadísticas
        # (mejor práctica: guardar trades individuales en store — mejora F4)
        if n_trades > 0:
            n_wins   = int(n_trades * wr)
            n_losses = n_trades - n_wins
            wins     = np.full(n_wins, avg_win)
            losses   = np.full(n_losses, -avg_loss)
            all_pnls.extend(wins.tolist())
            all_pnls.extend(losses.tolist())

    if len(all_pnls) < 10:
        console.print("[red]Insuficientes trades para Monte Carlo[/red]")
        return

    pnls = np.array(all_pnls)
    np.random.shuffle(pnls)  # Mezclar ventanas

    # Correr MC
    mc = MonteCarlo(MCConfig(n_simulations=n, seed=seed))
    mc_result = mc.run(pnls, run_id=run_id)

    # Persistir
    if save_to_supabase:
        sb = get_supabase_client()
        if sb:
            sb.save_mc_results(run_id, mc_result.to_dict())

    results_store.close()


# ── COMPARE SLEEVES ───────────────────────────────────────────────────────

@cli.command("compare-sleeves")
@click.option("--sleeves", required=True,
              help="Comma-separated run IDs o ea_versions (ej: v1_9,v2_3)")
@click.option("--symbol",  required=True)
def compare_sleeves(sleeves, symbol):
    """Compara KPIs de múltiples sleeves."""
    from python.portfolio.sleeve_scorer import SleeveScorer, SleeveKPIs
    import numpy as np

    sleeve_list = [s.strip() for s in sleeves.split(",")]
    results_store = ResultsStore()
    scorer = SleeveScorer()

    kpis_list = []
    for sleeve_id in sleeve_list:
        # Buscar run por ea_version
        runs = results_store.list_runs(ea_version=sleeve_id)
        if runs.empty:
            console.print(f"[yellow]No se encontró run para: {sleeve_id}[/yellow]")
            continue

        run_id = runs.iloc[0]["run_id"]
        run    = results_store.load_run(run_id)
        m      = run["metrics"]

        # Construir KPIs sintéticos desde métricas agregadas
        kpis = SleeveKPIs(
            sleeve_id       = sleeve_id,
            ea_version      = run["ea_version"],
            symbol          = run["symbol"],
            timeframe       = run["timeframe"],
            n_trades        = m.get("total_is_trades", 0),
            profit_factor   = m.get("avg_oos_pf", 0),
            sharpe          = m.get("avg_oos_sharpe", 0),
            is_pf           = m.get("avg_is_pf", 0),
            oos_pf          = m.get("avg_oos_pf", 0),
            robustness_index = m.get("avg_robustness_index", 0),
            max_dd_pct      = m.get("max_oos_dd", 0),
        )
        kpis_list.append(kpis)

    if kpis_list:
        scorer.compare_sleeves(kpis_list)

    results_store.close()


# ── PORTFOLIO ─────────────────────────────────────────────────────────────

@cli.command()
@click.option("--sleeves",  required=True, help="Run IDs separados por coma")
@click.option("--symbols",  required=True, help="Símbolos separados por coma")
def portfolio(sleeves, symbols):
    """Calcula asignación HRP multi-sleeve (F8)."""
    console.print(Panel(
        "[bold]Portfolio HRP — F8[/bold]\nEsta función estará completa en F8.",
        border_style="green"
    ))
    console.print("[dim]Infraestructura lista. Activar en F8 con datos de forward testing.[/dim]")


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
