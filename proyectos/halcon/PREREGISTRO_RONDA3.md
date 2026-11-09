# HALCÓN — Ronda 3: Turtle espejo (largo y corto), velas de 4 h — PREREGISTRO

Fecha de redacción: 2026-11-09. Este archivo se commitea **antes** de bajar los datos nuevos y de correr la medición. Después de ver los resultados no se cambia ninguna regla de esta página; si se quiere probar otra cosa, es una ronda nueva con su propio preregistro.

## Pedido del usuario (2026-11-09)
Operar largos y cortos, velas de 4 h, "los últimos 10 años", capital elegido por Claude, definir la estrategia lo antes posible y corregir/mejorar con lo que se vea.

## Hipótesis
La regla Turtle que ya corre el bot de Alpaca (solo largos) tiene un espejo simétrico para cortos, y juntas (largo + corto) aprovechan más operaciones que solo largos. No se afirma que funcione: se mide.

## Reglas (fijas, sin ajustar parámetros)
Velas de 4 h cerradas. Parámetros iguales a `alpaca_bot/config.py`.
- **Largo:** entra si el cierre > máximo de los 120 máximos previos (20 días). Sale si el cierre < mínimo de los 60 mínimos previos (10 días) o si el precio toca el stop = entrada − 2 × ATR(14).
- **Corto (espejo):** entra si el cierre < mínimo de los 120 mínimos previos. Sale si el cierre > máximo de los 60 máximos previos o si el precio toca el stop = entrada + 2 × ATR(14).
- Entrada y salida por canal a la apertura de la vela siguiente; stop intra-vela a su precio (o a la apertura si abre más allá). Una posición por sentido y par; se corren los dos sentidos de forma independiente y se informa cuántas veces se superponen en el tiempo.
- **Costos por lado:** comisión 0,25 % + slippage 0,05 % (iguales a los de `config.py`). Para el corto **no** se modela costo de préstamo ni financiamiento: es un corto virtual; el costo real de un corto en otro mercado queda sin medir y se dice como limitación.
- **Tamaño:** riesgo 1 % del patrimonio por operación hasta el stop, sin apalancamiento (la posición no supera el 100 % del patrimonio). Patrimonio virtual de **USD 10.000** (riesgo USD 100 por operación). Las métricas principales están en R y en % del precio, que no dependen del capital; el capital solo escala los dólares.

## Datos y variantes
Fuente: Twelve Data (la misma de las rondas anteriores; no es la fuente de Alpaca). **Límite conocido:** a 2026-11-09 el historial de 4 h de BTC/USD en Twelve Data empieza el 2020-01-06 (≈ 6,8 años), no 10; el diario empieza el 2017-08-28. Se usa todo lo disponible en cada caso, sin recortar a mano.
Variantes (9), cada una con sus tres sentidos: largo, corto, largo+corto:
1. BTC/USD, 4 h, todo el historial disponible.
2. ETH/USD, 4 h, todo el historial disponible.
3. BTC/USD, **diario** (20/10 velas diarias, ATR(14) diario; mismas reglas con el canal en velas diarias), desde 2017-08-28. Es una verificación de robustez en un período más largo, no es el pedido de 4 h.
Cantidad acumulada de variantes probadas en HALCÓN: 12 (rondas 1 y 2) + 9 = **21**.

## Tramos y línea base
Ajuste = primer 60 % del tiempo evaluable de cada serie; validación = último 40 %. No hay nada que ajustar (los parámetros están fijos); el corte solo sirve para comprobar consistencia. Línea base: entradas al azar del mismo sentido con la misma salida, 3.000 sorteos, semilla fija.

## Criterio para "pasa" (por variante y sentido)
1. n ≥ 30 operaciones en validación (si no llega: "no concluyente", no "pasa").
2. R neto promedio > 0 en ajuste **y** en validación.
3. p contra el azar en validación < 0,05 / 21 ≈ 0,0024.
Además se informa siempre: operaciones por mes, acierto, factor de beneficio, IC90 del R neto, mejor y peor operación, caída máxima, comprar-y-mantener del mismo período.

## Qué se hace con el resultado (decidido antes de verlo)
- **Si una variante pasa:** esa variante pasa a prueba **hacia adelante en papel** (HALCÓN), con largos reales en Alpaca Paper y cortos virtuales.
- **Si ninguna pasa:** el usuario ya pidió probar hacia adelante; se puede hacer igual como **experimento en papel**, dejando escrito que no hay evidencia previa. Se informa todo, incluidos los resultados negativos.
- **Dinero real:** no se pasa a dinero real con esta ronda. Mínimos antes de proponerlo: ≥ 30 operaciones hacia adelante en papel por sentido, resultado consistente con la medición histórica, costos reales de los cortos conocidos, y autorización explícita del usuario por cada orden (regla del proyecto). Un backtest, aunque sea de años, no prueba que la estrategia funcione.

## Riesgos de lectura ya conocidos
- BTC y ETH caen y suben juntos: las dos series no son muestras independientes.
- Parte de estos datos (2024-09 en adelante) ya se vio en las rondas 1 y 2; el hecho de que Bitcoin cayera 13 % en la validación de la ronda 1 favorece a un corto. Por eso la prueba que cuenta es la que se haga hacia adelante.
- Los datos de Twelve Data pueden tener huecos o diferencias con los de Alpaca; se informan los huecos detectados.
