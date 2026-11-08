# Bitcoin en cuenta ficticia con capital de USD 100

Fecha: 2026-11-08. Solicitud del usuario: capital de USD 100; que Claude defina el margen de pérdida y las alertas; probar ya en BTC con cuenta ficticia, para operar después según resultados y obtener estadística real.
Convención: lo observado va como hecho; las decisiones propuestas van marcadas como **propuesta**.

## 1. Hallazgo: el pack day-trader-skill NO soporta Bitcoin

Verificado en el código y por prueba:
- `trader-entry check BTC-USD` lo trata como una acción de la NYSE: responde "MARKET CLOSED, the NYSE is closed today (weekend)". El setup de apertura de rango (9:30 ET) no existe en un mercado 24/7.
- `trader-risk` (SKILL.md y `check.py`): el chequeo `asset` **bloquea cripto** ("crypto or anything that is not a US stock or ETF ticker").
- `trader-broker` (SKILL.md): "Never calls … option or crypto order tools on its own".
- `trader-timemachine` arma su universo con sesiones completas de 78 barras de 5 min de la NYSE; BTC tiene 24 h (no probado directamente; deducido del diseño descrito en su SKILL.md).
- `trader-budget`: el config de ejemplo trae `"fractional": false` (solo acciones enteras).
- Los datos de BTC sí existen en Yahoo: `BTC-USD`, velas de 5 min (110,6 h en 5 días), precio observado 75.916,34 USD.

Conclusión: para BTC hay que **adaptar o construir** herramientas nuevas; el pack tal cual no sirve.

## 2. Lo que ya existe en el repo del usuario (verificado leyendo `alpaca_bot/`)

- Un bot Turtle long-only en **Alpaca Paper** para BTC/USD y ETH/USD, por GitHub Actions cada 15 min.
- Estrategia (`config.py`): velas de 4 h, canal de entrada de 20 días (480 h), canal de salida de 10 días (240 h), stop 2 × ATR(14), riesgo 2 % por operación, costos simulados: comisión taker 0,25 % + slippage 0,05 %.
- Log desde **2026-10-07 hasta 2026-11-08**: **cero operaciones** (ninguna línea de orden, siempre "sin posicion"). Equity de la cuenta paper: **99.999,88 USD** (cuenta de USD 100.000, no de 100).
- Motivo (del propio log): el canal de entrada de BTC está en ~84.852,68 y el precio ronda 75.860, es decir, falta ~11,8 % para que dispare. Esta estrategia opera pocas veces: **no va a dar estadística en semanas**.

## 3. Costos (fuente web, a confirmar)

Alpaca, comisiones de cripto spot, escalón de 0 a 100.000 USD de volumen a 30 días: **0,15 % maker / 0,25 % taker**, según la documentación de Alpaca (consultada el 2026-11-08). No encontré una página de comisiones de 2026: confirmar en la página vigente antes de depender de estos números. Fuentes: https://docs.alpaca.markets/docs/crypto-fees y https://docs.alpaca.markets/us/docs/crypto-fees
Cripto está disponible en cuentas paper (según la documentación de Alpaca); paper simula el relleno con cotizaciones reales.

Impacto con USD 100 (aritmética): ida y vuelta taker = 0,50 %; con la posición de USD 56 del punto 5 son **USD 0,28** de comisión por operación, contra una pérdida máxima de USD 1: la comisión se come ~28 % del riesgo asignado. Más slippage (0,05 % por lado, supuesto del bot).

## 4. Datos de mercado medidos hoy (Yahoo BTC-USD, velas 1 h agrupadas en 4 h UTC, 357 velas cerradas)

- Último cierre: 75.872,42 USD.
- ATR(14) de 4 h (Wilder): **676,80 USD = 0,892 %** del precio.
- Stop a 2 × ATR: 1.353,60 USD = **1,784 %**.
- Máximo de 20 días (canal de entrada): 84.849,64 (el log del bot da 84.852,68: diferencia por fuente de datos, Yahoo vs Alpaca).
- Mínimo de 10 días (canal de salida): 74.791,00.

## 5. Propuesta de margen de pérdida (criterio, no norma verificada)

Criterio habitual de gestión de riesgo: arriesgar un porcentaje chico del capital por operación. Se propone para USD 100:

| Parámetro | Propuesta | Por qué |
|---|---|---|
| Pérdida máxima por operación | **USD 1 (1 %)** | Con stop de 1,784 % da una posición de USD 56, dentro de la cuenta. Con USD 2 (2 %, como el bot actual) la posición saldría de USD 112 > capital: requeriría apalancamiento, que el proyecto excluye. |
| Pérdida máxima por día | **USD 3 (3 %)** | Permite 3 pérdidas completas; después se frena hasta el día UTC siguiente. |
| Operaciones por día | 3 | Mismo orden de magnitud que el pack (3 por defecto en su config). |
| Recompensa/riesgo mínima | **1,5** | Con comisiones, 1,0 casi no deja margen. |
| Apalancamiento / corto | No | Alpaca no permite vender en corto cripto (comentario del `config.py` del bot); el apalancamiento queda excluido. |
| Efectivo mínimo | Posición ≤ USD 100 × 75 % = USD 75 | Mismo `max_position_pct` del config de ejemplo del pack. |

Fórmula: posición = pérdida máxima ÷ distancia al stop. Ejemplo hoy: 1 ÷ 0,01784 = USD 56,05. Si el stop es de 1 % la posición sería USD 100 (toda la cuenta) y si es de 0,5 %, USD 200 (imposible sin apalancamiento).

## 6. Propuesta de alertas para BTC (24/7)

El `trader-alerts` del pack asume horario de la NYSE (cierre 15:55, feriados): hay que adaptarlo.

1. **Entrada**: precio cruza el nivel de disparo definido por la estrategia.
2. **Stop**: precio toca el stop (la más crítica).
3. **Target**: precio toca el objetivo (recompensa/riesgo ≥ 1,5).
4. **Pérdida diaria**: pérdida acumulada del día ≥ USD 3 → no abrir más hasta el día UTC siguiente.
5. **Stop por tiempo** (reemplaza "flat by close"): posición abierta más de N horas. **N lo tiene que decidir el usuario**; no hay dato que lo fije.
6. **Salud de datos**: la fuente (Yahoo) es no oficial; alertar si el último dato tiene más de un umbral de antigüedad (a definir).
7. **Costo**: alertar si comisión + slippage de una operación supera una fracción del riesgo (a definir).

Limitación real: esta sesión de Claude no vigila de forma continua. Alertas sostenidas requieren una rutina recurrente (por ejemplo un workflow de GitHub Actions como los bots existentes). Hoy "alerta" significa que se calcula en el momento que se corre la herramienta.

## 7. Limitaciones sobre "estadística real"

- Un backtest sobre datos históricos de Yahoo **no es** un resultado real: no incluye rechazos, latencia ni la liquidez real de Alpaca. La cuenta paper simula rellenos con cotizaciones, no con exchanges.
- En la prueba de TSLA, 34 disparos no alcanzaron para concluir nada (simulación +0,070 R vs historial −0,067 R). Con USD 100 y pocas operaciones por semana, la estadística tarda en acumularse.
- Probar varias estrategias sobre los mismos datos y elegir la mejor genera sobreajuste: hay que separar datos de ajuste y datos de validación.
- Nada de esto es asesoramiento financiero; no se prometen ganancias.

## 8. Estado y pendientes

No se creó código nuevo ni se envió ninguna orden. Decisiones pendientes del usuario:
1. Confirmar o ajustar la pérdida máxima (propuesta: USD 1 por operación, USD 3 por día, 3 operaciones por día, R:R ≥ 1,5).
2. Elegir camino: (A) construir un simulador BTC propio con cuenta virtual de USD 100 + backtest con costos reales; (B) seguir con el bot Turtle de Alpaca Paper, que hasta hoy no operó; (C) A y B en paralelo (recomendado por Claude).
3. Si es A o C: definir la estrategia a probar (propuesta: empezar por una sola, con datos separados para ajuste y validación) y el valor de N horas del stop por tiempo.
4. Cualquier cambio que permita órdenes cripto en `trader-risk` / `trader-broker` toca controles de seguridad del pack: requiere aprobación explícita.
