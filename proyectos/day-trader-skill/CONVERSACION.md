# Registro de la conversación — Proyecto day-trader-skill

Sesión: 2026-11-08. Registro cronológico para no perder contexto.
Convención del proyecto: nada se inventa ni se supone; lo no verificado se marca como tal.

## 1. Pedido inicial

El usuario pasó un reel de Instagram donde aparece un repositorio de GitHub y pidió:
- investigar el repositorio,
- comenzarlo y guardarlo **como un proyecto**,
- y, una vez con la información, él decide cómo se sigue.

Reel: https://www.instagram.com/reel/Dfd1hpIOils/ (cuenta @nexayra, título visible: "Claude acaba de matar a los day traders…", etiqueta "Comentá CLAUDE" y "Cómo se instala").

## 2. Bloqueo y resolución

- Instagram no es accesible desde la sesión (`www.instagram.com` fuera de los dominios de red permitidos) y Claude no puede ver ni escuchar el video. La búsqueda por el código del reel no devolvió ningún repo vinculado.
- Se pidió el nombre del repo, una captura o el caption. El usuario envió una **captura**: se lee `github.com/Jakeschincariol/day-trader-skill`.

## 3. Investigación del repo

Repo clonado en modo lectura (shallow), commit `3d0f4ef` (2026-10-20), único commit visible.

Resumen: pack de 11 skills de Claude para day trading, Python estándar, sin API key, datos públicos gratuitos. MIT. Plugin 2.0.0. Es la v2 de `Jakeschincariol/trader-skill`. Detalle completo en `FICHA.md`.

Auditoría estática realizada (sin ejecutar código):
- Sin `eval`, `exec`, `os.system`, `pickle`, `shell=True`.
- Único `subprocess`: `trader-pelosi/ptr.py:342` (extractor de PDF, argumentos en lista).
- Hosts externos en el código: Yahoo Finance, Nasdaq Trader, SEC EDGAR, House Clerk, Stooq, NYSE.
- SKILL.md revisados con búsqueda de patrones sospechosos (curl, wget, rm -rf, sudo, base64, "ignore previous", etc.): sin coincidencias; solo URLs de fuentes de datos y de Alpaca / IBKR en las guías del broker.

## 4. Cosas que NO se pudieron hacer (y por qué)

| Intento | Resultado |
|---|---|
| Ejecutar los tests del repo (`unittest`) | Primero **bloqueado** por la política de seguridad de la sesión (código externo). Luego, con la autorización del usuario ("lo probemos"), se corrieron en copia aislada: ver sección 12. |
| Metadatos del repo (estrellas, forks, issues) vía `gh api` | 403: API de GitHub no habilitada para ese repo; además el token `GH_TOKEN` de la sesión es inválido. |
| Crear un repo nuevo en GitHub | No posible (token inválido; sin herramienta de creación). |
| Verificar afirmaciones externas del README (fin del PDT, versión del MCP de Alpaca) | No verificado. |

## 5. Conversación sobre dónde guardar

- Se ofrecieron 3 opciones; el usuario eligió **GitHub + Drive** ("para poder llamarla y utilizarla cuando necesitemos").
- Drive: hecho. Carpeta "Proyecto day-trader-skill" con `FICHA.md`.
  https://drive.google.com/drive/folders/199NRUSyoTlZbSrWEdp4DWJYPgBsqnA_y
- GitHub: el único repo con permiso de escritura en la sesión era `CaroEmma/bots-trading-privado`. El usuario confirmó que **la cuenta `CaroEmma` es suya** y pidió subirlo ahí (Claude lo había recomendado).
- Aviso registrado: ese repo figura como **público** pese al nombre. Se subió solo contenido no sensible.

## 6. Hook de la plataforma

Tres veces apareció un aviso del hook de la plataforma. Dos veces por "archivos sin seguimiento" en el clon del repo de un tercero (solo lectura): no se hizo push ahí y la ficha se movió fuera. La tercera fue un falso positivo: la rama ya estaba subida, pero el clon superficial no tenía registrada la referencia remota; se corrigió la configuración local.

## 7. Estado de lo que hay en el repo de CaroEmma

`bots-trading-privado` contiene bots de trading en paper (Alpaca Turtle BTC/ETH y funding-carry) que corren por cron en GitHub Actions y **commitean a `main` cada 15 min y cada 2 h**. Por eso este proyecto se subió en una **rama aparte**, `claude/proyecto-day-trader-skill`, carpeta `proyectos/day-trader-skill/`, para no interferir con el bot. Los workflows son solo por cron (no se disparan por push). Commits `c0ca563` y `c886a8c`.

## 8. Instalación del skill

- Pedido del usuario: instalar el skill en Claude para empezar a probarlo.
- Hecho: las 11 carpetas `trader-*` copiadas a `~/.claude/skills/` **en el contenedor de la sesión**; el sistema las lista como skills disponibles. Eso es efímero: se pierde al cerrar la sesión.
- Pendiente (acción del usuario): instalación permanente en su Claude de uso diario, comandos en `INSTALACION.md`:
  ```
  /plugin marketplace add Jakeschincariol/day-trader-skill
  /plugin install day-trader-skill@day-trader-skill
  ```
- No se ejecutó ninguna skill ni ningún script del pack.

## 9. Decisiones del usuario hasta ahora

1. El reel y el repo son el objeto de estudio; se guarda **como proyecto** (GitHub + Drive).
2. La cuenta `CaroEmma` es suya; autoriza usar `bots-trading-privado`.
3. Quiere el skill instalado para probarlo.
4. Quiere que quede claro como proyecto y que no se pierda nada de la conversación.
5. "Perfecto, lo probemos": autoriza correr tests y probar skills de lectura.

## 10. Preferencias de trabajo del usuario (de su perfil)

Español rioplatense técnico-profesional; respuesta directa primero; no inventar ni suponer datos; pedir documentación faltante antes de ejecutar (obligatoria / opcional); indicar fuente y fecha cuando se busca en la web; alertar riesgos normativos, de seguridad y de calidad; proponer mejoras.

Contexto del usuario relevante al proyecto (de las skills que tiene en su cuenta): usa skills propias `asesor-financiero-portfolio` (CEDEARs, Balanz / Cocos / Bull Market) y `trading-cripto-intradia`; su repo ya tiene bots de trading en paper con Alpaca. Su perfil profesional es de obras de gasoductos; este proyecto es de trading, un área aparte.

## 11. Próximos pasos (el usuario decide)

- A. Instalar en el Claude real y probar en paper.
- B. `budget` + `risk` con capital y pérdida máxima por operación del usuario.
- C. Revisión línea por línea de `broker`, `risk` y `budget`.
- D. Adaptar / combinar con `asesor-financiero-portfolio` y `trading-cripto-intradia`.
- E. Prueba con mercado abierto (lunes 9/11 desde 9:30 ET).
- F. Solo archivar.

## 12. Prueba 01 (2026-11-08, tras "perfecto, lo probemos")

- El usuario autorizó probar. Tests offline en copia aislada: **315 OK** (el primer intento falló por un error mío de invocación con `-t`; no es un fallo del repo).
- Las fuentes de datos estaban bloqueadas por la red de la sesión (403). Se creó, con aprobación del usuario, el entorno personal "day-trader-skill (datos de mercado)" con 8 hosts de solo lectura y la sesión pasó a usarlo.
- Skills probadas: news, scanner `universe`, entry, exit, timemachine. Sin broker ni órdenes. Hoy es domingo: se repitió la sesión del viernes 6/11 con `--now`.
- Resultado y hallazgo principal (simulación levemente positiva vs historial real levemente negativo, R −0,067 en 34 disparos): ver `PRUEBAS.md`.
- Pendiente de datos del usuario para seguir: capital y pérdida máxima por operación (budget / risk); opcional nombre y email para `sec_user_agent`.

## 13. Registro de cambios de este archivo

- 2026-11-08: sección 12 agregada con la Prueba 01; secciones 4, 6, 9 y 11 actualizadas.

- 2026-11-08: creación, tras identificar el repo, guardar en Drive, adjuntar `CaroEmma/bots-trading-privado` e instalar las skills en la sesión.
