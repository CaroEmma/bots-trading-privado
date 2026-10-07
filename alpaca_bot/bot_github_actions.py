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

Claves de Alpaca: SOLO via variables de entorno ALPACA_API_KEY /
ALPACA_SECRET_KEY (GitHub Secrets inyectados por el workflow). Nunca
hardcodeadas ni leidas de un archivo .env en este repo.
"""
import json
import math
import os
import time

import config
import estrategia
import brokers

RUTA_ESTADO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estado.json")
RUTA_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.log")


def _log(msg):
    linea = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) + " UTC | " + msg
    print(linea, flush=True)
    with open(RUTA_LOG, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


class Bot:
    def __init__(self, broker, simbolos=None, ruta_estado=RUTA_ESTADO, log=_log):
        self.b = broker
        self.simbolos = simbolos or config.SIMBOLOS
        self.ruta = ruta_estado
        self.log = log
        self.estado = {}
        if os.path.exists(self.ruta):
            self.estado = json.load(open(self.ruta, encoding="utf-8"))

    def _guardar(self):
        json.dump(self.estado, open(self.ruta, "w", encoding="utf-8"), indent=1)

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

    # ---- decision con la ultima vela CERRADA (una vez por vela nueva)
    def procesar_barra(self, simbolo, velas):
        ind = estrategia.calcular(velas)
        if ind is None:
            self.log(f"{simbolo}: historia insuficiente ({len(velas)} velas)")
            return
        st = self.estado.setdefault(simbolo, {})
        if st.get("barra_ts") == ind["ts"]:
            return  # esta vela ya fue evaluada
        barra_previa = st.get("barra_ts")
        st["barra_ts"] = ind["ts"]
        try:
            pos = self.b.posicion(simbolo)
            if pos is not None:
                if st.get("stop") and ind["close"] < ind["min_salida"]:
                    self._vender(simbolo, "ruptura_canal_salida")
                elif not st.get("stop"):
                    self.log(f"{simbolo}: hay posicion NO gestionada por el bot; no la toco")
            elif ind["close"] > ind["max_entrada"]:
                self._comprar(simbolo, ind)
        except Exception:
            # si la orden fallo, esta vela NO queda como evaluada: la proxima corrida (15-30 min) reintenta
            self.estado[simbolo]["barra_ts"] = barra_previa
            raise
        self._guardar()

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

    def _vender(self, simbolo, motivo):
        st = self.estado[simbolo]
        self.b.cancelar_ordenes(simbolo)
        fill = self.b.vender_todo(simbolo)
        entrada = st.get("entrada")
        pnl = (fill / entrada - 1) * 100 if (fill and entrada) else None
        self.log(f"{simbolo}: VENTA ({motivo}) fill={fill} pnl_precio={pnl if pnl is None else round(pnl, 2)}%")
        self.estado[simbolo] = {"barra_ts": st.get("barra_ts")}
        self._guardar()


def ciclo(bot):
    for s in bot.simbolos:
        velas = bot.b.barras(s, config.BARRAS_HISTORIA)
        antes = bot.estado.get(s, {}).get("barra_ts")
        bot.revisar_stop(s, bot.b.precio(s))
        bot.procesar_barra(s, velas)
        if bot.estado.get(s, {}).get("barra_ts") != antes:
            ind = estrategia.calcular(velas)
            bot.log(f"{s}: vela {time.strftime('%Y-%m-%d %H:%M', time.gmtime(ind['ts']/1000))} UTC evaluada | "
                    f"close={ind['close']:.2f} | entrada>{ind['max_entrada']:.2f} | salida<{ind['min_salida']:.2f} | "
                    f"{'EN POSICION' if bot.estado[s].get('stop') else 'sin posicion'}")


if __name__ == "__main__":
    key, secret = brokers.leer_env()
    broker = brokers.AlpacaPaper(key, secret)
    cuenta = broker.cuenta()
    _log(f"Conectado a Alpaca PAPER | cuenta {cuenta['status']} | equity={cuenta['equity']} USD")
    bot = Bot(broker)
    try:
        ciclo(bot)
    except Exception as e:
        _log(f"ERROR en el ciclo: {e}")
        raise  # que el workflow quede en rojo si algo fallo de verdad
