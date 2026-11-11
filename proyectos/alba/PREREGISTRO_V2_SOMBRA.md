# ALBA v2 en modo sombra — preregistro (2026-11-11)

Escrito **antes** del código y de cualquier dato de v2. Pedido del usuario: "sombra". Objetivo: saber con datos si agregar contexto
(volumen relativo, mercado general, catalizadores de noticias) mejora la ruptura del rango de apertura que hoy opera ALBA (v1).
**v2 no opera ni modifica nada de v1**: solo registra y mide.

## 1. Qué se registra (población)
Todo **hit nuevo del escáner ORB** (primera vez que se ve el símbolo en el día) cuya señal tenga **10 minutos o menos** de edad al
detectarlo (misma regla de frescura que v1), precio ≥ USD 5, durante la ventana de entradas de v1 (09:50 a 15:30 ET). Se registra
**aunque v1 no lo evalúe** (v1 evalúa como máximo 3 por ciclo y opera 1 posición a la vez). Tope: 15 hits nuevos por escaneo, en el
orden de v1 (menor `pct_over` primero); lo que exceda el tope no se registra y se cuenta como "truncado".

## 2. Rasgos que se guardan (valores crudos, sin interpretar)
1. `rvol`: volumen acumulado del día hasta la barra de la señal ÷ promedio del volumen acumulado hasta la misma hora en las sesiones
   previas disponibles (hasta 10), barras de 5 min de Yahoo.
2. `gap_pct`: apertura de hoy vs cierre de ayer.
3. `spy_pct`: variación de SPY desde el cierre de ayer hasta la barra de la señal. `spy_sobre_media`: cierre diario de ayer de SPY vs
   media de los cierres de las sesiones previas disponibles.
4. Noticias de 24 h del símbolo (skill news, sin SEC): lista de etiquetas y cantidad de titulares.
5. `pct_over`, rango de apertura en % del precio, hora de la señal.

## 3. Regla v2 (fijada ahora, no se cambia con los datos)
**PASA** si `rvol` ≥ 1,5 **y** `spy_pct` ≥ 0 **y** ninguna etiqueta de noticias en {earnings, halt, deal, legal, regulatory}.
**DESCARTA** si falta alguna condición. **SIN DATO** si no se pudo calcular `rvol` o `spy_pct` (se reportan aparte y no entran al test).
Los umbrales (1,5 y 0) los elegí yo: **no tienen respaldo estadístico**; por eso se prueban acá y no se asumen.
Limitación conocida: el detector de balances usa solo titulares (etiqueta earnings); un balance que no aparezca en titulares no se detecta.
No hay filtro por SEC porque exige identificación (`sec_user_agent`) que el usuario no cargó.

## 4. Resultado simulado de cada hit (misma regla que v1)
Entrada = precio del hit; stop = mitad del rango de apertura; objetivo = entrada + 2 × (entrada − stop). Se recorren las barras de 5 min
siguientes a la señal: si en una barra se tocan stop y objetivo, **cuenta el stop** (criterio conservador); si no se toca ninguno, se sale al
cierre de la última barra anterior a las 15:40 ET. R = (salida − entrada) ÷ (entrada − stop). Sin comisiones ni deslizamiento (Alpaca Paper no
cobra comisión de acciones; el deslizamiento real puede empeorar los resultados). Se resuelve al final del día con las barras del día.

## 5. Evaluación
- **Prueba principal (única):** diferencia de R promedio entre PASA y DESCARTA sobre todos los hits registrados; test de permutación de
  etiquetas (10.000 mezclas, una cola, H1: PASA > DESCARTA). Todo lo demás (cada rasgo por separado, v1 vs v2, subgrupos) es exploratorio y
  **no decide nada**.
- **Datos mínimos para evaluar:** ≥ 30 hits PASA, ≥ 30 hits DESCARTA y ≥ 10 días de mercado. Antes, solo conteos descriptivos y **ninguna decisión**.
- **Criterio para que v2 reemplace el filtro de v1:** diferencia > 0 con p < 0,05 **y** R promedio de PASA > 0 **y** el signo de la
  diferencia se mantiene en la mitad temprana y la tardía de los días. Si no se cumple: v2 no se adopta (no se cambia ALBA por esta vía).
- Se reportan también: n, tasa de acierto, R promedio y factor de beneficio por grupo, y el R de los hits que v1 realmente compró.

## 6. Riesgos y límites
- Los hits de un mismo día están correlacionados (mismo mercado): la muestra efectiva se acerca más a los días que a los hits.
- Datos de Yahoo no oficiales, con huecos y demoras; si Yahoo limita (429) el registro de v2 se interrumpe en ese escaneo y se anota; **v1 tiene prioridad**.
- Una racha corta no prueba nada, en ningún sentido.
- Sin evidencia previa de que estos filtros mejoren la ruptura del rango de apertura: es una hipótesis a probar, no un hecho.

## 7. Dónde queda
Rama `alba-estado`: `sombra.jsonl` (hits y rasgos) y `sombra_resultados.jsonl` (resultado simulado por hit). Código: `alba/sombra.py`.
