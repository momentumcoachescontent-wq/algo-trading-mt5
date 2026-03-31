# ADR-001: Stack inicial del proyecto

**Fecha:** 2026-03-31
**Estado:** Aceptado

## Contexto
Necesitamos un stack que permita iterar rápido en Fase 0-1
y que el proceso sea vendible como caso de estudio.

## Decisión
MT5 + MQL5 para ejecución, Python para análisis,
Supabase para persistencia, GitHub como fuente de verdad.

## Por qué no alternatives
- ccxt / Python directo: más flexibilidad, pero MT5 tiene
  Strategy Tester nativo que ahorra semanas en Fase 1.
- DB local: Supabase da API REST gratis para el dashboard
  de Cloudflare Pages sin infraestructura adicional.

## Consecuencias
- MQL5 requiere MetaEditor en Windows/Wine.
  En Mac: MT5 vía CrossOver o Wine, o Hostinger VPS en P3.
- El bridge Python necesita que MT5 esté corriendo para
  extraer datos en tiempo real.
