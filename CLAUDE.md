# CLAUDE.md — memoria del repositorio (CaroEmma/bots-trading-privado)

Leer completo al iniciar. Idioma: español rioplatense técnico-profesional. Respuesta directa primero, razonamiento después.
Regla absoluta del usuario: **nunca inventar ni suponer** datos, valores, normas, fechas ni nombres. Si algo no está verificado, decirlo ("No tengo certeza" / "Este dato no figura en la documentación recibida"). Ante ambigüedad o falta de datos: pedir primero la documentación (lista numerada, marcando OBLIGATORIO / OPCIONAL) y esperar. Si se busca en la web, citar fuente y fecha. Alertar riesgos normativos, de seguridad y de calidad; proponer mejoras.

## Sobre el usuario (solo lo dicho o visible en su perfil)

- Cuenta de GitHub `CaroEmma` es del usuario (lo confirmó). Su Drive/Gmail: ver el contexto de la sesión; no enviar el email a servicios no relacionados.
- Perfil profesional: dirección, coordinación y control de obras de gasoductos (QA/QC, EPC, Excel, presentaciones ejecutivas).
- Tiene skills propias de finanzas: `asesor-financiero-portfolio` (CEDEARs, Balanz / Cocos / Bull Market) y `trading-cripto-intradia`.
- Este repo contiene sus **bots de trading en paper** (Alpaca Turtle BTC/ETH y funding-carry) que corren por cron en GitHub Actions y **commitean a `main` cada 15 min y cada 2 h**. No tocarlos ni pisarlos.

## Proyectos activos

### 1. day-trader-skill — carpeta `proyectos/day-trader-skill/`

Para retomar: el usuario dice **"retomá el proyecto day-trader-skill"**. Leer en este orden, dentro de esa carpeta: `README.md` (estado y pendientes), `PRUEBAS.md` (resultados), `CONVERSACION.md` (historial completo), `FICHA.md` (investigación del repo), `INSTALACION.md`.

Resumen (todo verificado en la sesión del 2026-11-08, salvo lo marcado):
- Origen: reel de Instagram https://www.instagram.com/reel/Dfd1hpIOils/ (cuenta @nexayra, "Claude acaba de matar a los day traders…"). Claude **no puede ver el video** ni acceder a Instagram desde la sesión.
- Repo estudiado: https://github.com/Jakeschincariol/day-trader-skill — Jake Schincariol, MIT, plugin 2.0.0, commit analizado `3d0f4ef` (2026-10-20). Pack de 11 skills de day trading en Python estándar (scanner, news, entry, exit, timemachine, risk, budget, broker, alerts, analyst, pelosi). Mercado: acciones de EE. UU.
- Tests del repo en copia aislada: **315 OK**.
- Prueba 01 en vivo (domingo, mercado cerrado, sesión del 6/11 con `--now`): news, scanner universe (5.936 acciones), entry (disparo a 356,49), exit (stop 351,20, target 361,78), timemachine (target 39,2 % / stop 31,3 % / abierto 29,5 %). Sin broker ni órdenes.
- **Hallazgo:** simulación R promedio +0,070 vs historial real de la misma regla R −0,067 (34 disparos: 12 target / 15 stop / 7 sin definir). No concluyente; no es señal operable.
- No verificado: estrellas/forks/actividad del repo, afirmaciones del README (fin del PDT de USD 25.000 el 4/6/2026, Regulatory Notice 26-10; alpaca-mcp-server 2.4.0), números del ejemplo TSLA de octubre. Skills no probadas: budget, risk, alerts, analyst, pelosi, broker. Stooq no respondió.
- Instalación: las 11 skills se copiaron a `~/.claude/skills/` **solo del contenedor efímero** de la sesión. **Pendiente (lo hace el usuario)**: `/plugin marketplace add Jakeschincariol/day-trader-skill` y `/plugin install day-trader-skill@day-trader-skill`.

Pendientes (el usuario decide): (A) instalar en su Claude real y probar en paper; (B) `budget` + `risk` — **necesita del usuario [OBLIGATORIO] capital de la cuenta y pérdida máxima por operación**; (C) revisión línea por línea de `broker`, `risk`, `budget`; (D) adaptar/combinar con sus skills para CEDEARs; (E) prueba con mercado abierto (lunes 9/11 desde 9:30 ET: `scanner orb`, `entry watch`); (F) solo archivar. Opcional: nombre y email para `sec_user_agent` (SEC, 8-K, `trader-analyst`); no cargar un email sin que el usuario lo pida.

**Bitcoin (pedido del usuario, 2026-11-08): leer `proyectos/day-trader-skill/BITCOIN.md`.** Capital definido por el usuario: USD 100. El pack NO soporta BTC (risk bloquea cripto, entry asume NYSE). Propuesta de Claude pendiente de confirmación: pérdida máx USD 1 por operación, USD 3 por día, 3 operaciones por día, R:R ≥ 1,5, sin apalancamiento. El bot Turtle de Alpaca Paper del repo (cuenta de USD 100.000) lleva 0 operaciones desde 2026-10-07.

Reglas de prueba acordadas: **paper primero**; solo skills de lectura antes de cualquier broker; ninguna orden sin PASS de `trader-risk` + "yes" explícito del usuario + "Allow once"; herramienta de órdenes en "Needs approval"; claves solo en variables de entorno, **nunca en el chat**; no es consejo financiero.

## Dónde está guardado el proyecto

- GitHub: `CaroEmma/bots-trading-privado`, rama `claude/proyecto-day-trader-skill`, carpeta `proyectos/day-trader-skill/` (este `CLAUDE.md` va en la raíz). Se usó una rama aparte para no chocar con los commits del bot en `main`. Si esta rama aún no está fusionada a `main`, este archivo no se carga en sesiones nuevas hasta que se haga el merge.
- Drive del usuario: carpeta "Proyecto day-trader-skill" https://drive.google.com/drive/folders/199NRUSyoTlZbSrWEdp4DWJYPgBsqnA_y
  - IDs de archivos vigentes: README `19vOgkn72dIX1_8Yor6LIwm4ZHp_IRlic`, CONVERSACION `16lqIS1oTaTOw9gsAlmJY_L1ZmNcRwcp8`, PRUEBAS `1A1XYbuKeuiGNOCH7c8CpJn2ddIG9vk99`, FICHA `1mrO1TLVhnWpv28VBWe0WCeEvTOyoUUzd`, INSTALACION `1j-Mk_Q7KZnVbbjcCFgn_qnOwRz8vy61u`.
  - Las versiones viejas de README y CONVERSACION están en la papelera de Drive.
- Aviso: el repo figura como **público** aunque el nombre dice "privado". No subir claves, datos personales ni datos de cuentas.

## Convenciones de trabajo (aprendidas en la sesión)

1. Mantener **GitHub y Drive sincronizados**. La herramienta `update_file` de Drive solo cambia metadatos, **no el contenido**: para actualizar un archivo se crea la versión nueva y se manda la vieja a la papelera.
2. Cada avance se registra en `PRUEBAS.md` (resultados) y en `CONVERSACION.md` (decisiones, qué falló); actualizar también el estado en `README.md` de la carpeta.
3. No hacer push a repos de terceros (el clon de `Jakeschincariol/day-trader-skill` es de solo lectura). El hook de la plataforma puede pedir "commit y push" por archivos sin seguimiento en clones de terceros: no corresponde; mover o borrar el archivo propio del clon.
4. Código de terceros: ejecutarlo solo con autorización explícita del usuario, en copia aislada (scratchpad), con `python3 -I` y directorio de trabajo separado. La política de seguridad de la sesión bloquea correr código externo si el usuario no lo pidió.
5. Entorno de red: para datos de mercado en vivo usar el entorno personal **"day-trader-skill (datos de mercado)"** (`env_01DztpY3mi7yB1zEmgjmWPSs`), hosts permitidos: `query1/query2/feeds.finance.yahoo.com`, `www.nasdaqtrader.com`, `www.sec.gov`, `data.sec.gov`, `stooq.com`, `disclosures-clerk.house.gov`. En el entorno "Default" todos esos hosts dan 403.
6. El token `GH_TOKEN` del entorno daba "inválido": `gh` no sirve; usar `add_repo` y git. No se pudo crear repos nuevos.
7. En clones superficiales, tras crear una rama nueva hay que agregar la referencia remota (`git config --add remote.origin.fetch '+refs/heads/<rama>:refs/remotes/origin/<rama>'`) o el hook marca falsos "commits sin subir".
8. Antes de empezar una tarea compleja nueva, aplicar el protocolo del usuario: listar documentación necesaria (OBLIGATORIO / OPCIONAL) y esperar.
9. Commits con la atribución indicada por la plataforma. No poner nombres de modelo en archivos del repo.

## Historial de cambios de este archivo

- 2026-11-08: creación. Resume el proyecto day-trader-skill, ubicaciones, reglas y pendientes.
