# ALBA — acciones de EE. UU. intradía, 100 % automático, dinero ficticio (Alpaca Paper)

Estado (2026-11-08): **construido y probado offline; todavía no corre en la nube** (faltan 3 pasos del usuario, abajo).
Código: carpeta `alba/` del repo. Workflow: `.github/workflows/alba.yml`. Rama de trabajo: `claude/alba-halcon-bots`.

## Qué hace

Usa las skills de [day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) (copia fijada, commit `3d0f4ef`, MIT, sin modificar, en `alba/vendor/`) encadenadas por un orquestador, sin que nadie intervenga. Cada 5 minutos, de lunes a viernes, en la nube de GitHub (con la compu apagada):

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

- **Datos desde GitHub Actions:** Yahoo puede bloquear o limitar los pedidos desde servidores en la nube (desde la sesión de Claude respondió 429). Por eso existe el modo diagnóstico. Si falla, hay que cambiar la fuente de datos (Alpaca).
- Comportamiento real de Alpaca Paper (órdenes bracket, fills, estados de las patas): probado solo con un broker simulado. La primera semana hay que vigilar los avisos.
- Demora de los crons de GitHub (hasta 15–30 min según guías de terceros) y su desactivación tras 60 días sin actividad (no confirmada en documentación oficial).
- Que la estrategia tenga ventaja estadística: **no se sabe**. Las estadísticas con pocas operaciones no concluyen nada; el informe lo aclara hasta llegar a 30.

## Privacidad (repo público a propósito, por ahora)

El repo es **público**: la rama `alba-estado` muestra operaciones y posiciones (dinero ficticio). El usuario pidió pasarlo a privado, pero según la documentación de GitHub (consultada 2026-11-08) el plan Free incluye **2.000 minutos de Actions por mes solo en repos privados**; en repos públicos no hay tope. Con los bots actuales (cada 15 min, 24/7) más ALBA (cada 5 min en horario de mercado) se pasa de ese tope, y el control 24/7 se cortaría o se cobraría. Además, esta sesión no tiene permiso para cambiar la visibilidad del repo. Decisión pendiente del usuario: dejarlo público mientras todo sea ficticio, y para dinero real usar un repo privado aparte (con plan pago o menos ejecuciones).

## Pruebas

```bash
python3 -m unittest discover -s alba/tests -v
```

23 tests: guardas de seguridad, flujo completo (compra, descartes, límites, cierres por objetivo / stop / horario, informe) y una cadena real entry → exit → timemachine → budget → risk sobre los datos guardados del repo original.
