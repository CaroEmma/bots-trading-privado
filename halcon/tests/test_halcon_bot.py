import csv, datetime as dt, os, sys, tempfile, unittest
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import halcon_bot as hb  # noqa: E402
import medir_espejo as me  # noqa: E402
from velas import Vela  # noqa: E402

CSV_BTC = os.path.join(os.path.dirname(AQUI), "datos", "btc_usd_4h_twelvedata.csv")
SYM = "BTC/USD"


def velas_btc(n=2500):
    t, o, h, l, c = me.cargar(CSV_BTC)
    ts = [int(x.replace(tzinfo=dt.timezone.utc).timestamp() * 1000) for x in t]
    return [Vela(ts[i], o[i], h[i], l[i], c[i], 0.0) for i in range(len(t))][-n:]


class BrokerFalso:
    def __init__(self):
        self.pos, self.stops, self.px, self.ultima_venta, self.ordenes = {}, {}, None, {}, []

    def precio(self, s): return self.px
    def posicion(self, s): return self.pos.get(s)

    def comprar(self, s, qty, ref=None):
        f = self.px * (1 + hb.SLIP)
        self.pos[s] = {"qty": qty, "avg": f}
        self.ordenes.append(("buy", s, qty, f))
        return f

    def vender_todo(self, s, pf=None):
        self.pos.pop(s)
        self.stops.pop(s, None)
        return self.px * (1 - hb.SLIP)

    def proteger(self, s, stop, qty): self.stops[s] = stop
    def cancelar_ordenes(self, s): self.stops.pop(s, None)
    def fill_ultima_venta(self, s): return self.ultima_venta.get(s)

    def avanzar(self, s, vela):
        """El stop-limit del servidor se dispara dentro de la vela."""
        st = self.stops.get(s)
        if st is not None and s in self.pos and vela.low <= st:
            self.ultima_venta[s] = min(vela.open, st) * (1 - hb.SLIP)
            self.pos.pop(s)
            self.stops.pop(s)


class DatosFalsos:
    px = None
    def precio(self, s): return self.px


def a_csv(velas):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="")
    w = csv.writer(f); w.writerow(["t", "o", "h", "l", "c"])
    for v in velas:
        w.writerow([dt.datetime.fromtimestamp(v.ts / 1000, dt.timezone.utc).strftime(me.FMT), v.open, v.high, v.low, v.close])
    f.close()
    return f.name


def replay(velas, k0, paso=1, avisos=None):
    broker, datos = BrokerFalso(), DatosFalsos()
    ruta = os.path.join(tempfile.mkdtemp(), "e.json")
    aviso = (lambda t, c, telegram=None: avisos.append((t, c, telegram))) if avisos is not None else None
    bot = hb.Halcon(broker, datos, ruta, aviso=aviso, log=lambda *a: None, ventana=len(velas) + 1)
    bot.s["pares"][SYM] = {"barra_ts": velas[k0 - 1].ts, "largo": None, "corto": None}
    for k in range(k0, len(velas) - 1):
        broker.px = datos.px = velas[k + 1].open
        broker.avanzar(SYM, velas[k])
        if (k - k0) % paso == paso - 1:
            bot.procesar(SYM, velas[:k + 1])
    return bot, broker


class TestHalcon(unittest.TestCase):
    def test_las_senales_coinciden_con_la_medicion(self):
        velas = velas_btc(400)
        ind = hb.calcular(velas)
        s = me.Serie(a_csv(velas), 120, 60)
        k = len(velas) - 1
        for clave, ref in (("hi_e", s.hi_e[k]), ("lo_e", s.lo_e[k]), ("hi_x", s.hi_x[k]), ("lo_x", s.lo_x[k]), ("atr", s.atr[k])):
            self.assertAlmostEqual(ind[clave], ref, places=6, msg=clave)

    def test_repeticion_vela_por_vela_hace_las_mismas_operaciones_que_la_medicion(self):
        velas = velas_btc(2500)
        k0 = hb.NE + hb.ATR_P            # primera vela evaluable del bot (índice 134)
        bot, _ = replay(velas, k0)
        s = me.Serie(a_csv(velas), 120, 60)
        s.primero = k0
        total = 0
        for lado in ("largo", "corto"):
            esperadas = [o for o in s.operaciones(lado) if o["tipo"] != "abierta" and o["js"] < len(velas) - 3]
            reales = [o for o in bot.s["cerradas"] if o["lado"] == lado and o["salida_ts"] <= velas[-3].ts]
            self.assertGreater(len(esperadas), 5, lado)
            self.assertEqual(len(reales), len(esperadas), lado)
            for e, r in zip(esperadas, reales):
                self.assertEqual(velas[e["k"]].ts, r["entrada_ts"])
                self.assertEqual(e["tipo"], r["motivo"])
                self.assertAlmostEqual(e["R"], r["R"], places=6)
            total += len(esperadas)
        self.assertGreater(total, 10)

    def test_largos_son_reales_y_cortos_virtuales(self):
        velas = velas_btc(2500)
        bot, broker = replay(velas, hb.NE + hb.ATR_P)
        self.assertGreater(len(broker.ordenes), 3)                    # hubo órdenes reales (largos)
        self.assertTrue(all(o["real"] for o in bot.s["cerradas"] if o["lado"] == "largo"))
        self.assertTrue(all(not o["real"] for o in bot.s["cerradas"] if o["lado"] == "corto"))
        self.assertTrue(all(o[0] == "buy" for o in broker.ordenes))   # jamás una orden de venta en corto

    def test_si_faltan_corridas_las_salidas_se_aplican_y_las_entradas_viejas_se_cuentan(self):
        velas = velas_btc(2500)
        bot, _ = replay(velas, hb.NE + hb.ATR_P, paso=6)              # una corrida cada 6 velas (24 h)
        self.assertGreater(bot.s["entradas_perdidas"], 0)
        self.assertGreater(len(bot.s["cerradas"]), 3)
        self.assertTrue(any(o["tardia"] for o in bot.s["cerradas"]) or bot.s["entradas_perdidas"] > 0)

    def test_tamano_riesgo_1_por_ciento_y_sin_apalancar(self):
        velas = velas_btc(2500)
        bot, _ = replay(velas, hb.NE + hb.ATR_P)
        for o in bot.s["cerradas"]:
            manga = hb.CAPITAL / 2 * 3                # cota holgada: el capital virtual no se triplica en el período
            self.assertLessEqual(o["qty"] * o["entrada"], manga)
        primero = bot.s["cerradas"][0]
        self.assertLessEqual(primero["qty"] * primero["entrada"], hb.CAPITAL / 2 + 1e-6)

    def test_avisos_de_telegram_distinguen_real_y_virtual(self):
        avisos = []
        replay(velas_btc(2500), hb.NE + hb.ATR_P, avisos=avisos)
        entradas = [a for a in avisos if "ENTRADA" in a[0]]
        self.assertTrue(any("VIRTUAL" in a[2] for a in entradas if "CORTO" in a[0]))
        self.assertTrue(all("real en Alpaca Paper" in a[2] for a in entradas if "LARGO" in a[0]))
        self.assertTrue(any("SALIDA" in a[0] for a in avisos))

    def test_el_estado_se_guarda_y_se_recupera(self):
        velas = velas_btc(1200)
        bot, _ = replay(velas, hb.NE + hb.ATR_P)
        otro = hb.Halcon(BrokerFalso(), DatosFalsos(), bot.ruta, log=lambda *a: None)
        self.assertEqual(otro.s["cerradas"], bot.s["cerradas"])
        self.assertAlmostEqual(otro.equity(), bot.equity())

    def test_el_estado_a_pedido_va_solo_a_telegram_y_no_crea_issues(self):
        velas = velas_btc(1200)
        bot, _ = replay(velas, hb.NE + hb.ATR_P)
        enviados, avisos = [], []
        bot.aviso = lambda t, c, telegram=None: avisos.append(t)
        bot.aviso_estado = lambda t, c, html: enviados.append((t, html))
        bot.datos.px = velas[-1].close
        bot.enviar_estado()
        self.assertEqual(avisos, [])                                  # nada de issues
        self.assertEqual(len(enviados), 1)
        self.assertIn("ESTADO DE HALCÓN", enviados[0][1])
        self.assertIn("Entradas perdidas", enviados[0][1])

    def test_sin_claves_no_hace_nada(self):
        viejo = {k: os.environ.pop(k, None) for k in ("HALCON_ALPACA_KEY", "HALCON_ALPACA_SECRET")}
        try:
            self.assertEqual(hb.main(["--estado", tempfile.mkdtemp()]), 0)
        finally:
            for k, v in viejo.items():
                if v is not None:
                    os.environ[k] = v

    def test_solo_habla_con_paper(self):
        import config as cfg_turtle
        self.assertIn("paper-api.alpaca.markets", cfg_turtle.URL_TRADING_PAPER)


if __name__ == "__main__":
    unittest.main()
