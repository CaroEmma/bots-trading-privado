# Bots de trading en papel/demo — corriendo en GitHub Actions

Todo lo de esta carpeta es **paper/demo, sin dinero real**. Reemplaza dos
cosas que antes dependian de que la PC de Enrique estuviera prendida y
conectada (el bot Turtle) o de leer la pantalla a mano (el funding-carry):
ahora ambos corren solos, en los servidores de GitHub, con un cron.

## 1. `alpaca_bot/` — Bot Turtle (Donchian 480h/240h, BTC/USD y ETH/USD)

Mismo bot que corria en `Bot-Intradia-Cripto/alpaca_bot/` via tarea
programada de Windows, adaptado para correr **un solo ciclo por
ejecucion** (no `--loop` infinito): el workflow lo relanza cada 15 min
via cron, y cada corrida revisa el stop y, si cerro una vela 4h nueva,
evalua la señal.

- Cuenta: **Alpaca Paper Trading** (fondos ficticios, `https://paper-api.alpaca.markets`).
- Riesgo: 2% de la "manga" de cada par por operacion, sin apalancar.
- Estado persistente: `alpaca_bot/estado.json` (que vela ya se evaluo
  por simbolo, si hay posicion abierta y su stop). El workflow lo
  commitea al final de cada corrida para no perder el progreso entre
  ejecuciones.
- Log: `alpaca_bot/bot.log` (se va acumulando; el workflow tambien lo
  commitea).

## 2. `funding_carry/` — Tracker de funding-carry (simulacion, datos públicos)

Antes esto se trackeaba a mano leyendo la pantalla de Binance Demo
Trading (`demo.binance.com`) durante las sesiones de chat — nunca pudo
ser automatico porque **Binance Demo Trading no tiene API propia**.

`funding_carry/tracker.py` lo reemplaza con una **simulacion
matematica** que usa solo la API PUBLICA real de Binance (sin login,
sin API key, de solo lectura):

- `GET https://api.binance.com/api/v3/ticker/price` — precio spot
- `GET https://fapi.binance.com/fapi/v1/premiumIndex` — marca y funding actual del perpetuo
- `GET https://fapi.binance.com/fapi/v1/fundingRate` — historial de funding REAL ya liquidado

Simula la misma posicion delta-neutral (spot largo + perpetuo corto,
mismo simbolo) que se abrio a mano en el dry-run del demo el 03/04-oct-2026
para BTC, ETH, XRP, LTC y ADA — las cantidades y precios de apertura
estan hardcodeados en `tracker.py` tomados de
`Bot-FundingCarry-Cripto/dry_run/registro_dry_run.md`. A partir de ahi,
cada corrida suma el funding real liquidado desde la corrida anterior y
revalua PnL del perpetuo y del spot contra el precio actual.

Estado persistente: `funding_carry/estado_funding_carry.json` (funding
acumulado por simbolo, ultima liquidacion ya contada, historial de las
ultimas ~500 corridas). El workflow lo commitea cada vez.

**Limitacion documentada en el propio `tracker.py`:** el funding real
liquidado se multiplica por el nocional DE ENTRADA (cantidad x precio
de apertura), no por el nocional exacto en el momento de cada
liquidacion de 8h, porque la API publica gratuita no da precio de marca
historico con esa granularidad. Es la misma aproximacion que ya usa
`Bot-FundingCarry-Cripto/backtest/motor_backtest_carry.py`. Las tasas de
funding en si son siempre reales (API de Binance), nunca inventadas.

## 3. `informes/`

Carpeta vacia por ahora (placeholder) para informes que se puedan
generar mas adelante a partir del historial acumulado en los JSON de
estado.

## Secrets que hay que cargar en GitHub

Settings → Secrets and variables → Actions → New repository secret:

| Nombre exacto | Para que sirve | Lo necesita |
|---|---|---|
| `ALPACA_API_KEY` | API Key de la cuenta Alpaca **Paper Trading** | `alpaca-turtle.yml` |
| `ALPACA_SECRET_KEY` | Secret Key de la misma cuenta paper | `alpaca-turtle.yml` |

El tracker de funding-carry **no necesita ningun secret** (todo es API
publica de solo lectura).

`GITHUB_TOKEN` (para que el workflow pueda hacer `git commit` / `git push`
de los archivos de estado) es automatico de GitHub Actions, no hay que
crear nada para eso — pero si el repo tiene activado "Require pull
request before merging" o restricciones de branch protection sobre
`main`, el push del workflow puede fallar; en ese caso hay que permitir
que `github-actions[bot]` pushee directo a `main`, o cambiar el target
del commit a una rama propia.

## Como subir esto a GitHub (sin usar git, arrastrando en la web)

1. Entrar al repo `CaroEmma/bots-trading-privado` en github.com.
2. Add file → Upload files.
3. Arrastrar el CONTENIDO de esta carpeta (`bots-trading-privado-para-subir/`)
   tal cual — las carpetas `.github/`, `alpaca_bot/`, `funding_carry/`,
   `informes/` y este `README.md` — a la raiz del repo. GitHub conserva
   la estructura de carpetas al arrastrar.
4. Confirmar el commit ("Commit changes").
5. Ir a Settings → Secrets and variables → Actions y cargar
   `ALPACA_API_KEY` y `ALPACA_SECRET_KEY` (los valores de tu cuenta
   Alpaca Paper Trading).
6. Ir a la pestaña Actions del repo. Deberian aparecer los dos workflows
   ("Alpaca Turtle Bot (paper trading)" y "Funding-Carry Tracker
   (simulacion, datos publicos)"). Correr cada uno una vez a mano con
   "Run workflow" (el boton de `workflow_dispatch`) para confirmar que
   andan antes de dejarlos en automatico con el cron.

## Supuestos y limitaciones que hay que conocer (no se ocultan)

- **`estado.json` del bot Turtle**: se copio tal cual del archivo real
  en `Bot-Intradia-Cripto/alpaca_bot/estado.json` al momento de generar
  esta carpeta (ultima vela evaluada: BTC/USD y ETH/USD con el mismo
  `barra_ts`). Si Enrique sigue corriendo el bot viejo en su PC despues
  de subir esto, van a quedar DOS bots operando la misma cuenta paper en
  paralelo y pueden pisarse el estado — hay que apagar la tarea
  programada de Windows antes de activar el cron de GitHub Actions, o
  usar cuentas paper distintas.
- **Claves de Alpaca**: no se migra el `.env` real (nunca se sube ni se
  lee aca). Enrique tiene que cargar los mismos valores de su
  `Bot-Intradia-Cripto/alpaca_bot/.env` como Secrets de GitHub con los
  NUEVOS nombres `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` (el bot viejo
  usaba `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY`; se renombraron porque
  asi los pidio la tarea, pero son las mismas claves de la cuenta Paper).
- **Apertura del funding-carry**: las cantidades y precios de entrada en
  `tracker.py` vienen de la lectura manual registrada en
  `Bot-FundingCarry-Cripto/dry_run/registro_dry_run.md` ("Datos de
  apertura completados", 03/04-oct-2026). Los timestamps UTC de apertura
  se calcularon a partir de la hora local (ART, UTC-3) anotada en ese
  registro para cada pata; no hay un timestamp exacto en milisegundos
  registrado originalmente, asi que hay un margen de error de segundos
  (irrelevante: el primer funding liquido a las 08:00 UTC del 04-oct,
  varias horas despues de cualquier hora de apertura posible).
- **Funding acumulado "oficial" del dry-run manual (demo) vs. este
  tracker**: el registro manual en `registro_dry_run.md` mide el
  funding que el DEMO de Binance realmente acredito en pantalla, que el
  propio registro documenta como distorsionado (el perpetuo demo cotizo
  hasta +1.5% por encima de su indice en una lectura). Este tracker
  nuevo NO continua esa serie distorsionada: arranca su propio contador
  de funding acumulado en cero y suma unicamente tasas REALES de la API
  publica de Binance desde la apertura. Son dos mediciones del mismo
  dry-run con metodologias distintas; no se deben sumar ni comparar
  directamente sin ajustar.
- No se migra `Bot-Intradia-Cripto/alpaca_bot/replay.py` ni
  `Bot-FundingCarry-Cripto/backtest/` completo: no corren en GitHub
  Actions (son herramientas de analisis local), asi que no estan en esta
  carpeta. Si Enrique los necesita despues, siguen existiendo en los
  proyectos originales.
