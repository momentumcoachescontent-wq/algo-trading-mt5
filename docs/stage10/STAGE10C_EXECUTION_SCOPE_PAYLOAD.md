1. execution_scope Payload Design

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