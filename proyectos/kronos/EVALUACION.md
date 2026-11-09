# Kronos (shiyu-coder/Kronos) — evaluación del 2026-11-09

Modelo de fundación para velas (K-lines) de mercados financieros. **No se ejecutó ni se instaló nada**: la evaluación se hizo leyendo el código (clon superficial en el commit `67b630e`, 2026-04-13, aislado en `/home/user/shiyu-coder/kronos`) y el README. El paper (arXiv 2508.02739), las fichas de Hugging Face y arXiv **no pudieron leerse**: esos dominios están fuera de la red permitida de la sesión.

## Verificado directamente en el código / README
- Licencia **MIT** (archivo LICENSE, © 2025 ShiYu). Dependencias: torch ≥ 2.0, pandas, numpy, einops, huggingface_hub, safetensors, tqdm, matplotlib; Python 3.10+.
- Modelos: mini 4,1 M (contexto 2048), small 24,7 M (512), base 102,3 M (512) publicados en Hugging Face (`NeoQuasar/...`); **large (499,2 M) no publicado**.
- Uso: `KronosPredictor` recibe un DataFrame OHLC (volumen opcional), marcas de tiempo y `pred_len`; muestrea (parámetros T, top_p, `sample_count`) y promedia: **la salida es estocástica**. El README no declara una frecuencia soportada; el ejemplo usa 5 minutos y los scripts de fine-tuning suponen datos diarios.
- Actividad: 76 commits, **último commit 2026-04-13** (hace ~7 meses), sin releases. El README muestra 47,4 k estrellas y 7,8 k forks (popularidad ≠ rendimiento). Aceptado en AAAI 2026 (anotado en su propio README, 2025-11-10).
- Errores corregidos en abril de 2026: bug de `top_k` en el muestreo, dimensión de batch en el entrenamiento, y **fuga de información en la normalización del dataset de fine-tuning** (commit `79d6d40`: media y desvío se calculaban con toda la ventana, incluida la parte futura).
- **La fuga sigue sin corregir en `finetune_csv/finetune_base_model.py`**, el script de fine-tuning con CSV propios (el que usaríamos con datos de BTC): normaliza con toda la ventana. La **inferencia está limpia**: normaliza solo con el historial recibido (`model/kronos.py`, líneas ~544 y ~629). El efecto real sobre resultados no está medido.
- Los backtests incluidos son de acciones A-share chinas (Qlib), con costos (apertura 0,10 %, cierre 0,15 %), y el propio README dice que son una demostración, "not a production-ready quantitative trading system".
- Cripto: solo una demo web con el pronóstico de BTC/USDT a 24 h. **No hay en el repo un benchmark de cripto ni de resultados netos de costos.**
- Código del modelo y del predictor sin llamadas de red ni `exec`. Los scripts de ejemplo para bajar datos hacen requests y un `pip install` por subprocess (no usarlos). El fine-tuning carga archivos pickle propios (riesgo habitual si el archivo no es de confianza).

## Del paper (solo por resúmenes de terceros, no leído): afirmaciones de los autores
Preentrenado con ~12 mil millones de velas de 45 bolsas; mejora de 93 % en RankIC frente al mejor modelo general de series de tiempo, 9 % menos de MAE en volatilidad y 22 % más de fidelidad en datos sintéticos. **No verificado: intervalos de las velas, rango de fechas del preentrenamiento ni si BTC/ETH de 4 h están incluidos.**

## Conclusión
Hoy **no sirve como señal operativa**; sí sirve como **experimento en modo sombra** (corre en paralelo, registra pronósticos, no influye en ninguna decisión). Razones: (1) sin conocer el corte de fechas del preentrenamiento, cualquier backtest histórico sobre BTC, ETH o acciones puede estar contaminado (el modelo pudo haber visto esos precios); solo es limpia la prueba hacia adelante; (2) RankIC o MAE no son retorno neto de costos (0,6 % ida y vuelta en cripto en Alpaca); (3) la salida es estocástica; (4) mantenimiento esporádico y una fuga sin corregir en el script de fine-tuning con CSV; (5) no está medido que funcione en 4 h de cripto.

Ventaja del modo sombra: un pronóstico por vela da miles de observaciones en meses (la exactitud direccional se puede medir mucho antes que 30 operaciones de una estrategia). Criterio a preregistrar antes de correr: exactitud direccional contra la línea base ingenua y contra el azar, y solo contar los pronósticos con movimiento esperado mayor que el costo.

## Pendientes (decide el usuario)
1. Autorización explícita para ejecutar código de terceros (regla 4 del proyecto), en un workflow aparte y aislado.
2. Preregistro del experimento sombra.
3. Opcional: habilitar `arxiv.org` y `huggingface.co` en el entorno de la sesión para leer el paper completo y las fichas de los modelos.
