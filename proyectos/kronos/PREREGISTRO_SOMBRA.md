# Kronos en modo sombra — PREREGISTRO

Fecha de redacción: 2026-11-09. Se commitea **antes** de construir el workflow y de correr cualquier pronóstico. Ninguna regla de esta página se cambia después de ver resultados; si se quiere probar otra cosa, es un experimento nuevo con su propio preregistro. Autorización del usuario (2026-11-09): usar Kronos en modo sombra y redactar este preregistro. Evaluación previa: `proyectos/kronos/EVALUACION.md`.

## Pregunta
¿Tiene Kronos capacidad predictiva **hacia adelante** sobre BTC/USD y ETH/USD en velas de 4 h, en la dirección de los próximos 24 h, mejor que el azar y que una regla ingenua de momentum?

## Qué es "modo sombra"
Corre en paralelo, solo lee datos públicos y registra pronósticos. **No opera, no tiene claves de Alpaca, no lee ni escribe el estado de ALBA ni de HALCÓN y no influye en ninguna decisión.** Va en un workflow aparte (`kronos-sombra.yml`) y guarda en una rama propia (`kronos-sombra`).

## Configuración fija
- Código de Kronos: `shiyu-coder/Kronos` **fijado al commit `67b630e67f6a18c9e9be918d9b4337c960db1e9a`** (el revisado el 2026-11-09; MIT). Se clona en cada corrida a ese commit.
- Pesos: `NeoQuasar/Kronos-small` con `NeoQuasar/Kronos-Tokenizer-base`. En la primera corrida se resuelve el hash de revisión de cada uno y se **congela** en el estado; las corridas siguientes cargan exactamente esa revisión y abortan si cambia. Un solo modelo (no se prueban otros tamaños).
- Datos: velas de 4 h de BTC/USD y ETH/USD de la API pública de Alpaca (las mismas de HALCÓN), solo velas cerradas. Ventana de entrada (lookback) = 400 velas; horizonte = 6 velas (24 h).
- Muestreo: T = 1,0; top_k = 0; top_p = 0,9; sample_count = 5; semilla fija por pronóstico = marca de tiempo de la vela mod 2^31. El pronóstico es el **promedio** de las muestras (lo que devuelve `predict`).
- Cadencia: un pronóstico por par y por vela cerrada, con la última vela cerrada al momento de correr. Solo usa velas cerradas: no puede ver el futuro.
- Se registra por pronóstico: par, marca de la vela, cierre de referencia, cierres pronosticados h = 1..6, hora de emisión, modelo y revisiones, semilla, versiones de librerías, segundos de cómputo.

## Definiciones
- Retorno pronosticado a h: `cierre_pronosticado(h) / cierre_referencia − 1`. Retorno realizado a h: `cierre_real(h) / cierre_referencia − 1`.
- **Ancla**: la vela cuyo cierre es 00:00 UTC. Un pronóstico por par y por día, sin superposición entre días (24 h de horizonte).
- Un pronóstico **cuenta** solo si se emitió antes del cierre de la vela siguiente (como máximo 4 h después del cierre de su vela de referencia). **No se rellenan pronósticos atrasados** (backfill): los días sin pronóstico válido quedan como faltantes y se informan.
- Acierto direccional: el signo del retorno pronosticado a 24 h (h = 6) coincide con el del realizado (los realizados exactamente en 0 se excluyen).
- **Línea base de momentum:** el signo del retorno de las 6 velas anteriores a la vela de referencia.
- **Pronóstico operable:** `|retorno pronosticado a 24 h| > 0,6 %` (el costo de ida y vuelta de Alpaca en cripto).

## Evaluación formal (una sola vez)
Se hace cuando haya **al menos 90 días corridos** de operación y **al menos 150 pronósticos ancla válidos** (BTC y ETH juntos). Antes de eso solo hay informes descriptivos (cantidad, faltantes, tiempos, exactitud parcial con la aclaración "no es una conclusión") y ninguna decisión se toma con ellos.

**Pasa si cumple las tres:**
- **A.** Exactitud direccional a 24 h sobre los anclas (BTC+ETH juntos) > 50 %, con prueba binomial exacta de una cola p < 0,05.
- **B.** Esa exactitud supera a la del momentum, en los mismos días, por al menos 2 puntos porcentuales.
- **C.** Entre los pronósticos operables (|retorno pronosticado| > 0,6 %): exactitud ≥ 55 % con al menos 30 casos. Con menos de 30 casos el resultado de C es "no concluyente" y el conjunto **no pasa**.

Se informan siempre, sin entrar en el criterio: resultados por par, correlación de Spearman entre retorno pronosticado y realizado, exactitud a 4 h (h = 1), análisis con todas las velas (superpuestas, con bootstrap por bloques de 6 velas) y calibración por deciles. Son exploratorios.

## Qué se hace con el resultado (decidido antes de verlo)
- **Si pasa A, B y C:** no se integra nada de inmediato. Se escribe un preregistro nuevo para usarlo como filtro (HALCÓN o ALBA) y se necesita la autorización del usuario. Un resultado favorable en 90 días no prueba rentabilidad: los costos y la ejecución se miden aparte.
- **Si no pasa:** se archiva el experimento y se informa. Puede reintentarse solo con un preregistro nuevo.
- **Dinero real:** no se propone con este experimento.

## Aislamiento y seguridad
Código de terceros fijado por commit; workflow aparte, sin secretos del repo en el paso que ejecuta Kronos (las claves de Alpaca no se le entregan nunca; el token de GitHub y los secretos de Telegram solo los usa código propio en pasos separados); sin `pip install` de scripts del repo de terceros; solo se usan su paquete `model/` y sus dependencias de `requirements.txt`; los pesos se leen en formato safetensors.

## Condiciones que invalidan el experimento (se declaran y se reinicia)
Un cambio de revisión de los pesos o del código; más del 30 % de las velas ancla de un mes sin pronóstico válido; un error en los datos de Alpaca que afecte a más de 5 anclas.

## Limitaciones conocidas
- BTC y ETH están muy correlacionados: 150 pronósticos de dos pares no son 150 muestras independientes. Se informan ambos por separado.
- No se conoce el corte de fechas del preentrenamiento de Kronos. No importa para una prueba hacia adelante (el futuro no puede estar en sus datos), pero el modelo pudo haber visto el pasado reciente de estos mismos pares.
- 90 días permiten detectar diferencias grandes de exactitud; una ventaja pequeña requiere meses más.
- La salida es estocástica: la semilla fija hace reproducible cada pronóstico, pero otra semilla daría otro resultado.

## Anexo 1 (2026-11-09, 16:36 UTC): configuración congelada en la primera corrida
Es un registro de reproducibilidad; **no cambia ninguna regla** de este preregistro.
- Pesos `NeoQuasar/Kronos-small`: revisión `901c26c1332695a2a8f243eb2f37243a37bea320`. Tokenizador `NeoQuasar/Kronos-Tokenizer-base`: revisión `0e0117387f39004a9016484a186a908917e22426`. Código de Kronos: `67b630e67f6a18c9e9be918d9b4337c960db1e9a`.
- Librerías de la primera corrida: torch 2.15.0+cpu, pandas 2.2.2, numpy 2.5.4 (Python 3.12). Si una corrida posterior usa otras versiones, se anota en el registro de cada pronóstico (campo `versiones`).
- Primer pronóstico real: vela de las 12:00 UTC del 2026-11-09; cómputo de ≈ 10 s por par en CPU de GitHub.
- Estado y registros en la rama `kronos-sombra` (`pronosticos.jsonl`, `config_congelada.json`).
- Contador: la evaluación formal exige 90 días corridos desde el primer pronóstico válido (2026-11-09) → **no antes del 2027-02-07**, y al menos 150 anclas válidas.
