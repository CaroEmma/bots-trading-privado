import json, os, random, sys, tempfile, unittest
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import evaluar as ev  # noqa: E402
import sombra as sb  # noqa: E402

T0 = 1_700_000_000_000 - (1_700_000_000_000 % ev.DIA_MS)   # medianoche UTC


def mundo(dias, acierto, semilla=5, demora_ms=1000, frac_operables=0.5):
    """Velas reales (paseo al azar, 4 h) y un pronóstico ancla por par y por día con la exactitud pedida."""
    rng = random.Random(semilla)
    velas, pron = {}, []
    for par in sb.PARES:
        c, p = {}, 100.0
        for i in range((dias + 3) * 6 + 20):
            c[T0 + i * ev.MS] = p
            p *= 1 + rng.gauss(0, 0.012)
        velas[par] = c
        for d in range(1, dias):
            ts = T0 + d * ev.DIA_MS - ev.MS                  # vela que cierra a las 00:00 UTC
            ref, real = c[ts], c[ts + 6 * ev.MS] / c[ts] - 1
            signo = ev.signo(real) if rng.random() < acierto else -ev.signo(real)
            mag = 0.012 if rng.random() < frac_operables else 0.003
            cierres = [ref * (1 + 0.0005)] * 5 + [ref * (1 + signo * mag)]
            pron.append({"par": par, "vela_ts": ts, "cierre_ref": ref, "pred_cierres": cierres, "emitido_ms": ts + ev.MS + demora_ms})
    return velas, pron


class TestEvaluar(unittest.TestCase):
    def test_binomial_exacta(self):
        self.assertAlmostEqual(ev.binomial_una_cola(10, 9), 11 / 1024)
        self.assertAlmostEqual(ev.binomial_una_cola(10, 5), 638 / 1024)
        self.assertIsNone(ev.binomial_una_cola(0, 0))

    def test_pasa_si_cumple_a_b_y_c(self):
        velas, pron = mundo(120, acierto=0.68)
        r = ev.evaluar(pron, velas, T0 + 125 * ev.DIA_MS)
        self.assertTrue(r["formal_lista"])
        self.assertEqual(r["cumple"], {"A": True, "B": True, "C": True})
        self.assertTrue(r["veredicto"].startswith("PASA"))

    def test_no_pasa_si_es_azar(self):
        velas, pron = mundo(120, acierto=0.5, semilla=11)
        r = ev.evaluar(pron, velas, T0 + 125 * ev.DIA_MS)
        self.assertTrue(r["formal_lista"])
        self.assertTrue(r["veredicto"].startswith("NO PASA"))

    def test_antes_de_90_dias_no_hay_evaluacion_formal(self):
        velas, pron = mundo(30, acierto=0.9)
        r = ev.evaluar(pron, velas, T0 + 35 * ev.DIA_MS)
        self.assertFalse(r["formal_lista"])
        self.assertIn("AÚN NO", r["veredicto"])          # aunque acierte mucho, no es una conclusión

    def test_con_pocos_operables_c_es_no_concluyente_y_no_pasa(self):
        velas, pron = mundo(120, acierto=0.68, frac_operables=0.03)
        r = ev.evaluar(pron, velas, T0 + 125 * ev.DIA_MS)
        self.assertLess(r["C"]["n"], 30)
        self.assertFalse(r["cumple"]["C"])
        self.assertTrue(r["veredicto"].startswith("NO PASA"))
        self.assertIn("no concluyente", r["veredicto"])

    def test_los_pronosticos_atrasados_no_cuentan(self):
        velas, pron = mundo(120, acierto=0.68, demora_ms=3 * ev.MS)   # emitidos 3 velas tarde
        r = ev.evaluar(pron, velas, T0 + 125 * ev.DIA_MS)
        self.assertEqual(r["validas"], 0)
        self.assertEqual(r["descartadas_por_atraso"], r["total"])

    def test_exploratorio_se_calcula_sin_entrar_en_el_criterio(self):
        velas, pron = mundo(120, acierto=0.6)
        r = ev.evaluar(pron, velas, T0 + 125 * ev.DIA_MS)
        self.assertIn("BTC/USD", r["exploratorio"]["por_par"])
        self.assertIsNotNone(r["exploratorio"]["spearman_24h"])


class TestNecesita(unittest.TestCase):
    class V:
        def __init__(self, ts): self.ts = ts

    def test_decide_segun_lo_ya_pronosticado(self):
        d = tempfile.mkdtemp()
        barras = lambda par, n: [self.V(1000)]
        self.assertTrue(sb.necesita(d, barras))                       # nada guardado
        with open(os.path.join(d, sb.RUTA), "w") as f:
            for par in sb.PARES:
                f.write(json.dumps({"par": par, "vela_ts": 1000}) + "\n")
        self.assertFalse(sb.necesita(d, barras))                      # ya está todo
        self.assertTrue(sb.necesita(d, lambda par, n: [self.V(1000 + ev.MS)]))   # llegó una vela nueva

    def test_el_codigo_de_terceros_esta_fijado_por_commit(self):
        self.assertEqual(len(sb.KRONOS_SHA), 40)
        self.assertEqual(sb.PARAMS, {"T": 1.0, "top_k": 0, "top_p": 0.9, "sample_count": 5})   # los del preregistro


if __name__ == "__main__":
    unittest.main()
