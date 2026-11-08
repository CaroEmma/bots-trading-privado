# Proyecto: day-trader-skill

> Proyecto de evaluación de un pack de 11 skills de Claude para day trading,
> encontrado en un reel de Instagram. Estado: **investigado, tests offline OK
> (315), Prueba 01 en vivo OK en skills de lectura; sin broker ni órdenes**.

## Cómo retomar este proyecto (leer primero)

Decile a Claude: **"retomá el proyecto day-trader-skill"** y pasale una de estas dos fuentes:

- GitHub: `CaroEmma/bots-trading-privado`, carpeta `proyectos/day-trader-skill/`
  (rama `claude/proyecto-day-trader-skill`, hasta que se haga merge a `main`).
- Drive: carpeta "Proyecto day-trader-skill"
  https://drive.google.com/drive/folders/199NRUSyoTlZbSrWEdp4DWJYPgBsqnA_y

Archivos de esta carpeta:

| Archivo | Contenido |
|---|---|
| `README.md` | Este resumen: objetivo, estado, pendientes. |
| `FICHA.md` | Investigación técnica del repo (qué es, verificado / no verificado, riesgos). |
| `INSTALACION.md` | Cómo instalar y probar el pack, con versión fijada (commit). |
| `CONVERSACION.md` | Registro completo de la charla: qué se pidió, qué se hizo, qué falló, decisiones. |
| `PRUEBAS.md` | Resultados de las pruebas (tests, red, cadena entry → exit → timemachine) y hallazgos. |
| `BITCOIN.md` | Pedido de probar en BTC con USD 100: el pack no soporta BTC, costos, ATR medido, margen de pérdida y alertas propuestos, decisiones pendientes. |

Entorno para repetir pruebas en vivo: en Claude Code web elegir el entorno personal **"day-trader-skill (datos de mercado)"** (hosts de solo lectura permitidos: Yahoo, Nasdaq Trader, SEC, House Clerk, Stooq).

## Datos clave

| Dato | Valor |
|---|---|
| Origen | Reel https://www.instagram.com/reel/Dfd1hpIOils/ (cuenta @nexayra, "Claude acaba de matar a los day traders…") |
| Repo investigado | https://github.com/Jakeschincariol/day-trader-skill |
| Autor / licencia | Jake Schincariol / MIT |
| Versión analizada | commit `3d0f4ef` (2026-10-20), plugin 2.0.0 |
| Qué es | 11 skills: scanner, news, entry, exit, timemachine, risk, budget, broker, alerts, analyst, pelosi |
| Mercado | Acciones de EE. UU. (datos Yahoo / SEC / Nasdaq Trader / House Clerk / Stooq / NYSE) |
| Fecha de la investigación | 2026-11-08 |

## Estado

- [x] Repo identificado desde la captura del reel.
- [x] Repo clonado (solo lectura) y analizado: estructura, README, manifiestos, licencia.
- [x] Auditoría estática del código y de los SKILL.md (sin ejecutar).
- [x] Ficha guardada en Drive y en este repo.
- [x] Las 11 skills copiadas a `~/.claude/skills/` **del entorno efímero de la sesión** (ver INSTALACION.md para instalarlas en tu Claude real).
- [ ] Instalación en tu Claude de uso diario (Desktop / Code / claude.ai): **la tiene que hacer el usuario**, comandos en INSTALACION.md.
- [x] Tests del repo corridos en copia aislada (2026-11-08): **315 tests OK**. Ver `PRUEBAS.md`.
- [x] Prueba 01 en vivo de las skills de lectura (news, scanner universe, entry, exit, timemachine): OK. Ver `PRUEBAS.md`.
- [ ] Prueba de budget / risk (necesita capital y pérdida máxima por operación del usuario).
- [ ] Prueba con mercado abierto (scanner orb, entry watch) y prueba en paper con Alpaca.
- [ ] Decisión de adaptación (CEDEARs/BYMA, cripto, integración con skills propias).

## Qué NO está verificado (no asumir)

- Los números del ejemplo TSLA del README (octubre) no se reprodujeron; la prueba propia usó la sesión del 6/11.
- Skills no probadas: budget, risk, alerts, analyst, pelosi, broker; Stooq sin respuesta en la prueba.
- Estrellas, forks, issues y actividad del repo (API de GitHub no disponible para ese repo).
- Afirmaciones externas del README: fin del mínimo PDT de USD 25.000 (FINRA, 4/6/2026, Regulatory Notice 26-10) y versión 2.4.0 del servidor MCP de Alpaca.

## Riesgos principales

1. Fuente de datos no oficial (Yahoo): puede cambiar, limitar o atrasarse.
2. No es consejo financiero; el propio README dice que la mayoría de los day traders pierde dinero. El título del reel es marketing.
3. Hallazgo de la Prueba 01: en TSLA, la simulación da R promedio +0,070, pero el historial real de la misma regla dio R −0,067 (34 disparos). Resultado no concluyente; no tomarlo como señal.
4. Cubre acciones de EE. UU.; nada específico para CEDEARs/BYMA ni cripto.
5. Skill de terceros: SKILL.md revisados por patrones sospechosos (sin hallazgos); revisión línea por línea sigue pendiente.
6. Paper trading siempre primero. Claves del broker solo en variables de entorno, nunca en el chat.

## Pendientes / decisiones del usuario

Opciones de próximo paso (elegir):

- **A.** Instalar en el Claude real y probar en paper.
- **B.** `budget` + `risk` con datos reales del usuario (capital y pérdida máxima por operación).
- **C.** Revisión línea por línea de `broker`, `risk` y `budget`.
- **D.** Adaptar/combinar con las skills propias `asesor-financiero-portfolio` y `trading-cripto-intradia` para CEDEARs.
- **E.** Prueba con mercado abierto (lunes 9/11 desde 9:30 ET).
- **F.** Solo archivar como referencia.

## Nota sobre este repositorio

`CaroEmma/bots-trading-privado` figura como **público** en GitHub aunque el nombre dice "privado". Esta carpeta no contiene claves, datos personales ni credenciales. Si se agrega material sensible en el futuro, conviene pasar el repo a privado antes.
