import csv, datetime as dt, os, random, sys, tempfile, unittest
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import medir_espejo as me  # noqa: E402


def serie_sintetica(n=2500, semilla=3, reflejar=None):
    rng = random.Random(semilla)
    p, filas, t0 = 100.0, [], dt.datetime(2020, 1, 1)
    for i in range(n):
        o = p
        c = max(5.0, o * (1 + rng.gauss(0.0004, 0.012)))
        h = max(o, c) * (1 + abs(rng.gauss(0, 0.004)))
        l = min(o, c) * (1 - abs(rng.gauss(0, 0.004)))
        filas.append((t0 + dt.timedelta(hours=4 * i), o, h, l, c))
        p = c
    if reflejar is not None:                      # espejo de precios: K - precio (alto y bajo se intercambian)
        K = reflejar
        filas = [(t, K - o, K - l, K - h, K - c) for t, o, h, l, c in filas]
    return filas


def a_csv(filas):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="")
    w = csv.writer(f); w.writerow(["t", "o", "h", "l", "c"])
    for t, o, h, l, c in filas:
        w.writerow([t.strftime(me.FMT), o, h, l, c])
    f.close()
    return f.name


class TestEspejo(unittest.TestCase):
    def setUp(self):
        self._fee, self._slip = me.FEE, me.SLIP
        me.FEE = me.SLIP = 0.0          # sin costos la simetría debe ser exacta

    def tearDown(self):
        me.FEE, me.SLIP = self._fee, self._slip

    def test_corto_sobre_serie_reflejada_igual_a_largo_sobre_la_original(self):
        orig = serie_sintetica()
        K = 2 * max(max(f[2] for f in orig), 1) + 1000.0   # K grande: el reflejo queda positivo
        refl = serie_sintetica(reflejar=K)
        s1, s2 = me.Serie(a_csv(orig), 120, 60), me.Serie(a_csv(refl), 120, 60)
        largos = s1.operaciones("largo")
        cortos = s2.operaciones("corto")
        self.assertGreater(len(largos), 3)
        self.assertEqual(len(largos), len(cortos))
        for a, b in zip(largos, cortos):
            self.assertEqual((a["e"], a["js"], a["tipo"]), (b["e"], b["js"], b["tipo"]))
            self.assertAlmostEqual(a["R"], b["R"], places=6)

    def test_con_costos_el_resultado_baja(self):
        me.FEE, me.SLIP = self._fee, self._slip
        s = me.Serie(a_csv(serie_sintetica()), 120, 60)
        sin = sum(x["R"] for x in s.operaciones("largo"))
        me.FEE = me.SLIP = 0.0
        s = me.Serie(a_csv(serie_sintetica()), 120, 60)
        self.assertGreater(sum(x["R"] for x in s.operaciones("largo")), sin)

    def test_los_stops_nunca_se_ejecutan_a_mejor_precio_que_el_stop(self):
        s = me.Serie(a_csv(serie_sintetica(semilla=9)), 120, 60)
        vistos = 0
        for op in s.operaciones("corto"):
            if op["tipo"] == "stop":
                vistos += 1
                self.assertGreaterEqual(op["salida"], op["entrada"] + op["dist"] - 1e-6)   # corto: sale a stop o peor (más caro)
        for op in s.operaciones("largo"):
            if op["tipo"] == "stop":
                vistos += 1
                self.assertLessEqual(op["salida"], op["entrada"] - op["dist"] + 1e-6)      # largo: sale a stop o peor (más barato)
        self.assertGreater(vistos, 0)


if __name__ == "__main__":
    unittest.main()
