"""Tests offline del bot Turtle (sin red, sin claves). Correr: python3 -m unittest discover -s alpaca_bot/tests -v"""
import os
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(AQUI)
RAIZ = os.path.dirname(BOT)
sys.path.insert(0, BOT)

import bot_github_actions as bga  # noqa: E402
import config  # noqa: E402
import estrategia  # noqa: E402
from velas import Vela  # noqa: E402

MS = config.MINUTOS_VELA * 60_000
T0 = 1_700_000_000_000


def velas_planas(n, close=100.0):
    """n velas con rango constante: máximo 101, mínimo 99 (ATR = 2)."""
    return [Vela(T0 + i * MS, close, 101.0, 99.0, close, 1.0) for i in range(n)]


def con_cierres(base, cierres):
    """Agrega velas con esos cierres (alto/bajo envuelven el cierre sin cambiar el rango de las previas)."""
    out = list(base)
    for c in cierres:
        i = len(out)
        out.append(Vela(T0 + i * MS, c, max(c, 101.0) + 0.0, min(c, 99.0) - 0.0, c, 1.0))
    return out


class BrokerFalso:
    def __init__(self, precio=100.0, equity=100_000.0):
        self.precio_actual, self.eq, self.pos, self.ordenes, self.velas = precio, equity, None, [], []

    def barras(self, s, n):
        return self.velas[-n:]

    def precio(self, s):
        return self.precio_actual

    def equity(self):
        return self.eq

    def posicion(self, s):
        return self.pos

    def comprar(self, s, qty, ref=None):
        self.ordenes.append(("buy", qty))
        self.pos = {"qty": qty, "avg": self.precio_actual}
        return self.precio_actual

    def proteger(self, s, stop, qty):
        pass

    def cancelar_ordenes(self, s):
        pass

    def vender_todo(self, s, precio_fill=None):
        self.ordenes.append(("sell", self.pos["qty"]))
        self.pos = None
        return self.precio_actual


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.logs, self.avisos = [], []
        self.broker = BrokerFalso()
        self.bot = bga.Bot(self.broker, simbolos=["BTC/USD"], ruta_estado=os.path.join(self.dir, "estado.json"),
                           log=self.logs.append, aviso=lambda t, c, telegram=None: self.avisos.append((t, c)))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def evaluar_hasta(self, velas):
        """Simula que la corrida ve estas velas cerradas."""
        self.broker.velas = velas
        self.bot.procesar_pendientes("BTC/USD", velas)


class TestPendientes(Base):
    def test_primera_corrida_solo_evalua_la_ultima_y_no_opera_sobre_historia(self):
        velas = con_cierres(velas_planas(150), [105.0, 100.0])    # la vela 150 rompió, la última (151) no
        self.evaluar_hasta(velas)
        self.assertEqual(self.broker.ordenes, [])
        self.assertEqual(self.bot.estado["BTC/USD"]["barra_ts"], velas[-1].ts)

    def test_entrada_solo_con_la_ultima_vela(self):
        base = velas_planas(150)
        self.evaluar_hasta(base)                                    # deja barra_ts en la vela 149
        self.evaluar_hasta(con_cierres(base, [105.0, 100.0]))       # rompió en una vela vieja y ya volvió
        self.assertEqual(self.broker.ordenes, [])
        self.evaluar_hasta(con_cierres(base, [105.0, 100.0, 110.0]))   # la ultima rompe el canal
        self.assertEqual(self.broker.ordenes, [("buy", self.broker.ordenes[0][1])])
        self.assertTrue(any("TURTLE | COMPRA" in t for t, _ in self.avisos))

    def test_salida_por_canal_en_vela_intermedia_se_aplica_tarde(self):
        base = velas_planas(150)
        self.evaluar_hasta(base)
        self.bot.estado["BTC/USD"].update(stop=90.0, entrada=105.0, qty=10.0)
        self.broker.pos = {"qty": 10.0, "avg": 105.0}
        self.broker.precio_actual = 99.0
        self.evaluar_hasta(con_cierres(base, [98.0, 98.5, 100.0]))  # cerró bajo el mínimo en la 1.ª pendiente
        self.assertEqual([o[0] for o in self.broker.ordenes], ["sell"])
        self.assertTrue(any("TARDIA" in m for m in self.logs))
        self.assertTrue(any("TURTLE | VENTA" in t for t, _ in self.avisos))
        self.assertNotIn("stop", self.bot.estado["BTC/USD"])

    def test_tras_salida_tardia_la_ultima_vela_puede_volver_a_entrar(self):
        base = velas_planas(150)
        self.evaluar_hasta(base)
        self.bot.estado["BTC/USD"].update(stop=90.0, entrada=105.0, qty=10.0)
        self.broker.pos = {"qty": 10.0, "avg": 105.0}
        self.evaluar_hasta(con_cierres(base, [98.0, 98.5, 110.0]))
        self.assertEqual([o[0] for o in self.broker.ordenes], ["sell", "buy"])

    def test_no_reevalua_velas_ya_vistas(self):
        base = velas_planas(150)
        velas = con_cierres(base, [110.0])
        self.evaluar_hasta(base)
        self.evaluar_hasta(velas)
        n = len(self.broker.ordenes)
        self.evaluar_hasta(velas)
        self.assertEqual(len(self.broker.ordenes), n)

    def test_si_la_orden_falla_la_vela_no_queda_evaluada(self):
        base = velas_planas(150)
        self.evaluar_hasta(base)
        ultimo = self.bot.estado["BTC/USD"]["barra_ts"]

        def boom(*a, **k):
            raise RuntimeError("Alpaca caído")
        self.broker.comprar = boom
        with self.assertRaises(RuntimeError):
            self.evaluar_hasta(con_cierres(base, [110.0]))
        self.assertEqual(self.bot.estado["BTC/USD"]["barra_ts"], ultimo)

    def test_un_aviso_que_falla_no_rompe_la_operacion(self):
        def boom(t, c):
            raise OSError("sin red")
        self.bot.aviso = boom
        base = velas_planas(150)
        self.evaluar_hasta(base)
        self.evaluar_hasta(con_cierres(base, [110.0]))
        self.assertEqual(len(self.broker.ordenes), 1)

    def test_tope_de_velas_pendientes(self):
        base = velas_planas(150)
        self.evaluar_hasta(base)
        self.evaluar_hasta(con_cierres(base, [100.0] * 40))
        self.assertEqual(self.bot.estado["BTC/USD"]["barra_ts"], T0 + 189 * MS)


# ------------------------------------------------------------------ réplica de la historia con el bot real
class Replay:
    """Broker que reproduce la historia: precio = apertura de la vela siguiente; stop del servidor intra-vela."""
    def __init__(self, velas):
        self.v, self.k, self.revisado, self.pos, self.eventos = velas, 0, -1, None, []

    def avanzar(self, k):
        self.k = k
        for j in range(self.revisado + 1, k + 1):
            p = self.pos
            if p and p.get("stop") and j >= p["entry_bar"] and self.v[j].low <= p["stop"]:
                self.eventos.append(("stop", j))
                self.pos = None
        self.revisado = k

    def barras(self, s, n):
        return self.v[max(0, self.k - n + 1):self.k + 1]

    def precio(self, s):
        return self.v[self.k + 1].open if self.k + 1 < len(self.v) else self.v[self.k].close

    def equity(self):
        return 50_000.0

    def posicion(self, s):
        return None if self.pos is None else {"qty": self.pos["qty"], "avg": self.pos["avg"]}

    def comprar(self, s, qty, ref=None):
        fill = self.precio(s) * (1 + config.SLIPPAGE_SIM)
        self.pos = {"qty": qty, "avg": fill, "entry_bar": self.k + 1}
        self.eventos.append(("compra", self.k + 1))
        return fill

    def proteger(self, s, stop, qty):
        self.pos["stop"] = stop

    def cancelar_ordenes(self, s):
        pass

    def vender_todo(self, s, precio_fill=None):
        self.eventos.append(("venta", self.k + 1))
        self.pos = None
        return self.precio(s) * (1 - config.SLIPPAGE_SIM)


def cargar_velas_4h(ruta):
    sys.path.insert(0, os.path.join(RAIZ, "halcon"))
    import backtest as bt
    t, o, h, l, c, seg = bt.cargar(ruta, 4)
    velas = [Vela(int(x.timestamp() * 1000), o[i], h[i], l[i], c[i], 0.0) for i, x in enumerate(t)]
    return t, velas


def replay(velas, paso):
    br = Replay(velas)
    d = tempfile.mkdtemp()
    bot = bga.Bot(br, simbolos=["BTC/USD"], ruta_estado=os.path.join(d, "e.json"), log=lambda m: None)
    primero = estrategia.canales()[0] + config.ATR_PERIODO
    for k in range(primero, len(velas) - 1, paso):
        br.avanzar(k)
        bga.ciclo(bot)
    return br.eventos


RUTA_BTC = os.path.join(RAIZ, "halcon", "datos", "btc_usd_1h_twelvedata.csv")
RUTA_ETH = os.path.join(RAIZ, "halcon", "datos", "eth_usd_1h_twelvedata.csv")


@unittest.skipUnless(os.path.exists(RUTA_BTC), "faltan los datos históricos de halcon/datos")
class TestReplayConHistoria(unittest.TestCase):
    def test_el_bot_real_hace_las_mismas_operaciones_que_la_medicion(self):
        sys.path.insert(0, os.path.join(RAIZ, "halcon"))
        import medir_turtle as mt
        import datetime as dt
        t, velas = cargar_velas_4h(RUTA_BTC)
        medidas = mt.correr_par("BTC/USD", RUTA_BTC, dt.datetime(2025, 12, 24))["trades"]
        ev = replay(velas, paso=1)
        entradas = [str(t[i]) for tipo, i in ev if tipo == "compra"]
        salidas = [str(t[i]) for tipo, i in ev if tipo in ("venta", "stop")]
        self.assertEqual(entradas, [x["entrada_ts"] for x in medidas])
        self.assertEqual(salidas, [x["salida_ts"] for x in medidas])
        self.assertEqual(len(entradas), 24)

    def test_el_bot_real_hace_las_mismas_operaciones_en_eth(self):
        sys.path.insert(0, os.path.join(RAIZ, "halcon"))
        import medir_turtle as mt
        import datetime as dt
        t, velas = cargar_velas_4h(RUTA_ETH)
        medidas = mt.correr_par("ETH/USD", RUTA_ETH, dt.datetime(2025, 12, 24))["trades"]
        ev = replay(velas, paso=1)
        self.assertEqual([str(t[i]) for tipo, i in ev if tipo == "compra"], [x["entrada_ts"] for x in medidas])
        self.assertEqual([str(t[i]) for tipo, i in ev if tipo in ("venta", "stop")], [x["salida_ts"] for x in medidas])
        self.assertEqual(len(medidas), 17)

    def test_con_corridas_salteadas_nunca_queda_una_posicion_sin_salida_por_canal(self):
        t, velas = cargar_velas_4h(RUTA_BTC)
        ev = replay(velas, paso=6)           # una corrida cada 24 h: se saltea 5 de cada 6 velas
        compras = [e for e in ev if e[0] == "compra"]
        cierres = [e for e in ev if e[0] in ("venta", "stop")]
        self.assertGreater(len(compras), 5)
        self.assertGreaterEqual(len(compras) - len(cierres), 0)
        self.assertLessEqual(len(compras) - len(cierres), 1)     # a lo sumo la última puede seguir abierta


if __name__ == "__main__":
    unittest.main()
