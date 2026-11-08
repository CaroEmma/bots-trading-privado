# HALCÓN — Bitcoin en Alpaca Paper (estado: backtest hecho, ninguna estrategia validada, sin bot)

Fecha: 2026-11-08. Código y datos: carpeta `halcon/` (script `backtest.py` con el **preregistro** en su cabecera, 15 tests, `resultados/`).
Datos: 19.084 velas de BTC/USD de 1 h, 2024-09-01 a 2026-11-08, fuente Twelve Data (no es la misma fuente que Alpaca; 3 huecos de 23 h donde se unieron los tramos de descarga). Ajuste = primer 60 % (hasta 2025-12-24), validación = último 40 %.

## Qué se probó (reglas fijadas ANTES de correr; el preregistro se commiteó antes de cada ronda)
- 3 señales de entrada con parámetros estándar, sin ajustar: S1 ruptura de 48 velas, S2 RSI(14) < 30 con precio sobre SMA(200), S3 retroceso a la EMA(20) con EMA(50) > EMA(200).
- Salida común: stop 2 × ATR(14), objetivo 3 × ATR (R:R bruto 1,5), salida por tiempo. Solo largos, una posición a la vez.
- Costos por lado: 0,25 % de comisión (taker, a confirmar en la página vigente de Alpaca) + 0,05 % de slippage (supuesto del bot Turtle existente). Sensibilidad con 0,15 %.
- Línea base: entradas al azar con la misma salida. Regla para "pasar": n ≥ 30 en validación, R neto > 0 en ajuste y validación, y p/azar < 0,05 dividido por la cantidad acumulada de variantes probadas.

## Resultado: 0 de 12 variantes pasan
| Ronda | Velas | Variantes | Pasan | R neto (validación) | Observación |
|---|---|---|---|---|---|
| 1 | 1 h | 6 | 0 | −0,52 a −0,65 en S1 y S3 | El costo de ida y vuelta (0,6 %) se come ~0,5 R por operación: el stop de 2 × ATR en 1 h es solo ~1,15 % del precio. Hasta las entradas al azar dan −0,5 R. |
| 2 | 4 h | 6 | 0 | −0,40 a −0,55 en S1 y S3 | El costo pesa menos (azar ≈ −0,2 R) pero la ventaja bruta es ≈ 0 en ajuste y negativa en validación. |

- S2 (reversión) casi no opera: 8 operaciones en validación a 1 h y 1 a 4 h; su R positivo con n = 8 no es evidencia (p 0,04–0,05 contra un umbral de 0,0083, y n < 30).
- Contexto: Bitcoin subió 38,9–54,9 % en el período de ajuste y bajó 13 % en el de validación; las estrategias solo-largos tuvieron viento en contra en la validación.
- Pérdida máxima por operación: con USD 100 de capital y sin apalancamiento la posición está topada (USD 75), así que la pérdida real al tocarse el stop es **USD 0,86 (velas de 1 h) o USD 1,79 (4 h)** aunque se permita USD 5. Con USD 5 permitidos los resultados en R no cambian; solo se pierden más dólares (ej.: S1 a 4 h, validación −USD 26,9 en vez de −14,5).

## Limitaciones (honestas)
- Un backtest no es un resultado real: sin latencia, rechazos ni liquidez de Alpaca. Datos de otra fuente. Posible sobreajuste de la lectura aunque no se afinaron parámetros.
- Solo se probaron 3 familias de señal con una salida; que ninguna valga no prueba que ninguna estrategia pueda valer.
- Poca potencia estadística: con ~0,7 operaciones por semana a 4 h hacen falta meses para juntar 30 operaciones.

## Estado y decisiones pendientes del usuario
No se construyó ningún bot ni se envió ninguna orden. Opciones: (A) no operar HALCÓN hasta tener una hipótesis nueva, preregistrada; (B) medir el bot Turtle existente (4 h, canal 20/10 días) con este mismo marco como referencia; (C) probar otra familia (por ejemplo velas diarias, con pocas operaciones). Capital de HALCÓN: USD 100 (dicho por el usuario); margen de pérdida por operación: el usuario pidió probar USD 5 (sin efecto práctico, ver arriba).
