"""ALBA v2 en MODO SOMBRA: registra y mide, NO opera ni modifica nada de v1.

Reglas fijadas en proyectos/alba/PREREGISTRO_V2_SOMBRA.md (escrito antes que este código). Para cada hit nuevo y fresco del
escáner ORB guarda rasgos (volumen relativo, brecha, SPY, etiquetas de noticias), da el veredicto de la regla v2 y, al final del
día, simula el resultado con las barras reales (misma regla de stop y objetivo que v1). El informe compara PASA vs DESCARTA.

Todo es mejor esfuerzo: un fallo acá se registra y se sigue; v1 tiene prioridad (si Yahoo limita, se corta el registro de v2).
"""
import datetime as dt
import json
import math
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
UA = "Mozilla/5.0 (compatible; day-trader-skill/2.0; +https://github.com/Jakeschincariol/day-trader-skill)"
HOSTS = ("query2", "query1")

# --- regla v2 (preregistro, sección 3): NO cambiar con los datos
RVOL_MIN = 1.5
SPY_MIN = 0.0
ETIQUETAS_EXCLUYENTES = {"earnings", "halt", "deal", "legal", "regulatory"}
SALIDA_MIN = 15 * 60 + 40        # 15:40 ET: cierre forzado de v1
MAX_NUEVOS_POR_ESCANEO = 15
MIN_PASA, MIN_DESCARTA, MIN_DIAS = 30, 30, 10      # datos mínimos para evaluar (preregistro, sección 5)
PERMUTACIONES = 10000
_cache_spy = {"clave": None, "barras": None}


class Limitado(Exception):
    """Yahoo respondió 429."""


class SombraError(Exception):
    pass


# ------------------------------------------------------------------ datos
def barras_yahoo(sym, abrir=urllib.request.urlopen, dormir=time.sleep, rango="1mo"):
    """Barras de 5 min (1 mes) de Yahoo: lista de dicts {t, o, h, l, c, v}. Lanza Limitado o SombraError."""
    ultimo = None
    for n, host in enumerate(HOSTS):
        if n:
            dormir(1)
        url = "https://%s.finance.yahoo.com/v8/finance/chart/%s?range=%s&interval=5m" % (
            host, urllib.parse.quote(sym.upper().replace(".", "-")), rango)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with abrir(req, timeout=20) as r:
                datos = json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            ultimo = e.code
            if e.code == 404:
                raise SombraError("Yahoo no tiene gráfico de %s" % sym)
            continue
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise SombraError("no pude leer Yahoo (%s)" % type(e).__name__)
        return _parsear(datos, sym)
    if ultimo == 429:
        raise Limitado()
    raise SombraError("Yahoo respondió HTTP %s para %s" % (ultimo, sym))


def _parsear(datos, sym):
    try:
        r = datos["chart"]["result"][0]
        ts, q = r["timestamp"], r["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        raise SombraError("respuesta de Yahoo sin barras para %s" % sym)
    out = []
    for i, t in enumerate(ts):
        try:
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        except (IndexError, TypeError):
            continue
        if None in (o, h, l, c):
            continue
        v = (q.get("volume") or [0] * len(ts))[i] or 0
        out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
    return out


def _min_del_dia(t):
    d = dt.datetime.fromtimestamp(t, NY)
    return d.hour * 60 + d.minute


def sesiones(barras):
    """{fecha: [barras de la sesión regular 09:30-16:00 ET, en orden]}."""
    out = {}
    for b in barras:
        d = dt.datetime.fromtimestamp(b["t"], NY)
        m = d.hour * 60 + d.minute
        if d.weekday() < 5 and 9 * 60 + 30 <= m < 16 * 60:
            out.setdefault(d.date(), []).append(b)
    return out


# ------------------------------------------------------------------ rasgos y veredicto
def _media(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def rasgos(barras_sym, barras_spy, fecha, corte_min):
    """Rasgos del preregistro, sección 2. corte_min = minuto (ET) en que termina la barra de la señal. None = sin dato."""
    r = {"rvol": None, "gap_pct": None, "spy_pct": None, "spy_sobre_media": None}
    ses = sesiones(barras_sym)
    hoy, previas = ses.get(fecha), [d for d in sorted(ses) if d < fecha][-10:]
    if hoy and previas:
        vol_hoy = sum(b["v"] for b in hoy if _min_del_dia(b["t"]) < corte_min)
        vols = [sum(b["v"] for b in ses[d] if _min_del_dia(b["t"]) < corte_min) for d in previas]
        m = _media([v for v in vols if v > 0])
        if m:
            r["rvol"] = round(vol_hoy / m, 3)
        cierre_ayer = ses[previas[-1]][-1]["c"]
        if cierre_ayer:
            r["gap_pct"] = round((hoy[0]["o"] / cierre_ayer - 1) * 100, 3)
    sspy = sesiones(barras_spy or [])
    hoy_s, prev_s = sspy.get(fecha), [d for d in sorted(sspy) if d < fecha][-11:]
    if hoy_s and prev_s:
        hasta = [b for b in hoy_s if _min_del_dia(b["t"]) < corte_min]
        cierre_ayer = sspy[prev_s[-1]][-1]["c"]
        if hasta and cierre_ayer:
            r["spy_pct"] = round((hasta[-1]["c"] / cierre_ayer - 1) * 100, 3)
        anteriores = [sspy[d][-1]["c"] for d in prev_s[:-1]]
        if anteriores:
            r["spy_sobre_media"] = cierre_ayer > sum(anteriores) / len(anteriores)
    return r


def veredicto(r, tags):
    """('PASA' | 'DESCARTA' | 'SIN DATO', [motivos]) según la regla fijada en el preregistro."""
    if r.get("rvol") is None or r.get("spy_pct") is None:
        return "SIN DATO", ["falta rvol o spy_pct"]
    fallas = []
    if r["rvol"] < RVOL_MIN:
        fallas.append("rvol %.2f < %.1f" % (r["rvol"], RVOL_MIN))
    if r["spy_pct"] < SPY_MIN:
        fallas.append("SPY %+.2f%% < 0" % r["spy_pct"])
    malas = sorted(set(tags or []) & ETIQUETAS_EXCLUYENTES)
    if malas:
        fallas.append("noticias: " + ",".join(malas))
    return ("DESCARTA" if fallas else "PASA"), fallas


def simular(barras_dia, entrada, stop, corte_min):
    """Resultado simulado (preregistro, sección 4). Devuelve {'salida','motivo','r'} o None si no hay barras posteriores."""
    riesgo = entrada - stop
    if riesgo <= 0:
        return None
    objetivo = entrada + 2 * riesgo
    ultima = None
    for b in barras_dia:
        m = _min_del_dia(b["t"])
        if m < corte_min or m >= SALIDA_MIN:
            continue
        ultima = b
        if b["o"] <= stop:                    # abre por debajo del stop: sale en la apertura
            return {"salida": b["o"], "motivo": "stop", "r": round((b["o"] - entrada) / riesgo, 3)}
        if b["l"] <= stop:                    # si en la misma barra toca ambos, cuenta el stop
            return {"salida": stop, "motivo": "stop", "r": -1.0}
        if b["h"] >= objetivo:
            return {"salida": objetivo, "motivo": "objetivo", "r": 2.0}
    if ultima is None:
        return None
    return {"salida": ultima["c"], "motivo": "horario", "r": round((ultima["c"] - entrada) / riesgo, 3)}


# ------------------------------------------------------------------ registro durante el día
def _spy(abrir, dormir, ahora):
    clave = (ahora.date(), ahora.hour, ahora.minute // 5)
    if _cache_spy["clave"] != clave:
        _cache_spy["barras"] = barras_yahoo("SPY", abrir, dormir)
        _cache_spy["clave"] = clave
    return _cache_spy["barras"]


def _etiquetas(pack, sym, json_de):
    """Etiquetas de noticias de 24 h (skill news, sin SEC). (lista, n_titulares, ok)."""
    rc, out, _ = pack.correr("news", ["--tickers", sym, "--hours", "24", "--no-sec", "--json"])
    nj = json_de(out) if rc in (0, 1) else None
    if nj is None:
        return [], 0, False
    tags, n = set(), 0
    for it in nj.get("items", []):
        n += 1
        tags.update(str(t).lower() for t in (it.get("tags") or []))
    return sorted(tags), n, True


def paso(cfg, pack, est, ahora, h, escanear, json_de, leer_json, abrir=urllib.request.urlopen, dormir=time.sleep):
    """Un paso de v2 dentro del ciclo de ALBA. escanear(archivo) -> datos del escáner ORB (lo arma el orquestador)."""
    sc = cfg.get("sombra") or {}
    if not sc.get("activa"):
        return
    pc, ec = cfg["pack_config"], cfg["estrategia"]
    hhmm = ahora.strftime("%H:%M")
    if hhmm < pc["no_entries_before"] or hhmm > pc["no_entries_after"] or hhmm < ec["escaneo_orb_desde"]:
        return
    s = h.setdefault("sombra", {"vistos": [], "perdidos": [], "ultimo_scan": 0, "limitado": 0, "errores": 0})
    ts = ahora.timestamp()
    desde_v1 = ts - h.get("ultimo_scan", 0)
    if desde_v1 < 90:
        datos = leer_json(est.ruta_trader("orb.json"))            # v1 acaba de escanear: se reutiliza
    elif desde_v1 < ec["escaneo_cada_min"] * 60:
        return                                                    # v1 escanea seguido: no se duplica el pedido a Yahoo
    elif ts - s["ultimo_scan"] >= ec["escaneo_cada_min"] * 60:    # v1 no escanea (posición abierta o límite): escaneo propio
        s["ultimo_scan"] = ts
        datos = escanear("trader/orb_sombra.json")
    else:
        return
    if not datos or not datos.get("hits"):
        return
    nuevos = 0
    for hit in sorted(datos["hits"], key=lambda x: x.get("pct_over", 0)):
        sym = hit["symbol"]
        if sym in s["vistos"] or sym in s["perdidos"]:
            continue
        fin = int(hit["bar_start"][:2]) * 60 + int(hit["bar_start"][3:5]) + 5
        edad = ahora.hour * 60 + ahora.minute - fin
        if edad > ec["max_edad_senal_min"]:
            s["perdidos"].append(sym)          # la vimos tarde: v1 tampoco la tomaría
            continue
        if nuevos >= MAX_NUEVOS_POR_ESCANEO:
            break
        try:
            dormir(0.5)
            barras = barras_yahoo(sym, abrir, dormir)
            r = rasgos(barras, _spy(abrir, dormir, ahora), ahora.date(), fin)
        except Limitado:
            s["limitado"] += 1
            print("(sombra) Yahoo limita (429): corto el registro de v2 en este escaneo.", flush=True)
            return
        except SombraError as e:
            s["errores"] += 1
            print("(sombra) %s: %s" % (sym, e), flush=True)
            continue
        tags, n_tit, ok_news = _etiquetas(pack, sym, json_de)
        ver, motivos = veredicto(r, tags)
        medio = (hit["or_high"] + hit["or_low"]) / 2
        est.agregar("sombra.jsonl", {
            "fecha": ahora.date().isoformat(), "hora_senal": "%02d:%02d" % divmod(fin, 60), "simbolo": sym,
            "precio": hit["price"], "stop": round(medio, 4), "pct_over": hit.get("pct_over"),
            "or_rango_pct": round((hit["or_high"] - hit["or_low"]) / hit["price"] * 100, 3),
            **r, "tags": tags, "n_titulares": n_tit, "noticias_ok": ok_news, "veredicto": ver, "motivos": motivos})
        s["vistos"].append(sym)
        nuevos += 1
    if nuevos:
        print("(sombra) registrados %d hits nuevos." % nuevos, flush=True)


# ------------------------------------------------------------------ resolución (fin del día) e informe
def resolver(est, hasta_fecha, abrir=urllib.request.urlopen, dormir=time.sleep):
    """Simula el resultado de todo hit registrado y sin resolver (hoy o días previos aún dentro de la ventana de Yahoo)."""
    registros = est.leer_lineas("sombra.jsonl")
    hechos = {(x["fecha"], x["simbolo"]) for x in est.leer_lineas("sombra_resultados.jsonl")}
    pendientes = [x for x in registros if (x["fecha"], x["simbolo"]) not in hechos]
    por_simbolo = {}
    for x in pendientes:
        por_simbolo.setdefault(x["simbolo"], []).append(x)
    nuevos = 0
    for sym, regs in por_simbolo.items():
        try:
            dormir(0.5)
            ses = sesiones(barras_yahoo(sym, abrir, dormir))
        except Limitado:
            print("(sombra) Yahoo limita (429): sigo mañana con lo pendiente.", flush=True)
            break
        except SombraError as e:
            print("(sombra) no pude resolver %s: %s" % (sym, e), flush=True)
            continue
        for x in regs:
            dia = dt.date.fromisoformat(x["fecha"])
            if dia > hasta_fecha:
                continue
            corte = int(x["hora_senal"][:2]) * 60 + int(x["hora_senal"][3:5])
            res = simular(ses.get(dia, []), x["precio"], x["stop"], corte)
            if res is None:
                if (hasta_fecha - dia).days < 3:
                    continue                      # puede que Yahoo todavía no tenga el día: se reintenta
                res = {"salida": None, "motivo": "sin datos", "r": None}
            est.agregar("sombra_resultados.jsonl", {"fecha": x["fecha"], "simbolo": sym, **res})
            nuevos += 1
    return nuevos


def _resumen(rs):
    rs = [r for r in rs if r is not None]
    n = len(rs)
    if not n:
        return {"n": 0, "media": None, "acierto": None, "pf": None}
    ganancias, perdidas = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
    return {"n": n, "media": sum(rs) / n, "acierto": sum(1 for r in rs if r > 0) / n,
            "pf": (ganancias / perdidas) if perdidas else None}


def permutacion(a, b, veces=PERMUTACIONES, semilla=20261111):
    """p una cola de H1: media(a) > media(b), mezclando etiquetas. Semilla fija (reproducible)."""
    if not a or not b:
        return None
    obs = sum(a) / len(a) - sum(b) / len(b)
    todos, rnd, mayores = list(a) + list(b), random.Random(semilla), 0
    for _ in range(veces):
        rnd.shuffle(todos)
        d = sum(todos[:len(a)]) / len(a) - sum(todos[len(a):]) / len(b)
        if d >= obs - 1e-12:
            mayores += 1
    return (mayores + 1) / (veces + 1)


def analizar(est):
    """Datos para el informe: grupos, conteos, cobertura y la prueba principal si hay datos mínimos."""
    regs = {(x["fecha"], x["simbolo"]): x for x in est.leer_lineas("sombra.jsonl")}
    res = {(x["fecha"], x["simbolo"]): x for x in est.leer_lineas("sombra_resultados.jsonl") if x.get("r") is not None}
    compras = {(d["fecha"], d["simbolo"]) for d in est.leer_lineas("decisiones.jsonl") if d.get("accion") == "comprar"}
    grupos = {"PASA": [], "DESCARTA": [], "SIN DATO": []}
    v1 = []
    for k, x in regs.items():
        if k in res:
            grupos[x["veredicto"]].append((x["fecha"], res[k]["r"]))
            if k in compras:
                v1.append(res[k]["r"])
    dias = {f for g in grupos.values() for f, _ in g}
    out = {"registrados": len(regs), "resueltos": sum(len(g) for g in grupos.values()), "dias": len(dias),
           "grupos": {k: _resumen([r for _, r in g]) for k, g in grupos.items()},
           "v1_compras": _resumen(v1), "p": None, "mitades": None, "suficiente": False}
    out["todos"] = _resumen([r for g in grupos.values() for _, r in g])
    n_p, n_d = len(grupos["PASA"]), len(grupos["DESCARTA"])
    out["suficiente"] = n_p >= MIN_PASA and n_d >= MIN_DESCARTA and len(dias) >= MIN_DIAS
    if out["suficiente"]:
        rp, rd = [r for _, r in grupos["PASA"]], [r for _, r in grupos["DESCARTA"]]
        out["p"] = permutacion(rp, rd)
        out["diferencia"] = sum(rp) / len(rp) - sum(rd) / len(rd)
        orden = sorted(dias)
        corte = orden[len(orden) // 2]
        m = []
        for lado in (lambda f: f < corte, lambda f: f >= corte):
            p_ = [r for f, r in grupos["PASA"] if lado(f)]
            d_ = [r for f, r in grupos["DESCARTA"] if lado(f)]
            m.append((sum(p_) / len(p_) - sum(d_) / len(d_)) if p_ and d_ else None)
        out["mitades"] = m
        out["cumple"] = bool(out["diferencia"] > 0 and out["p"] < 0.05 and _resumen(rp)["media"] > 0
                             and all(x is not None and x > 0 for x in m))
    return out


def _f(x, dec=3):
    return "n/d" if x is None else ("%+." + str(dec) + "f") % x


def texto_informe(a):
    L = ["Hits registrados: %d | con resultado simulado: %d | días: %d" % (a["registrados"], a["resueltos"], a["dias"])]
    for k in ("PASA", "DESCARTA", "SIN DATO"):
        g = a["grupos"][k]
        L.append("- %s: n=%d | R promedio %s | acierto %s | factor de beneficio %s"
                 % (k, g["n"], _f(g["media"]), "n/d" if g["acierto"] is None else "%.0f%%" % (g["acierto"] * 100),
                    "n/d" if g["pf"] is None else "%.2f" % g["pf"]))
    L.append("- Todos los hits: n=%d | R promedio %s" % (a["todos"]["n"], _f(a["todos"]["media"])))
    L.append("- Lo que v1 compró de ellos: n=%d | R promedio %s" % (a["v1_compras"]["n"], _f(a["v1_compras"]["media"])))
    falta = ["PASA %d/%d" % (a["grupos"]["PASA"]["n"], MIN_PASA), "DESCARTA %d/%d" % (a["grupos"]["DESCARTA"]["n"], MIN_DESCARTA),
             "días %d/%d" % (a["dias"], MIN_DIAS)]
    if not a["suficiente"]:
        L.append("\nTodavía NO hay datos suficientes para evaluar (%s). Nada de esto permite concluir nada; v2 no cambia ALBA." % ", ".join(falta))
    else:
        L.append("\nPrueba principal: diferencia PASA − DESCARTA = %s R, p = %.4f; mitades: %s / %s."
                 % (_f(a["diferencia"]), a["p"], _f(a["mitades"][0]), _f(a["mitades"][1])))
        L.append("Criterio del preregistro: " + ("CUMPLIDO (recién ahí se puede discutir adoptar v2)." if a["cumple"]
                                                  else "NO cumplido: v2 no se adopta."))
    L.append("\n_Modo sombra: v2 no opera. Resultados simulados (sin deslizamiento). Ver PREREGISTRO_V2_SOMBRA.md._")
    return "\n".join(L)
