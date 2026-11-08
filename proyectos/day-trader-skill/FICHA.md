# Proyecto: day-trader-skill (investigación inicial)

Fecha de la investigación: 2026-11-08
Origen: reel de Instagram https://www.instagram.com/reel/Dfd1hpIOils/ (cuenta @nexayra, "Claude acaba de matar a los day traders…")
Repo: https://github.com/Jakeschincariol/day-trader-skill
Clon local (shallow, 1 commit): /home/user/jakeschincariol/day-trader-skill

## Qué es
Pack de 11 skills de Claude para day trading, en Python estándar (sin pip, sin API key), que leen datos públicos gratuitos.
Autor: Jake Schincariol. Licencia: MIT. Versión 2.0.0 (plugin.json). Es la "v2" de https://github.com/Jakeschincariol/trader-skill (13F, screener, lotes fiscales).

## Datos verificados en el clon
- 1 solo commit visible: 3d0f4ef, 2026-10-20, "The Trader skill v2: 11 day-trading skills" (historial completo no verificado: clon shallow).
- ~14.900 líneas entre skills .py, SKILL.md y tests. Tamaño 2,0 MB (fixtures incluidos).
- Estructura: 11 carpetas `trader-*/` (SKILL.md + script .py), `tests/` (unittest offline con fixtures), `.claude-plugin/` (plugin + marketplace).
- Requiere Python >= 3.8 (según README).

## Las 11 skills
scanner, news, entry, exit, timemachine, risk, budget, broker, alerts, analyst, pelosi.
Flujo: scanner -> news -> entry -> exit -> timemachine -> budget -> risk -> broker; alerts mientras la posición está abierta.

## Fuentes de datos externas (según grep del código)
Yahoo Finance (chart y feeds, endpoint no oficial), Nasdaq Trader (listas de símbolos), SEC EDGAR (www.sec.gov, data.sec.gov), House Clerk (disclosures-clerk.house.gov), Stooq (stooq.com), NYSE (calendario/feriados, www.nyse.com).

## Auditoría estática (solo lectura, sin ejecutar código)
- `eval`, `exec`, `os.system`, `pickle`, `shell=True`: sin coincidencias.
- Único `subprocess`: trader-pelosi/ptr.py:342, llama a un ejecutable de extracción de PDF con argumentos en lista (no shell).
- Las URLs de github.com en los .py no se revisaron una por una (probablemente User-Agent / referencias); pendiente.
- `ticket.py` (broker) según su SKILL.md no habla con ningún broker: genera tickets y registra confirmaciones. La ejecución real pasaría por el MCP de Alpaca, con 3 compuertas (trader-risk PASS, "yes" explícito del usuario, "Allow once" de Claude).

## NO verificado
- No se ejecutaron los tests (bloqueado por la política de seguridad de la sesión al tratarse de código externo). Hay que correrlos en un entorno aislado y con tu autorización.
- Estrellas, forks, issues, actividad: no disponibles (API de GitHub no habilitada para este repo en la sesión).
- Afirmaciones del README que no comprobé contra fuentes: FINRA eliminó el mínimo PDT de USD 25.000 el 4/6/2026 (Regulatory Notice 26-10); versión 2.4.0 del alpaca-mcp-server.
- Que los endpoints de Yahoo funcionen hoy: no probado.
- Resultados del ejemplo TSLA (29,4 % target / 25,5 % stop / 45,1 % abierto): sin reproducir.

## Riesgos / observaciones
1. Fuente de datos no oficial (Yahoo): puede cambiar, limitar o atrasarse.
2. El propio README aclara que no es consejo financiero y que la mayoría de los day traders pierde dinero; el veredicto del ejemplo del Time Machine fue "casi una moneda al aire". El título del reel es marketing.
3. Mercado cubierto: acciones de EE. UU. No hay nada específico para CEDEARs/BYMA ni cripto.
4. Es una skill de terceros: antes de instalarla como plugin conviene revisar cada SKILL.md (instrucciones que Claude seguiría).

## Próximos pasos posibles (a definir por vos)
A. Instalar tal cual en Claude Code (plugin o copiando carpetas a ~/.claude/skills/) y probar en paper.
B. Correr los tests en entorno aislado y reportar resultado.
C. Revisión línea por línea de SKILL.md y .py críticos (broker, risk, budget).
D. Adaptar/combinar con tus skills existentes (asesor-financiero-portfolio, trading-cripto-intradia) para CEDEARs.
E. Solo archivar como referencia.
