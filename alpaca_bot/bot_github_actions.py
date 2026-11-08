"""
Bot Turtle LONG-ONLY (4h, BTC/USD y ETH/USD) para Alpaca PAPER.
Version para GitHub Actions: UN SOLO CICLO (no --loop infinito). El
cron del workflow .github/workflows/alpaca-turtle.yml se encarga de
relanzar este script cada 15-30 min; cada corrida hace su trabajo y
termina. Las ordenes SOLO van a paper-api.alpaca.markets (fondos
ficticios) - ver config.py.

Reglas (identicas al backtest validado y a la version original que
corria en la PC de Enrique via tarea programada):
  COMPRA : cierre de la vela 4h cerrada > maximo de las 120 velas previas (20 dias)
  VENTA  : cierre < minimo de las 60 velas previas (10 dias)  O  precio <= stop (entrada - 2xATR14)
  TAMANO : arriesga 2% de la manga del par hasta el stop (manga = patrimonio / n pares), sin apalancar

MEJORA 2026-11-08 (a pedido del usuario; la estrategia y sus parametros NO cambian): GitHub no cumple el cron "cada 15 min"
(en la practica corre ~4 veces por dia), asi que entre dos corridas pueden cerrar varias velas de 4 h. Antes solo se evaluaba
la ULTIMA vela cerrada y una salida por canal en una vela intermedia se perdia. Ahora cada corrida revisa TODAS las velas
cerradas desde la ultima evaluada, en orden:
  - las SALIDAS (canal de salida) se aplican aunque la vela sea vieja (se registran como "tardia");
  - las ENTRADAS solo se toman con la ULTIMA vela cerrada (entrar por una senal vieja seria otro trade);
  - en la primera corrida (sin estado) solo se evalua la ultima vela, sin operar sobre historia.
Ademas avisa cada compra / venta por issue del repo (si hay GITHUB_TOKEN).

Claves de Alpaca: SOLO via variables de entorno ALPACA_API_KEY /
ALPACA_SECRET_KEY (GitHub Secrets inyectados por el workflow). Nunca
hardcodeadas ni leidas de un archivo .env en este repo.
"""
import json
import math
import os
import sys
import time

import config
import estrategia
import brokers

MAX_PENDIENTES = 24    # velas de 4 h (4 dias) como maximo por corrida y par


def _hora(ts_ms):
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ts_ms / 1000))


RUTA_ESTADO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estado.json")
RUTA_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.log")


def _log(msg):
    linea = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) + " UTC | " + msg
    print(linea, flush=True)
    with open(RUTA_LOG, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


class Bot:
    def __init__(self, broker, simbolos=None, ruta_estado=RUTA_ESTADO, log=_log, aviso=None):
        self.b = broker
        self.aviso = aviso              # callable(titulo, cuerpo) o None; nunca debe romper el ciclo
        self.simbolos = simbolos or config.SIMBOLOS
        self.ruta = ruta_estado
        self.log = log
        self.estado = {}
        if os.path.exists(self.ruta):
            with open(self.ruta, encoding="utf-8") as f:
                self.estado = json.load(f)

    def _guardar(self):
        with open(self.ruta, "w", encoding="utf-8") as f:
            json.dump(self.estado, f, indent=1)

    def _avisar(self, titulo, cuerpo):
        if not self.aviso:
            return
        try:
            self.aviso(titulo, cuerpo)
        except Exception as e:  # noqa: BLE001 - un aviso nunca debe romper una orden ya enviada
            self.log("(aviso no enviado: %s)" % e)

    # ---- stop intra-vela
    def revisar_stop(self, simbolo, precio_chequeo):
        st = self.estado.get(simbolo, {})
        if not st.get("stop"):
            return
        if self.b.posicion(simbolo) is None:
            self.log(f"{simbolo}: posicion ya cerrada por el stop del servidor; limpio estado")
            self.estado[simbolo] = {"barra_ts": st.get("barra_ts")}
            self._guardar()
            return
        if precio_chequeo <= st["stop"]:
            self._vender(simbolo, "stop_atr")

    # ---- decision sobre TODAS las velas cerradas pendientes (la ultima puede abrir entradas; las viejas solo salidas)
    def procesar_pendientes(self, simbolo, velas):
        st = self.estado.setdefault(simbolo, {})
        ultimo = st.get("barra_ts")
        if ultimo is None:
            indices = [len(velas) - 1]          # primera corrida: solo la ultima vela, sin operar sobre historia
        else:
            indices = [k for k, v in enumerate(velas) if v.ts > ultimo][-MAX_PENDIENTES:]
        for k in indices:
            es_ultima = k == len(velas) - 1
            ventana = velas[max(0, k - config.BARRAS_HISTORIA + 1):k + 1]
            ind = estrategia.calcular(ventana)
            if ind is None:
                if es_ultima:
                    self.log(f"{simbolo}: historia insuficiente ({len(velas)} velas)")
                self.estado.setdefault(simbolo, {})["barra_ts"] = velas[k].ts
                continue
            self._evaluar(simbolo, ind, entrada_permitida=es_ultima, tardia=not es_ultima)
        self._guardar()

    def procesar_barra(self, simbolo, velas):   # compatibilidad con el nombre anterior
        self.procesar_pendientes(simbolo, velas)

    def _evaluar(self, simbolo, ind, entrada_permitida, tardia):
        st = self.estado.setdefault(simbolo, {})
        barra_previa = st.get("barra_ts")
        st["barra_ts"] = ind["ts"]
        try:
            pos = self.b.posicion(simbolo)
            if pos is not None:
                if st.get("stop") and ind["close"] < ind["min_salida"]:
                    self._vender(simbolo, "ruptura_canal_salida" + (" (TARDIA: vela %s)" % _hora(ind["ts"]) if tardia else ""))
                elif not st.get("stop"):
                    self.log(f"{simbolo}: hay posicion NO gestionada por el bot; no la toco")
            elif entrada_permitida and ind["close"] > ind["max_entrada"]:
                self._comprar(simbolo, ind)
        except Exception:
            # si la orden fallo, esta vela NO queda como evaluada: la proxima corrida reintenta
            self.estado[simbolo]["barra_ts"] = barra_previa
            raise

    def _comprar(self, simbolo, ind):
        precio = self.b.precio(simbolo)
        manga = self.b.equity() / len(self.simbolos)
        dist = config.ATR_MULT_STOP * ind["atr"]
        qty = min(manga / precio, config.RIESGO_POR_OPERACION * manga / dist)
        qty = math.floor(qty * 1e6) / 1e6
        if qty * precio < config.NOCIONAL_MINIMO_USD:
            self.log(f"{simbolo}: senal de compra pero nocional {qty*precio:.2f} USD < minimo; omito")
            return
        try:
            fill = self.b.comprar(simbolo, qty, precio)
        except Exception as e:
            self.b.cancelar_ordenes(simbolo)
            pos = self.b.posicion(simbolo)
            if pos is None:
                raise
            self.log(f"{simbolo}: AVISO la compra devolvio error ({e}) pero hay posicion; la adopto")
            fill = pos["avg"]
        pos = self.b.posicion(simbolo)
        qty_real = pos["qty"] if pos else qty
        stop = fill - dist
        st = self.estado[simbolo]
        st.update(stop=stop, entrada=fill, qty=qty_real, entrada_ts=int(time.time() * 1000))
        try:
            self.b.proteger(simbolo, stop, qty_real)
        except Exception as e:
            self.log(f"{simbolo}: AVISO no pude colocar el stop-limit en el servidor: {e}")
        self.log(f"{simbolo}: COMPRA qty={qty_real:.6f} fill={fill:.2f} stop={stop:.2f} "
                 f"(ATR={ind['atr']:.2f}, riesgo={config.RIESGO_POR_OPERACION*100:.1f}% de manga {manga:.0f} USD)")
        self._avisar(f"TURTLE | COMPRA {simbolo} @ {fill:.2f}",
                     f"**{simbolo}** — compra {qty_real:.6f} a {fill:.2f} (Alpaca Paper, dinero ficticio)\n\n"
                     f"- Stop: {stop:.2f} (2 x ATR = {config.ATR_MULT_STOP * ind['atr']:.2f})\n"
                     f"- Señal: cierre {ind['close']:.2f} > máximo de 20 días {ind['max_entrada']:.2f}\n"
                     f"- Sale por: cierre < {ind['min_salida']:.2f} (mínimo de 10 días) o precio <= stop")

    def _vender(self, simbolo, motivo):
        st = self.estado[simbolo]
        self.b.cancelar_ordenes(simbolo)
        fill = self.b.vender_todo(simbolo)
        entrada = st.get("entrada")
        pnl = (fill / entrada - 1) * 100 if (fill and entrada) else None
        self.log(f"{simbolo}: VENTA ({motivo}) fill={fill} pnl_precio={pnl if pnl is None else round(pnl, 2)}%")
        self._avisar(f"TURTLE | VENTA {simbolo} ({motivo.split(' ')[0]})" + (f" {pnl:+.2f}%" if pnl is not None else ""),
                     f"**{simbolo}** — vendida a {fill} (entrada {entrada})\n\n- Motivo: {motivo}\n"
                     f"- Resultado sobre el precio: {'n/d' if pnl is None else '%+.2f%%' % pnl} (sin costos)\n\n"
                     f"_Alpaca Paper, dinero ficticio._")
        self.estado[simbolo] = {"barra_ts": st.get("barra_ts")}
        self._guardar()


def ciclo(bot):
    for s in bot.simbolos:
        velas = bot.b.barras(s, config.BARRAS_HISTORIA)
        antes = bot.estado.get(s, {}).get("barra_ts")
        bot.revisar_stop(s, bot.b.precio(s))
        bot.procesar_pendientes(s, velas)
        if bot.estado.get(s, {}).get("barra_ts") != antes:
            ind = estrategia.calcular(velas)
            bot.log(f"{s}: vela {time.strftime('%Y-%m-%d %H:%M', time.gmtime(ind['ts']/1000))} UTC evaluada | "
                    f"close={ind['close']:.2f} | entrada>{ind['max_entrada']:.2f} | salida<{ind['min_salida']:.2f} | "
                    f"{'EN POSICION' if bot.estado[s].get('stop') else 'sin posicion'}")


def _crear_aviso():
    """Avisos por issue del repo con el Notificador de ALBA (misma convencion). None si no esta disponible."""
    try:
        aqui = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, os.path.join(os.path.dirname(aqui), "alba"))
        from notificar import Notificador
        cfg_alba = json.load(open(os.path.join(os.path.dirname(aqui), "alba", "config.json"), encoding="utf-8"))
        n = Notificador(mencionar=cfg_alba.get("mencionar"), etiqueta="turtle")
        return n.avisar
    except Exception as e:  # noqa: BLE001
        print("(avisos desactivados: %s)" % e)
        return None


if __name__ == "__main__":
    key, secret = brokers.leer_env()
    broker = brokers.AlpacaPaper(key, secret)
    cuenta = broker.cuenta()
    _log(f"Conectado a Alpaca PAPER | cuenta {cuenta['status']} | equity={cuenta['equity']} USD")
    bot = Bot(broker, aviso=_crear_aviso())
    try:
        ciclo(bot)
    except Exception as e:
        _log(f"ERROR en el ciclo: {e}")
        raise  # que el workflow quede en rojo si algo fallo de verdad
