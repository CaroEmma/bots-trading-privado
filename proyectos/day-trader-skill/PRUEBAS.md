# Pruebas del pack day-trader-skill

Versión probada: commit `3d0f4ef` (plugin 2.0.0), copia aislada, Python 3.13.18.
Convención: solo se registra lo observado; nada inventado.

## Prueba 01 — 2026-11-08 (domingo, mercado cerrado)

Alcance: tests offline + skills de **solo lectura**. No se usó `trader-broker`, no se enviaron órdenes, no se conectó ningún broker. No se usaron claves.

Cómo se corrió: copia del repo en el scratchpad de la sesión (sin `.git`), `python3 -I` (modo aislado), directorio de trabajo separado para que los archivos `trader/` no toquen el proyecto.

### Entorno de red

- Primer intento: **bloqueado**. El proxy de la sesión devolvió `403` para todas las fuentes de datos (el entorno "Default" no tenía hosts permitidos).
- Se creó (con aprobación del usuario) un entorno personal **"day-trader-skill (datos de mercado)"** con 8 hosts exactos de solo lectura: `query1.finance.yahoo.com`, `query2.finance.yahoo.com`, `feeds.finance.yahoo.com`, `www.nasdaqtrader.com`, `www.sec.gov`, `data.sec.gov`, `stooq.com`, `disclosures-clerk.house.gov`.
- Resultado de conectividad (HTTP): Yahoo chart 200, Yahoo RSS 200, Nasdaq Trader 200, SEC data 200, House Clerk 200. **Stooq: sin respuesta** (solo es respaldo para alertas; sin impacto en esta prueba).
- Para repetir pruebas en vivo en una sesión futura hay que **elegir ese entorno** al iniciar la sesión.

### Resultados

| # | Prueba | Resultado |
|---|---|---|
| 1 | `unittest discover` (offline, fixtures) | **315 tests, OK**, 10 s |
| 2 | `trader-news` TSLA, 72 h | OK: precio 358,22, +4,23 % vs cierre previo (343,69) y titulares reales con hora de Nueva York. Las 8-K de la SEC se omitieron porque falta `sec_user_agent` (no se cargó ningún email). |
| 3 | `trader-scanner universe` | OK: 13.276 filas de Nasdaq Trader (archivos del 2026-11-06 21:31 ET), **5.936** acciones/ADR conservadas, con desglose de lo descartado. |
| 4 | `trader-entry check TSLA` (domingo) | OK: detecta "MARKET CLOSED, fin de semana" y da la próxima apertura (2026-11-09 09:30). |
| 5 | `trader-entry` con `--now "2026-11-06 10:15"` | OK: rango 9:30–9:45 máx 354,80 / mín 347,60; **disparó a las 10:00 a 356,49** (barra de 9:55). Avisa que entrar tarde es otro trade. "Nothing was placed". |
| 6 | `trader-exit plan` | OK: stop 351,20 (mitad del rango), target 361,78 (1R), riesgo/acción 5,29, flat 15:55 ET. Avisa que el plan es del 6/11 y no de hoy. |
| 7 | `trader-timemachine` (seed 19) | OK: 10.000 réplicas → target primero 39,2 %, stop primero 31,3 %, sin definir 29,5 %; R promedio simulado +0,070. |

### Hallazgo importante (no contradicción menor)

En el paso 7 el **modelo simulado** "se inclina al target" (R promedio +0,070), pero el **historial real de la misma regla** en las 59 sesiones previas dio: disparó 34 veces → **12 target, 15 stop, 7 sin definir, R promedio −0,067**. Es decir, la simulación es levemente positiva y el registro real, levemente negativo. Con 34 casos y una diferencia tan chica, ninguno de los dos es concluyente. Esto coincide con la advertencia del propio README (en su ejemplo el veredicto fue "casi una moneda al aire"). Tomarlo como un chequeo de realidad, no como señal operable.

### Observaciones menores

- Con el mercado cerrado, `news` muestra "vs yesterday's close … at 16:00 ET" (en domingo, "ayer" no es el día anterior). Etiqueta ambigua, sin impacto en cálculos.
- El feed de Yahoo trae notas que mencionan otros emisores (p. ej. Rivian, TransMedics) etiquetadas bajo TSLA: ruido de la fuente, hay que leer cada nota.
- Los precios del reel/README (octubre) y los de esta prueba (noviembre) no se compararon entre sí.

### No probado todavía

- `trader-scanner daily` / `orb` sobre todo el universo (cientos de pedidos a Yahoo; conviene hacerlo con mercado abierto y de a pocos).
- `trader-budget`, `trader-risk`, `trader-alerts`, `trader-analyst`, `trader-pelosi`, `trader-broker`.
- Alpaca / paper trading.
- Para `budget` y `risk` hacen falta datos del usuario: capital de la cuenta y pérdida máxima por operación (no se inventan).

### Siguiente prueba sugerida

1. [OBLIGATORIO] Capital y pérdida máxima por operación → `trader-budget` + `trader-risk` (aritmética local, sin órdenes).
2. [OPCIONAL] Nombre y email para `sec_user_agent` → noticias con 8-K y `trader-analyst`.
3. Con mercado abierto (lunes 9/11 desde 9:30 ET): `scanner orb` y `entry watch`.
4. Recién después, `trader-broker` en paper con Alpaca, claves solo en variables de entorno.
