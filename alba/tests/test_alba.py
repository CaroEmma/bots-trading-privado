"""Tests offline de ALBA (sin red, sin dinero, sin claves). Correr:
    python3 -m unittest discover -s alba/tests -v
"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import orquestador as oq  # noqa: E402
from alpaca_paper import AlpacaPaper, ErrorAlpaca, ModoRealNoAutorizado, URL_PAPER  # noqa: E402
from notificar import Notificador  # noqa: E402

CFG = oq.leer_json(os.path.join(os.path.dirname(AQUI), "config.json"))
FIX = "/home/user/jakeschincariol/day-trader-skill/tests/fixtures"  # solo para el end-to-end opcional


def ny(texto):
    return dt.datetime.strptime(texto, "%Y-%m-%d %H:%M").replace(tzinfo=oq.NY)


class BrokerFalso:
    def __init__(self, abierto=True):
        self.abierto, self.pos, self.ordenes, self.colocadas, self.cerradas = abierto, {}, {}, [], []
        self.fill_precio = 102.0
        self.secuencia = []          # lista de (abierto, timestamp); se consume de a uno
        self.timestamp = "2026-11-09T10:15:00.123456789-05:00"
        self.next_open = "2026-11-10T09:30:00-05:00"
        self.fallar = 0              # cuántas llamadas a reloj() deben fallar
        self.llamadas_reloj = 0

    def reloj(self):
        self.llamadas_reloj += 1
        if self.fallar > 0:
            self.fallar -= 1
            raise RuntimeError("sin red")
        abierto, ts = self.secuencia.pop(0) if self.secuencia else (self.abierto, self.timestamp)
        return {"is_open": abierto, "timestamp": ts, "next_open": self.next_open}

    def posiciones(self):
        return dict(self.pos)

    def posicion(self, s):
        return self.pos.get(s)

    def orden(self, oid, con_patas=True):
        return self.ordenes[oid]

    def colocar_bracket(self, s, qty, tp, sl):
        oid = "o%d" % (len(self.colocadas) + 1)
        self.colocadas.append((s, qty, tp, sl))
        self.pos[s] = {"qty": float(qty), "avg": self.fill_precio, "valor": qty * self.fill_precio}
        self.ordenes[oid] = {"id": oid, "legs": []}
        return {"id": oid}

    def esperar_fill(self, oid, **kw):
        return self.fill_precio

    def cancelar_ordenes(self, s):
        pass

    def cerrar_posicion(self, s):
        self.cerradas.append(s)
        self.pos.pop(s, None)
        return "cierre-" + s


class PackFalso:
    """Simula las salidas de las skills escribiendo los mismos archivos que las reales."""

    def __init__(self, est, mc_r=0.2, riesgo="PASS", qty="9", entry_status="triggered", minutes_since=0):
        self.est, self.mc_r, self.riesgo, self.qty = est, mc_r, riesgo, qty
        self.entry_status, self.minutes_since, self.llamadas = entry_status, minutes_since, []
        self.hit_prices = {}

    def correr(self, skill, args):
        self.llamadas.append((skill, tuple(args)))
        t = self.est.ruta_trader
        if skill == "scanner" and args[0] == "universe":
            with open(t("universe.txt"), "w") as f:
                f.write("TSLA|Tesla\n")
            return 0, "", ""
        if skill == "scanner":
            oq.escribir_json(t("orb.json"), {"hits": [
                {"symbol": "TSLA", "price": 102.0, "or_high": 101.0, "or_low": 99.0, "pct_over": 0.9},
                {"symbol": "CARA", "price": 900.0, "or_high": 880.0, "or_low": 700.0, "pct_over": 0.1}]})
            return 0, "", ""
        if skill == "news":
            return 0, json.dumps({"items": [{"title": "Tesla sube", "tags": ["analyst"]}]}), ""
        if skill == "entry":
            return 0, json.dumps({"status": self.entry_status, "minutes_since": self.minutes_since,
                                  "reason": "la barra de las 10:10 cerró sobre el rango"}), ""
        if skill == "exit":
            oq.escribir_json(t("plan.json"), {"symbol": "TSLA", "entry": 102.0, "stop": 100.0, "target": 106.0})
            return 0, "", ""
        if skill == "timemachine":
            oq.escribir_json(t("timemachine.json"), {
                "mc": {"avg_R": self.mc_r, "p_target": 0.4, "p_stop": 0.3},
                "history": {"triggered": 34, "avg_R": -0.067}, "verdict": "x"})
            return 0, "", ""
        if skill == "size":
            if self.qty is None:
                return 0, "No order: ...", ""
            oq.escribir_json(t("orders.json"), {"orders": [{
                "symbol": "TSLA", "side": "buy", "qty": self.qty, "type": "market", "time_in_force": "day",
                "order_class": "bracket", "take_profit_limit_price": "106.00", "stop_loss_stop_price": "100.00",
                "plan": {"entry": 102.0, "stop": 100.0, "target": 106.0, "max_loss": 18.0, "reward_risk": 2.0}}]})
            return 0, "", ""
        if skill == "risk":
            return 0, json.dumps({"results": [{"verdict": self.riesgo, "fingerprint": "abc",
                                               "reasons": [] if self.riesgo == "PASS" else ["loss: demasiado"]}]}), ""
        return 0, "", ""


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.est = oq.Estado(self.dir)
        self.notif = Notificador(entorno={})
        self.broker = BrokerFalso()
        self.cfg = json.loads(json.dumps(CFG))
        self.cfg["pausa_cierre_s"] = 0
        self._sleep, oq.time.sleep = oq.time.sleep, (lambda s: None)

    def tearDown(self):
        oq.time.sleep = self._sleep
        shutil.rmtree(self.dir, ignore_errors=True)

    def ciclo(self, pack, hora="2026-11-09 10:15"):
        return oq.ciclo(self.cfg, self.broker, pack, self.est, self.notif, ny(hora))


class TestSeguridad(unittest.TestCase):
    def test_solo_paper(self):
        with self.assertRaises(ModoRealNoAutorizado):
            AlpacaPaper("k", "s", base="https://api.alpaca.markets")
        AlpacaPaper("k", "s", base=URL_PAPER)

    def test_exige_claves(self):
        with self.assertRaises(RuntimeError):
            AlpacaPaper("", "")

    def test_payload_bracket(self):
        visto = {}

        def http(m, ruta, params=None, cuerpo=None):
            visto.update(m=m, ruta=ruta, cuerpo=cuerpo)
            return {"id": "x"}
        AlpacaPaper("k", "s", http=http).colocar_bracket("TSLA", 9, "361.784", 351.2)
        c = visto["cuerpo"]
        self.assertEqual((visto["m"], visto["ruta"]), ("POST", "/v2/orders"))
        self.assertEqual((c["side"], c["order_class"], c["qty"], c["time_in_force"]), ("buy", "bracket", "9", "gtc"))
        self.assertEqual((c["take_profit"]["limit_price"], c["stop_loss"]["stop_price"]), ("361.78", "351.20"))

    def test_sin_claves_no_hace_nada(self):
        for v in ("ALBA_ALPACA_KEY", "ALBA_ALPACA_SECRET"):
            os.environ.pop(v, None)
        self.assertEqual(oq.main(["--estado", tempfile.mkdtemp()]), 0)


class TestNotificador(unittest.TestCase):
    def test_issue_y_telegram(self):
        env = {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r", "ALBA_TELEGRAM_TOKEN": "tt", "ALBA_TELEGRAM_CHAT": "9"}
        llamadas = []
        n = Notificador(mencionar="CaroEmma", enviar=lambda *a, **k: llamadas.append((a, k)), entorno=env)
        n.avisar("titulo", "cuerpo")
        self.assertEqual(len(llamadas), 2)
        self.assertIn("api.github.com/repos/o/r/issues", llamadas[0][0][0])
        self.assertIn("@CaroEmma", llamadas[0][0][1]["body"])
        self.assertIn("api.telegram.org", llamadas[1][0][0])

    def test_un_fallo_no_rompe(self):
        def boom(*a, **k):
            raise OSError("sin red")
        Notificador(enviar=boom, entorno={"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r"}).avisar("a", "b")


class TestEstadisticas(unittest.TestCase):
    def test_numeros(self):
        e = oq.estadisticas([{"pnl": 10, "r": 1.0}, {"pnl": -5, "r": -1.0}, {"pnl": 10, "r": 1.0}])
        self.assertEqual(e["n"], 3)
        self.assertAlmostEqual(e["tasa_acierto"], 2 / 3)
        self.assertAlmostEqual(e["factor_beneficio"], 4.0)
        self.assertAlmostEqual(e["caida_maxima"], 5.0)
        self.assertIn("NO permite concluir", oq.texto_estadisticas(e))


class TestCiclo(Base):
    def test_compra_completa(self):
        pack = PackFalso(self.est)
        self.assertEqual(self.ciclo(pack), "operando")
        self.assertEqual(self.broker.colocadas, [("TSLA", 9, "106.00", "100.00")])
        self.assertIn("TSLA", self.est.d["abiertas"])
        self.assertEqual(self.est.d["hoy"]["entradas"], 1)
        self.assertTrue(any("COMPRA TSLA" in t for t, _ in self.notif.enviado))
        reg = oq.leer_json(self.est.ruta_trader("state/broker.json"))["orders"][0]
        self.assertEqual((reg["status"], reg["kind"], reg["auto_paper"]), ("placed", "entry", True))
        self.assertNotIn("reply", reg)  # nunca se inventa un "yes" humano
        # CARA (acción de $900) se descartó antes de gastar llamadas: ni una acción entra en la pérdida máxima
        self.assertEqual(self.est.d["hoy"]["evaluados"]["CARA"][:8], "omitida:")
        self.assertNotIn(("entry", ("check", "CARA", "--write", "--json")), pack.llamadas)

    def test_gate_timemachine(self):
        self.ciclo(PackFalso(self.est, mc_r=-0.1))
        self.assertEqual(self.broker.colocadas, [])
        self.assertIn("timemachine", self.est.d["hoy"]["evaluados"]["TSLA"])

    def test_risk_block(self):
        self.ciclo(PackFalso(self.est, riesgo="BLOCK"))
        self.assertEqual(self.broker.colocadas, [])
        self.assertIn("risk BLOCK", self.est.d["hoy"]["evaluados"]["TSLA"])

    def test_sin_acciones_en_budget(self):
        self.ciclo(PackFalso(self.est, qty=None))
        self.assertEqual(self.broker.colocadas, [])

    def test_senal_vieja(self):
        self.ciclo(PackFalso(self.est, minutes_since=45))
        self.assertEqual(self.broker.colocadas, [])
        self.assertIn("señal vieja", self.est.d["hoy"]["evaluados"]["TSLA"])

    def test_no_reevalua_el_mismo_simbolo(self):
        pack = PackFalso(self.est, mc_r=-1)
        self.ciclo(pack)
        n = len([c for c in pack.llamadas if c[0] == "entry"])
        self.ciclo(pack, hora="2026-11-09 10:21")
        self.assertEqual(len([c for c in pack.llamadas if c[0] == "entry"]), n)

    def test_limite_de_trades_del_dia(self):
        self.ciclo(PackFalso(self.est))
        self.est.d["abiertas"].clear()
        self.broker.pos.clear()
        self.est.d["hoy"]["entradas"] = self.cfg["pack_config"]["max_trades_per_day"]
        self.est.d["hoy"]["evaluados"].clear()
        self.broker.colocadas.clear()
        self.ciclo(PackFalso(self.est))
        self.assertEqual(self.broker.colocadas, [])

    def test_limite_de_perdida_diaria(self):
        estado_del = oq.estado_del_dia(self.est, "2026-11-09")
        estado_del["pnl"] = -self.cfg["pack_config"]["max_daily_loss_usd"]
        self.ciclo(PackFalso(self.est))
        self.assertEqual(self.broker.colocadas, [])

    def test_fuera_de_ventana(self):
        self.ciclo(PackFalso(self.est), hora="2026-11-09 09:35")
        self.assertEqual(self.broker.colocadas, [])
        self.ciclo(PackFalso(self.est), hora="2026-11-09 15:35")
        self.assertEqual(self.broker.colocadas, [])

    def test_cierre_por_objetivo(self):
        pack = PackFalso(self.est)
        self.ciclo(pack)
        self.broker.pos.clear()  # el servidor cerró por el take-profit
        self.broker.ordenes["o1"]["legs"] = [{"type": "limit", "status": "filled", "filled_avg_price": "106.00"}]
        self.ciclo(pack, hora="2026-11-09 11:00")
        ops = self.est.leer_lineas("operaciones.jsonl")
        self.assertEqual(len(ops), 1)
        self.assertEqual((ops[0]["motivo"], ops[0]["r"], ops[0]["pnl"]), ("objetivo", 2.0, 36.0))
        self.assertEqual(self.est.d["abiertas"], {})
        self.assertTrue(any("OBJETIVO" in t for t, _ in self.notif.enviado))

    def test_cierre_por_stop(self):
        pack = PackFalso(self.est)
        self.ciclo(pack)
        self.broker.pos.clear()
        self.broker.ordenes["o1"]["legs"] = [{"type": "stop", "status": "filled", "filled_avg_price": "100.00"}]
        self.ciclo(pack, hora="2026-11-09 11:00")
        op = self.est.leer_lineas("operaciones.jsonl")[0]
        self.assertEqual((op["motivo"], op["pnl"]), ("stop", -18.0))
        self.assertAlmostEqual(op["r"], -1.0)
        self.assertAlmostEqual(self.est.d["hoy"]["pnl"], -18.0)

    def test_cierre_horario(self):
        pack = PackFalso(self.est)
        self.ciclo(pack)
        self.broker.fill_precio = 101.0
        self.assertEqual(self.ciclo(pack, hora="2026-11-09 15:41"), "cierre")
        self.assertEqual(self.broker.cerradas, ["TSLA"])
        op = self.est.leer_lineas("operaciones.jsonl")[0]
        self.assertEqual((op["motivo"], op["pnl"], op["r"]), ("cierre_horario", -9.0, -0.5))
        self.assertEqual(self.est.d["abiertas"], {})

    def test_salida_desconocida_se_avisa(self):
        self.ciclo(PackFalso(self.est))
        self.broker.pos.clear()
        self.ciclo(PackFalso(self.est), hora="2026-11-09 11:00")
        self.assertTrue(any("ATENCIÓN" in t for t, _ in self.notif.enviado))
        self.assertEqual(self.est.leer_lineas("operaciones.jsonl"), [])

    def test_informe_diario_una_sola_vez(self):
        pack = PackFalso(self.est)
        self.ciclo(pack)
        self.broker.abierto = False
        self.ciclo(pack, hora="2026-11-09 16:10")
        self.ciclo(pack, hora="2026-11-09 16:15")
        self.assertEqual(len([t for t, _ in self.notif.enviado if "Informe diario" in t]), 1)

    def test_mercado_cerrado_no_opera(self):
        self.broker.abierto = False
        self.assertEqual(self.ciclo(PackFalso(self.est), hora="2026-11-08 12:00"), "cerrado")
        self.assertEqual(self.broker.colocadas, [])


class _Resp:
    def __init__(self, datos):
        self._d = json.dumps(datos).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._d


def _http_error(codigo, descripcion):
    import io
    import urllib.error
    return urllib.error.HTTPError("u", codigo, "x", {}, io.BytesIO(json.dumps({"ok": False, "description": descripcion}).encode()))


class TestTelegram(Base):
    TOKEN_OK = "123456789:AAH_abc-DEF1234567890abcdefghijk"
    ENV = {"ALBA_TELEGRAM_TOKEN": "123456789:AAH_abc-DEF1234567890abcdefghijk", "ALBA_TELEGRAM_CHAT": "9"}

    def test_texto_plano_sin_markdown(self):
        from notificar import _plano
        self.assertEqual(_plano("**TSLA** compra\n_Dinero ficticio (paper)._"), "TSLA compra\nDinero ficticio (paper).")

    def test_cada_compra_y_cada_venta_llegan_a_telegram(self):
        envios = []
        self.notif = Notificador(entorno=self.ENV, enviar=lambda url, cuerpo, headers, form=False: envios.append((url, cuerpo)))
        pack = PackFalso(self.est)
        self.ciclo(pack)
        self.broker.pos.clear()
        self.broker.ordenes["o1"]["legs"] = [{"type": "limit", "status": "filled", "filled_avg_price": "106.00"}]
        self.ciclo(pack, hora="2026-11-09 11:00")
        textos = [c["text"] for u, c in envios if "api.telegram.org" in u]
        self.assertEqual(len(textos), 2)
        self.assertIn("COMPRA TSLA", textos[0])
        self.assertIn("US$ 100,00", textos[0])            # stop, en formato rioplatense
        self.assertIn("OBJETIVO TSLA", textos[1])
        self.assertIn("+US$ 36,00", textos[1])
        self.assertIn("Objetivo alcanzado", textos[1])
        self.assertTrue(all("**" not in x for x in textos))
        self.assertTrue(all(c.get("parse_mode") == "HTML" for u, c in envios if "api.telegram.org" in u))
        self.assertFalse(any(" the " in x.split("Noticias")[0] for x in textos))   # nada en inglés fuera de los titulares
        self.assertTrue(all(c["chat_id"] == "9" for u, c in envios if "api.telegram.org" in u))

    def test_si_telegram_rechaza_el_formato_se_reenvia_en_texto_plano(self):
        envios = []

        def enviar(url, cuerpo, headers, form=False):
            envios.append(cuerpo)
            if cuerpo.get("parse_mode") == "HTML":
                raise RuntimeError("Bad Request: can't parse entities")
        Notificador(entorno=self.ENV, enviar=enviar).avisar("ALBA | COMPRA X", "**X** compra", telegram="<b>mal")
        self.assertEqual(len(envios), 2)
        self.assertEqual(envios[0]["parse_mode"], "HTML")
        self.assertNotIn("parse_mode", envios[1])
        self.assertIn("COMPRA X", envios[1]["text"])

    def test_formato_numeros_rioplatense_y_escape(self):
        import formato
        self.assertEqual(formato.num(1234.5), "1.234,50")
        self.assertEqual(formato.usd(-18), "-US$ 18,00")
        self.assertEqual(formato.usd(85.951, True), "+US$ 85,95")
        self.assertEqual(formato.num(-0.0001), "0,00")                     # sin "-0,00"
        self.assertIn("&lt;script&gt;", formato.alerta("t", "<script>"))   # un error con < > no rompe el HTML
        self.assertEqual(formato.senal_es("the 9:45 bar closed above the range high"),
                         "la vela de las 9:45 cerró por encima del máximo del rango de apertura")
        self.assertEqual(formato.senal_es("algo desconocido"), "ruptura del rango de apertura")

    def test_informe_diario_en_telegram_tiene_tabla_y_aviso_de_muestra_chica(self):
        import formato
        ops = [{"simbolo": "SPCX", "entrada": 141.77, "salida": 147.5, "motivo": "objetivo", "r": 1.69, "pnl": 85.95}]
        acum = oq.estadisticas([dict(o) for o in ops])
        txt = formato.informe_diario("2026-11-09", ops, {"timemachine": 3}, 85.95, acum)
        self.assertIn("INFORME DIARIO ALBA", txt)
        self.assertIn("141,77 → 147,50", txt)
        self.assertIn("Muestra chica", txt)
        self.assertLess(len(txt), 3900)

    def test_limpio_saca_espacios_saltos_y_comillas(self):
        from notificar import limpio, token_con_formato
        self.assertEqual(limpio('  "123456789:AAH_abc-DEF1234567890abcdefghijk"\n'), "123456789:AAH_abc-DEF1234567890abcdefghijk")
        self.assertTrue(token_con_formato("123456789:AAH_abc-DEF1234567890abcdefghijk"))
        self.assertFalse(token_con_formato("token: 123456789:AAH_abc-DEF1234567890abcdefghijk"))
        self.assertFalse(token_con_formato("ALBA-AVISOS"))
        self.assertFalse(token_con_formato(None))

    def test_un_token_pegado_con_salto_de_linea_se_usa_igual(self):
        envios = []
        env = {"ALBA_TELEGRAM_TOKEN": "123456789:AAH_abc-DEF1234567890abcdefghijk\n", "ALBA_TELEGRAM_CHAT": " 9 "}
        Notificador(entorno=env, enviar=lambda url, cuerpo, headers, form=False: envios.append((url, cuerpo))).avisar("t", "c")
        self.assertEqual(envios[0][0], "https://api.telegram.org/bot123456789:AAH_abc-DEF1234567890abcdefghijk/sendMessage")
        self.assertEqual(envios[0][1]["chat_id"], "9")

    def test_cli_avisa_si_el_token_no_tiene_formato(self):
        self.assertEqual(oq.telegram_cli("descubrir", env={"ALBA_TELEGRAM_TOKEN": "esto no es un token"}), 1)

    def test_quien_es_el_bot_del_token(self):
        from notificar import telegram_quien
        r = _Resp({"ok": True, "result": {"id": 1, "is_bot": True, "first_name": "ALBA-AVISOS", "username": "alba_avisos_bot"}})
        self.assertEqual(telegram_quien("tok", abrir=lambda url, timeout: r),
                         ({"username": "alba_avisos_bot", "nombre": "ALBA-AVISOS"}, None))

        def abrir(url, timeout):
            raise _http_error(401, "Unauthorized")
        quien, error = telegram_quien("malo", abrir=abrir)
        self.assertIsNone(quien)
        self.assertIn("401", error)

    def test_descubrir_chat(self):
        from notificar import telegram_descubrir
        r = _Resp({"ok": True, "result": [{"message": {"chat": {"id": 123456, "type": "private"}}}]})
        self.assertEqual(telegram_descubrir("tok", abrir=lambda url, timeout: r), ({123456: "private"}, None))
        vacio = _Resp({"ok": True, "result": []})
        self.assertEqual(telegram_descubrir("tok", abrir=lambda url, timeout: vacio), ({}, None))

    def test_descubrir_con_token_malo(self):
        from notificar import telegram_descubrir

        def abrir(url, timeout):
            raise _http_error(401, "Unauthorized")
        chats, error = telegram_descubrir("malo", abrir=abrir)
        self.assertEqual(chats, {})
        self.assertIn("401", error)

    def test_probar_ok_y_error(self):
        from notificar import telegram_probar
        self.assertEqual(telegram_probar("t", "9", "hola", abrir=lambda r, timeout: _Resp({"ok": True})), (True, "enviado"))

        def abrir(r, timeout):
            raise _http_error(400, "Bad Request: chat not found")
        ok, detalle = telegram_probar("t", "9", "hola", abrir=abrir)
        self.assertFalse(ok)
        self.assertIn("chat not found", detalle)

    def test_cli_pide_lo_que_falta(self):
        self.assertEqual(oq.telegram_cli("probar", env={}), 1)
        self.assertEqual(oq.telegram_cli("probar", env={"ALBA_TELEGRAM_TOKEN": self.TOKEN_OK}), 1)

    def test_cli_descubrir_y_probar(self):
        resp = _Resp({"ok": True, "result": [{"message": {"chat": {"id": 55, "type": "private"}}}]})
        self.assertEqual(oq.telegram_cli("descubrir", env={"ALBA_TELEGRAM_TOKEN": self.TOKEN_OK}, abrir=lambda *a, **k: resp), 0)
        self.assertEqual(oq.telegram_cli("probar", env=self.ENV, abrir=lambda *a, **k: _Resp({"ok": True})), 0)


class TestEscaneo(Base):
    def test_el_escaner_corre_cada_cinco_minutos(self):
        pack = PackFalso(self.est, mc_r=-1)
        orb = lambda: len([c for c in pack.llamadas if c[0] == "scanner" and c[1][0] == "orb"])  # noqa: E731
        self.ciclo(pack, hora="2026-11-09 10:15")
        self.ciclo(pack, hora="2026-11-09 10:17")
        self.assertEqual(orb(), 1)
        self.ciclo(pack, hora="2026-11-09 10:21")
        self.assertEqual(orb(), 2)


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class TestSesion(Base):
    def correr(self, pack=None, duracion=None, publicar=None):
        mono = Reloj()
        dormidos = []

        def dormir(s):
            dormidos.append(s)
            mono.t += s
        oq.sesion(self.cfg, self.broker, pack or PackFalso(self.est), self.est, self.notif,
                  duracion_max_min=duracion, dormir=dormir, mono=mono, publicar=publicar)
        return dormidos

    def test_termina_si_esta_cerrado_y_no_hay_nada_pendiente(self):
        self.broker.abierto = False
        self.broker.timestamp = "2026-11-08T12:00:00-05:00"   # domingo; la apertura es en ~21 h
        self.assertEqual(self.correr(), [])
        self.assertEqual(self.broker.llamadas_reloj, 1)

    def test_espera_una_apertura_cercana(self):
        self.broker.next_open = "2026-11-09T09:30:00-05:00"
        self.broker.secuencia = [(False, "2026-11-09T09:00:00-05:00"), (False, "2026-11-09T09:01:00-05:00"),
                                 (True, "2026-11-09T09:02:00-05:00")]
        dormidos = self.correr(duracion=120)
        self.assertGreaterEqual(len(dormidos), 2)

    def test_no_espera_una_apertura_que_no_alcanza_a_ver(self):
        self.broker.next_open = "2026-11-09T09:30:00-05:00"
        self.broker.secuencia = [(False, "2026-11-09T09:00:00-05:00")]
        self.assertEqual(self.correr(duracion=5), [])

    def test_respeta_la_duracion_maxima(self):
        dormidos = self.correr(duracion=3)
        self.assertEqual(len(dormidos), 3)
        self.assertEqual(self.broker.llamadas_reloj, 4)

    def test_espera_el_informe_diario_tras_el_cierre(self):
        oq.estado_del_dia(self.est, "2026-11-09")
        self.est.d["hoy"].update(sesion=True, universo=True)
        self.broker.abierto = False
        self.broker.secuencia = [(False, "2026-11-09T16:01:00-05:00"), (False, "2026-11-09T16:06:00-05:00")]
        self.broker.timestamp = "2026-11-09T16:06:00-05:00"
        dormidos = self.correr()
        self.assertEqual(dormidos, [60])
        self.assertEqual(len([t for t, _ in self.notif.enviado if "Informe diario" in t]), 1)

    def test_un_error_pasajero_no_tira_la_sesion(self):
        self.broker.abierto = False
        self.broker.timestamp = "2026-11-08T12:00:00-05:00"
        self.broker.fallar = 1
        self.assertEqual(self.correr(), [60])
        self.assertTrue(any("ERROR" in t for t, _ in self.notif.enviado))

    def test_errores_seguidos_se_propagan(self):
        self.broker.fallar = 999
        self.cfg["sesion"]["errores_seguidos_max"] = 3
        with self.assertRaises(RuntimeError):
            self.correr()

    def test_publica_el_estado(self):
        llamadas = []
        self.cfg["sesion"]["publicar_cada_min"] = 1
        self.correr(duracion=3, publicar=lambda: llamadas.append(1))
        self.assertGreaterEqual(len(llamadas), 2)


class TestPublicarEstado(unittest.TestCase):
    """Replica el armado del workflow (rama huérfana en un worktree) contra un remoto local."""

    def test_publica_en_la_rama_alba_estado(self):
        import subprocess
        raiz = tempfile.mkdtemp()
        try:
            def g(*a, cwd=raiz):
                return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout
            g("init", "-q", "--bare", "-b", "main", "remoto.git")
            g("clone", "-q", "remoto.git", "repo")
            repo = os.path.join(raiz, "repo")
            g("config", "user.email", "t@t", cwd=repo)
            g("config", "user.name", "t", cwd=repo)
            open(os.path.join(repo, "a.txt"), "w").close()
            g("add", ".", cwd=repo)
            g("commit", "-q", "-m", "init", cwd=repo)
            g("push", "-q", "origin", "HEAD:main", cwd=repo)
            g("worktree", "add", "-q", "--detach", "estado", "HEAD", cwd=repo)
            estado = os.path.join(repo, "estado")
            g("checkout", "-q", "--orphan", "alba-estado", cwd=estado)
            g("rm", "-rq", "--cached", ".", cwd=estado)
            os.remove(os.path.join(estado, "a.txt"))
            with open(os.path.join(estado, "alba_estado.json"), "w") as f:
                f.write("{}")
            oq.publicar_estado(estado)
            self.assertIn("alba_estado.json", g("ls-tree", "--name-only", "alba-estado", cwd=os.path.join(raiz, "remoto.git")))
            self.assertNotIn("a.txt", g("ls-tree", "--name-only", "alba-estado", cwd=os.path.join(raiz, "remoto.git")))
            with open(os.path.join(estado, "alba_estado.json"), "w") as f:
                f.write('{"x": 1}')
            oq.publicar_estado(estado)   # segundo push: incremental
            self.assertEqual(g("rev-list", "--count", "alba-estado", cwd=os.path.join(raiz, "remoto.git")).strip(), "2")
            oq.publicar_estado(estado)   # sin cambios: no crea commit
            self.assertEqual(g("rev-list", "--count", "alba-estado", cwd=os.path.join(raiz, "remoto.git")).strip(), "2")
        finally:
            shutil.rmtree(raiz, ignore_errors=True)


@unittest.skipUnless(os.path.isdir(FIX), "fixtures del repo original no disponibles")
class TestExtremoAExtremoConSkillsReales(Base):
    """Cadena REAL entry -> exit -> timemachine -> budget -> risk sobre datos guardados (TSLA, 2026-10-19 10:15)."""

    def test_cadena_real(self):
        now = "2026-10-19 10:15"
        f = FIX + "/trader-entry/TSLA-2026-10-19-5m.json"
        extra = {"entry": ["--offline", f, "--now", now], "exit": ["--offline", f, "--now", now],
                 "timemachine": ["--offline", FIX + "/trader-timemachine/TSLA-60d5m.json.gz", "--now", now],
                 "size": ["--now", now], "risk": ["--now", now, "--no-write"], "news": ["--offline", FIX + "/trader-news", "--now", now],
                 "alerts": ["--offline", self.dir + "/no-existe"], "ticket": ["--now", now]}
        pack = oq.Pack(self.dir, extra=extra)
        self.cfg["estrategia"]["max_edad_senal_min"] = 600
        self.cfg["estrategia"]["gate_timemachine"] = "off"
        oq.escribir_config_pack(self.est, self.cfg)
        h = oq.estado_del_dia(self.est, "2026-10-19")
        ok = oq.evaluar(self.cfg, self.broker, pack, self.est, self.notif, ny(now), h,
                        {"symbol": "TSLA", "price": 364.18, "or_high": 362.18, "or_low": 354.47})
        self.assertTrue(ok, h["evaluados"])
        s, qty, tp, sl = self.broker.colocadas[0]
        self.assertEqual(s, "TSLA")
        self.assertGreater(qty, 0)
        self.assertLess(float(sl), float(tp))
        # la pérdida máxima en el stop respeta el límite de la config
        self.assertLessEqual(qty * (364.18 - float(sl)), self.cfg["pack_config"]["max_loss_per_trade_usd"] + 0.01)


if __name__ == "__main__":
    unittest.main()
