"""Tests offline de ALBA v2 en modo sombra (sin red). Correr: python3 -m unittest discover -s alba/tests -v"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import orquestador as oq  # noqa: E402
import sombra  # noqa: E402

NY = oq.NY
CFG = oq.leer_json(os.path.join(os.path.dirname(AQUI), "config.json"))


def epoch(fecha, hhmm):
    d = dt.datetime.strptime("%s %s" % (fecha, hhmm), "%Y-%m-%d %H:%M").replace(tzinfo=NY)
    return int(d.timestamp())


def sesion_dia(fecha, base, vol=1000, abre=None, n=78, paso=0.0):
    """Barras de 5 min de 09:30 a 16:00 con precio casi constante (para probar volumen y brechas)."""
    out, t = [], epoch(fecha, "09:30")
    for i in range(n):
        p = base + paso * i
        o = abre if (abre is not None and i == 0) else p
        out.append({"t": t + 300 * i, "o": o, "h": p + 0.05, "l": p - 0.05, "c": p, "v": vol})
    return out


DIAS = ["2026-10-%02d" % d for d in (26, 27, 28, 29, 30)] + ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
HOY = "2026-11-09"


def historia(base, vol_prev, vol_hoy, abre_hoy=None, paso_hoy=0.0):
    b = []
    for d in DIAS:
        b += sesion_dia(d, base, vol_prev)
    b += sesion_dia(HOY, base, vol_hoy, abre=abre_hoy, paso=paso_hoy)
    return b


def respuesta(barras):
    return {"chart": {"result": [{"timestamp": [b["t"] for b in barras], "indicators": {"quote": [{
        "open": [b["o"] for b in barras], "high": [b["h"] for b in barras], "low": [b["l"] for b in barras],
        "close": [b["c"] for b in barras], "volume": [b["v"] for b in barras]}]}}]}}


class Resp:
    def __init__(self, dato):
        self.dato = dato

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self.dato).encode()


def http429(url="x"):
    return urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)


class TestRasgos(unittest.TestCase):
    def test_rvol_gap_y_spy(self):
        sym = historia(100, 1000, 2000, abre_hoy=102)          # hoy el doble de volumen y +2 % de brecha
        spy = historia(500, 1000, 1000, abre_hoy=500, paso_hoy=0.1)
        r = sombra.rasgos(sym, spy, dt.date(2026, 11, 9), 9 * 60 + 50)
        self.assertAlmostEqual(r["rvol"], 2.0, places=2)
        self.assertAlmostEqual(r["gap_pct"], 2.0, places=2)
        self.assertGreater(r["spy_pct"], 0)          # SPY sube dentro del día
        self.assertIn(r["spy_sobre_media"], (True, False))

    def test_sin_historia_no_hay_dato(self):
        r = sombra.rasgos(sesion_dia(HOY, 100), [], dt.date(2026, 11, 9), 9 * 60 + 50)
        self.assertIsNone(r["rvol"])
        self.assertIsNone(r["spy_pct"])


class TestVeredicto(unittest.TestCase):
    def test_reglas_del_preregistro(self):
        ok = {"rvol": 1.5, "spy_pct": 0.0}
        self.assertEqual(sombra.veredicto(ok, [])[0], "PASA")
        self.assertEqual(sombra.veredicto({"rvol": 1.49, "spy_pct": 0.1}, [])[0], "DESCARTA")
        self.assertEqual(sombra.veredicto({"rvol": 3, "spy_pct": -0.01}, [])[0], "DESCARTA")
        for tag in ("earnings", "halt", "deal", "legal", "regulatory"):
            self.assertEqual(sombra.veredicto(ok, [tag])[0], "DESCARTA", tag)
        self.assertEqual(sombra.veredicto(ok, ["analyst", "macro"])[0], "PASA")       # esas etiquetas no excluyen
        self.assertEqual(sombra.veredicto({"rvol": None, "spy_pct": 1}, [])[0], "SIN DATO")
        self.assertEqual(sombra.veredicto({"rvol": 2, "spy_pct": None}, [])[0], "SIN DATO")


class TestSimular(unittest.TestCase):
    def barras(self, h_l):
        """h_l: lista de (open, high, low, close) a partir de las 09:50."""
        t0 = epoch(HOY, "09:50")
        return [{"t": t0 + 300 * i, "o": o, "h": h, "l": l, "c": c, "v": 1} for i, (o, h, l, c) in enumerate(h_l)]

    def test_objetivo(self):
        r = sombra.simular(self.barras([(100, 100.5, 99.5, 100), (100, 102.1, 99.9, 102)]), 100, 99, 9 * 60 + 50)
        self.assertEqual((r["motivo"], r["r"]), ("objetivo", 2.0))

    def test_stop_y_misma_barra_cuenta_stop(self):
        r = sombra.simular(self.barras([(100, 102.5, 98.5, 100)]), 100, 99, 9 * 60 + 50)
        self.assertEqual((r["motivo"], r["r"]), ("stop", -1.0))

    def test_apertura_bajo_el_stop(self):
        r = sombra.simular(self.barras([(98, 98.5, 97, 98)]), 100, 99, 9 * 60 + 50)
        self.assertEqual(r["motivo"], "stop")
        self.assertAlmostEqual(r["r"], -2.0)

    def test_cierre_por_horario(self):
        b = sesion_dia(HOY, 100.5)
        r = sombra.simular(b, 100, 99, 9 * 60 + 50)
        self.assertEqual(r["motivo"], "horario")
        self.assertAlmostEqual(r["r"], 0.5)

    def test_sin_barras_o_riesgo_invalido(self):
        self.assertIsNone(sombra.simular([], 100, 99, 590))
        self.assertIsNone(sombra.simular(self.barras([(100, 101, 99.5, 100)]), 100, 101, 590))


class PackFalso:
    def __init__(self, tags=("analyst",), rc=0):
        self.tags, self.rc, self.llamadas = tags, rc, []

    def correr(self, skill, args):
        self.llamadas.append((skill, args))
        return self.rc, json.dumps({"items": [{"title": "x", "tags": list(self.tags)}]}), ""


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.est = oq.Estado(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.sym = historia(100, 1000, 2000)
        self.spy = historia(500, 1000, 1000, paso_hoy=0.1)
        self.h = {"fecha": HOY, "ultimo_scan": 0}
        self.cfg = json.loads(json.dumps(CFG))

    def abrir(self, req, timeout=20):
        return Resp(respuesta(self.spy if "/SPY?" in req.full_url else self.sym))

    def hit(self, sym, bar_start="09:45", pct=1.0):
        return {"symbol": sym, "price": 101.0, "or_high": 100.5, "or_low": 99.5, "bar_start": bar_start, "pct_over": pct}

    def ahora(self, hhmm):
        return dt.datetime.strptime("%s %s" % (HOY, hhmm), "%Y-%m-%d %H:%M").replace(tzinfo=NY)

    def paso(self, datos, hhmm="09:52", pack=None, abrir=None, h=None, escanear=None):
        pack = pack or PackFalso()
        sombra.paso(self.cfg, pack, self.est, self.ahora(hhmm), h if h is not None else self.h,
                    escanear or (lambda f: datos), oq.json_de, oq.leer_json, abrir or self.abrir, lambda s: None)
        return pack


class TestPaso(Base):
    def test_registra_un_hit_fresco_una_sola_vez(self):
        orb = {"hits": [self.hit("AAA")]}
        sombra._cache_spy["clave"] = None
        self.h["ultimo_scan"] = self.ahora("09:52").timestamp()          # v1 acaba de escanear
        os.makedirs(self.est.trader, exist_ok=True)
        oq.escribir_json(self.est.ruta_trader("orb.json"), orb)
        self.paso(None)
        self.paso(None, hhmm="09:53")
        filas = self.est.leer_lineas("sombra.jsonl")
        self.assertEqual(len(filas), 1)
        f = filas[0]
        self.assertEqual((f["simbolo"], f["veredicto"], f["hora_senal"]), ("AAA", "PASA", "09:50"))
        self.assertAlmostEqual(f["rvol"], 2.0, places=2)
        self.assertEqual(f["stop"], 100.0)

    def test_etiqueta_excluyente_descarta(self):
        self.paso({"hits": [self.hit("AAA")]}, pack=PackFalso(tags=("earnings",)))
        f = self.est.leer_lineas("sombra.jsonl")[0]
        self.assertEqual(f["veredicto"], "DESCARTA")
        self.assertIn("earnings", f["tags"])

    def test_senal_vieja_no_se_registra(self):
        self.paso({"hits": [self.hit("AAA", bar_start="09:45")]}, hhmm="10:30")
        self.assertEqual(self.est.leer_lineas("sombra.jsonl"), [])
        self.assertIn("AAA", self.h["sombra"]["perdidos"])

    def test_si_yahoo_limita_se_corta_sin_romper(self):
        def abrir(req, timeout=20):
            raise http429()
        self.paso({"hits": [self.hit("AAA")]}, abrir=abrir)
        self.assertEqual(self.est.leer_lineas("sombra.jsonl"), [])
        self.assertEqual(self.h["sombra"]["limitado"], 1)

    def test_inactivo_no_hace_nada(self):
        self.cfg["sombra"]["activa"] = False
        self.paso({"hits": [self.hit("AAA")]})
        self.assertEqual(self.est.leer_lineas("sombra.jsonl"), [])

    def test_tope_de_nuevos_por_escaneo(self):
        hits = [self.hit("S%02d" % i, pct=i) for i in range(20)]
        self.paso({"hits": hits})
        self.assertEqual(len(self.est.leer_lineas("sombra.jsonl")), sombra.MAX_NUEVOS_POR_ESCANEO)

    def test_escaneo_propio_solo_si_v1_no_escanea(self):
        llamadas = []
        esc = lambda f: llamadas.append(f) or {"hits": []}  # noqa: E731
        self.h["ultimo_scan"] = self.ahora("09:52").timestamp() - 120          # v1 escaneó hace 2 min: no se duplica
        self.paso(None, escanear=esc)
        self.assertEqual(llamadas, [])
        self.h["ultimo_scan"] = self.ahora("09:52").timestamp() - 900          # v1 bloqueado (posición abierta): v2 escanea
        self.paso(None, escanear=esc)
        self.assertEqual(llamadas, ["trader/orb_sombra.json"])


class TestResolverEInforme(Base):
    def test_resuelve_una_vez_y_no_duplica(self):
        h = self.hit("AAA")
        h.update(price=100.4, or_low=99.0)          # stop 99,75: el precio plano de 100 no lo toca
        self.paso({"hits": [h]})
        n = sombra.resolver(self.est, dt.date(2026, 11, 9), abrir=self.abrir, dormir=lambda s: None)
        self.assertEqual(n, 1)
        self.assertEqual(sombra.resolver(self.est, dt.date(2026, 11, 9), abrir=self.abrir, dormir=lambda s: None), 0)
        res = self.est.leer_lineas("sombra_resultados.jsonl")
        self.assertEqual((res[0]["simbolo"], res[0]["motivo"]), ("AAA", "horario"))

    def test_informe_sin_datos_suficientes_no_concluye(self):
        self.paso({"hits": [self.hit("AAA")]})
        sombra.resolver(self.est, dt.date(2026, 11, 9), abrir=self.abrir, dormir=lambda s: None)
        a = sombra.analizar(self.est)
        self.assertFalse(a["suficiente"])
        self.assertEqual(a["grupos"]["PASA"]["n"], 1)
        self.assertIn("NO hay datos suficientes", sombra.texto_informe(a))

    def test_informe_con_datos_suficientes(self):
        for i in range(40):
            dia = (dt.date(2026, 10, 1) + dt.timedelta(days=i)).isoformat()
            for k, (ver, r) in enumerate((("PASA", 0.6 if i % 2 else -0.2), ("DESCARTA", -0.3 if i % 2 else 0.1))):
                self.est.agregar("sombra.jsonl", {"fecha": dia, "simbolo": "%s%d" % (ver[:1], i), "veredicto": ver})
                self.est.agregar("sombra_resultados.jsonl", {"fecha": dia, "simbolo": "%s%d" % (ver[:1], i), "r": r})
        a = sombra.analizar(self.est)
        self.assertTrue(a["suficiente"])
        self.assertIsNotNone(a["p"])
        self.assertIn("Prueba principal", sombra.texto_informe(a))

    def test_permutacion_reproducible(self):
        a, b = [1, 1, 1, 1, 1], [-1, -1, -1, -1, -1]
        p1, p2 = sombra.permutacion(a, b, veces=500), sombra.permutacion(a, b, veces=500)
        self.assertEqual(p1, p2)
        self.assertLess(p1, 0.05)
        self.assertIsNone(sombra.permutacion([], b))


if __name__ == "__main__":
    unittest.main()
