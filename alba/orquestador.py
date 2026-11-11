#!/usr/bin/env python3
"""ALBA: day trading de acciones de EE. UU. con las skills de day-trader-skill, sin intervención.

Corre UN ciclo por ejecución (lo lanza el cron de GitHub Actions cada 5 min). Cada ciclo:
  1. concilia con Alpaca Paper: detecta posiciones cerradas por stop/target y las registra;
  2. si el mercado está abierto y es hora de cerrar (>= cerrar_desde), cierra todo;
  3. si no, y hay lugar para operar: scanner -> news -> entry -> exit -> timemachine ->
     budget -> risk y, SOLO si trader-risk da PASS, manda la orden bracket a Alpaca PAPER;
  4. avisa cada entrada / salida y arma el informe diario con estadísticas.

Seguridad: solo paper (ver alpaca_paper.py). Las claves salen de variables de entorno.
Este flujo reemplaza el "yes" manual del pack SOLO en paper, por pedido expreso del usuario
(2026-11-08). Para dinero real hay que pedir autorización humana por cada orden.
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

from alpaca_paper import AlpacaPaper, ErrorAlpaca, claves_desde_entorno  # noqa: E402
import formato  # noqa: E402
import sombra  # noqa: E402
from notificar import Notificador, limpio, telegram_descubrir, telegram_probar, telegram_quien, token_con_formato  # noqa: E402

VENDOR = os.path.join(AQUI, "vendor", "day-trader-skill")
SCRIPTS = {
    "scanner": "trader-scanner/scan.py", "news": "trader-news/news.py", "entry": "trader-entry/entry.py",
    "exit": "trader-exit/exit.py", "timemachine": "trader-timemachine/timemachine.py",
    "size": "trader-budget/size.py", "risk": "trader-risk/check.py", "ticket": "trader-broker/ticket.py",
    "alerts": "trader-alerts/alerts.py",
}
NY = ZoneInfo("America/New_York")
ARCHIVOS_DE_CANDIDATO = ("entry.json", "plan.json", "timemachine.json", "orders.json")


# ============================================================ utilidades
def leer_json(ruta, defecto=None):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def escribir_json(ruta, dato):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dato, f, indent=1, ensure_ascii=False)
    os.replace(tmp, ruta)


def parsear_fecha(texto):
    texto = re.sub(r"(\.\d{6})\d+", r"\1", texto.replace("Z", "+00:00"))
    return dt.datetime.fromisoformat(texto)


def hora_ar(ahora):
    """La misma hora en Argentina (para los avisos de Telegram)."""
    return ahora.astimezone(ZoneInfo("America/Argentina/Buenos_Aires"))


def usd(x):
    return ("-" if x < 0 else "") + "$%.2f" % abs(x)


def usd_s(x):
    return ("+" if x >= 0 else "-") + "$%.2f" % abs(x)


def signo(x, dec=2):
    return ("+" if x >= 0 else "") + ("%." + str(dec) + "f") % x


# ============================================================ pack (skills)
class Pack:
    """Ejecuta los scripts del pack (copia fijada en vendor/) como procesos aparte, aislados (-I)."""

    def __init__(self, cwd, extra=None, timeout=300):
        self.cwd, self.extra, self.timeout = cwd, extra or {}, timeout

    def correr(self, skill, args):
        cmd = [sys.executable, "-I", os.path.join(VENDOR, SCRIPTS[skill]), *args, *self.extra.get(skill, [])]
        try:
            p = subprocess.run(cmd, cwd=self.cwd, capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return 124, "", "timeout tras %ss" % self.timeout
        return p.returncode, p.stdout, p.stderr


def json_de(texto):
    """El primer objeto JSON de la salida estándar (los scripts a veces imprimen texto antes)."""
    i = texto.find("{")
    if i < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(texto[i:])[0]
    except ValueError:
        return None


# ============================================================ estado
class Estado:
    def __init__(self, directorio):
        self.dir = directorio
        self.trader = os.path.join(directorio, "trader")
        os.makedirs(os.path.join(self.trader, "state"), exist_ok=True)
        self.ruta = os.path.join(directorio, "alba_estado.json")
        self.d = leer_json(self.ruta, {}) or {}
        self.d.setdefault("abiertas", {})
        self.d.setdefault("hoy", {})

    def guardar(self):
        escribir_json(self.ruta, self.d)

    def agregar(self, nombre, registro):
        with open(os.path.join(self.dir, nombre), "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")

    def leer_lineas(self, nombre):
        out = []
        try:
            with open(os.path.join(self.dir, nombre), encoding="utf-8") as f:
                for linea in f:
                    try:
                        out.append(json.loads(linea))
                    except ValueError:
                        pass
        except OSError:
            pass
        return out

    def ruta_trader(self, nombre):
        return os.path.join(self.trader, nombre)


def estado_del_dia(est, fecha):
    h = est.d.get("hoy") or {}
    if h.get("fecha") != fecha:
        h = {"fecha": fecha, "entradas": 0, "pnl": 0.0, "r": 0.0, "evaluados": {},
             "universo": False, "sesion": False, "informe": False}
        est.d["hoy"] = h
    return h


# ============================================================ estadísticas
def estadisticas(ops):
    n = len(ops)
    if not n:
        return {"n": 0}
    rs = [o["r"] for o in ops]
    ganadoras = [o for o in ops if o["pnl"] > 0]
    perdedoras = [o for o in ops if o["pnl"] < 0]
    bruto_g = sum(o["pnl"] for o in ganadoras)
    bruto_p = -sum(o["pnl"] for o in perdedoras)
    acumulado, pico, caida = 0.0, 0.0, 0.0
    for o in ops:
        acumulado += o["pnl"]
        pico = max(pico, acumulado)
        caida = max(caida, pico - acumulado)
    return {"n": n, "ganadoras": len(ganadoras), "perdedoras": len(perdedoras),
            "tasa_acierto": len(ganadoras) / n, "r_promedio": sum(rs) / n, "pnl": sum(o["pnl"] for o in ops),
            "factor_beneficio": (bruto_g / bruto_p) if bruto_p else None, "caida_maxima": caida}


def texto_estadisticas(e):
    if not e.get("n"):
        return "Todavía no hay operaciones cerradas."
    fb = "n/d" if e["factor_beneficio"] is None else "%.2f" % e["factor_beneficio"]
    aviso = ""
    if e["n"] < 30:
        aviso = "\n\nMuestra chica (%d operaciones): con tan pocos casos el resultado NO permite concluir " \
                "si la estrategia funciona." % e["n"]
    return ("%d operaciones | acierto %.0f%% | R promedio %s | resultado %s | factor de beneficio %s | "
            "caída máxima %s%s" % (e["n"], e["tasa_acierto"] * 100, signo(e["r_promedio"], 3), usd(e["pnl"]), fb,
                                   usd(e["caida_maxima"]), aviso))


# ============================================================ pasos del pack
def escribir_config_pack(est, cfg):
    pc = dict(cfg["pack_config"])
    pc["paper"] = True
    pc["broker"] = "alpaca"
    escribir_json(est.ruta_trader("config.json"), pc)


def limpiar_candidato(est):
    for n in ARCHIVOS_DE_CANDIDATO:
        try:
            os.remove(est.ruta_trader(n))
        except OSError:
            pass


def registrar_decision(est, ahora, simbolo, accion, motivo, **datos):
    reg = {"fecha": ahora.date().isoformat(), "hora": ahora.strftime("%H:%M"), "simbolo": simbolo,
           "accion": accion, "motivo": motivo}
    reg.update(datos)
    est.agregar("decisiones.jsonl", reg)
    return reg


def omitir(est, h, ahora, simbolo, motivo, **datos):
    h["evaluados"][simbolo] = "omitida: " + motivo
    print("  - %s omitida: %s" % (simbolo, motivo), flush=True)
    return registrar_decision(est, ahora, simbolo, "omitir", motivo, **datos)


def evaluar(cfg, broker, pack, est, notif, ahora, h, hit):
    """Cadena completa de skills para UN candidato. Devuelve True si compró."""
    sym = hit["symbol"]
    pc, ec = cfg["pack_config"], cfg["estrategia"]
    limpiar_candidato(est)

    # 1) noticias (informativo; solo un 'halt' frena)
    titulares = []
    rc, out, _ = pack.correr("news", ["--tickers", sym, "--hours", "24", "--no-sec", "--json"])
    nj = json_de(out) if rc in (0, 1) else None
    for it in (nj or {}).get("items", []):
        tags = [str(t).lower() for t in (it.get("tags") or [])]
        titulares.append(str(it.get("title") or it.get("headline") or "")[:140])
        if "halt" in tags:
            return omitir(est, h, ahora, sym, "noticia con 'halt' (suspensión)") and False

    # 2) entrada
    rc, out, err = pack.correr("entry", ["check", sym, "--write", "--json"])
    ej = json_de(out)
    if not ej:
        return omitir(est, h, ahora, sym, "entry sin datos (%s)" % (err.strip()[:80] or "salida vacía")) and False
    if ej.get("status") != "triggered":
        return omitir(est, h, ahora, sym, "entry: %s" % ej.get("status")) and False
    edad = ej.get("minutes_since")
    if edad is not None and edad > ec["max_edad_senal_min"]:
        return omitir(est, h, ahora, sym, "señal vieja (%s min)" % edad) and False

    # 3) salida (stop y objetivo)
    rc, out, err = pack.correr("exit", ["plan", "--write", "--stop", ec["stop"], "--target", ec["objetivo"]])
    plan = leer_json(est.ruta_trader("plan.json"))
    if rc != 0 or not plan or plan.get("symbol") != sym:
        return omitir(est, h, ahora, sym, "exit: %s" % ((out + err).strip()[-120:] or "sin plan")) and False

    # 4) máquina del tiempo
    rc, out, err = pack.correr("timemachine", ["run", "--write"])
    tm = leer_json(est.ruta_trader("timemachine.json"))
    if not tm:
        return omitir(est, h, ahora, sym, "timemachine sin resultado") and False
    mc_r = (tm.get("mc") or {}).get("avg_R")
    hi = tm.get("history") or {}
    resumen_tm = {"mc_avg_R": mc_r, "p_target": (tm.get("mc") or {}).get("p_target"),
                  "p_stop": (tm.get("mc") or {}).get("p_stop"), "hist_disparos": hi.get("triggered"),
                  "hist_avg_R": hi.get("avg_R"), "veredicto": tm.get("verdict")}
    gate = ec["gate_timemachine"]
    if gate in ("solo_mc", "mc_y_historia") and not (mc_r is not None and mc_r > 0):
        return omitir(est, h, ahora, sym, "timemachine: R promedio simulado %s no es > 0" % mc_r, tm=resumen_tm) and False
    if gate == "mc_y_historia" and not (hi.get("avg_R") is not None and hi["avg_R"] > 0):
        return omitir(est, h, ahora, sym, "timemachine: R promedio histórico %s no es > 0" % hi.get("avg_R"),
                      tm=resumen_tm) and False

    # 5) cotización fresca (si falla, el riesgo se mide desde el plan) + tamaño + riesgo
    pack.correr("alerts", ["quote", sym, "--write"])
    rc, out, err = pack.correr("size", ["--write"])
    ordenes = leer_json(est.ruta_trader("orders.json"), {}).get("orders") or []
    if not ordenes:
        txt = (out + err).strip().splitlines()
        return omitir(est, h, ahora, sym, "budget: " + (txt[-2] if len(txt) > 1 else "sin orden")[:160],
                      tm=resumen_tm) and False
    rc, out, err = pack.correr("risk", ["--json"])
    rj = json_de(out) or {}
    res = (rj.get("results") or [{}])[0]
    if res.get("verdict") != "PASS":
        return omitir(est, h, ahora, sym, "risk BLOCK: " + "; ".join(res.get("reasons") or ["sin veredicto"])[:200],
                      tm=resumen_tm) and False

    # 6) colocar en Alpaca PAPER
    orden = ordenes[0]
    qty = int(float(orden["qty"]))
    try:
        r = broker.colocar_bracket(sym, qty, orden["take_profit_limit_price"], orden["stop_loss_stop_price"])
    except ErrorAlpaca as e:
        return omitir(est, h, ahora, sym, "Alpaca rechazó la orden: %s" % str(e)[:160]) and False
    fill = broker.esperar_fill(r["id"])
    if fill is None:
        broker.cancelar_ordenes(sym)
        pos = broker.posicion(sym)
        if pos is None:
            return omitir(est, h, ahora, sym, "la orden no se llenó en 30 s; cancelada") and False
        fill = pos["avg"]
    stop, target = float(orden["stop_loss_stop_price"]), float(orden["take_profit_limit_price"])
    plan_o = orden.get("plan") or {}
    h["entradas"] += 1
    h["evaluados"][sym] = "COMPRADA"
    est.d["abiertas"][sym] = {"orden_id": r["id"], "qty": qty, "entrada": fill, "stop": stop, "target": target,
                              "fecha": ahora.date().isoformat(), "hora": ahora.strftime("%H:%M"),
                              "max_loss": plan_o.get("max_loss"), "tm": resumen_tm}
    registrar_en_broker_json(est, ahora, orden, res, r["id"])
    pack.correr("ticket", ["fill", "--symbol", sym, "--side", "buy", "--qty", str(qty), "--price", "%.4f" % fill])
    registrar_decision(est, ahora, sym, "comprar", "todas las skills en verde", qty=qty, fill=fill, stop=stop,
                       target=target, tm=resumen_tm)
    p_t, p_s = resumen_tm["p_target"], resumen_tm["p_stop"]
    senal = formato.senal_es(ej.get("reason", ""))
    tg = formato.compra("ALBA", sym, qty, fill, stop, target, formato.horas(ahora, hora_ar(ahora)), senal,
                        tm=resumen_tm, titulares=titulares)
    cuerpo = ("**%s** — compra %d acciones a %s (paper, dinero ficticio)\n\n"
              "- Stop: %s | Objetivo: %s | Riesgo máximo: %s | Recompensa/riesgo: %s\n"
              "- Señal: %s\n"
              "- Máquina del tiempo: objetivo primero %s, stop primero %s, R promedio simulado %s; "
              "historial: %s disparos, R promedio %s\n"
              "- Trader-risk: PASS\n- Noticias (24 h, titulares originales en inglés): %s\n\n"
              "_Estrategia en prueba. Resultado ficticio; no es consejo financiero._"
              % (sym, qty, usd(fill), usd(stop), usd(target), usd(plan_o.get("max_loss") or 0),
                 plan_o.get("reward_risk", "n/d"), senal,
                 "n/d" if p_t is None else "%.0f%%" % (p_t * 100), "n/d" if p_s is None else "%.0f%%" % (p_s * 100),
                 resumen_tm["mc_avg_R"], resumen_tm["hist_disparos"], resumen_tm["hist_avg_R"],
                 "; ".join(titulares[:3]) if titulares else "sin titulares"))
    notif.avisar("ALBA | COMPRA %s x%d @ %s" % (sym, qty, usd(fill)), cuerpo, telegram=tg)
    return True


def registrar_en_broker_json(est, ahora, orden, res, oid):
    """Deja en trader/state/broker.json el mismo registro que trader-broker (status 'placed'), para que
    trader-risk cuente trades del día, pérdida diaria y duplicados. Se marca auto_paper: no hubo 'yes' humano."""
    ruta = est.ruta_trader("state/broker.json")
    st = leer_json(ruta, {"orders": []}) or {"orders": []}
    plan = orden.get("plan") or {}
    st.setdefault("orders", []).append({
        "at": ahora.isoformat(timespec="minutes"), "date": ahora.date().isoformat(), "index": 1,
        "fingerprint": res.get("fingerprint"), "symbol": orden["symbol"], "side": "buy", "qty": orden["qty"],
        "kind": "entry", "max_loss": plan.get("max_loss"), "stop": float(orden["stop_loss_stop_price"]),
        "plain": "buy %s %s (ALBA, paper automático)" % (orden["qty"], orden["symbol"]),
        "status": "placed", "broker_order_id": oid, "auto_paper": True})
    escribir_json(ruta, st)


# ============================================================ cierres y conciliación
def salida_desde_patas(broker, t):
    try:
        o = broker.orden(t["orden_id"])
    except ErrorAlpaca:
        return None, None
    for leg in o.get("legs") or []:
        if leg.get("status") == "filled" and leg.get("filled_avg_price"):
            return float(leg["filled_avg_price"]), ("objetivo" if leg.get("type") == "limit" else "stop")
    return None, None


def finalizar(cfg, pack, est, notif, ahora, h, sym, t, salida, motivo):
    qty, entrada = t["qty"], t["entrada"]
    riesgo = entrada - t["stop"]
    if salida is None:
        registro = {"fecha": t["fecha"], "simbolo": sym, "estado": "salida_desconocida", "qty": qty,
                    "entrada": entrada, "motivo": motivo}
        est.agregar("anomalias.jsonl", registro)
        notif.avisar("ALBA | ATENCIÓN %s: posición cerrada sin precio de salida" % sym,
                     "La posición ya no existe en Alpaca Paper pero no pude leer el precio de salida. "
                     "Revisar a mano. Entrada %s, qty %d." % (usd(entrada), qty),
                     telegram=formato.alerta("ATENCIÓN %s: posición cerrada sin precio de salida" % sym,
                                             "La posición ya no existe en Alpaca Paper pero no pude leer el precio "
                                             "de salida. Entrada %s, cantidad %d." % (usd(entrada), qty),
                                             "Hay que revisarlo a mano.", "🚨"))
        est.d["abiertas"].pop(sym, None)
        return
    pnl = (salida - entrada) * qty
    r = (salida - entrada) / riesgo if riesgo > 0 else 0.0
    h["pnl"] += pnl
    h["r"] += r
    op = {"fecha": t["fecha"], "hora_entrada": t["hora"], "hora_salida": ahora.strftime("%H:%M"),
          "simbolo": sym, "qty": qty, "entrada": entrada, "salida": salida, "stop": t["stop"],
          "target": t["target"], "motivo": motivo, "pnl": round(pnl, 2), "r": round(r, 3), "tm": t.get("tm")}
    est.agregar("operaciones.jsonl", op)
    pack.correr("ticket", ["fill", "--symbol", sym, "--side", "sell", "--qty", str(qty), "--price", "%.4f" % salida])
    est.d["abiertas"].pop(sym, None)
    etiqueta = {"objetivo": "OBJETIVO", "stop": "STOP", "cierre_horario": "CIERRE POR HORARIO",
                "arrastre": "CIERRE DE ARRASTRE"}.get(motivo, motivo.upper())
    acum = estadisticas(est.leer_lineas("operaciones.jsonl"))
    notif.avisar("ALBA | %s %s %s R (%s)" % (etiqueta, sym, signo(r), usd_s(pnl)),
                 "**%s** — vendida a %s (entrada %s, %d acciones)\n\n- Resultado: %s (%s R)\n- Motivo: %s\n"
                 "- Acumulado: %s\n\n_Dinero ficticio (paper)._"
                 % (sym, usd(salida), usd(entrada), qty, usd_s(pnl), signo(r), motivo, texto_estadisticas(acum)),
                 telegram=formato.venta("ALBA", sym, motivo, qty, entrada, salida, pnl, r,
                                        "%s · salida %s" % (t.get("fecha", ""), formato.horas(ahora, hora_ar(ahora))),
                                        acumulado=acum))


def conciliar(cfg, broker, pack, est, notif, ahora, h, mercado_abierto):
    pos = broker.posiciones()
    for sym, t in list(est.d["abiertas"].items()):
        if sym in pos:
            if t["fecha"] != ahora.date().isoformat() and mercado_abierto:
                cerrar_posicion(cfg, broker, pack, est, notif, ahora, h, sym, t, "arrastre")
            continue
        salida, motivo = salida_desde_patas(broker, t)
        finalizar(cfg, pack, est, notif, ahora, h, sym, t, salida, motivo or "desconocido")


def cerrar_posicion(cfg, broker, pack, est, notif, ahora, h, sym, t, motivo):
    broker.cancelar_ordenes(sym)
    oid, ultimo = None, None
    for _ in range(4):
        time.sleep(cfg.get("pausa_cierre_s", 2))
        try:
            oid = broker.cerrar_posicion(sym)
            break
        except ErrorAlpaca as e:
            ultimo = e
    if not oid:
        notif.avisar("ALBA | ERROR al cerrar %s" % sym, "No pude cerrar la posición: %s" % ultimo,
                     telegram=formato.alerta("ERROR al cerrar %s" % sym, str(ultimo)[:500],
                                             "No pude cerrar la posición. Revisar a mano.", "🚨"))
        return
    fill = broker.esperar_fill(oid)
    finalizar(cfg, pack, est, notif, ahora, h, sym, t, fill, motivo)


def cerrar_todo(cfg, broker, pack, est, notif, ahora, h):
    for sym, t in list(est.d["abiertas"].items()):
        cerrar_posicion(cfg, broker, pack, est, notif, ahora, h, sym, t, "cierre_horario")


# ============================================================ búsqueda de entradas
def preparar_universo(cfg, pack, est, h):
    if h["universo"]:
        return True
    rc, out, err = pack.correr("scanner", ["universe"])
    ok = os.path.exists(est.ruta_trader("universe.txt")) and rc == 0
    h["universo"] = ok
    if not ok:
        print("(aviso) no pude armar el universo: %s" % (err or out)[-200:], flush=True)
    return ok


def candidatos(cfg, pack, est, ahora, h):
    ec, pc = cfg["estrategia"], cfg["pack_config"]
    args = ["orb", "--json", "--quiet", "--out", "trader/orb.json", "--min-price", str(ec["precio_minimo"])]
    rc, out, err = pack.correr("scanner", args)
    datos = leer_json(est.ruta_trader("orb.json")) if rc == 0 else None
    if not datos:
        print("  (el escáner ORB no devolvió candidatos: %s)" % (err.strip()[-120:] or "sin hits"), flush=True)
        return []
    lista = []
    for hit in datos.get("hits", []):
        sym = hit["symbol"]
        if sym in h["evaluados"]:
            continue
        precio, medio = hit["price"], (hit["or_high"] + hit["or_low"]) / 2
        riesgo = precio - medio
        if ec["stop"] == "or-mid" and (riesgo <= 0 or math.floor(pc["max_loss_per_trade_usd"] / riesgo) < 1):
            omitir(est, h, ahora, sym, "ni una acción entra en la pérdida máxima (riesgo %.2f por acción)" % riesgo)
            continue
        lista.append(hit)
    lista.sort(key=lambda x: x.get("pct_over", 0))
    return lista[:ec["max_candidatos_por_ciclo"]]


def buscar_entradas(cfg, broker, pack, est, notif, ahora, h):
    pc, ec = cfg["pack_config"], cfg["estrategia"]
    hhmm = ahora.strftime("%H:%M")
    if len(est.d["abiertas"]) >= ec["max_posiciones_abiertas"]:
        return
    if h["entradas"] >= pc["max_trades_per_day"]:
        return
    if -h["pnl"] >= pc["max_daily_loss_usd"]:
        print("Límite de pérdida diaria alcanzado (%s): no se abren más entradas hoy." % usd(h["pnl"]), flush=True)
        return
    if hhmm < pc["no_entries_before"] or hhmm > pc["no_entries_after"] or hhmm < ec["escaneo_orb_desde"]:
        return
    escribir_config_pack(est, cfg)
    if not preparar_universo(cfg, pack, est, h):
        return
    if ahora.timestamp() - h.get("ultimo_scan", 0) < ec["escaneo_cada_min"] * 60:
        return  # no martillar Yahoo: el escáner corre cada escaneo_cada_min minutos
    h["ultimo_scan"] = ahora.timestamp()
    for hit in candidatos(cfg, pack, est, ahora, h):
        if len(est.d["abiertas"]) >= ec["max_posiciones_abiertas"] or h["entradas"] >= pc["max_trades_per_day"]:
            break
        print("Evaluando %s ..." % hit["symbol"], flush=True)
        evaluar(cfg, broker, pack, est, notif, ahora, h, hit)
        est.guardar()


# ============================================================ informes
def informe_diario(cfg, est, notif, ahora, h):
    fecha = ahora.date().isoformat()
    ops = [o for o in est.leer_lineas("operaciones.jsonl") if o["fecha"] == fecha]
    dec = [d for d in est.leer_lineas("decisiones.jsonl") if d["fecha"] == fecha]
    motivos = {}
    for d in dec:
        if d["accion"] == "omitir":
            clave = d["motivo"].split(":")[0][:60]
            motivos[clave] = motivos.get(clave, 0) + 1
    lineas = ["**Operaciones del día:** %d" % len(ops)]
    for o in ops:
        lineas.append("- %s %s→%s (%s) %s R, %s" % (o["simbolo"], usd(o["entrada"]), usd(o["salida"]), o["motivo"],
                                                    signo(o["r"]), usd(o["pnl"])))
    lineas.append("\n**Resultado del día:** %s | **Candidatos descartados:** %d %s"
                  % (usd(sum(o["pnl"] for o in ops)), sum(motivos.values()),
                     ("(" + ", ".join("%s: %d" % kv for kv in sorted(motivos.items())) + ")") if motivos else ""))
    lineas.append("\n**Acumulado:** " + texto_estadisticas(estadisticas(est.leer_lineas("operaciones.jsonl"))))
    lineas.append("\n_Dinero ficticio (paper). Un backtest o una racha corta no prueban que la estrategia funcione._")
    notif.avisar("ALBA | Informe diario %s" % fecha, "\n".join(lineas),
                 telegram=formato.informe_diario(fecha, ops, motivos, sum(o["pnl"] for o in ops),
                                                 estadisticas(est.leer_lineas("operaciones.jsonl"))))
    h["informe"] = True


# ============================================================ v2 en modo sombra (solo registra y mide)
def sombra_paso(cfg, pack, est, ahora, h):
    def escanear(archivo):
        escribir_config_pack(est, cfg)
        if not preparar_universo(cfg, pack, est, h):
            return None
        rc, _, _ = pack.correr("scanner", ["orb", "--json", "--quiet", "--out", "trader/" + os.path.basename(archivo),
                                           "--min-price", str(cfg["estrategia"]["precio_minimo"])])
        return leer_json(est.ruta_trader(os.path.basename(archivo))) if rc == 0 else None
    try:
        sombra.paso(cfg, pack, est, ahora, h, escanear, json_de, leer_json)
    except Exception as e:  # noqa: BLE001 - v2 nunca debe afectar a v1
        print("(sombra) error ignorado: %s" % e, flush=True)


def sombra_cierre(cfg, est, notif, ahora, h):
    if not (cfg.get("sombra") or {}).get("activa") or h.get("sombra_resuelto"):
        return
    h["sombra_resuelto"] = True
    try:
        sombra.resolver(est, ahora.date())
        notif.avisar("ALBA v2 (sombra) | Resumen %s" % ahora.date().isoformat(), sombra.texto_informe(sombra.analizar(est)))
    except Exception as e:  # noqa: BLE001
        print("(sombra) no pude resolver el día: %s" % e, flush=True)


# ============================================================ ciclo principal
def ciclo(cfg, broker, pack, est, notif, ahora=None):
    reloj = broker.reloj()
    est.ultimo_reloj = reloj
    ahora = ahora or parsear_fecha(reloj["timestamp"]).astimezone(NY)
    h = estado_del_dia(est, ahora.date().isoformat())
    abierto = bool(reloj.get("is_open"))
    conciliar(cfg, broker, pack, est, notif, ahora, h, abierto)
    if not abierto:
        if h.get("sesion") and not h["informe"] and ahora.strftime("%H:%M") >= "16:05":
            informe_diario(cfg, est, notif, ahora, h)
        if h.get("sesion") and ahora.strftime("%H:%M") >= "16:05":
            sombra_cierre(cfg, est, notif, ahora, h)
        est.guardar()
        return "cerrado"
    h["sesion"] = True
    if ahora.strftime("%H:%M") >= cfg["estrategia"]["cerrar_desde"]:
        cerrar_todo(cfg, broker, pack, est, notif, ahora, h)
        est.guardar()
        return "cierre"
    buscar_entradas(cfg, broker, pack, est, notif, ahora, h)
    sombra_paso(cfg, pack, est, ahora, h)
    est.guardar()
    return "operando"


def publicar_estado(directorio):
    """Sube el estado a la rama alba-estado (mejor esfuerzo; nunca rompe la sesión)."""
    def git(*a):
        return subprocess.run(["git", "-C", directorio, *a], capture_output=True, text=True)
    try:
        git("add", "-A")
        if git("diff", "--cached", "--quiet").returncode == 0:
            return
        git("commit", "-q", "-m", "alba: estado %s [skip ci]" % time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()))
        for _ in range(3):
            if git("push", "origin", "HEAD:alba-estado").returncode == 0:
                return
            git("fetch", "origin", "alba-estado")
            git("rebase", "origin/alba-estado")
    except Exception as e:  # noqa: BLE001
        print("(aviso) no pude publicar el estado: %s" % e, flush=True)


def sesion(cfg, broker, pack, est, notif, duracion_max_min=None, dormir=time.sleep, mono=time.monotonic,
           publicar=None):
    """Una sesión larga: repite el ciclo cada intervalo_s hasta el cierre del mercado (o hasta agotar
    duracion_max_min). Así ALBA no depende de que GitHub cumpla un cron cada 5 minutos: alcanza con que
    dispare una vez (hay disparos de respaldo)."""
    sc = cfg["sesion"]
    duracion = (duracion_max_min or sc["duracion_max_min"]) * 60
    t0 = ultima_pub = mono()
    errores = 0
    while True:
        try:
            estado = ciclo(cfg, broker, pack, est, notif)
            errores = 0
        except Exception as e:  # noqa: BLE001 - un fallo de red pasajero no debe tirar la sesión
            errores += 1
            print("(error en el ciclo %d) %s" % (errores, e), flush=True)
            if time.time() - est.d.get("ultimo_aviso_error", 0) > 3600:
                est.d["ultimo_aviso_error"] = time.time()
                notif.avisar("ALBA | ERROR en el ciclo", "`%s`\n\nSigo intentando; si se repite avisaré." % str(e)[:500],
                             telegram=formato.alerta("ERROR en el ciclo", str(e)[:500],
                                                     "Sigo intentando; si se repite, aviso."))
            est.guardar()
            if errores >= sc["errores_seguidos_max"]:
                raise
            estado = "error"
        if publicar and mono() - ultima_pub >= sc["publicar_cada_min"] * 60:
            publicar()
            ultima_pub = mono()
        if mono() - t0 >= duracion:
            print("Sesión: tiempo máximo alcanzado; sigue la corrida de relevo.", flush=True)
            break
        if estado == "cerrado":
            r = getattr(est, "ultimo_reloj", {}) or {}
            h = est.d.get("hoy", {})
            informe_pendiente = h.get("sesion") and not h.get("informe")
            minutos_a_abrir = None
            try:
                ahora = parsear_fecha(r["timestamp"])
                minutos_a_abrir = (parsear_fecha(r["next_open"]) - ahora).total_seconds() / 60
            except (KeyError, ValueError):
                pass
            espera_ok = minutos_a_abrir is not None and 0 <= minutos_a_abrir <= sc["espera_apertura_max_min"] \
                and minutos_a_abrir * 60 + (mono() - t0) < duracion
            if not (informe_pendiente or espera_ok):
                print("Sesión: mercado cerrado y sin tareas pendientes; termino.", flush=True)
                break
        dormir(sc["intervalo_s"])
    if publicar:
        publicar()


def diagnostico(broker, notif):
    import urllib.request
    lineas = []
    for nombre, url in (("Yahoo chart", "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1d&interval=5m"),
                        ("Nasdaq Trader", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"),
                        ("Alpaca datos", "https://data.alpaca.markets/v2/stocks/AAPL/quotes/latest")):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (alba-diagnostico)"})
            with urllib.request.urlopen(req, timeout=20) as r:
                lineas.append("- %s: HTTP %s" % (nombre, r.status))
        except Exception as e:  # noqa: BLE001
            codigo = getattr(e, "code", type(e).__name__)
            lineas.append("- %s: %s" % (nombre, codigo))
    try:
        c, cu = broker.reloj(), broker.cuenta()
        lineas.append("- Alpaca Paper: OK | mercado %s | cuenta %s | equity %s" %
                      ("abierto" if c["is_open"] else "cerrado", cu.get("status"), cu.get("equity")))
    except Exception as e:  # noqa: BLE001
        lineas.append("- Alpaca Paper: ERROR %s" % str(e)[:150])
    notif.avisar("ALBA | Diagnóstico de conexiones", "\n".join(lineas),
                 telegram=formato.diagnostico([l[2:].split(": ", 1) if l.startswith("- ") and ": " in l else (l, "")
                                               for l in lineas]))


def telegram_cli(modo, env=None, abrir=None):
    """Ayuda para configurar Telegram sin pasar claves por el chat (se corre desde el workflow)."""
    env = os.environ if env is None else env
    kw = {"abrir": abrir} if abrir else {}
    n = Notificador(entorno=env)
    token, chat = limpio(env.get("ALBA_TELEGRAM_TOKEN")), limpio(env.get("ALBA_TELEGRAM_CHAT"))
    if token and not token_con_formato(token):
        texto = ("El secret `ALBA_TELEGRAM_TOKEN` NO tiene el formato de un token de bot (debe ser números, dos puntos y letras, "
                 "sin espacios ni texto extra). Largo recibido: %d caracteres, %s dos puntos. Pedile el token a BotFather con "
                 "`/token`, copiá solo esa línea y volvé a crear el secret." % (len(token), "con" if ":" in token else "SIN"))
        n._resumen("ALBA | Telegram", texto)
        print(texto)
        return 1
    if not token:
        n._resumen("ALBA | Telegram", "Falta el secret `ALBA_TELEGRAM_TOKEN`. Cargalo en Settings > Secrets > Actions y repetí.")
        print("Falta ALBA_TELEGRAM_TOKEN")
        return 1
    if modo == "descubrir":
        quien, err_quien = telegram_quien(token, **kw)
        cabecera = ("El token pertenece al bot **@%s** (nombre: %s). Es el mismo bot con el que tenés que hablar en Telegram.\n\n"
                    % (quien["username"], quien["nombre"])) if quien and quien.get("username") else ""
        chats, error = telegram_descubrir(token, **kw)
        if error:
            texto = "No pude leer los chats: %s. Si dice 401 el token está mal copiado." % error
        elif not chats:
            texto = ("El bot no recibió ningún mensaje todavía. Abrí Telegram, entrá al chat con TU bot, tocá **Iniciar** "
                     "(o escribí `hola`) y repetí este paso.")
        else:
            texto = "Chats que le escribieron al bot:\n" + "\n".join("- `%s` (%s)" % (i, t) for i, t in chats.items()) + \
                    "\n\nCargá el número del chat tipo `private` como secret `ALBA_TELEGRAM_CHAT`."
        texto = cabecera + texto
        n._resumen("ALBA | Telegram: descubrir chat", texto)
        print(texto)
        return 0 if (chats and not error) else 1
    if not chat:
        n._resumen("ALBA | Telegram", "Falta el secret `ALBA_TELEGRAM_CHAT`. Usá el paso 'descubrir_chat' para ver el número.")
        print("Falta ALBA_TELEGRAM_CHAT")
        return 1
    ok, detalle = telegram_probar(token, chat, "ALBA | Prueba de avisos: si ves este mensaje, Telegram quedó configurado. "
                                  "Dinero ficticio (paper).", **kw)
    n._resumen("ALBA | Telegram: prueba", "Resultado: **%s** (%s)" % ("OK, revisá tu Telegram" if ok else "FALLÓ", detalle))
    print("Telegram:", ok, detalle)
    if ok and abrir is None:
        ejemplos_telegram(n)
    return 0 if ok else 1


def enviar_estado(cfg, broker, est, notif):
    """Manda a Telegram el estado del momento: cuenta y posiciones en vivo (Alpaca) + operaciones del día (rama de estado)."""
    reloj = broker.reloj()
    ahora = parsear_fecha(reloj["timestamp"]).astimezone(NY)
    fecha = ahora.date().isoformat()
    try:
        cu = broker.cuenta()
        equity = float(cu["equity"])
        variacion = equity - float(cu["last_equity"]) if cu.get("last_equity") is not None else None
    except Exception as e:  # noqa: BLE001 - sin datos de cuenta igual se manda lo demás
        print("(estado) no pude leer la cuenta: %s" % e)
        equity = variacion = None
    abiertas = est.d.get("abiertas", {})
    posiciones = []
    for sym, p in broker.posiciones().items():
        t = abiertas.get(sym, {})
        posiciones.append({"sym": sym, "qty": p["qty"], "entrada": p["avg"],
                           "actual": (p["valor"] / p["qty"]) if p["qty"] else None,
                           "stop": t.get("stop"), "target": t.get("target")})
    dec = [d for d in est.leer_lineas("decisiones.jsonl") if d.get("fecha") == fecha]
    compras = [(d["hora"], d["simbolo"], d["qty"], d["fill"]) for d in dec if d.get("accion") == "comprar"]
    cierres = [(o["hora_salida"], o["simbolo"], o["motivo"], o["r"], o["pnl"])
               for o in est.leer_lineas("operaciones.jsonl") if o.get("fecha") == fecha]
    descartados = sum(1 for d in dec if d.get("accion") == "omitir")
    html = formato.estado(formato.horas(ahora, hora_ar(ahora)), bool(reloj.get("is_open")), equity, variacion,
                          posiciones, compras, cierres, descartados)
    plano = "ALBA | Estado: %d posición(es) abierta(s), %d compra(s) y %d cierre(s) hoy, %d candidatos descartados." % (
        len(posiciones), len(compras), len(cierres), descartados)
    notif._telegram("ALBA | Estado", plano, html)
    n_resumen = "Estado enviado a Telegram: %d posición(es), %d compra(s), %d cierre(s)." % (
        len(posiciones), len(compras), len(cierres))
    notif._resumen("ALBA | Estado", n_resumen)
    print(n_resumen)
    return True


def ejemplos_telegram(n):
    """Manda 4 mensajes de EJEMPLO (datos de muestra, marcados como tales) para ver el formato de los avisos."""
    marca = "🧪 <b>EJEMPLO</b> — datos de muestra, no es una operación real\n\n"
    ahora = dt.datetime.now(NY)
    hs = formato.horas(ahora, hora_ar(ahora))
    tm = {"p_target": 0.33, "p_stop": 0.40, "mc_avg_R": 0.15, "hist_disparos": 30, "hist_avg_R": 0.10}
    op = {"simbolo": "XXXX", "entrada": 100.0, "salida": 104.0, "motivo": "objetivo", "r": 2.0, "pnl": 80.0}
    acum = estadisticas([{"r": 2.0, "pnl": 80.0}])
    textos = [
        formato.compra("ALBA", "XXXX", 20, 100.0, 98.0, 104.0, hs, formato.senal_es(""), tm=tm,
                       titulares=["Example headline"]),
        formato.venta("ALBA", "XXXX", "objetivo", 20, 100.0, 104.0, 80.0, 2.0, hs, acumulado=acum),
        formato.informe_diario(ahora.date().isoformat(), [op], {"timemachine": 2}, 80.0, acum),
        formato.alerta("ERROR en el ciclo", "ConnectionError: ejemplo", "Sigo intentando; si se repite, aviso."),
    ]
    for t in textos:
        n._telegram("EJEMPLO", "ejemplo de aviso", marca + t if t else None)


def main(argv=None):
    ap = argparse.ArgumentParser(description="ALBA: un ciclo del bot de acciones intradía (paper)")
    ap.add_argument("--estado", required=True, help="carpeta de estado (rama alba-estado)")
    ap.add_argument("--config", default=os.path.join(AQUI, "config.json"))
    ap.add_argument("--diagnostico", action="store_true")
    ap.add_argument("--telegram", choices=["descubrir", "probar", "estado"],
                    help="configurar / probar los avisos por Telegram, o mandar el estado actual")
    ap.add_argument("--sombra", choices=["informe"], help="informe de ALBA v2 en modo sombra (no necesita claves)")
    ap.add_argument("--sesion", action="store_true", help="repetir el ciclo hasta el cierre del mercado")
    ap.add_argument("--duracion-max-min", type=int, help="tope de duración de la sesión (minutos)")
    a = ap.parse_args(argv)
    cfg = leer_json(a.config)
    if a.sombra == "informe":
        print(sombra.texto_informe(sombra.analizar(Estado(a.estado))))
        return 0
    if a.telegram == "estado":
        key, secret = claves_desde_entorno("ALBA_")
        if not key or not secret:
            print("ALBA: faltan los secrets ALBA_ALPACA_KEY / ALBA_ALPACA_SECRET.")
            return 1
        enviar_estado(cfg, AlpacaPaper(key, secret), Estado(a.estado), Notificador(mencionar=cfg.get("mencionar")))
        return 0
    if a.telegram:
        return telegram_cli(a.telegram)
    key, secret = claves_desde_entorno("ALBA_")
    if not key or not secret:
        print("ALBA: faltan los secrets ALBA_ALPACA_KEY / ALBA_ALPACA_SECRET. No hago nada (ver proyectos/alba/README.md).")
        return 0
    broker = AlpacaPaper(key, secret)
    notif = Notificador(mencionar=cfg.get("mencionar"))
    if a.diagnostico:
        diagnostico(broker, notif)
        return 0
    est = Estado(a.estado)
    pack = Pack(est.dir)
    try:
        if a.sesion:
            sesion(cfg, broker, pack, est, notif, a.duracion_max_min, publicar=lambda: publicar_estado(est.dir))
            print("ALBA: sesión terminada")
        else:
            print("ALBA:", ciclo(cfg, broker, pack, est, notif))
    except Exception as e:  # noqa: BLE001
        ahora = time.time()
        if ahora - est.d.get("ultimo_aviso_error", 0) > 3600:
            est.d["ultimo_aviso_error"] = ahora
            notif.avisar("ALBA | ERROR en el ciclo", "`%s`\n\nRevisar la corrida en la pestaña Actions." % str(e)[:500],
                         telegram=formato.alerta("ERROR en el ciclo", str(e)[:500],
                                                 "Revisar la corrida en la pestaña Actions de GitHub.", "🚨"))
        est.guardar()
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
