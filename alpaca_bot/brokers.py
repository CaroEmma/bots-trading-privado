"""Brokers: AlpacaPaper (cuenta ficticia real de Alpaca). Adaptado de
Bot-Intradia-Cripto/alpaca_bot/brokers.py para GitHub Actions:
- usa velas.py local en vez de importar desde ../backtest (este repo
  no incluye esa carpeta).
- leer_env() SOLO lee variables de entorno (ALPACA_API_KEY /
  ALPACA_SECRET_KEY, inyectadas por el workflow desde GitHub Secrets).
  Nunca se lee ni se crea un archivo .env en este repo.
- se quito SimBroker (solo se usa para replay local, no corre en Actions).
"""
import calendar
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from velas import Vela

import config

MS_VELA = config.MINUTOS_VELA * 60_000


def _sin_barra(simbolo):
    return simbolo.replace("/", "")


def _iso_a_ms(t):
    return calendar.timegm(time.strptime(t[:19], "%Y-%m-%dT%H:%M:%S")) * 1000


def _http(base, metodo, ruta, headers, params=None, cuerpo=None):
    url = base + ruta + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=data, method=metodo, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read()
            return json.loads(txt) if txt else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Alpaca {e.code} en {metodo} {ruta}: {e.read().decode()[:300]}")


def leer_env():
    """Lee ALPACA_API_KEY / ALPACA_SECRET_KEY SOLO de variables de entorno
    (GitHub Secrets inyectados por el workflow). Nunca de un archivo."""
    return os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")


# ----------------------------------------------------------------- datos publicos
def barras(simbolo, desde_ms, hasta_ms=None):
    """Velas 4h de Alpaca (datos cripto publicos, sin keys), ordenadas,
    SOLO las ya cerradas."""
    out, token = [], None
    inicio = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(desde_ms / 1000))
    while True:
        p = {"symbols": simbolo, "timeframe": config.TIMEFRAME_ALPACA, "start": inicio, "limit": 1000}
        if token:
            p["page_token"] = token
        r = _http(config.URL_DATOS, "GET", "/v1beta3/crypto/us/bars", {"Accept": "application/json"}, params=p)
        for b in r["bars"].get(simbolo, []):
            out.append(Vela(_iso_a_ms(b["t"]), b["o"], b["h"], b["l"], b["c"], b["v"]))
        token = r.get("next_page_token")
        if not token:
            break
    ahora = int(time.time() * 1000)
    return [v for v in out if v.ts + MS_VELA <= ahora and (hasta_ms is None or v.ts <= hasta_ms)]


def precio_ultimo(simbolo):
    r = _http(config.URL_DATOS, "GET", "/v1beta3/crypto/us/latest/trades",
              {"Accept": "application/json"}, params={"symbols": simbolo})
    return float(r["trades"][simbolo]["p"])


# ----------------------------------------------------------------- Alpaca paper
class AlpacaPaper:
    def __init__(self, key, secret):
        if not key or not secret:
            raise RuntimeError("Faltan ALPACA_API_KEY / ALPACA_SECRET_KEY (ver GitHub Secrets del repo)")
        self.h = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
                  "Content-Type": "application/json", "Accept": "application/json"}

    def _t(self, metodo, ruta, params=None, cuerpo=None):
        return _http(config.URL_TRADING_PAPER, metodo, ruta, self.h, params, cuerpo)

    def cuenta(self):
        return self._t("GET", "/v2/account")

    def equity(self):
        return float(self.cuenta()["equity"])

    def posicion(self, simbolo):
        try:
            p = self._t("GET", f"/v2/positions/{_sin_barra(simbolo)}")
        except RuntimeError as e:
            if " 404 " in str(e):
                return None
            raise
        return {"qty": float(p["qty"]), "avg": float(p["avg_entry_price"])}

    def precio(self, simbolo):
        return precio_ultimo(simbolo)

    def barras(self, simbolo, cantidad):
        """Cada corrida de GitHub Actions es un proceso nuevo (sin cache en
        memoria entre corridas), asi que siempre pide la historia completa
        necesaria para calcular canal + ATR."""
        desde = int(time.time() * 1000) - (cantidad + 5) * MS_VELA
        return barras(simbolo, desde)[-cantidad:]

    def comprar(self, simbolo, qty, precio_ref=None):
        o = self._t("POST", "/v2/orders", cuerpo={"symbol": simbolo, "qty": f"{qty:.6f}", "side": "buy",
                                                  "type": "market", "time_in_force": "gtc"})
        return self._esperar_fill(o["id"])

    def vender_todo(self, simbolo, precio_fill=None):
        o = self._t("DELETE", f"/v2/positions/{_sin_barra(simbolo)}")
        oid = o.get("id") or (o.get("body") or {}).get("id")
        return self._esperar_fill(oid) if oid else None

    def _esperar_fill(self, oid, intentos=30):
        for _ in range(intentos):
            o = self._t("GET", f"/v2/orders/{oid}")
            if o["status"] == "filled":
                return float(o["filled_avg_price"])
            if o["status"] in ("canceled", "expired", "rejected"):
                raise RuntimeError(f"orden {oid} {o['status']}")
            time.sleep(1)
        raise RuntimeError(f"orden {oid} sin fill tras {intentos}s")

    def proteger(self, simbolo, stop, qty):
        """Stop-limit de venta en el servidor (red de seguridad por si el bot cae)."""
        self._t("POST", "/v2/orders", cuerpo={
            "symbol": simbolo, "qty": f"{qty:.6f}", "side": "sell", "type": "stop_limit",
            "stop_price": f"{stop:.2f}", "limit_price": f"{stop * 0.98:.2f}", "time_in_force": "gtc"})

    def cancelar_ordenes(self, simbolo):
        abiertas = self._t("GET", "/v2/orders", params={"status": "open", "symbols": simbolo}) or []
        for o in abiertas:
            self._t("DELETE", f"/v2/orders/{o['id']}")
