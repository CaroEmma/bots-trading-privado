#!/usr/bin/env python3
"""HALCÓN: Turtle espejo largo/corto, velas de 4 h, BTC/USD y ETH/USD. EXPERIMENTO HACIA ADELANTE en papel (dinero ficticio).

Reglas = las preregistradas en proyectos/halcon/PREREGISTRO_RONDA3.md y medidas en halcon/medir_espejo.py (no se ajusta nada):
  LARGO : entra si cierre > máx. de las 120 velas previas; sale si cierre < mín. de las 60 previas o stop = fill - 2 ATR(14).
  CORTO : entra si cierre < mín. de las 120 previas; sale si cierre > máx. de las 60 previas o stop = fill + 2 ATR(14).
  Tamaño: 1 % de la manga del par (capital virtual USD 10.000 / 2 pares) hasta el stop, sin apalancar (posición <= manga).
  Costos simulados en el libro, iguales a los del backtest: comisión 0,25 % + slippage 0,05 % por lado.
LARGOS = órdenes REALES en Alpaca Paper (con stop-limit en el servidor). CORTOS = VIRTUALES (Alpaca no permite cortos en cripto):
se anotan en un libro propio con las velas reales. Los cortos NO tienen costo de préstamo ni financiamiento.

Cada corrida (cron de GitHub Actions, no puntual) revisa TODAS las velas cerradas pendientes: las salidas se aplican aunque
la vela sea vieja; las entradas solo con la última vela (entrar por una señal vieja sería otra operación). Las señales de entrada
que se ven tarde se cuentan como "entradas perdidas": es información sobre la infraestructura, no sobre la estrategia.
Solo paper: las órdenes van únicamente a paper-api.alpaca.markets (alpaca_bot/config.py). No hay modo dinero real.
"""
import argparse
import json
import math
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(RAIZ, "alba"))
sys.path.insert(0, os.path.join(RAIZ, "alpaca_bot"))

import brokers  # noqa: E402  (alpaca_bot: velas públicas de Alpaca y cliente paper)
import formato  # noqa: E402
from indicadores import atr as atr_wilder  # noqa: E402
from notificar import Notificador  # noqa: E402
from velas import Vela  # noqa: E402

SIMBOLOS = ["BTC/USD", "ETH/USD"]
NE, NX, ATR_P, STOP_MULT = 120, 60, 14, 2.0
RIESGO, CAPITAL = 0.01, 10_000.0
FEE, SLIP = 0.0025, 0.0005
VENTANA, MAX_PEND, NOCIONAL_MIN = 300, 24, 10.0
NOMBRE_ESTADO = "halcon_estado.json"


def calcular(velas):
    """Señales sobre velas CERRADAS (la última es la más reciente). None si falta historia."""
    if len(velas) < NE + ATR_P + 1:
        return None
    h, l, c = [v.high for v in velas], [v.low for v in velas], [v.close for v in velas]
    return {"ts": velas[-1].ts, "close": c[-1], "high": h[-1], "low": l[-1], "atr": atr_wilder(h, l, c, ATR_P)[-1],
            "hi_e": max(h[-NE - 1:-1]), "lo_e": min(l[-NE - 1:-1]), "hi_x": max(h[-NX - 1:-1]), "lo_x": min(l[-NX - 1:-1])}


def _hora(ts_ms):
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ts_ms / 1000))


class AlpacaHalcon(brokers.AlpacaPaper):
    """Cliente paper + lectura del fill de la última venta (para registrar el stop que ejecutó el servidor)."""

    def fill_ultima_venta(self, simbolo):
        ords = self._t("GET", "/v2/orders", params={"status": "closed", "symbols": simbolo, "limit": 10, "direction": "desc"}) or []
        for o in ords:
            if o.get("side") == "sell" and o.get("status") == "filled" and o.get("filled_avg_price"):
                return float(o["filled_avg_price"])
        return None


class DatosAlpaca:
    """Velas de 4 h cerradas y último precio (datos públicos de Alpaca, sin claves)."""

    def barras(self, simbolo, cantidad):
        desde = int(time.time() * 1000) - (cantidad + 5) * brokers.MS_VELA
        return brokers.barras(simbolo, desde)[-cantidad:]

    def precio(self, simbolo):
        return brokers.precio_ultimo(simbolo)


class Halcon:
    def __init__(self, broker, datos, ruta_estado, aviso=None, log=print, ventana=VENTANA):
        self.b, self.datos, self.ruta, self.aviso, self.log, self.ventana = broker, datos, ruta_estado, aviso, log, ventana
        self.s = {"capital_inicial": CAPITAL, "pnl_total": 0.0, "pares": {}, "cerradas": [], "entradas_perdidas": 0, "eventos": []}
        if os.path.exists(ruta_estado):
            with open(ruta_estado, encoding="utf-8") as f:
                self.s.update(json.load(f))

    # ------------------------------------------------------------------ estado
    def guardar(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.ruta)), exist_ok=True)
        with open(self.ruta, "w", encoding="utf-8") as f:
            json.dump(self.s, f, indent=1)

    def equity(self):
        return self.s["capital_inicial"] + self.s["pnl_total"]

    def _avisar(self, titulo, cuerpo, telegram=None):
        if not self.aviso:
            return
        try:
            self.aviso(titulo, cuerpo, telegram=telegram)
        except Exception as e:  # noqa: BLE001 - un aviso nunca debe romper una orden ya enviada
            self.log("(aviso no enviado: %s)" % e)

    # ------------------------------------------------------------------ ciclo
    def ciclo(self):
        for sym in SIMBOLOS:
            velas = self.datos.barras(sym, self.ventana)
            self.procesar(sym, velas)

    def procesar(self, sym, velas):
        par = self.s["pares"].setdefault(sym, {"barra_ts": None, "largo": None, "corto": None})
        ultimo = par["barra_ts"]
        indices = [len(velas) - 1] if ultimo is None else [k for k, v in enumerate(velas) if v.ts > ultimo][-MAX_PEND:]
        for k in indices:
            previa = par["barra_ts"]
            par["barra_ts"] = velas[k].ts
            ind = calcular(velas[max(0, k - self.ventana + 1):k + 1])
            if ind is None:
                continue
            try:
                self._vela(sym, par, velas, k, ind, es_ultima=(k == len(velas) - 1))
            except Exception:
                par["barra_ts"] = previa          # si una orden falló, esta vela se reintenta en la próxima corrida
                self.guardar()
                raise
        self.guardar()

    def _vela(self, sym, par, velas, k, ind, es_ultima):
        no_entrar = set()
        # ---- salidas (siempre, aunque la vela sea vieja)
        pos = par["largo"]
        if pos:
            if self.b.posicion(sym) is None:                  # el stop-limit del servidor ya la vendió
                fill = self.b.fill_ultima_venta(sym)
                self._cerrar(sym, par, "largo", fill if fill else pos["stop"], "stop", velas[k].ts, estimado=not fill)
            elif ind["close"] < ind["lo_x"]:
                self.b.cancelar_ordenes(sym)
                self._cerrar(sym, par, "largo", self.b.vender_todo(sym), "canal", velas[k].ts, tardia=not es_ultima)
                no_entrar.add("largo")
        pos = par["corto"]
        if pos:
            if ind["high"] >= pos["stop"]:
                ref = max(velas[k].open, pos["stop"])      # si la vela abre más arriba del stop, se sale a la apertura
                self._cerrar(sym, par, "corto", ref * (1 + SLIP), "stop", velas[k].ts)
            elif ind["close"] > ind["hi_x"]:
                ref = velas[k + 1].open if k + 1 < len(velas) else self.datos.precio(sym)
                self._cerrar(sym, par, "corto", ref * (1 + SLIP), "canal", velas[k].ts, tardia=not es_ultima)
                no_entrar.add("corto")
        # ---- entradas
        for lado in ("largo", "corto"):
            if par[lado] or lado in no_entrar:
                continue
            señal = ind["close"] > ind["hi_e"] if lado == "largo" else ind["close"] < ind["lo_e"]
            if not señal:
                continue
            if es_ultima:
                self._abrir(sym, par, lado, ind)
            else:
                self.s["entradas_perdidas"] += 1
                self.s["eventos"].append({"tipo": "entrada_perdida", "sym": sym, "lado": lado, "vela": _hora(ind["ts"])})
                self.log("%s: señal de %s en la vela %s vista tarde: no se opera" % (sym, lado, _hora(ind["ts"])))

    # ------------------------------------------------------------------ operaciones
    def _abrir(self, sym, par, lado, ind):
        precio = self.datos.precio(sym)
        manga = self.equity() / len(SIMBOLOS)
        dist = STOP_MULT * ind["atr"]
        qty = math.floor(min(manga / precio, RIESGO * manga / dist) * 1e6) / 1e6
        if qty * precio < NOCIONAL_MIN:
            self.log("%s: señal %s pero nocional %.2f USD < mínimo; omito" % (sym, lado, qty * precio))
            return
        if lado == "largo":
            fill = self.b.comprar(sym, qty, precio)
            stop = fill - dist
            try:
                self.b.proteger(sym, stop, qty)
            except Exception as e:  # noqa: BLE001
                self.log("%s: AVISO no pude colocar el stop del servidor: %s (el bot lo vigila igual)" % (sym, e))
        else:
            fill = precio * (1 - SLIP)
            stop = fill + dist
        par[lado] = {"qty": qty, "entrada": fill, "stop": stop, "dist": dist, "ts": ind["ts"], "real": lado == "largo"}
        self.log("%s: ENTRADA %s qty=%.6f fill=%.2f stop=%.2f %s" % (sym, lado.upper(), qty, fill, stop, "real" if lado == "largo" else "virtual"))
        self._avisar("HALCÓN | ENTRADA %s %s @ %.2f" % (lado.upper(), sym, fill),
                     "%s %s: %.6f a %.2f, stop %.2f (%s)" % (lado, sym, qty, fill, stop, "real" if lado == "largo" else "virtual"),
                     telegram=formato.halcon_entrada(sym, lado, qty, fill, stop, dist, lado == "largo", _hora(ind["ts"]), manga))

    def _cerrar(self, sym, par, lado, salida, motivo, ts, tardia=False, estimado=False):
        pos = par[lado]
        if lado == "largo":
            pnl_u = salida * (1 - FEE) - pos["entrada"] * (1 + FEE)
        else:
            pnl_u = pos["entrada"] * (1 - FEE) - salida * (1 + FEE)
        r = pnl_u / pos["dist"]
        pnl = pos["qty"] * pnl_u
        op = {"sym": sym, "lado": lado, "real": pos["real"], "entrada_ts": pos["ts"], "salida_ts": ts, "qty": pos["qty"],
              "entrada": pos["entrada"], "salida": salida, "motivo": motivo, "R": r, "pnl": pnl, "tardia": tardia, "estimado": estimado}
        self.s["cerradas"].append(op)
        self.s["pnl_total"] += pnl
        par[lado] = None
        self.log("%s: SALIDA %s (%s) %.2f -> %.2f R=%+.2f pnl=%+.2f" % (sym, lado.upper(), motivo, pos["entrada"], salida, r, pnl))
        self._avisar("HALCÓN | SALIDA %s %s %+.2f R (%+.2f USD)" % (lado.upper(), sym, r, pnl),
                     "%s %s cerrada por %s: R %+.2f, %+.2f USD" % (lado, sym, motivo, r, pnl),
                     telegram=formato.halcon_salida(sym, lado, motivo, pos["qty"], pos["entrada"], salida, pnl, r, pos["real"],
                                                    _hora(ts), self._resumen_filas(), tardia, estimado))

    def _resumen_filas(self):
        ops = self.s["cerradas"]
        n = len(ops)
        gan = sum(1 for o in ops if o["pnl"] > 0)
        por = {l: [o for o in ops if o["lado"] == l] for l in ("largo", "corto")}
        f = [("Operaciones", str(n)), ("Aciertos", "%d (%s %%)" % (gan, formato.num(100 * gan / n, 0) if n else "0")),
             ("R promedio", formato.num(sum(o["R"] for o in ops) / n, 2, True) if n else "n/d"),
             ("Resultado", formato.usd(self.s["pnl_total"], True)), ("Capital virtual", formato.usd(self.equity())),
             ("Entradas perdidas", str(self.s["entradas_perdidas"]))]
        for l, lst in por.items():
            f.append(("  %s" % l, "%d op. R %s" % (len(lst), formato.num(sum(o["R"] for o in lst) / len(lst), 2, True) if lst else "n/d")))
        return f

    # ------------------------------------------------------------------ estado a pedido
    def enviar_estado(self):
        abiertas, ultima = [], "n/d"
        for sym, par in self.s["pares"].items():
            if par.get("barra_ts"):
                ultima = _hora(par["barra_ts"])
            for lado in ("largo", "corto"):
                if par.get(lado):
                    try:
                        actual = self.datos.precio(sym)
                    except Exception:  # noqa: BLE001
                        actual = None
                    abiertas.append(dict(par[lado], lado=lado, sym=sym, actual=actual))
        html = formato.halcon_estado(_hora(int(time.time() * 1000)), self.equity(), self.s["pnl_total"], abiertas,
                                     len(self.s["cerradas"]), self.s["entradas_perdidas"], ultima)
        self._avisar("HALCÓN | Estado", "%d posiciones abiertas, %d cerradas" % (len(abiertas), len(self.s["cerradas"])), telegram=html)


def main(argv=None):
    ap = argparse.ArgumentParser(description="HALCÓN: Turtle espejo largo/corto (paper, experimento hacia adelante)")
    ap.add_argument("--estado", required=True, help="carpeta de estado (rama halcon-estado)")
    ap.add_argument("--resumen", action="store_true", help="mandar el estado actual a Telegram y terminar")
    a = ap.parse_args(argv)
    key, secret = os.environ.get("HALCON_ALPACA_KEY"), os.environ.get("HALCON_ALPACA_SECRET")
    if not key or not secret:
        print("HALCÓN: faltan los secrets HALCON_ALPACA_KEY / HALCON_ALPACA_SECRET. No hago nada (ver proyectos/halcon/README.md).")
        return 0
    cfg = json.load(open(os.path.join(RAIZ, "alba", "config.json"), encoding="utf-8"))
    notif = Notificador(mencionar=cfg.get("mencionar"), etiqueta="halcon")
    bot = Halcon(AlpacaHalcon(key, secret), DatosAlpaca(), os.path.join(a.estado, NOMBRE_ESTADO), aviso=notif.avisar)
    if a.resumen:
        bot.enviar_estado()
        return 0
    try:
        bot.ciclo()
    except Exception as e:  # noqa: BLE001
        if time.time() - bot.s.get("ultimo_aviso_error", 0) > 3600:
            bot.s["ultimo_aviso_error"] = time.time()
            notif.avisar("HALCÓN | ERROR en el ciclo", "`%s`" % str(e)[:500],
                         telegram=formato.alerta("HALCÓN · ERROR en el ciclo", str(e)[:500], "Revisar la corrida en Actions.", "🚨"))
        bot.guardar()
        raise
    bot.guardar()
    print("HALCÓN: ciclo terminado | capital virtual %.2f | abiertas: %s" % (
        bot.equity(), [(s, l) for s, p in bot.s["pares"].items() for l in ("largo", "corto") if p.get(l)]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
