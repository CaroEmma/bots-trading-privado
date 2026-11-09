"""Evaluación del experimento Kronos en modo sombra (proyectos/kronos/PREREGISTRO_SOMBRA.md). Solo biblioteca estándar.
No ejecuta Kronos: lee los pronósticos guardados y las velas reales y calcula las métricas preregistradas."""
import math
import random
import statistics

MS = 4 * 3600 * 1000           # una vela de 4 h
DIA_MS = 86_400_000
H_LARGO = 6                    # 24 h
UMBRAL_OPERABLE = 0.006        # costo de ida y vuelta de Alpaca en cripto


def signo(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)


def binomial_una_cola(n, k):
    """P(X >= k) con X ~ Binomial(n, 0,5): prueba exacta de una cola contra el azar."""
    if n == 0:
        return None
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def spearman(a, b):
    def rangos(v):
        orden = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[orden[j + 1]] == v[orden[i]]:
                j += 1
            for k in range(i, j + 1):
                r[orden[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    if len(a) < 3:
        return None
    ra, rb = rangos(a), rangos(b)
    ma, mb = statistics.fmean(ra), statistics.fmean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else None


def preparar(pronosticos, velas):
    """pronosticos: registros guardados. velas: {par: {ts_apertura_ms: cierre}}. Devuelve una fila por pronóstico."""
    filas = []
    for p in pronosticos:
        c = velas.get(p["par"], {})
        ts, ref = p["vela_ts"], p["cierre_ref"]
        f = {"par": p["par"], "ts": ts, "emitido_ms": p["emitido_ms"],
             "valido": p["emitido_ms"] <= ts + 2 * MS,                  # antes del cierre de la vela siguiente
             "ancla": (ts + MS) % DIA_MS == 0}                          # vela que cierra a las 00:00 UTC
        for h in (1, H_LARGO):
            real = c.get(ts + h * MS)
            f["pred%d" % h] = p["pred_cierres"][h - 1] / ref - 1
            f["real%d" % h] = (real / ref - 1) if real is not None else None
        prev = c.get(ts - H_LARGO * MS)
        f["mom"] = signo(ref / prev - 1) if prev else None
        filas.append(f)
    return filas


def aciertos(filas, h):
    f = [x for x in filas if x["real%d" % h] not in (None, 0) and x["pred%d" % h] != 0]
    return len(f), sum(1 for x in f if signo(x["pred%d" % h]) == signo(x["real%d" % h]))


def ic_bloques(filas, h=H_LARGO, bloque=6, reps=1000, semilla=7):
    """IC90 de la exactitud con todas las velas (superpuestas) por bootstrap de bloques de 6 velas consecutivas."""
    rng = random.Random(semilla)
    bloques = []
    for par in sorted({x["par"] for x in filas}):
        seq = sorted((x for x in filas if x["par"] == par and x["real%d" % h] not in (None, 0)), key=lambda x: x["ts"])
        hits = [1 if signo(x["pred%d" % h]) == signo(x["real%d" % h]) else 0 for x in seq]
        bloques += [hits[i:i + bloque] for i in range(0, len(hits), bloque) if hits[i:i + bloque]]
    if len(bloques) < 5:
        return None
    accs = []
    for _ in range(reps):
        m = [b for _ in bloques for b in [rng.choice(bloques)]]
        n = sum(len(b) for b in m)
        accs.append(sum(sum(b) for b in m) / n)
    accs.sort()
    return accs[int(reps * 0.05)], accs[int(reps * 0.95)]


def calibracion(filas, h=H_LARGO, grupos=10):
    f = sorted((x for x in filas if x["real%d" % h] is not None), key=lambda x: x["pred%d" % h])
    if len(f) < grupos * 3:
        return None
    out = []
    for g in range(grupos):
        s = f[g * len(f) // grupos:(g + 1) * len(f) // grupos]
        out.append({"n": len(s), "pred_prom": statistics.fmean(x["pred%d" % h] for x in s),
                    "real_prom": statistics.fmean(x["real%d" % h] for x in s)})
    return out


def evaluar(pronosticos, velas, ahora_ms, dias_min=90, n_min=150):
    filas = preparar(pronosticos, velas)
    validas = [x for x in filas if x["valido"]]
    res = {"total": len(filas), "validas": len(validas), "descartadas_por_atraso": len(filas) - len(validas)}
    if not validas:
        res.update(dias=0.0, anclas_n=0, formal_lista=False, veredicto="Sin pronósticos válidos todavía.")
        return res
    inicio = min(x["emitido_ms"] for x in validas)
    dias = (ahora_ms - inicio) / DIA_MS
    anclas_todas = [x for x in validas if x["ancla"]]
    anclas = [x for x in anclas_todas if x["real%d" % H_LARGO] not in (None, 0) and x["mom"]]
    n, hits = aciertos(anclas, H_LARGO)
    res.update(dias=dias, anclas_n=len(anclas), anclas_pendientes=sum(1 for x in anclas_todas if x["real%d" % H_LARGO] is None),
               anclas_esperadas=2 * int(dias), formal_lista=dias >= dias_min and len(anclas) >= n_min)
    # criterios preregistrados
    res["A"] = {"n": n, "aciertos": hits, "exactitud": hits / n if n else None, "p": binomial_una_cola(n, hits)}
    hm = sum(1 for x in anclas if x["mom"] == signo(x["real%d" % H_LARGO]))
    res["B"] = {"exactitud_momentum": hm / len(anclas) if anclas else None,
                "diferencia_pp": ((hits / n - hm / len(anclas)) * 100) if n and anclas else None}
    oper = [x for x in anclas if abs(x["pred%d" % H_LARGO]) > UMBRAL_OPERABLE]
    nc, hc = aciertos(oper, H_LARGO)
    res["C"] = {"n": nc, "aciertos": hc, "exactitud": hc / nc if nc else None}
    cumple_a = n > 0 and hits / n > 0.5 and res["A"]["p"] < 0.05
    cumple_b = res["B"]["diferencia_pp"] is not None and res["B"]["diferencia_pp"] >= 2.0
    cumple_c = nc >= 30 and hc / nc >= 0.55
    res["cumple"] = {"A": cumple_a, "B": cumple_b, "C": cumple_c}
    if not res["formal_lista"]:
        falta_d, falta_n = max(0, dias_min - dias), max(0, n_min - len(anclas))
        res["veredicto"] = "AÚN NO HAY EVALUACIÓN FORMAL: faltan %d días y %d pronósticos ancla (no es una conclusión)." % (math.ceil(falta_d), falta_n)
    elif cumple_a and cumple_b and cumple_c:
        res["veredicto"] = "PASA (A, B y C): preparar un preregistro nuevo para usarlo como filtro; no integrar nada todavía."
    else:
        res["veredicto"] = "NO PASA (A %s, B %s, C %s%s): archivar." % (
            "sí" if cumple_a else "no", "sí" if cumple_b else "no", "sí" if cumple_c else "no",
            "; C no concluyente (<30 casos)" if nc < 30 else "")
    # exploratorio (no entra en el criterio)
    expl = {"por_par": {}}
    for par in sorted({x["par"] for x in anclas}):
        npar, hpar = aciertos([x for x in anclas if x["par"] == par], H_LARGO)
        expl["por_par"][par] = {"n": npar, "exactitud": hpar / npar if npar else None}
    expl["spearman_24h"] = spearman([x["pred%d" % H_LARGO] for x in anclas], [x["real%d" % H_LARGO] for x in anclas])
    n1, h1 = aciertos(validas, 1)
    expl["exactitud_4h"] = {"n": n1, "exactitud": h1 / n1 if n1 else None}
    nt, ht = aciertos(validas, H_LARGO)
    expl["todas_las_velas_24h"] = {"n": nt, "exactitud": ht / nt if nt else None, "ic90_bloques": ic_bloques(validas)}
    expl["calibracion_24h"] = calibracion(validas)
    res["exploratorio"] = expl
    return res
