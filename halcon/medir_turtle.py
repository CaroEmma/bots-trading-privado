#!/usr/bin/env python3
"""Medición del bot Turtle de Alpaca (alpaca_bot/) sobre la historia, con las MISMAS reglas que corre en producción.

Es una MEDICIÓN de una regla ya fija (no se prueban variantes, no se ajusta nada). Fidelidad: las señales salen de las propias
funciones del bot (alpaca_bot/estrategia.calcular y alpaca_bot/config.py) aplicadas a las últimas 300 velas cerradas, igual que
en vivo (BARRAS_HISTORIA). Reglas del bot (bot_github_actions.py):
  COMPRA : cierre de la vela 4 h cerrada > máximo de los 120 máximos previos (20 días).
  VENTA  : cierre < mínimo de los 60 mínimos previos (10 días)  O  precio <= stop (entrada - 2 x ATR14).
  TAMAÑO : arriesga 2 % del patrimonio de la "manga" de cada par hasta el stop, sin apalancar (manga = patrimonio / 2).
Supuestos del simulador: entrada y salida por canal al precio de apertura de la vela siguiente; stop intra-vela a
min(stop, apertura) si el mínimo de la vela lo toca; costos por lado = comisión 0,25 % + slippage 0,05 % (los de config.py).
Cada par se simula con su manga independiente (el bot recalcula la manga con el patrimonio total en cada entrada: aproximación).
Línea base: entradas al azar con la misma salida (3.000 sorteos).
"""
import json
import os
import random
import statistics
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "alpaca_bot"))
sys.path.insert(0, AQUI)

import backtest as bt  # noqa: E402
import config as cfg  # noqa: E402
import estrategia  # noqa: E402
from velas import Vela  # noqa: E402

FEE, SLIP = cfg.COMISION_SIM, cfg.SLIPPAGE_SIM
VENTANA = cfg.BARRAS_HISTORIA
CAPITAL = 100_000.0
MANGAS = len(cfg.SIMBOLOS)


def indicadores_del_bot(t, o, h, l, c):
    """calcular() del bot en cada vela cerrada k, con las últimas 300 velas (como en vivo)."""
    velas = [Vela(int(x.timestamp() * 1000), o[i], h[i], l[i], c[i], 0.0) for i, x in enumerate(t)]
    out = [None] * len(t)
    for k in range(len(t)):
        out[k] = estrategia.calcular(velas[max(0, k - VENTANA + 1):k + 1])
    return out


def cerrar(entrada_ref, salida_ref, stop_dist):
    entrada = entrada_ref * (1 + SLIP)
    salida = salida_ref * (1 - SLIP)
    r = salida * (1 - FEE) / (entrada * (1 + FEE)) - 1
    return r, r / (stop_dist / entrada_ref)


def simular_salida(e, ind, o, l, ref_entrada):
    """Desde la entrada a la apertura de la vela e (señal en e-1). Devuelve (ref_salida, tipo, vela_salida) o None si sigue abierta."""
    atr = ind[e - 1]["atr"]
    dist = cfg.ATR_MULT_STOP * atr
    fill = ref_entrada * (1 + SLIP)
    stop = fill - dist
    for j in range(e, len(o)):
        if l[j] <= stop:
            return min(o[j], stop), "stop", j, dist
        s = ind[j]
        if s is not None and j + 1 < len(o) and s["close"] < s["min_salida"]:
            return o[j + 1], "canal", j + 1, dist
    return None, "abierta", len(o) - 1, dist


def correr_par(simbolo, ruta, corte_ts):
    t, o, h, l, c, seg = bt.cargar(ruta, 4)
    ind = indicadores_del_bot(t, o, h, l, c)
    corte = next(i for i, x in enumerate(t) if x >= corte_ts)
    trades, j, equity = [], 0, CAPITAL / MANGAS
    curva = [(t[0], equity)]
    activos = [i for i in range(len(t)) if ind[i] is not None]
    primero = activos[0]
    while j < len(t) - 1:
        s = ind[j]
        if s is not None and s["close"] > s["max_entrada"]:
            e = j + 1
            ref_s, tipo, js, dist = simular_salida(e, ind, o, l, o[e])
            ultimo_close = c[-1]
            if tipo == "abierta":
                ref_s = ultimo_close
            r, R = cerrar(o[e], ref_s, dist)
            fraccion = min(1.0, cfg.RIESGO_POR_OPERACION * o[e] / dist)
            equity *= 1 + fraccion * r
            trades.append({"simbolo": simbolo, "entrada_ts": str(t[e]), "salida_ts": str(t[js]), "entrada": o[e],
                           "salida": ref_s, "tipo": tipo, "R": R, "r": r, "fraccion": fraccion,
                           "barras": js - e + 1, "equity": equity, "e": e, "stop_pct": dist / o[e]})
            curva.append((t[js], equity))
            j = js            # la próxima señal se evalúa al cierre de la vela de salida
            if tipo == "abierta":
                break
        else:
            j += 1
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "ind": ind, "corte": corte, "primero": primero,
            "trades": trades, "curva": curva, "equity": equity}


def metricas(trs, rng, dias):
    n = len(trs)
    if not n:
        return {"n": 0}
    Rs = [x["R"] for x in trs]
    gan = [x for x in Rs if x > 0]
    per = [-x for x in Rs if x < 0]
    medias = sorted(statistics.fmean(rng.choices(Rs, k=n)) for _ in range(2000))
    return {"n": n, "por_mes": n / (dias / 30.4) if dias else None, "acierto": len(gan) / n,
            "R_neto": statistics.fmean(Rs), "ic90": (medias[100], medias[1900]),
            "factor_beneficio": (sum(gan) / sum(per)) if per else None,
            "mejor_R": max(Rs), "peor_R": min(Rs),
            "barras_prom": statistics.fmean(x["barras"] for x in trs),
            "tipos": {k: sum(1 for x in trs if x["tipo"] == k) for k in ("stop", "canal", "abierta")}}


def al_azar(par, desde, hasta, n, rng, sorteos=3000):
    """R neto promedio de n entradas al azar (misma salida) entre las velas desde..hasta."""
    ind, o, l, c = par["ind"], par["o"], par["l"], par["c"]
    pool = []
    for e in range(max(desde, par["primero"] + 1), min(hasta, len(o) - 2)):
        ref_s, tipo, js, dist = simular_salida(e, ind, o, l, o[e])
        if tipo == "abierta":
            continue
        pool.append(cerrar(o[e], ref_s, dist)[1])
    if n == 0 or n > len(pool):
        return None, None, len(pool)
    return statistics.fmean(pool), pool, len(pool)


def p_azar(obs, pool, n, rng, sorteos=3000):
    if not pool or n == 0 or n > len(pool):
        return None
    return (1 + sum(1 for _ in range(sorteos) if statistics.fmean(rng.sample(pool, n)) >= obs)) / (1 + sorteos)


def max_dd(curva):
    pico, dd = 0.0, 0.0
    for _, e in curva:
        pico = max(pico, e)
        dd = max(dd, (pico - e) / pico)
    return dd


def main():
    import datetime as dt
    rng = random.Random(7)
    corte_ts = dt.datetime(2025, 12, 24)
    datos = {"BTC/USD": os.path.join(AQUI, "datos", "btc_usd_1h_twelvedata.csv"),
             "ETH/USD": os.path.join(AQUI, "datos", "eth_usd_1h_twelvedata.csv")}
    salida = {"reglas": {"canal_entrada_velas": estrategia.canales()[0], "canal_salida_velas": estrategia.canales()[1],
                         "atr": cfg.ATR_PERIODO, "stop_atr": cfg.ATR_MULT_STOP, "riesgo": cfg.RIESGO_POR_OPERACION,
                         "comision": FEE, "slippage": SLIP}, "pares": {}}
    todas = []
    print("Reglas del bot: entrada = máx. de %d velas 4h previas, salida = mín. de %d velas, stop %.0f x ATR(%d), riesgo %.0f %% de la manga, costos %.2f %% + %.2f %% por lado" %
          (estrategia.canales()[0], estrategia.canales()[1], cfg.ATR_MULT_STOP, cfg.ATR_PERIODO,
           cfg.RIESGO_POR_OPERACION * 100, FEE * 100, SLIP * 100))
    for simbolo, ruta in datos.items():
        par = correr_par(simbolo, ruta, corte_ts)
        t, trades = par["t"], par["trades"]
        ultimo = par["ind"][-1]
        dias = (t[-1] - t[par["primero"]]).days
        bh = par["c"][-1] / par["c"][par["primero"]] - 1
        print("\n=== %s | %d velas 4h | evaluable desde %s | %d días" % (simbolo, len(t), t[par["primero"]], dias))
        print("  Estado AHORA (última vela cerrada %s): cierre %.2f | entrada si cierra > %.2f (falta %+.1f %%) | salida si < %.2f | ATR %.2f" %
              (t[-1], ultimo["close"], ultimo["max_entrada"], (ultimo["max_entrada"] / ultimo["close"] - 1) * 100,
               ultimo["min_salida"], ultimo["atr"]))
        per = {"todo": trades, "ajuste": [x for x in trades if x["e"] < par["corte"]],
               "validacion": [x for x in trades if x["e"] >= par["corte"]]}
        res = {"buy_hold": bh, "retorno_manga": par["equity"] / (CAPITAL / MANGAS) - 1, "dd_manga": max_dd(par["curva"]),
               "periodos": {}}
        print("  Turtle: retorno de la manga %+.1f %% (máx. caída %.1f %%) | comprar y mantener %+.1f %%" %
              (res["retorno_manga"] * 100, res["dd_manga"] * 100, bh * 100))
        for nombre, trs in per.items():
            desde = par["primero"] if nombre != "validacion" else par["corte"]
            hasta = par["corte"] if nombre == "ajuste" else len(t)
            d = (t[min(hasta, len(t)) - 1] - t[desde]).days
            m = metricas(trs, rng, d)
            if m["n"]:
                obs_azar, pool, npool = al_azar(par, desde, hasta, m["n"], rng)
                m["R_azar"] = obs_azar
                m["p_vs_azar"] = p_azar(m["R_neto"], pool, m["n"], rng)
                fb = "n/d" if m["factor_beneficio"] is None else "%.2f" % m["factor_beneficio"]
                print("  %-10s n=%2d (%.1f/mes) acierto %2.0f%% R neto %+.3f IC90 [%+.2f;%+.2f] FB %s mejor %+.1fR peor %+.1fR barras prom %.0f | azar %+.3f p/azar %s | stop %d canal %d abierta %d" %
                      (nombre, m["n"], m["por_mes"], m["acierto"] * 100, m["R_neto"], m["ic90"][0], m["ic90"][1], fb,
                       m["mejor_R"], m["peor_R"], m["barras_prom"], m["R_azar"],
                       "n/d" if m["p_vs_azar"] is None else "%.3f" % m["p_vs_azar"],
                       m["tipos"]["stop"], m["tipos"]["canal"], m["tipos"]["abierta"]))
            else:
                print("  %-10s sin operaciones" % nombre)
            res["periodos"][nombre] = m
        print("  Operaciones:")
        for x in trades:
            print("    %s -> %s  %9.2f -> %9.2f  %-7s %+5.2fR  (%3d velas, %.0f %% de la manga)" %
                  (x["entrada_ts"][:10], x["salida_ts"][:10], x["entrada"], x["salida"], x["tipo"], x["R"], x["barras"],
                   x["fraccion"] * 100))
        salida["pares"][simbolo] = {"resumen": res, "trades": [{k: v for k, v in x.items() if k != "e"} for x in trades]}
        todas.extend(trades)
    total = sum(p["resumen"]["retorno_manga"] for p in salida["pares"].values()) / MANGAS
    print("\n=== Cuenta completa (2 mangas de USD %.0f): retorno %+.1f %% sobre USD %.0f | operaciones: %d" %
          (CAPITAL / MANGAS, total * 100, CAPITAL, len(todas)))
    salida["retorno_total"] = total
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            json.dump(salida, f, indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
