# ALBA — acciones de EE. UU. intradía, 100 % automático, dinero ficticio (Alpaca Paper)

Estado (2026-11-08): **en `main`, con claves cargadas y diagnóstico de conexiones OK (Yahoo 200, Nasdaq Trader 200, Alpaca Paper ACTIVE con equity 5.000). Primera sesión real: lunes 2026-11-09.** 33 tests offline.
Código: carpeta `alba/` del repo. Workflow: `.github/workflows/alba.yml`. Rama de trabajo: `claude/alba-halcon-bots`.

## Qué hace

Usa las skills de [day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) (copia fijada, commit `3d0f4ef`, MIT, sin modificar, en `alba/vendor/`) encadenadas por un orquestador, sin que nadie intervenga. De lunes a viernes, en la nube de GitHub (con la compu apagada), en una **sesión larga** que repite este ciclo cada minuto (el escáner, cada 5 min):

| Paso | Skill | Qué hace el bot |
|---|---|---|
| 1 | scanner | Arma el universo del día y busca rupturas del rango de apertura (desde las 9:50 ET). |
| 2 | news | Mira titulares de 24 h del candidato; solo un "halt" lo frena, el resto va en el aviso. |
| 3 | entry | Exige que la señal esté disparada y sea reciente (máx. 10 min). |
| 4 | exit | Fija stop (mitad del rango) y objetivo (2R, valor por defecto del pack). |
| 5 | timemachine | Simula 10.000 sesiones; exige R promedio simulado > 0 (`solo_mc`). |
| 6 | budget | Calcula las acciones enteras que entran en la pérdida máxima. |
| 7 | risk | Si da BLOCK, no se opera. |
| 8 | (broker) | Con PASS manda una orden **bracket** (compra + stop + objetivo en el servidor de Alpaca Paper). |
| 9 | — | A las 15:40 ET cierra todo lo abierto. Avisa cada compra, cada cierre y el informe diario con estadísticas. |

Todo candidato (comprado u omitido, con el motivo) queda en `decisiones.jsonl`; cada operación cerrada en `operaciones.jsonl` (rama `alba-estado`).

## Cómo corre: sesiones largas, no un cron frecuente

**Hallazgo del 2026-11-08:** GitHub no cumple los crons al minuto. El workflow del bot Turtle está programado cada 15 min y en la práctica corre unas 4 veces por día (visto en la pestaña Actions). Un cron cada 5 minutos habría hecho perder señales y el cierre de las 15:40. Por eso cada corrida de ALBA es una **sesión de hasta 340 min** que revisa el mercado cada 60 s hasta el cierre (y espera la apertura si arranca antes). Disparos (UTC, lunes a viernes): 13:05, 13:35 y 14:05 inician la sesión; 18:30 y 19:05 son el relevo (una corrida de GitHub dura como máximo 360 min). Con `concurrency`, un disparo que llega con una sesión en curso queda en espera y arranca cuando esa termina.
- El estado se sube a la rama `alba-estado` cada 10 min y al final.
- Los stops y objetivos de las órdenes bracket son **GTC** (no vencen al cierre): si fallara el cierre de las 15:40, la posición sigue protegida y se cierra "de arrastre" en la apertura siguiente.
- Consumo: ~6,5 h de runner por día hábil. En repos públicos es gratis; en privados el plan Free tiene tope de 2.000 min/mes.
- Si los disparos de GitHub fallaran todos, ALBA no opera ese día (no hay riesgo, solo se pierde la sesión). Corrida manual: Actions → ALBA → Run workflow (opciones: solo diagnóstico, o un solo ciclo).

## Riesgo de condiciones de uso (no resuelto)

Las sesiones de ALBA (hasta 340 min, casi 6,5 h por día hábil) son un uso intensivo de GitHub Actions para algo que no es CI/CD. Versiones anteriores de las condiciones de GitHub mencionan "serverless computing" entre los usos no previstos; no pude confirmar el texto vigente (consultado 2026-11-08, ver `proyectos/halcon/README.md`). Si GitHub lo considerara abuso podría cortar jobs o restringir Actions en el repo. ALBA necesita sesiones largas porque el cron de GitHub no es puntual. Alternativas si se quiere eliminar el riesgo: un servidor propio o un servicio de ejecución continua.

## Seguridad

- Solo `paper-api.alpaca.markets`; cualquier otra URL lanza error (test incluido). El modo real **no está implementado**.
- Claves solo como GitHub Secrets. Nunca en el chat ni en archivos.
- El "yes" humano del pack se reemplaza por la automatización **únicamente en paper**, por pedido del usuario (2026-11-08). Cada registro del bot lleva `auto_paper: true` y nunca se escribe un `reply` inventado.
- **Dinero real:** cuando se decida pasar, hay que pedirle autorización al usuario por cada orden. Eso requiere código nuevo y aprobación explícita antes.
- Los tests corren antes de cada ciclo; si fallan, no se opera.

## Qué tiene que hacer el usuario (3 pasos)

1. Crear una cuenta **Alpaca Paper nueva** solo para ALBA (en el panel de Alpaca → Paper Trading; según un hilo del foro de Alpaca el límite es 3 cuentas paper por usuario; no verificado, confirmarlo en el panel) y sacar sus claves.
2. En GitHub → repo → Settings → Secrets and variables → Actions, cargar `ALBA_ALPACA_KEY` y `ALBA_ALPACA_SECRET`. Opcional para avisos al celular: `ALBA_TELEGRAM_TOKEN` y `ALBA_TELEGRAM_CHAT`.
3. Decir "mergeá a main" (los crons de GitHub solo corren desde la rama principal). Después, correr una vez a mano **Actions → ALBA → Run workflow → diagnóstico** para comprobar las conexiones.

Hasta que existan los secrets, el workflow termina sin hacer nada.

## Seguimiento semanal (rutina de Claude)

Rutina `trig_01Qjx3KMRYZV9CsK8aDBtwYj` ("ALBA - evaluación semanal de resultados"): los **viernes 17:47 hora de Nueva York** (primera: 2026-11-13) abre una sesión nueva de Claude, lee la rama `alba-estado`, calcula las métricas y manda una notificación push. Es solo lectura. Si todavía no hay datos, informa qué pasos faltan. Usa la cuota de Claude del usuario. Se pausa o borra desde la lista de rutinas de claude.ai o pidiéndoselo a Claude.

## Avisos

Canal por defecto: un **issue** en el repo por cada compra / cierre / informe, con mención a `@CaroEmma`; GitHub lo manda por correo y a la app móvil si las notificaciones están activas. Es opcional sumar Telegram. Siempre queda también el resumen en la pestaña Actions.

## Supuestos que puse yo (cambiarlos es editar `alba/config.json`)

| Supuesto | Valor | Por qué / riesgo |
|---|---|---|
| Capital virtual y límites | **USD 5.000 (confirmado por el usuario el 2026-11-08)**, pérdida máx. USD 50 por operación y USD 150 por día, 3 operaciones por día | Son los valores de ejemplo del pack. **Con USD 100 y USD 1 de pérdida máxima el pack no compra ni una acción de TSLA** (riesgo de USD 5,29 por acción): casi nunca operaría. El capital de ALBA lo define el usuario. |
| Filtro de la máquina del tiempo | R simulado > 0 (`solo_mc`) | En la Prueba 01 el historial real de TSLA dio R −0,067 mientras la simulación daba +0,070. Se registra el R histórico de cada candidato para medir después si conviene exigirlo (`mc_y_historia`). |
| Orden de candidatos | Menor distancia a la ruptura primero | Criterio mío, sin respaldo estadístico. |
| Una sola posición abierta a la vez | `max_posiciones_abiertas: 1` | Simplifica el control del riesgo diario. |

## Qué NO está verificado

- **Datos desde GitHub Actions:** el diagnóstico del 2026-11-08 dio Yahoo (endpoint chart) HTTP 200 y Nasdaq Trader HTTP 200, pero fue un solo pedido suelto: **no está verificado** que Yahoo aguante el volumen del escáner ORB ni que acepte la identificación de las skills. Si empieza a dar 429, hay que espaciar los pedidos o cambiar la fuente (Alpaca).
- Comportamiento real de Alpaca Paper (órdenes bracket, fills, estados de las patas): probado solo con un broker simulado. La primera semana hay que vigilar los avisos.
- Demora de los crons de GitHub (hasta 15–30 min según guías de terceros) y su desactivación tras 60 días sin actividad (no confirmada en documentación oficial).
- Que la estrategia tenga ventaja estadística: **no se sabe**. Las estadísticas con pocas operaciones no concluyen nada; el informe lo aclara hasta llegar a 30.

## Privacidad (repo público a propósito, por ahora)

El repo es **público**: la rama `alba-estado` muestra operaciones y posiciones (dinero ficticio). El usuario pidió pasarlo a privado, pero según la documentación de GitHub (consultada 2026-11-08) el plan Free incluye **2.000 minutos de Actions por mes solo en repos privados**; en repos públicos no hay tope. Con los bots actuales (cada 15 min, 24/7) más ALBA (cada 5 min en horario de mercado) se pasa de ese tope, y el control 24/7 se cortaría o se cobraría. Además, esta sesión no tiene permiso para cambiar la visibilidad del repo. Decisión pendiente del usuario: dejarlo público mientras todo sea ficticio, y para dinero real usar un repo privado aparte (con plan pago o menos ejecuciones).

## Pruebas

```bash
python3 -m unittest discover -s alba/tests -v
```

33 tests: guardas de seguridad, flujo completo (compra, descartes, límites, cierres por objetivo / stop / horario, informe) y sesión larga (espera de apertura, tope de duración, errores pasajeros, informe tras el cierre), publicación real del estado con git contra un remoto local, y una cadena real entry → exit → timemachine → budget → risk sobre los datos guardados del repo original (esta última solo corre si están los fixtures del repo original).
