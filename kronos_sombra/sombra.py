#!/usr/bin/env python3
"""Kronos en MODO SOMBRA (proyectos/kronos/PREREGISTRO_SOMBRA.md). Registra pronósticos; NO opera ni influye en ALBA/HALCÓN.

  --necesita     (solo biblioteca estándar) imprime hacer=si|no: si hay una vela cerrada sin pronóstico todavía.
  --pronosticar  corre Kronos (código de terceros fijado por commit, en --kronos DIR) y agrega a pronosticos.jsonl.
  --informe      evalúa con las velas reales y muestra el informe; con --telegram lo manda (solo código propio).
Datos: velas de 4 h públicas de Alpaca (sin claves). No usa ni recibe claves de Alpaca.
"""
import argparse
import json
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(RAIZ, "alpaca_bot"))
sys.path.insert(0, os.path.join(RAIZ, "alba"))
sys.path.insert(0, AQUI)

import evaluar as ev  # noqa: E402

PARES = ["BTC/USD", "ETH/USD"]
LOOKBACK, PRED_LEN, MS = 400, 6, ev.MS
KRONOS_SHA = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
MODELO, TOKENIZER = "NeoQuasar/Kronos-small", "NeoQuasar/Kronos-Tokenizer-base"
PARAMS = {"T": 1.0, "top_k": 0, "top_p": 0.9, "sample_count": 5}
RUTA, CONGELADO = "pronosticos.jsonl", "config_congelada.json"


def velas_cerradas(par, cantidad):
    import brokers
    desde = int(time.time() * 1000) - (cantidad + 5) * MS
    return brokers.barras(par, desde)[-cantidad:]


def leer(dir_estado, nombre):
    ruta = os.path.join(dir_estado, nombre)
    if not os.path.exists(ruta):
        return [] if nombre.endswith(".jsonl") else {}
    with open(ruta, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()] if nombre.endswith(".jsonl") else json.load(f)


def necesita(dir_estado, barras=velas_cerradas):
    hechos = {(p["par"], p["vela_ts"]) for p in leer(dir_estado, RUTA)}
    for par in PARES:
        v = barras(par, 2)
        if v and (par, v[-1].ts) not in hechos:
            return True
    return False


def pronosticar(dir_estado, dir_kronos):
    import numpy as np
    import pandas as pd
    import torch
    from huggingface_hub import HfApi
    sys.path.insert(0, dir_kronos)
    from model import Kronos, KronosTokenizer, KronosPredictor

    os.makedirs(dir_estado, exist_ok=True)
    cfg = leer(dir_estado, CONGELADO)
    if not cfg:                                   # primera corrida: se resuelven y CONGELAN las revisiones
        api = HfApi()
        cfg = {"modelo": MODELO, "tokenizer": TOKENIZER, "rev_modelo": api.model_info(MODELO).sha,
               "rev_tokenizer": api.model_info(TOKENIZER).sha, "kronos_sha": KRONOS_SHA, "params": PARAMS,
               "lookback": LOOKBACK, "pred_len": PRED_LEN, "congelada_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime())}
        with open(os.path.join(dir_estado, CONGELADO), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
        print("Revisiones congeladas:", cfg["rev_modelo"], cfg["rev_tokenizer"])
    elif cfg.get("kronos_sha") != KRONOS_SHA or cfg.get("params") != PARAMS:
        raise SystemExit("La configuración congelada no coincide con el código: experimento invalidado (ver preregistro).")
    sha_real = os.popen("git -C %s rev-parse HEAD" % dir_kronos).read().strip()
    if sha_real != KRONOS_SHA:
        raise SystemExit("El código de Kronos no está en el commit fijado (%s)." % sha_real)

    tokenizer = KronosTokenizer.from_pretrained(TOKENIZER, revision=cfg["rev_tokenizer"])
    modelo = Kronos.from_pretrained(MODELO, revision=cfg["rev_modelo"])
    predictor = KronosPredictor(modelo, tokenizer, device="cpu", max_context=512)
    versiones = {"torch": torch.__version__, "pandas": pd.__version__, "numpy": np.__version__}
    hechos = {(p["par"], p["vela_ts"]) for p in leer(dir_estado, RUTA)}

    for par in PARES:
        velas = velas_cerradas(par, LOOKBACK)
        if len(velas) < LOOKBACK:
            print("%s: solo %d velas (< %d); omito" % (par, len(velas), LOOKBACK))
            continue
        ts_ref = velas[-1].ts
        if (par, ts_ref) in hechos:
            continue
        emitido = int(time.time() * 1000)
        df = pd.DataFrame({"open": [v.open for v in velas], "high": [v.high for v in velas], "low": [v.low for v in velas],
                           "close": [v.close for v in velas], "volume": [v.volume for v in velas]})
        x_ts = pd.Series(pd.to_datetime([v.ts for v in velas], unit="ms"))
        y_ts = pd.Series(pd.to_datetime([ts_ref + (i + 1) * MS for i in range(PRED_LEN)], unit="ms"))
        semilla = (ts_ref // 1000) % (2 ** 31)
        torch.manual_seed(semilla)
        np.random.seed(semilla % (2 ** 32))
        t0 = time.time()
        pred = predictor.predict(df=df, x_timestamp=x_ts, y_timestamp=y_ts, pred_len=PRED_LEN, verbose=False, **PARAMS)
        seg = time.time() - t0
        cierres = [float(c) for c in pred["close"].tolist()]
        reg = {"par": par, "vela_ts": ts_ref, "cierre_ref": velas[-1].close, "pred_cierres": cierres, "emitido_ms": emitido,
               "semilla": semilla, "segundos": round(seg, 1), "rev_modelo": cfg["rev_modelo"], "versiones": versiones}
        with open(os.path.join(dir_estado, RUTA), "a", encoding="utf-8") as f:
            f.write(json.dumps(reg) + "\n")
        print("%s: pronóstico vela %s | ref %.2f -> +24 h %.2f (%+.2f %%) | %.1f s" % (
            par, time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts_ref / 1000)), velas[-1].close, cierres[-1],
            (cierres[-1] / velas[-1].close - 1) * 100, seg))


def reunir_velas(pronosticos):
    import brokers
    velas = {}
    for par in PARES:
        mios = [p["vela_ts"] for p in pronosticos if p["par"] == par]
        if not mios:
            continue
        desde = min(mios) - 8 * MS
        velas[par] = {v.ts: v.close for v in brokers.barras(par, desde)}
    return velas


def texto(res):
    L = ["KRONOS EN MODO SOMBRA — informe %s UTC" % time.strftime("%Y-%m-%d %H:%M", time.gmtime()),
         "Pronósticos: %d (válidos %d, descartados por atraso %d) | días corridos: %.1f" % (res["total"], res["validas"], res["descartadas_por_atraso"], res["dias"]),
         res["veredicto"]]
    if "A" in res:
        A, B, C = res["A"], res["B"], res["C"]
        L += ["Anclas con resultado: %d (pendientes %d, esperadas ~%d)" % (res["anclas_n"], res["anclas_pendientes"], res["anclas_esperadas"]),
              "A) exactitud 24 h: %s (%d/%d) p=%s" % (_p(A["exactitud"]), A["aciertos"], A["n"], "n/d" if A["p"] is None else "%.3f" % A["p"]),
              "B) momentum: %s | diferencia %s pp" % (_p(B["exactitud_momentum"]), "n/d" if B["diferencia_pp"] is None else "%+.1f" % B["diferencia_pp"]),
              "C) operables (>0,6 %%): %s (%d casos)" % (_p(C["exactitud"]), C["n"])]
    return "\n".join(L)


def _p(x):
    return "n/d" if x is None else "%.1f %%" % (x * 100)


def informe(dir_estado, telegram):
    pron = leer(dir_estado, RUTA)
    if not pron:
        print("Todavía no hay pronósticos.")
        return
    res = ev.evaluar(pron, reunir_velas(pron), int(time.time() * 1000))
    txt = texto(res)
    print(txt)
    print(json.dumps({k: v for k, v in res.items() if k != "exploratorio"}, indent=1, default=str)[:1500])
    if telegram:
        import formato
        from notificar import Notificador
        filas = [("Pronósticos válidos", "%d / %d" % (res["validas"], res["total"])), ("Días corridos", formato.num(res["dias"], 1))]
        if "A" in res:
            filas += [("Anclas con resultado", str(res["anclas_n"])), ("Exactitud 24 h", _p(res["A"]["exactitud"])),
                      ("Momentum (base)", _p(res["B"]["exactitud_momentum"])), ("Operables", "%s (%d)" % (_p(res["C"]["exactitud"]), res["C"]["n"]))]
        html = "\n".join(["🧪 <b>KRONOS EN MODO SOMBRA</b>", "<i>informe semanal · no opera · dinero ficticio</i>", "", formato.tabla(filas), "",
                          formato.esc(res["veredicto"]), "", "<i>Hasta la evaluación formal estos números NO son una conclusión.</i>"])
        Notificador(entorno=os.environ)._telegram("Kronos sombra", texto(res), html)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--estado", required=True)
    ap.add_argument("--necesita", action="store_true")
    ap.add_argument("--pronosticar", action="store_true")
    ap.add_argument("--informe", action="store_true")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--kronos", default="/opt/kronos")
    a = ap.parse_args(argv)
    if a.necesita:
        print("hacer=%s" % ("si" if necesita(a.estado) else "no"))
    elif a.pronosticar:
        pronosticar(a.estado, a.kronos)
    elif a.informe:
        informe(a.estado, a.telegram)
    return 0


if __name__ == "__main__":
    sys.exit(main())
