#!/usr/bin/env python3
"""Diagnostico de solo lectura de las claves de Alpaca (Turtle y HALCON) y de los limites de datos de cripto.
Imprime y publica en un issue SOLO codigos HTTP, mensajes de error de Alpaca y datos ya publicos (ultimos 4 del numero de cuenta,
equity). Nunca imprime claves."""
import json
import os
import time
import urllib.error
import urllib.request

TRADING = "https://paper-api.alpaca.markets/v2/account"
DATOS = "https://data.alpaca.markets/v1beta3/crypto/us/latest/trades?symbols=BTC%2FUSD"


def pedir(url, key=None, secret=None):
    h = {"Accept": "application/json", "User-Agent": "diagnostico-alpaca/1.0"}
    if key and secret:
        h["APCA-API-KEY-ID"], h["APCA-API-SECRET-KEY"] = key, secret
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=20) as r:
            return r.status, json.loads(r.read().decode() or "null"), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            cuerpo = json.loads(e.read().decode())
        except Exception:  # noqa: BLE001
            cuerpo = None
        return e.code, cuerpo, dict(e.headers)
    except Exception as e:  # noqa: BLE001
        return type(e).__name__, None, {}


def cuenta(nombre, key, secret):
    if not key or not secret:
        return "- %s: el secret NO está cargado (vacío)." % nombre
    st, d, _ = pedir(TRADING, key, secret)
    if st == 200 and isinstance(d, dict):
        return "- %s: HTTP 200 | cuenta %s | estado %s | equity %s" % (
            nombre, "…" + str(d.get("account_number", ""))[-4:], d.get("status"), d.get("equity"))
    msg = (d or {}).get("message") if isinstance(d, dict) else None
    return "- %s: HTTP %s | mensaje de Alpaca: %s" % (nombre, st, msg)


def datos(nombre, key, secret, n=8):
    estados = []
    for _ in range(n):
        st, _, h = pedir(DATOS, key, secret)
        estados.append(str(st))
        time.sleep(0.3)
    return "- Datos de cripto %s, %d pedidos seguidos: %s" % (nombre, n, ", ".join(estados))


def main():
    k = os.environ
    lineas = ["**Cuentas (GET /v2/account en paper)**",
              cuenta("claves del Turtle (ALPACA_API_KEY)", k.get("TURTLE_KEY"), k.get("TURTLE_SECRET")),
              cuenta("claves de HALCÓN (HALCON_ALPACA_KEY)", k.get("HALCON_KEY"), k.get("HALCON_SECRET")),
              "", "**Pedidos de datos de cripto (último precio de BTC/USD)**",
              datos("sin claves", None, None),
              datos("con claves de HALCÓN", k.get("HALCON_KEY"), k.get("HALCON_SECRET"))]
    texto = "\n".join(lineas)
    print(texto)
    token, repo = k.get("GITHUB_TOKEN"), k.get("GITHUB_REPOSITORY")
    if token and repo:
        req = urllib.request.Request("https://api.github.com/repos/%s/issues" % repo, method="POST",
                                     data=json.dumps({"title": "Diagnóstico de Alpaca (Turtle y HALCÓN)", "body": texto,
                                                      "labels": ["diagnostico"]}).encode(),
                                     headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                                              "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=20).read()
        except Exception as e:  # noqa: BLE001
            print("(no pude crear el issue: %s)" % e)


if __name__ == "__main__":
    main()
