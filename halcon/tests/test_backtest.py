"""Tests del backtest de HALCÓN con series sintéticas (sin red). Correr: python3 -m unittest discover -s halcon/tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backtest as bt  # noqa: E402


def serie(n, precio=100.0):
    o = [precio] * n; h = [precio] * n; l = [precio] * n; c = [precio] * n
    return o, h, l, c, [None] * n, [0] * n


class TestSimular(unittest.TestCase):
    def armar(self, n=60):
        o, h, l, c, atr, seg = serie(n)
        atr[10] = 1.0            # stop = 98, objetivo = 103 con entrada a 100
        return o, h, l, c, atr, seg

    def test_stop(self):
        o, h, l, c, atr, seg = self.armar()
        l[13] = 97.5
        tr = bt.simular(10, 24, o, h, l, c, atr, seg)
        self.assertEqual((tr["tipo"], tr["ref_out"], tr["j"]), ("stop", 98.0, 13))
        self.assertAlmostEqual(tr["stop_pct"], 0.02)

    def test_objetivo(self):
        o, h, l, c, atr, seg = self.armar()
        h[15] = 103.5
        tr = bt.simular(10, 24, o, h, l, c, atr, seg)
        self.assertEqual((tr["tipo"], tr["ref_out"], tr["j"]), ("objetivo", 103.0, 15))

    def test_tiempo(self):
        o, h, l, c, atr, seg = self.armar()
        c[11 + 24 - 1] = 101.0
        tr = bt.simular(10, 24, o, h, l, c, atr, seg)
        self.assertEqual((tr["tipo"], tr["ref_out"], tr["j"]), ("tiempo", 101.0, 34))

    def test_si_tocan_stop_y_objetivo_en_la_misma_vela_gana_el_stop(self):
        o, h, l, c, atr, seg = self.armar()
        h[12] = 104.0; l[12] = 97.0
        self.assertEqual(bt.simular(10, 24, o, h, l, c, atr, seg)["tipo"], "stop")

    def test_gap_bajo_el_stop_sale_a_la_apertura(self):
        o, h, l, c, atr, seg = self.armar()
        o[12] = 95.0; l[12] = 94.0
        self.assertEqual(bt.simular(10, 24, o, h, l, c, atr, seg)["ref_out"], 95.0)

    def test_no_completa_si_cruza_un_hueco_o_el_final(self):
        o, h, l, c, atr, seg = self.armar()
        for k in range(20, 60):
            seg[k] = 1
        self.assertIsNone(bt.simular(10, 24, o, h, l, c, atr, seg))
        self.assertIsNone(bt.simular(10, 24, *self.armar(30)))


class TestAgregar(unittest.TestCase):
    def test_4h_completas_y_descarta_incompletas(self):
        import datetime as dt
        base = dt.datetime(2026, 1, 1, 0, 0)
        t = [base + dt.timedelta(hours=k) for k in range(9)]        # 00..08 -> grupos 0-3, 4-7 completos; 8 incompleto
        o = [float(k) for k in range(9)]
        h = [k + 10.0 for k in range(9)]
        l = [k - 10.0 for k in range(9)]
        c = [k + 0.5 for k in range(9)]
        T, O, H, L, C = bt.agregar(t, o, h, l, c, 4)
        self.assertEqual(len(T), 2)
        self.assertEqual((O[0], C[0], H[0], L[0]), (0.0, 3.5, 13.0, -10.0))
        self.assertEqual((O[1], C[1]), (4.0, 7.5))

    def test_grupo_con_hueco_se_descarta(self):
        import datetime as dt
        base = dt.datetime(2026, 1, 1, 0, 0)
        t = [base, base + dt.timedelta(hours=1), base + dt.timedelta(hours=3)]   # falta la hora 2
        r = bt.agregar(t, [1.0] * 3, [1.0] * 3, [1.0] * 3, [1.0] * 3, 4)
        self.assertEqual(len(r[0]), 0)


class TestCostos(unittest.TestCase):
    def test_costo_ida_y_vuelta(self):
        tr = {"ref_in": 100.0, "ref_out": 100.0, "stop_pct": 0.02}
        r, R = bt.r_neto(tr, bt.TAKER)
        self.assertAlmostEqual(r, -0.00598, places=4)      # ~ -(2 x 0,30 %)
        self.assertAlmostEqual(R, r / 0.02)
        self.assertGreater(bt.r_neto(tr, bt.MAKER)[0], r)  # con comisión maker se pierde menos

    def test_objetivo_ganador_en_R(self):
        tr = {"ref_in": 100.0, "ref_out": 103.0, "stop_pct": 0.02}
        self.assertAlmostEqual(bt.r_bruto(tr), 1.5)
        self.assertLess(bt.r_neto(tr, bt.TAKER)[1], 1.5)


class TestIndicadores(unittest.TestCase):
    def test_rsi_sube_siempre(self):
        self.assertAlmostEqual(bt.rsi_wilder([float(i) for i in range(40)])[-1], 100.0)

    def test_rsi_baja_siempre(self):
        self.assertAlmostEqual(bt.rsi_wilder([float(100 - i) for i in range(40)])[-1], 0.0)

    def test_atr_de_rango_constante(self):
        n = 40
        h = [101.0] * n; l = [99.0] * n; c = [100.0] * n
        self.assertAlmostEqual(bt.atr_wilder(h, l, c)[-1], 2.0)

    def test_sma_y_ema(self):
        c = [float(i) for i in range(1, 11)]
        self.assertAlmostEqual(bt.sma(c, 4)[-1], 8.5)
        self.assertAlmostEqual(bt.ema([5.0] * 30, 10)[-1], 5.0)


class TestEstadistica(unittest.TestCase):
    def test_valor_p_de_una_moneda_sesgada(self):
        import random
        rng = random.Random(1)
        pool = [-1.0] * 90 + [3.0] * 10
        p_bajo = bt.valor_p(2.0, pool, 20, rng)    # media 2,0 en 20 trades: casi imposible por azar
        p_alto = bt.valor_p(-0.9, pool, 20, rng)   # peor que el azar
        self.assertLess(p_bajo, 0.01)
        self.assertGreater(p_alto, 0.9)


if __name__ == "__main__":
    unittest.main()


class TestMedirTurtle(unittest.TestCase):
    def setUp(self):
        import medir_turtle as mt
        self.mt = mt

    def armar(self, n=12):
        o = [100.0] * n; l = [100.0] * n
        ind = [{"close": 100.0, "min_salida": 90.0, "max_entrada": 120.0, "atr": 1.0} for _ in range(n)]
        return o, l, ind

    def test_stop_intravela(self):
        o, l, ind = self.armar()
        l[4] = 97.0                       # stop = 100*(1+slip) - 2*ATR ~ 98,05 -> se toca
        ref, tipo, j, dist = self.mt.simular_salida(3, ind, o, l, 100.0)
        self.assertEqual((tipo, j, dist), ("stop", 4, 2.0))
        self.assertLess(ref, 100.0)

    def test_salida_por_canal_a_la_apertura_siguiente(self):
        o, l, ind = self.armar()
        ind[5]["close"] = 85.0            # cierra bajo el mínimo de las 60 previas
        o[6] = 99.5
        ref, tipo, j, _ = self.mt.simular_salida(3, ind, o, l, 100.0)
        self.assertEqual((tipo, ref, j), ("canal", 99.5, 6))

    def test_sigue_abierta_si_no_hay_salida(self):
        o, l, ind = self.armar()
        self.assertEqual(self.mt.simular_salida(3, ind, o, l, 100.0)[1], "abierta")

    def test_costos_del_bot(self):
        r, R = self.mt.cerrar(100.0, 100.0, 2.0)
        self.assertAlmostEqual(r, -0.00598, places=4)
        self.assertAlmostEqual(R, r / 0.02)
