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

## Medición del bot Turtle existente (opción B, 2026-11-08)

Script `halcon/medir_turtle.py`; resultados en `halcon/resultados/turtle_medicion.txt` y `.json`. Usa las **mismas funciones del bot** (`alpaca_bot/estrategia.calcular`, `config.py`) sobre velas de 4 h de BTC y ETH (Twelve Data, 2024-09-23 a 2026-11-07, 775 días evaluables). Es una medición de una regla fija, sin ajustar nada. Costos del bot: 0,25 % + 0,05 % por lado. Cada par con su manga independiente (USD 50.000).

| | BTC/USD | ETH/USD |
|---|---|---|
| Operaciones (2 años) | 24 (5 ganadoras, 19 stops) | 17 (6 ganadoras, 11 stops) |
| Acierto | 21 % | 29 % |
| R neto promedio | −0,03 (IC90 −0,88 a +0,90) | +0,83 (IC90 −0,51 a +2,37) |
| Factor de beneficio | 0,98 | 2,03 |
| Retorno de la manga | −1,8 % (caída máx. 23,8 %) | +27,1 % (caída máx. 18,5 %) |
| Comprar y mantener | +19,6 % | −15,3 % |
| p contra entradas al azar | 0,47 | 0,14 |

- Cuenta completa: **+12,6 % en 775 días** (2 mangas, USD 100.000), con 41 operaciones.
- Ni BTC ni ETH se distinguen estadísticamente de entrar al azar con la misma salida. En ETH, ajuste +1,79 R (n = 9) y validación −0,26 R (n = 8): no se sostuvo.
- Perfil típico de seguidor de tendencia: gana poco seguido (21–29 %) y depende de pocas operaciones grandes (BTC: +23,2 R de ganadoras contra −23,8 R de stops; las 3 mejores operaciones de BTC suman +19,8 R).
- **Consistencia con el bot real:** hoy el bot no entra porque BTC (75.868) está 11,9 % bajo el nivel de entrada (84.898, el log del bot da 84.852) y ETH 12,8 % bajo (2.527). La simulación tampoco tiene entradas desde el 8/10/2026.
- Casi siempre invierte toda la manga: con stop de 2 × ATR (~2 % del precio), el riesgo del 2 % no limita el tamaño (la fracción de la manga es 34–100 %).

Limitaciones de esta medición: es una simulación (entrada a la apertura siguiente; el bot real corre unas 4 veces por día por la demora de los crons de GitHub y solo evalúa la última vela cerrada en cada corrida, así que puede entrar tarde o perder una señal); no se sabe si Alpaca Paper cobra las comisiones del replay; datos de otra fuente; n chico.

## Mejora aplicada al bot Turtle (2026-11-08, autorizada por el usuario)

Qué cambió (la estrategia y sus parámetros NO cambiaron; archivos: `alpaca_bot/bot_github_actions.py`, `.github/workflows/alpaca-turtle.yml`, tests en `alpaca_bot/tests/`):
1. **Revisa todas las velas cerradas pendientes** en cada corrida, no solo la última. Las salidas por canal se aplican aunque la vela sea vieja (se loguean como "TARDIA"); las **entradas solo con la última vela** (entrar por una señal vieja sería otro trade); la primera corrida sin estado solo evalúa la última vela.
2. **Avisa cada compra y cada venta** por issue del repo (con mención), igual que ALBA.
3. **Workflow:** cron cada hora y al cierre de cada vela de 4 h (antes `*/15`, que GitHub corría ~4 veces por día), `issues: write`, tests antes de operar (si fallan no se opera), y reintento de push con rebase.
4. El estado (`estado.json`) mantiene el mismo formato: no hay migración.

Verificación (offline): 11 tests; el bot real reproducido vela por vela sobre 775 días hace **exactamente las mismas operaciones que la medición** (BTC: 24, ETH: 17, mismas fechas de entrada y salida). Efecto medido en BTC con corridas salteadas:
| Frecuencia de corridas | Compras (antes → ahora) | Cierres (antes → ahora) |
|---|---|---|
| cada 4 h | 24 → 24 | 24 → 24 |
| cada 8 h | 22 → 22 | 21 → **22** (una salida por canal ya no se pierde) |
| cada 24 h | 6 → 6 | 5 → **6** |

**Límite que la mejora NO arregla:** las entradas dependen de que una corrida vea la vela de ruptura como la última cerrada. Con corridas cada 24 h se pierden 3 de cada 4 compras (6 de 24). La densidad real de corridas depende de que GitHub cumpla los crons; el diseño por sesiones largas (como ALBA) la asegura, pero no se aplicó acá (ver riesgo siguiente).

**Riesgo no resuelto — condiciones de uso de GitHub Actions:** versiones anteriores de las condiciones de GitHub listan "serverless computing" entre los usos no previstos de Actions y una discusión de la comunidad lo trata como fuera del alcance de CI/CD (no es política oficial). No pude confirmar el texto vigente. Un bot de trading con corridas cortas y esporádicas está en una zona gris; sesiones de 6 horas casi continuas (como las de ALBA) lo están más. Consecuencia posible: GitHub puede cortar jobs o restringir Actions. Por eso el Turtle NO se pasó a sesiones largas. Alternativa más segura a futuro: un servidor propio o un servicio de ejecución pensado para esto. Fuentes (consultadas 2026-11-08): https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features , https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies

## Limitaciones (honestas)
- Un backtest no es un resultado real: sin latencia, rechazos ni liquidez de Alpaca. Datos de otra fuente. Posible sobreajuste de la lectura aunque no se afinaron parámetros.
- Solo se probaron 3 familias de señal con una salida; que ninguna valga no prueba que ninguna estrategia pueda valer.
- Poca potencia estadística: con ~0,7 operaciones por semana a 4 h hacen falta meses para juntar 30 operaciones.

## Estado y decisiones pendientes del usuario
No se construyó ningún bot ni se envió ninguna orden. Opciones: (A) no operar HALCÓN hasta tener una hipótesis nueva, preregistrada; (B) medir el bot Turtle existente (4 h, canal 20/10 días) con este mismo marco como referencia; (C) probar otra familia (por ejemplo velas diarias, con pocas operaciones). Capital de HALCÓN: USD 100 (dicho por el usuario); margen de pérdida por operación: el usuario pidió probar USD 5 (sin efecto práctico, ver arriba).


## Ronda 3 (2026-11-09): Turtle espejo largo/corto, 4 h — resultado: 0 de 9 variantes pasan

Preregistro: `PREREGISTRO_RONDA3.md` (commit `234a3d6`, anterior a los datos y a la corrida). Código: `halcon/medir_espejo.py` (+ `halcon/tests/test_espejo.py`, incluye un test de simetría: largo sobre la serie = corto sobre la serie reflejada). Resultados completos: `halcon/resultados/ronda3_espejo.txt` y `.json`. Datos: `halcon/datos/*_4h_twelvedata.csv`, `btc_usd_1d_twelvedata.csv`, limpieza en `halcon/datos/LIMPIEZA.txt`.

**Límite de datos (no son 10 años en 4 h):** Twelve Data entrega BTC en 4 h desde 2020-01-06 (6,8 años) y ETH desde 2019-09-26 (7,1 años). Para BTC se agregó la serie diaria desde 2017-08-28 (9,2 años). Para tener 10 años en 4 h hace falta otra fuente (Bitstamp, `www.bitstamp.net`), hoy bloqueada por la red de la sesión. Kraken Futures demo: **dado de baja el 2026-07-14** (soporte de Kraken, artículo actualizado 2026-10-29).

| Variante (USD 10.000 virtuales, riesgo 1 %) | Sentido | n (todo / validación) | R neto (todo) | Mediana R | R neto validación | p vs azar (validación) | Veredicto |
|---|---|---|---|---|---|---|---|
| BTC 4 h | largo | 62 / 29 | +2,64 (sin la mejor: +1,33) | −1,17 | −0,14 | 0,49 | no concluyente (n<30) |
| BTC 4 h | corto | 50 / 26 | +0,01 | −1,18 | −0,48 | 0,63 | no concluyente (n<30) |
| BTC 4 h | largo+corto | 112 / 55 | +1,47 | −1,17 | −0,30 | 0,59 | no pasa |
| ETH 4 h | largo | 50 / 21 | +3,00 | −1,11 | +1,46 | 0,10 | no concluyente (n<30) |
| ETH 4 h | corto | 55 / 24 | +0,05 | −1,11 | +0,08 | 0,33 | no concluyente (n<30) |
| ETH 4 h | largo+corto | 105 / 45 | +1,45 | −1,11 | +0,72 | 0,10 | no pasa |
| BTC diario | largo | 49 / 21 | +2,01 | −0,29 | +0,65 | 0,19 | no concluyente (n<30) |
| BTC diario | corto | 46 / 19 | +0,02 | −0,63 | −0,26 | 0,41 | no concluyente (n<30) |
| BTC diario | largo+corto | 95 / 40 | +1,05 | −0,55 | +0,22 | 0,18 | no pasa |

Lectura: (1) **el corto no tiene ventaja medible**: R neto ≈ 0 en las tres series (+0,006; +0,05; +0,02), antes de cualquier costo de préstamo o financiamiento; (2) el largo gana en el total, pero por **pocas operaciones enormes** (BTC 4 h: mejor +83 R, mediana −1,17 R, 26 % de acierto) y **no se distingue de entrar al azar con la misma salida** (p 0,12–0,17); en la validación, BTC largo da −0,14 R; (3) sumar cortos **no mejora el retorno** (BTC 4 h: largo +250 % con caída 14 %, largo+corto +247 % con caída 25 %; ETH +275 % vs +278 %, caída 10 % vs 17 %) y agrega caída; (4) las operaciones por mes (0,4–0,9 por sentido) implican **años** para juntar 30 operaciones hacia adelante (BTC+ETH largo+corto ≈ 2,6 por mes, correlacionadas: ~12 meses como mínimo); (5) resultados casi idénticos excluyendo las operaciones que tocan la ventana dañada de 2023.

**Desviaciones del preregistro (declaradas):** (a) la limpieza de datos se definió después de ver los errores de la fuente (no los resultados): se descartan velas abiertas, incoherentes o con mínimo/máximo/cierre fuera de [0,5x; 2x] de la apertura; BTC 4 h perdió 109 velas corruptas (2023-03 a 2023-09) y ETH 2; (b) el preregistro pedía veredicto también para largo+corto pero no definía su línea base: se usó "entrada y sentido al azar" (se calculó después de la primera corrida); (c) la segunda corrida agregó mediana y "R sin la mejor operación"; los p-valores cambian en el cuarto decimal por el orden de los sorteos.

**Estado de señales al 2026-11-09 08:00 UTC:** BTC cierra 74.372; el espejo tiene un **corto ya abierto** (entrada 74.851 a la apertura del 9/11); ETH también (entrada 2.127). Un bot nuevo no debe adoptar esas posiciones: solo entra con señales nuevas.

**Decisión preregistrada para este resultado:** ninguna variante pasa, así que no hay evidencia previa de ventaja; el experimento hacia adelante, en papel, solo se hace como experimento. Dinero real: no.


## Bot HALCÓN (experimento hacia adelante, opción A elegida por el usuario el 2026-11-09)

Código `halcon/halcon_bot.py`, workflow `.github/workflows/halcon.yml`, 9 tests (`halcon/tests/test_halcon_bot.py`). **Estado: construido y probado offline; inactivo hasta que se carguen los secrets.** Dinero ficticio; no existe modo dinero real.

- **Qué hace:** Turtle espejo (reglas del preregistro de la ronda 3) en BTC/USD y ETH/USD, velas de 4 h. **Largos reales** en Alpaca Paper (orden de mercado + stop-limit en el servidor). **Cortos virtuales** en un libro propio (Alpaca no permite cortos en cripto), con las velas reales y los costos del backtest (0,25 % + 0,05 % por lado); sin costo de préstamo ni financiamiento.
- **Capital virtual USD 10.000** (dos mangas de USD 5.000); riesgo **1 % de la manga** (USD 50) por operación; posición ≤ manga. El tamaño sale del libro virtual, no del patrimonio de la cuenta de Alpaca.
- **Verificación:** una repetición vela por vela sobre 2.500 velas de BTC (≈ 14 meses) da **las mismas operaciones, mismas entradas, mismos motivos y mismo R (6 decimales)** que `medir_espejo.py`, largos y cortos. Se probó también el caso de corridas salteadas (salidas tardías y entradas perdidas contadas), que las órdenes reales sean solo compras, y que sin claves no haga nada.
- **Limitación de infraestructura:** GitHub no corre los crons a horario. Cada corrida revisa todas las velas pendientes (las salidas se aplican aunque sean viejas), pero las entradas solo se toman con la última vela. Las señales de entrada vistas tarde se cuentan en `entradas_perdidas` (también en el aviso de estado). Es una medición de la infraestructura, no de la estrategia.
- **Qué guarda:** rama `halcon-estado`, archivo `halcon_estado.json` (libro de operaciones cerradas, posiciones abiertas, capital virtual, entradas perdidas). Avisos por issue (etiqueta `halcon`) y Telegram, en español.
- **Qué tiene que hacer el usuario:** (1) crear una cuenta **Alpaca Paper nueva** solo para HALCÓN (panel de Alpaca → Paper Trading; el límite de cuentas paper por usuario no está verificado); (2) cargar en GitHub → Settings → Secrets and variables → Actions los secrets `HALCON_ALPACA_KEY` y `HALCON_ALPACA_SECRET` (nunca por el chat); (3) correr una vez Actions → HALCON → Run workflow para verificar. Para pedir el estado a Telegram: Run workflow con `resumen` tildado.
- **Cómo se evalúa (fijado antes de operar):** no se saca ninguna conclusión antes de 30 operaciones cerradas por sentido; se compara con el backtest (largo: R neto histórico +2,6 en BTC por unas pocas operaciones enormes y mediana −1,2 R; corto: R neto ≈ 0). Se informa siempre `entradas_perdidas`. Un resultado hacia adelante favorable con pocas operaciones no prueba nada; un resultado desfavorable tampoco. Con ≈ 2,6 operaciones por mes entre BTC y ETH y ambos sentidos, juntar 30 por sentido lleva años. **Dinero real: no antes de eso y solo con autorización explícita del usuario por cada orden.**
