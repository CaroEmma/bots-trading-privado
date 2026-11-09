#!/usr/bin/env python3
"""HALCÓN ronda 3: Turtle espejo (largo y corto). Reglas y criterios fijados en proyectos/halcon/PREREGISTRO_RONDA3.md
(commit 234a3d6) ANTES de correr esto. No se ajusta ningún parámetro.

Largo : entra si cierre > máx. de los N_e máximos previos; sale si cierre < mín. de los N_x mínimos previos o stop = fill - 2 ATR.
Corto : entra si cierre < mín. de los N_e mínimos previos; sale si cierre > máx. de los N_x máximos previos o stop = fill + 2 ATR.
Entrada/salida por canal a la apertura de la vela siguiente; stop intra-vela a su precio (o a la apertura si abre más allá).
Costos por lado: comisión 0,25 % + slippage 0,05 % (config.py del Turtle). Corto sin costo de préstamo/financiamiento (virtual).
Tamaño: riesgo 1 % del patrimonio hasta el stop, posición <= 100 % del patrimonio (sin apalancamiento).
"""
import csv
import datetime as dt
import json
import os
import random
import statistics
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "alpaca_bot"))
from indicadores import atr as atr_wilder  # noqa: E402

FEE, SLIP = 0.0025, 0.0005
ATR_P, STOP_MULT, RIESGO = 14, 2.0, 0.01
CAPITAL = 10_000.0
FMT = "%Y-%m-%d %H:%M:%S"
K_VARIANTES = 21                       # 12 (rondas 1 y 2) + 9 de esta ronda
UMBRAL_P = 0.05 / K_VARIANTES
VENTANA_DANADA = (dt.datetime(2023, 3, 29), dt.datetime(2023, 9, 16))   # 109 velas corruptas de BTC 4 h (ver datos/LIMPIEZA.txt)


def cargar(ruta):
    t, o, h, l, c = [], [], [], [], []
    with open(ruta, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t.append(dt.datetime.strptime(r["t"], FMT))
            o.append(float(r["o"])); h.append(float(r["h"])); l.append(float(r["l"])); c.append(float(r["c"]))
    return t, o, h, l, c


class Serie:
    def __init__(self, ruta, ne, nx):
        self.t, self.o, self.h, self.l, self.c = cargar(ruta)
        n = len(self.t)
        self.ne, self.nx, self.n = ne, nx, n
        a = atr_wilder(self.h, self.l, self.c, ATR_P)
        self.atr = a
        self.hi_e = [None] * n; self.lo_e = [None] * n; self.hi_x = [None] * n; self.lo_x = [None] * n
        for k in range(ne, n):
            self.hi_e[k] = max(self.h[k - ne:k]); self.lo_e[k] = min(self.l[k - ne:k])
            self.hi_x[k] = max(self.h[k - nx:k]); self.lo_x[k] = min(self.l[k - nx:k])
        self.primero = max(ne, ATR_P)

    def simular(self, lado, k):
        """Señal en la vela cerrada k. Devuelve dict de la operación (entrada a la apertura de k+1) o None si no hay vela siguiente."""
        e = k + 1
        if e >= self.n - 1:
            return None
        o, h, l, c = self.o, self.h, self.l, self.c
        dist = STOP_MULT * self.atr[k]
        if lado == "largo":
            fill = o[e] * (1 + SLIP); stop = fill - dist
        else:
            fill = o[e] * (1 - SLIP); stop = fill + dist
        tipo, js, ref = "abierta", self.n - 1, c[-1]
        for j in range(e, self.n):
            if lado == "largo":
                if l[j] <= stop:
                    tipo, js, ref = "stop", j, min(o[j], stop); break
                if j + 1 < self.n and self.lo_x[j] is not None and c[j] < self.lo_x[j]:
                    tipo, js, ref = "canal", j + 1, o[j + 1]; break
            else:
                if h[j] >= stop:
                    tipo, js, ref = "stop", j, max(o[j], stop); break
                if j + 1 < self.n and self.hi_x[j] is not None and c[j] > self.hi_x[j]:
                    tipo, js, ref = "canal", j + 1, o[j + 1]; break
        if lado == "largo":
            pnl = ref * (1 - SLIP) * (1 - FEE) - o[e] * (1 + SLIP) * (1 + FEE) if tipo != "abierta" else ref * (1 - SLIP) * (1 - FEE) - o[e] * (1 + SLIP) * (1 + FEE)
        else:
            pnl = o[e] * (1 - SLIP) * (1 - FEE) - ref * (1 + SLIP) * (1 + FEE)
        r = pnl / o[e]                       # retorno por unidad de precio de referencia
        R = pnl / dist
        return {"lado": lado, "k": k, "e": e, "js": js, "tipo": tipo, "entrada": o[e], "salida": ref, "R": R, "r": r,
                "dist": dist, "barras": js - e + 1, "t_entrada": self.t[e], "t_salida": self.t[js]}

    def operaciones(self, lado):
        ops, k = [], self.primero
        while k < self.n - 2:
            s_largo = self.hi_e[k] is not None and self.c[k] > self.hi_e[k]
            s_corto = self.lo_e[k] is not None and self.c[k] < self.lo_e[k]
            if (lado == "largo" and s_largo) or (lado == "corto" and s_corto):
                op = self.simular(lado, k)
                if op is None:
                    break
                ops.append(op)
                if op["tipo"] == "abierta":
                    break
                k = op["js"]              # la próxima señal se evalúa al cierre de la vela de salida
            else:
                k += 1
        return ops

    def pool_azar(self, lado, desde, hasta):
        pool = []
        for k in range(max(desde, self.primero), min(hasta, self.n - 3)):
            op = self.simular(lado, k)
            if op and op["tipo"] != "abierta":
                pool.append(op["R"])
        return pool


def equity_curva(ops):
    eq, pico, dd, curva = CAPITAL, CAPITAL, 0.0, []
    for op in sorted(ops, key=lambda x: x["t_entrada"]):
        fraccion = min(1.0, RIESGO * op["entrada"] / op["dist"])
        eq *= 1 + fraccion * op["r"]
        pico = max(pico, eq); dd = max(dd, (pico - eq) / pico)
    return eq, dd


def metricas(ops, rng, meses):
    ops = [x for x in ops if x["tipo"] != "abierta"]
    n = len(ops)
    if not n:
        return {"n": 0}
    Rs = [x["R"] for x in ops]
    gan = [x for x in Rs if x > 0]; per = [-x for x in Rs if x < 0]
    medias = sorted(statistics.fmean(rng.choices(Rs, k=n)) for _ in range(2000))
    eq, dd = equity_curva(ops)
    return {"n": n, "por_mes": n / meses if meses else None, "acierto": len(gan) / n, "R_neto": statistics.fmean(Rs),
            "ic90": (medias[100], medias[1900]), "factor_beneficio": (sum(gan) / sum(per)) if per else None,
            "mediana_R": statistics.median(Rs), "R_sin_mejor": statistics.fmean(sorted(Rs)[:-1]) if n > 1 else None,
            "mejor_R": max(Rs), "peor_R": min(Rs), "barras_prom": statistics.fmean(x["barras"] for x in ops),
            "retorno_pct": (eq / CAPITAL - 1) * 100, "caida_max_pct": dd * 100,
            "tipos": {k: sum(1 for x in ops if x["tipo"] == k) for k in ("stop", "canal")}}


def p_azar(obs, pool, n, rng, sorteos=3000):
    if not pool or not n or n > len(pool):
        return None
    return (1 + sum(1 for _ in range(sorteos) if statistics.fmean(rng.sample(pool, n)) >= obs)) / (1 + sorteos)


def correr(nombre, ruta, ne, nx, tf_horas, rng, resumen):
    s = Serie(ruta, ne, nx)
    inicio, fin = s.t[s.primero], s.t[-1]
    corte_t = inicio + (fin - inicio) * 0.6
    corte = next(i for i, x in enumerate(s.t) if x >= corte_t)
    meses_total = (fin - inicio).days / 30.4
    bh = s.c[-1] / s.c[s.primero] - 1
    print("\n" + "=" * 100)
    print("%s | %d velas | evaluable %s -> %s (%.1f años) | ajuste hasta %s, validación después | comprar y mantener %+.0f %%" %
          (nombre, s.n, inicio.date(), fin.date(), meses_total / 12, s.t[corte].date(), bh * 100))
    u = s.n - 1
    print("  Estado ahora (última vela cerrada %s): cierre %.2f | entra LARGO si cierra > %.2f (%+.1f %%) | entra CORTO si cierra < %.2f (%+.1f %%) | ATR %.2f" %
          (s.t[u], s.c[u], s.hi_e[u], (s.hi_e[u] / s.c[u] - 1) * 100, s.lo_e[u], (s.lo_e[u] / s.c[u] - 1) * 100, s.atr[u]))
    res = {"velas": s.n, "desde": str(inicio), "hasta": str(fin), "corte": str(s.t[corte]), "buy_hold_pct": bh * 100,
           "estado_ahora": {"cierre": s.c[u], "entra_largo_sobre": s.hi_e[u], "entra_corto_bajo": s.lo_e[u], "atr": s.atr[u]},
           "lados": {}}
    todas = {}
    for lado in ("largo", "corto"):
        ops = s.operaciones(lado)
        todas[lado] = ops
    todas["largo+corto"] = todas["largo"] + todas["corto"]
    for lado in ("largo", "corto", "largo+corto"):
        ops = todas[lado]
        tramos = {"todo": ops, "ajuste": [x for x in ops if x["e"] < corte], "validacion": [x for x in ops if x["e"] >= corte]}
        if nombre.startswith("BTC/USD 4h"):
            tramos["sin_ventana_danada"] = [x for x in ops if not (VENTANA_DANADA[0] <= x["t_entrada"] <= VENTANA_DANADA[1]
                                                                     or VENTANA_DANADA[0] <= x["t_salida"] <= VENTANA_DANADA[1])]
        res["lados"][lado] = {}
        print("\n  --- %s ---" % lado.upper())
        solape = 0
        if lado == "largo+corto":
            cortos = todas["corto"]
            solape = sum(1 for a in todas["largo"] for b in cortos if a["t_entrada"] < b["t_salida"] and b["t_entrada"] < a["t_salida"])
            print("  Operaciones largo y corto superpuestas en el tiempo: %d" % solape)
        for tn, trs in tramos.items():
            desde = s.primero if tn in ("todo", "ajuste", "sin_ventana_danada") else corte
            hasta = corte if tn == "ajuste" else s.n
            meses = (s.t[min(hasta, s.n) - 1] - s.t[desde]).days / 30.4
            m = metricas(trs, rng, meses)
            if m["n"]:
                if tn in ("ajuste", "validacion", "todo"):
                    pool = (s.pool_azar("largo", desde, hasta) + s.pool_azar("corto", desde, hasta)) if lado == "largo+corto" \
                        else s.pool_azar(lado, desde, hasta)
                    m["R_azar"] = statistics.fmean(pool) if pool else None
                    m["p_vs_azar"] = p_azar(m["R_neto"], pool, m["n"], rng)
                fb = "n/d" if m["factor_beneficio"] is None else "%.2f" % m["factor_beneficio"]
                print("  %-19s n=%3d (%.1f/mes) acierto %3.0f%% R neto %+.3f (mediana %+.2f, sin la mejor %+.3f) IC90 [%+.2f;%+.2f] FB %s mejor %+.1fR peor %+.1fR | retorno %+.0f%% caída %.0f%%%s" %
                      (tn, m["n"], m["por_mes"] or 0, m["acierto"] * 100, m["R_neto"], m["mediana_R"], m["R_sin_mejor"] if m["R_sin_mejor"] is not None else float("nan"),
                       m["ic90"][0], m["ic90"][1], fb, m["mejor_R"],
                       m["peor_R"], m["retorno_pct"], m["caida_max_pct"],
                       (" | azar %+.3f p/azar %.4f" % (m["R_azar"], m["p_vs_azar"])) if m.get("p_vs_azar") is not None else ""))
            else:
                print("  %-19s sin operaciones" % tn)
            res["lados"][lado][tn] = m
        if True:
            a, v = res["lados"][lado].get("ajuste", {}), res["lados"][lado].get("validacion", {})
            c1 = v.get("n", 0) >= 30
            c2 = a.get("n", 0) > 0 and v.get("n", 0) > 0 and a["R_neto"] > 0 and v["R_neto"] > 0
            c3 = v.get("p_vs_azar") is not None and v["p_vs_azar"] < UMBRAL_P
            veredicto = "PASA" if (c1 and c2 and c3) else ("NO CONCLUYENTE (n<30 en validación)" if not c1 else "NO PASA")
            res["lados"][lado]["criterios"] = {"n_val>=30": c1, "R>0 ajuste y validación": c2, "p<%.4f" % UMBRAL_P: c3, "veredicto": veredicto}
            print("  CRITERIOS %s: n_val>=30 %s | R>0 en ambos tramos %s | p<%.4f %s  =>  %s" % (lado, c1, c2, UMBRAL_P, c3, veredicto))
        res["lados"][lado]["superpuestas"] = solape
    abiertas = {lado: [x for x in todas[lado] if x["tipo"] == "abierta"] for lado in ("largo", "corto")}
    for lado, lst in abiertas.items():
        for x in lst:
            print("  Posición %s ABIERTA hoy: entrada %s a %.2f" % (lado, x["t_entrada"], x["entrada"]))
    res["ops"] = {lado: [{k: (str(v) if isinstance(v, dt.datetime) else v) for k, v in x.items()} for x in todas[lado]]
                  for lado in ("largo", "corto")}
    resumen[nombre] = res


def main():
    rng = random.Random(7)
    datos = os.path.join(AQUI, "datos")
    resumen = {}
    print("HALCÓN ronda 3 — Turtle espejo largo/corto | costos %.2f %% + %.2f %% por lado | riesgo %.0f %% | umbral p = 0,05/%d = %.4f" %
          (FEE * 100, SLIP * 100, RIESGO * 100, K_VARIANTES, UMBRAL_P))
    correr("BTC/USD 4h", os.path.join(datos, "btc_usd_4h_twelvedata.csv"), 120, 60, 4, rng, resumen)
    correr("ETH/USD 4h", os.path.join(datos, "eth_usd_4h_twelvedata.csv"), 120, 60, 4, rng, resumen)
    correr("BTC/USD diario", os.path.join(datos, "btc_usd_1d_twelvedata.csv"), 20, 10, 24, rng, resumen)
    destino = os.path.join(AQUI, "resultados", "ronda3_espejo.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(resumen, f, indent=1, default=str)
    print("\nResultados completos en", destino)


if __name__ == "__main__":
    main()
