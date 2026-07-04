Stage10C Design Pack — Config/Input Plan,execution_scope Payload & touch_gapInstrumentation
1. Config/Input Plan — Stage10C
Objetivo
Preparar la configuración conceptual para que Stage10C opere bajo una política USDJPY-first, sinimplementar todavía cambios en EA, Worker ni Supabase.
Política de símbolos
Símbolo
Modo
Realtrading
Shadowtelemetry
Comentario
USDJPY
REAL
Sí
Sí
Único símbolo autorizado paracapital real
EURUSD
SHADOW_ONLY
No
Sí
Se conserva observabilidad
EURJPY
SHADOW_ONLY
No
Sí
Sin capital real
GBPUSD
SHADOW_ONLY
No
Sí
Sin capital real
Configuración conceptual
La configuración Stage10C deberá separar explícitamente:
signal_evaluation
: evaluación técnica de entrada.
execution_scope
: autorización de ejecución real.
capital_scope
: autorización de uso de capital.
order_send_allowed
: permiso final para enviar orden.
Inputs conceptuales futuros del EA
No se implementan todavía, pero el diseño deberá contemplar inputs equivalentes a:
StagePhase = Stage10C-USDJPYFirstGovernanceReset
SymbolPolicyMode = USDJPY_FIRST
ExecutionScope = REAL | SHADOW_ONLY
AllowRealTrading = true | false
AllowShadowTelemetry = true
OrderSendAllowed = true | false
•
•
•
•
1
Resolución esperada por símbolo
USDJPY
ExecutionScope = REAL
AllowRealTrading = true
AllowShadowTelemetry = true
OrderSendAllowed = true
CapitalEnabled = true
EURUSD / EURJPY / GBPUSD
ExecutionScope = SHADOW_ONLY
AllowRealTrading = false
AllowShadowTelemetry = true
OrderSendAllowed = false
CapitalEnabled = false
Regla de seguridad
Si existe conflicto entre configuración local del EA y política del Worker, debe ganar la política másrestrictiva.
Orden de precedencia recomendado:
Global kill switch.
Worker capital policy.
Symbol execution policy.
EA local input.
Signal technical readiness.
La ausencia de
execution_scope
debe resolverse de forma segura como:
ExecutionScope = SHADOW_ONLY
OrderSendAllowed = false
2. execution_scope Payload Design
Objetivo
Hacer explícito en cada evaluación si una señal puede ejecutarse en real o si solo debe registrarse comoshadow.
1.
2.
3.
4.
5.
2
Principio clave
ENTRY_READY
no debe significar automáticamente
ORDER_ALLOWED
.
Stage10C separa:
technical_signal_status != capital_execution_permission
Estructura propuesta
{"execution_scope":{"policy_name":"stage10c_usdjpy_first_governance_reset","mode":"REAL","capital_enabled":true,"order_send_allowed":true,"symbol_real_allowed":true,"shadow_only":false,"resolved_by":"worker_policy","resolution_source":["ea_input","worker_policy"],"reason":"USDJPY is the only real-trading symbol allowed under Stage10C"}
}
Ejemplo USDJPY REAL
{"symbol":"USDJPY","signal_status":"ENTRY_READY","execution_scope":{"policy_name":"stage10c_usdjpy_first_governance_reset","mode":"REAL","capital_enabled":true,"order_send_allowed":true,"symbol_real_allowed":true,"shadow_only":false,"resolved_by":"worker_policy","reason":"USDJPY allowed for real execution under Stage10C"}
}
Ejemplo EURJPY SHADOW_ONLY
{"symbol":"EURJPY",
3
"signal_status":"ENTRY_READY","execution_scope":{"policy_name":"stage10c_usdjpy_first_governance_reset","mode":"SHADOW_ONLY","capital_enabled":false,"order_send_allowed":false,"symbol_real_allowed":false,"shadow_only":true,"resolved_by":"worker_policy","reason":"EURJPY is shadow-only under Stage10C; real execution is not
allowed"}
}
Estados derivados recomendados
Para evitar ambigüedad en dashboard y auditoría, se recomiendan estados derivados como:
ENTRY_READY_REAL_ALLOWED
ENTRY_READY_SHADOW_ONLY_BLOCKED
BLOCKED_BY_TECHNICAL_GUARD
BLOCKED_BY_EXECUTION_SCOPE
Estos estados son de diseño. No se implementan todavía.
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
4. Stage10C Guardrails
Durante Stage10C quedan prohibidos:
No F5B
No BE
No touch_025 global
No cambio TP/SL
No ML
No EURJPY real
No GBPUSD real
No v4.43.0 implementation yet
No additional validations yet
Resultado de diseño
Stage10C queda preparado como una etapa de reset de gobernanza, no como una etapa deoptimización agresiva.
El objetivo es proteger capital real, preservar telemetría y mejorar trazabilidad antes de cualquiercambio de versión.
•
•
•
•
•
•
•
•
6