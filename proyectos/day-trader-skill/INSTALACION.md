# Instalación y prueba del pack day-trader-skill

Versión fijada: commit `3d0f4ef` (2026-10-20), plugin 2.0.0.
Repo origen: https://github.com/Jakeschincariol/day-trader-skill (MIT).

> Importante: en la sesión de investigación las 11 skills se copiaron a
> `~/.claude/skills/` **del contenedor de esa sesión**, que es efímero. Eso
> sirve para probar dentro de esa sesión, no queda en tu Claude de uso diario.
> Para instalarlas de forma permanente, usá una de las opciones de abajo.

## Opción 1 — Plugin en Claude Code (recomendada)

```
/plugin marketplace add Jakeschincariol/day-trader-skill
/plugin install day-trader-skill@day-trader-skill
```

Las skills quedan con prefijo: `/day-trader-skill:trader-scanner`, etc.

## Opción 2 — Copiar carpetas (comandos sin prefijo, `/trader-scanner`)

```bash
git clone https://github.com/Jakeschincariol/day-trader-skill.git
cd day-trader-skill && git checkout 3d0f4ef
cp -r trader-* ~/.claude/skills/
```

Para que valga solo en un proyecto, copiar a `.claude/skills/` de ese proyecto.

## Opción 3 — Pegar en un chat de Claude (según el README del repo)

```
https://github.com/Jakeschincariol/day-trader-skill

install skill
```

Alternativa sin instalar: pegar un `SKILL.md` al inicio del chat y funciona como modo. Se pierden las herramientas Python; queda solo el método.

## Requisitos

- Python 3.8 o superior. No hay nada que instalar con pip (según README).
- Las herramientas SEC (news con 8-K y analyst) piden identificarse: poner nombre y email en `trader/config.json` (`"sec_user_agent": "Tu Nombre tu@email"`) o en la variable `SEC_USER_AGENT`.
- Todo se escribe en una carpeta `trader/` dentro del proyecto donde se use.

## Reglas de prueba (acordadas en este proyecto)

1. **Paper primero**, siempre. `"paper": true` es el valor por defecto en `trader-budget/config.example.json`.
2. Ninguna orden sale sin: PASS de `trader-risk` para esa orden, un "yes" explícito del usuario y el "Allow once" de Claude.
3. En Claude, dejar la herramienta de órdenes del broker en "Needs approval", nunca "Always allow".
4. Las claves del broker van en variables de entorno o en el archivo de configuración local, **nunca en el chat**.
5. Probar primero solo las skills de lectura: `trader-scanner`, `trader-news`, `trader-entry`, `trader-exit`, `trader-timemachine`. `trader-broker` se conecta al final y solo en paper.

## Verificación sugerida antes del primer uso real

```bash
python3 -m unittest discover -s tests -v
```

Los tests corren offline con fixtures. **No se ejecutaron en la sesión de investigación**: la política de seguridad bloqueó correr código externo sin autorización. Correrlos en un entorno aislado y reportar el resultado en `CONVERSACION.md`.

## Prueba mínima sugerida (solo lectura de mercado, sin broker)

```bash
python3 trader-scanner/scan.py universe
python3 trader-news/news.py --tickers TSLA --hours 12
python3 trader-entry/entry.py check TSLA --setup orb
```

Requieren acceso de red a Yahoo Finance, Nasdaq Trader y SEC. Comprobar que respondan hoy: no está verificado.
