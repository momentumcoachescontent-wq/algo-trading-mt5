"""
python/infra/supabase_client.py
────────────────────────────────
Cliente Supabase para persistencia de resultados de research.

Persiste en Supabase:
    - Resultados de runs WFA (tabla: research_runs)
    - Ventanas WFA detalladas (tabla: wfa_windows)
    - Resultados Monte Carlo (tabla: mc_results)
    - KPIs de sleeves (tabla: sleeve_kpis)

La persistencia es asíncrona best-effort — si falla, el pipeline
continúa y se puede re-sincronizar manualmente.
"""

import os
import json
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

console = Console()

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False


class ResearchSupabaseClient:
    """
    Cliente para persistir resultados de research en Supabase.
    Tablas en el proyecto: fxttpblmiqgoerbvfons.supabase.co
    """

    def __init__(self):
        if not SUPABASE_AVAILABLE:
            raise ImportError("supabase no instalado. Ejecutar: pip install supabase")

        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")

        if not url or not key:
            raise ValueError(
                "SUPABASE_URL y SUPABASE_KEY deben estar en .env\n"
                "Ver .env.example para referencia."
            )

        self._client: Client = create_client(url, key)

    # ── Research Runs ─────────────────────────────────────────────────────

    def save_run(
        self,
        run_id:      str,
        ea_version:  str,
        symbol:      str,
        timeframe:   str,
        params:      dict,
        metrics:     dict,
        run_type:    str = "wfa",
        passed_f3:   bool = False,
    ) -> bool:
        """
        Persiste un run WFA en Supabase.

        Returns:
            True si exitoso, False si error.
        """
        try:
            self._client.table("research_runs").upsert({
                "run_id":      run_id,
                "ea_version":  ea_version,
                "symbol":      symbol,
                "timeframe":   timeframe,
                "params":      json.dumps(params),
                "metrics":     json.dumps(metrics),
                "run_type":    run_type,
                "passed_f3":   passed_f3,
                "created_at":  datetime.now(timezone.utc).isoformat(),
            }).execute()

            console.print(f"[dim green]✓ Run guardado en Supabase: {run_id}[/dim green]")
            return True

        except Exception as e:
            console.print(f"[dim yellow]⚠ Supabase save_run falló: {e}[/dim yellow]")
            return False

    def save_wfa_windows(self, run_id: str, windows: list[dict]) -> bool:
        """Persiste detalle de ventanas WFA."""
        try:
            records = []
            for w in windows:
                records.append({
                    "run_id":      run_id,
                    "window_idx":  w.get("window_idx"),
                    "is_from":     str(w.get("is_from", "")),
                    "is_to":       str(w.get("is_to", "")),
                    "oos_from":    str(w.get("oos_from", "")),
                    "oos_to":      str(w.get("oos_to", "")),
                    "is_metrics":  json.dumps(w.get("is_metrics", {})),
                    "oos_metrics": json.dumps(w.get("oos_metrics", {})),
                })

            self._client.table("wfa_windows").upsert(records).execute()
            console.print(
                f"[dim green]✓ {len(windows)} ventanas guardadas en Supabase[/dim green]"
            )
            return True

        except Exception as e:
            console.print(f"[dim yellow]⚠ Supabase save_wfa_windows falló: {e}[/dim yellow]")
            return False

    def save_mc_results(self, run_id: str, mc_dict: dict) -> bool:
        """Persiste resultados de Monte Carlo."""
        try:
            # Convertir arrays numpy a listas para JSON
            mc_serializable = {
                k: v.tolist() if hasattr(v, "tolist") else v
                for k, v in mc_dict.items()
                if k != "pf_distribution"  # demasiado grande — guardar solo percentiles
            }
            mc_serializable["run_id"] = run_id

            self._client.table("mc_results").upsert(mc_serializable).execute()
            console.print(f"[dim green]✓ MC results guardados en Supabase[/dim green]")
            return True

        except Exception as e:
            console.print(f"[dim yellow]⚠ Supabase save_mc_results falló: {e}[/dim yellow]")
            return False

    def save_sleeve_kpis(self, kpis_dict: dict) -> bool:
        """Persiste KPIs de un sleeve."""
        try:
            kpis_dict["saved_at"] = datetime.now(timezone.utc).isoformat()
            self._client.table("sleeve_kpis").upsert(kpis_dict).execute()
            return True
        except Exception as e:
            console.print(f"[dim yellow]⚠ Supabase save_sleeve_kpis falló: {e}[/dim yellow]")
            return False

    # ── Consultas ─────────────────────────────────────────────────────────

    def get_run(self, run_id: str) -> Optional[dict]:
        """Recupera un run por su ID."""
        try:
            result = (
                self._client
                .table("research_runs")
                .select("*")
                .eq("run_id", run_id)
                .execute()
            )
            if result.data:
                return result.data[0]
        except Exception as e:
            console.print(f"[dim yellow]⚠ Supabase get_run: {e}[/dim yellow]")
        return None

    def list_runs(
        self,
        ea_version: Optional[str] = None,
        symbol:     Optional[str] = None,
        passed_f3:  Optional[bool] = None,
        limit:      int = 50,
    ) -> list[dict]:
        """Lista runs con filtros opcionales."""
        try:
            query = (
                self._client
                .table("research_runs")
                .select("run_id, ea_version, symbol, run_type, passed_f3, created_at")
                .order("created_at", desc=True)
                .limit(limit)
            )
            if ea_version:
                query = query.eq("ea_version", ea_version)
            if symbol:
                query = query.eq("symbol", symbol)
            if passed_f3 is not None:
                query = query.eq("passed_f3", passed_f3)

            result = query.execute()
            return result.data or []

        except Exception as e:
            console.print(f"[dim yellow]⚠ Supabase list_runs: {e}[/dim yellow]")
            return []

    def get_best_runs(
        self,
        symbol:     str,
        metric:     str = "oos_pf",
        top_n:      int = 5,
    ) -> list[dict]:
        """Retorna los mejores runs por una métrica."""
        try:
            runs = self.list_runs(symbol=symbol, passed_f3=True, limit=100)
            # Ordenar por métrica en metrics JSON
            scored = []
            for run in runs:
                metrics = json.loads(run.get("metrics", "{}"))
                score = metrics.get(metric, 0)
                scored.append((score, run))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [r for _, r in scored[:top_n]]
        except Exception as e:
            console.print(f"[dim yellow]⚠ Supabase get_best_runs: {e}[/dim yellow]")
            return []

    def health_check(self) -> bool:
        """Verifica conectividad con Supabase."""
        try:
            self._client.table("research_runs").select("run_id").limit(1).execute()
            console.print("[green]✓ Supabase conectado[/green]")
            return True
        except Exception as e:
            console.print(f"[red]✗ Supabase health check falló: {e}[/red]")
            return False
