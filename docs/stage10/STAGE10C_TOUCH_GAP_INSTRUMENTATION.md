3. touch_gap Instrumentation Design
Objetivo
Diseñar una instrumentación futura para medir qué tan lejos queda una señal del touch requerido, sinmodificar reglas de entrada.
touch_gap
debe ser observacional. No debe abrir operaciones, no debe relajar guards y no debeactivar
touch_025
global.
Pregunta que debe responder
Cuando una señal no entra por falta de touch, Stage10C+ debe poder responder:
¿Qué tan lejos estuvo el precio de cumplir el touch?
4
Estructura propuesta
{"touch_gap":{"instrumented":true,"timeframe":"H4","ema_reference":"entry_ema","nearest_touch_zone":"outside_exact_inside_soft","exact_threshold":0.25,"soft_threshold":0.50,"extended_threshold":1.50,"min_gap_pips":3.2,"min_gap_points":32,"min_gap_atr_ratio":0.18,"close_gap_atr_ratio":0.31,"high_low_gap_atr_ratio":0.18,"passed_exact_touch":false,"passed_soft_touch":true,"passed_extended_touch":true,"reason":"Price missed exact touch but was inside soft touch range"}
}
Clasificación propuesta
inside_exact
outside_exact_inside_soft
outside_soft_inside_extended
outside_extended
unknown
Uso permitido
touch_gap
podrá utilizarse para:
Diagnóstico.
Auditoría.
Dashboard.
Research posterior.
Comparación de missed entries.
Evaluación futura de frecuencia potencial.
Uso prohibido en esta etapa
touch_gap
no puede utilizarse para:
Habilitar entrada real.
•
•
•
•
•
•
•
5
Cambiar touch rule.
Activar
touch_025
global.
Modificar TP/SL.
Introducir BE.
Activar F5B.
Cambiar capital allocation.
Justificar EURJPY real.
Justificar GBPUSD real.

# Stage10C touch_gap Instrumentation Design Freeze

## Status

Accepted for design.

This document does not authorize EA implementation, Worker implementation, Supabase migration, dashboard implementation, validation, deployment, or version bump to v4.43.0.

## Purpose

Define the final design contract for future `touch_gap` instrumentation.

`touch_gap` is intended to measure how far price was from satisfying the configured EMA touch condition when an evaluation is blocked or near-blocked by touch logic.

## Core Rule

```text
touch_gap is observational, not operational.