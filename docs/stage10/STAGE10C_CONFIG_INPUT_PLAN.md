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