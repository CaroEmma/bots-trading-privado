#!/usr/bin/env python3
"""HALCÓN: backtest de estrategias candidatas de ENTRADA para BTC/USD en velas de 1 hora.

PREREGISTRO (fijado ANTES de correr el backtest; no se cambia después de ver resultados):
- Tres señales de entrada con parámetros estándar, SIN ajustar nada con los datos:
    S1 ruptura   : cierre > máximo de las 48 velas anteriores.
    S2 reversión : RSI(14) cruza por debajo de 30 estando el cierre sobre la SMA(200).
    S3 retroceso : EMA(50) > EMA(200) y el cierre cruza hacia arriba la EMA(20).
- Salida IGUAL para todas (así se compara solo la entrada): stop 2 x ATR(14), objetivo 3 x ATR (recompensa/riesgo
  bruta 1,5), salida por tiempo a las N horas (N = 24 y 48). Solo largos, una posición a la vez.
- Entrada a la apertura de la vela siguiente a la señal. Si en una vela se tocan stop y objetivo, se asume el stop.
- Costos por lado: comisión 0,25 % (taker, escenario base) + slippage 0,05 %. Escenario de sensibilidad: comisión 0,15 %.
- Datos: primeros 60 % = ajuste/entrenamiento, últimos 40 % = validación (nunca usada para elegir nada).
- Línea base: entradas al azar con la misma salida (3.000 sorteos) -> valor p.
- REGLA DE DECISIÓN (escenario base): una variante "pasa" solo si: n >= 30 en validación, R neto promedio > 0 en ajuste Y
  en validación, y valor p de validación < 0,05 / 6 variantes = 0,0083 (corrección por probar 6 variantes).
  Si ninguna pasa, la conclusión es "ninguna validada" y NO se elige una por ser la menos mala.
"""
import csv
import datetime as dt
import json
import math
import random
import statistics
import sys

TAKER, MAKER, SLIP = 0.0025, 0.0015, 0.0005
ATR_P, STOP_ATR, TARGET_ATR = 14, 2.0, 3.0
HOLDS = (24, 48)
WARM = 250
CAPITAL, RIESGO_USD, POS_MAX = 100.0, 1.0, 75.0
PASA_P = 0.05 / 6
FMT = "%Y-%m-%d %H:%M:%S"


# ------------------------------------------------------------------ datos
def cargar(ruta):
    t, o, h, l, c = [], [], [], [], []
    with open(ruta, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t.append(dt.datetime.strptime(r["t"], FMT))
            o.append(float(r["o"])); h.append(float(r["h"])); l.append(float(r["l"])); c.append(float(r["c"]))
    seg, s = [0], 0
    for i in range(1, len(t)):
        if t[i] - t[i - 1] > dt.timedelta(hours=1):
            s += 1
        seg.append(s)
    return t, o, h, l, c, seg


# ------------------------------------------------------------------ indicadores
def atr_wilder(h, l, c, p=ATR_P):
    n = len(c)
    tr = [0.0] * n
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    out = [None] * n
    if n > p:
        a = sum(tr[1:p + 1]) / p
        out[p] = a
        for i in range(p + 1, n):
            a = (a * (p - 1) + tr[i]) / p
            out[i] = a
    return out


def sma(c, p):
    out, s = [None] * len(c), 0.0
    for i, x in enumerate(c):
        s += x
        if i >= p:
            s -= c[i - p]
        if i >= p - 1:
            out[i] = s / p
    return out


def ema(c, p):
    out = [None] * len(c)
    if len(c) < p:
        return out
    e = sum(c[:p]) / p
    out[p - 1] = e
    k = 2.0 / (p + 1)
    for i in range(p, len(c)):
        e = c[i] * k + e * (1 - k)
        out[i] = e
    return out


def rsi_wilder(c, p=14):
    out = [None] * len(c)
    if len(c) <= p:
        return out
    g = sum(max(c[i] - c[i - 1], 0) for i in range(1, p + 1)) / p
    ls = sum(max(c[i - 1] - c[i], 0) for i in range(1, p + 1)) / p
    out[p] = 100.0 if ls == 0 else 100 - 100 / (1 + g / ls)
    for i in range(p + 1, len(c)):
        d = c[i] - c[i - 1]
        g = (g * (p - 1) + max(d, 0)) / p
        ls = (ls * (p - 1) + max(-d, 0)) / p
        out[i] = 100.0 if ls == 0 else 100 - 100 / (1 + g / ls)
    return out


# ------------------------------------------------------------------ señales
def senales(o, h, l, c):
    n = len(c)
    e20, e50, e200, s200, rs = ema(c, 20), ema(c, 50), ema(c, 200), sma(c, 200), rsi_wilder(c)
    s1, s2, s3 = [False] * n, [False] * n, [False] * n
    for i in range(WARM, n):
        if c[i] > max(h[i - 48:i]):
            s1[i] = True
        if rs[i] is not None and rs[i - 1] is not None and rs[i] < 30 <= rs[i - 1] and c[i] > s200[i]:
            s2[i] = True
        if e50[i] > e200[i] and c[i - 1] < e20[i - 1] and c[i] > e20[i]:
            s3[i] = True
    return {"S1 ruptura 48h": s1, "S2 reversion RSI<30 en tendencia": s2, "S3 retroceso a EMA20 en tendencia": s3}


# ------------------------------------------------------------------ simulación de un trade
def simular(i, hold, o, h, l, c, atr, seg):
    """Señal al cierre de la vela i; entrada a la apertura de i+1. Devuelve None si no se puede completar."""
    e = i + 1
    if e + hold - 1 >= len(c) or atr[i] is None or seg[e] != seg[i] or seg[e + hold - 1] != seg[i]:
        return None
    ref = o[e]
    stop, target = ref - STOP_ATR * atr[i], ref + TARGET_ATR * atr[i]
    stop_pct = STOP_ATR * atr[i] / ref
    for j in range(e, e + hold):
        if l[j] <= stop:
            return {"ref_in": ref, "ref_out": min(stop, o[j]), "stop_pct": stop_pct, "tipo": "stop", "j": j}
        if h[j] >= target:
            return {"ref_in": ref, "ref_out": target, "stop_pct": stop_pct, "tipo": "objetivo", "j": j}
    return {"ref_in": ref, "ref_out": c[e + hold - 1], "stop_pct": stop_pct, "tipo": "tiempo", "j": e + hold - 1}


def r_neto(tr, fee):
    entrada = tr["ref_in"] * (1 + SLIP)
    salida = tr["ref_out"] * (1 - SLIP)
    r = salida * (1 - fee) / (entrada * (1 + fee)) - 1
    return r, r / tr["stop_pct"]


def r_bruto(tr):
    return (tr["ref_out"] / tr["ref_in"] - 1) / tr["stop_pct"]


# ------------------------------------------------------------------ métricas
def metricas(trades, fee, semanas, rng, remuestreos=2000):
    n = len(trades)
    if n == 0:
        return {"n": 0}
    rs, usd, brutos = [], [], []
    for tr in trades:
        r, R = r_neto(tr, fee)
        pos = min(POS_MAX, RIESGO_USD / tr["stop_pct"])
        rs.append(R); usd.append(pos * r); brutos.append(r_bruto(tr))
    gan = [x for x in rs if x > 0]
    per = [-x for x in rs if x < 0]
    acum, pico, dd = 0.0, 0.0, 0.0
    for x in rs:
        acum += x; pico = max(pico, acum); dd = max(dd, pico - acum)
    medias = sorted(statistics.fmean(rng.choices(rs, k=n)) for _ in range(remuestreos))
    racha = mejor = 0
    for x in rs:
        racha = racha + 1 if x < 0 else 0
        mejor = max(mejor, racha)
    return {"n": n, "por_semana": n / semanas if semanas else None, "acierto": len(gan) / n,
            "R_neto": statistics.fmean(rs), "R_bruto": statistics.fmean(brutos),
            "factor_beneficio": (sum(gan) / sum(per)) if per else None, "dd_R": dd,
            "ic90": (medias[int(0.05 * remuestreos)], medias[int(0.95 * remuestreos)]),
            "usd_total": sum(usd), "racha_perdedora": mejor,
            "tipos": {k: sum(1 for t in trades if t["tipo"] == k) for k in ("stop", "objetivo", "tiempo")}}


def valor_p(obs, pool, n, rng, sorteos=3000):
    if n == 0 or n > len(pool):
        return None
    mayores = sum(1 for _ in range(sorteos) if statistics.fmean(rng.sample(pool, n)) >= obs)
    return (1 + mayores) / (1 + sorteos)


# ------------------------------------------------------------------ corrida completa
def correr(ruta):
    t, o, h, l, c, seg = cargar(ruta)
    n = len(c)
    atr = atr_wilder(h, l, c)
    sig = senales(o, h, l, c)
    corte = int(0.6 * n)
    tramos = {"ajuste": (WARM, corte), "validacion": (corte, n)}
    rng = random.Random(7)
    res = {"datos": {"velas": n, "desde": str(t[0]), "hasta": str(t[-1]), "corte_ajuste_validacion": str(t[corte]),
                     "huecos": sum(1 for i in range(1, n) if seg[i] != seg[i - 1])},
           "buy_hold": {}, "variantes": []}
    for nombre, (a, b) in tramos.items():
        res["buy_hold"][nombre] = c[b - 1] / c[a] - 1
    stop_pcts = [STOP_ATR * atr[i] / c[i] for i in range(WARM, n) if atr[i]]
    res["stop_pct_mediano"] = statistics.median(stop_pcts)
    res["posicion_usd_mediana"] = min(POS_MAX, RIESGO_USD / res["stop_pct_mediano"])
    for hold in HOLDS:
        todas = {i: simular(i, hold, o, h, l, c, atr, seg) for i in range(WARM, n - 1)}
        for nombre_s, s in sig.items():
            v = {"senal": nombre_s, "hold": hold, "tramos": {}}
            for tn, (a, b) in tramos.items():
                semanas = (t[min(b, n) - 1] - t[a]).days / 7
                trades, libre = [], 0
                for i in range(a, b):
                    if s[i] and i >= libre and todas.get(i):
                        trades.append(todas[i]); libre = todas[i]["j"]
                pool = {fee: [r_neto(todas[i], fee)[1] for i in range(a, b) if todas.get(i)] for fee in (TAKER, MAKER)}
                v["tramos"][tn] = {}
                for etiqueta, fee in (("base_taker", TAKER), ("sens_maker", MAKER)):
                    m = metricas(trades, fee, semanas, rng)
                    if m["n"]:
                        m["p_vs_azar"] = valor_p(m["R_neto"], pool[fee], m["n"], rng)
                        m["R_neto_azar"] = statistics.fmean(pool[fee])
                    v["tramos"][tn][etiqueta] = m
            aj, va = v["tramos"]["ajuste"]["base_taker"], v["tramos"]["validacion"]["base_taker"]
            v["pasa"] = bool(va.get("n", 0) >= 30 and aj.get("n", 0) > 0 and aj["R_neto"] > 0 and va["R_neto"] > 0
                             and va.get("p_vs_azar") is not None and va["p_vs_azar"] < PASA_P)
            res["variantes"].append(v)
    return res


def imprimir(res):
    d = res["datos"]
    print("Datos: %d velas 1h | %s -> %s | corte ajuste/validación: %s | huecos: %d" %
          (d["velas"], d["desde"], d["hasta"], d["corte_ajuste_validacion"], d["huecos"]))
    print("Buy&hold  ajuste %+.1f %%  validación %+.1f %%" % (res["buy_hold"]["ajuste"] * 100, res["buy_hold"]["validacion"] * 100))
    print("Stop 2xATR mediano: %.2f %% del precio -> posición mediana por USD 1 de riesgo: USD %.0f (tope %d)" %
          (res["stop_pct_mediano"] * 100, res["posicion_usd_mediana"], POS_MAX))
    for v in res["variantes"]:
        print("\n== %s | salida por tiempo %dh | PASA: %s" % (v["senal"], v["hold"], "SÍ" if v["pasa"] else "no"))
        for tn in ("ajuste", "validacion"):
            for et in ("base_taker", "sens_maker"):
                m = v["tramos"][tn][et]
                if not m["n"]:
                    print("  %-10s %-10s sin operaciones" % (tn, et)); continue
                fb = "n/d" if m["factor_beneficio"] is None else "%.2f" % m["factor_beneficio"]
                print("  %-10s %-10s n=%3d (%.1f/sem) acierto %2.0f%% R neto %+.3f (bruto %+.3f) IC90 [%+.2f;%+.2f] FB %s "
                      "DD %.1fR USD %+.1f p/azar %s azar %+.3f" %
                      (tn, et, m["n"], m["por_semana"], m["acierto"] * 100, m["R_neto"], m["R_bruto"], m["ic90"][0],
                       m["ic90"][1], fb, m["dd_R"], m["usd_total"],
                       "n/d" if m.get("p_vs_azar") is None else "%.3f" % m["p_vs_azar"], m["R_neto_azar"]))
    pasan = [v for v in res["variantes"] if v["pasa"]]
    print("\nVariantes que pasan la regla preregistrada: %d de %d" % (len(pasan), len(res["variantes"])))


if __name__ == "__main__":
    ruta = sys.argv[1] if len(sys.argv) > 1 else "halcon/datos/btc_usd_1h_twelvedata.csv"
    r = correr(ruta)
    imprimir(r)
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            json.dump(r, f, indent=1, ensure_ascii=False, default=str)
