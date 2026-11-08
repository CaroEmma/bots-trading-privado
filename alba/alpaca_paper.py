"""Cliente mínimo de Alpaca para ALBA. SOLO PAPER (fondos ficticios).

Garantías de seguridad (verificadas por tests):
- la URL base tiene que ser exactamente la de paper; cualquier otra lanza
  ModoRealNoAutorizado antes de hacer un solo pedido;
- las claves se leen únicamente de variables de entorno (GitHub Secrets);
- el modo real NO está implementado: para habilitarlo hay que escribir código
  nuevo con la autorización explícita del usuario para cada orden.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

URL_PAPER = "https://paper-api.alpaca.markets"


class ModoRealNoAutorizado(RuntimeError):
    pass


class ErrorAlpaca(RuntimeError):
    def __init__(self, codigo, mensaje):
        super().__init__("Alpaca %s: %s" % (codigo, mensaje))
        self.codigo = codigo


def claves_desde_entorno(prefijo="ALBA_"):
    return os.environ.get(prefijo + "ALPACA_KEY"), os.environ.get(prefijo + "ALPACA_SECRET")


class AlpacaPaper:
    def __init__(self, key, secret, base=URL_PAPER, http=None):
        if base.rstrip("/") != URL_PAPER:
            raise ModoRealNoAutorizado(
                "Solo se permite %s. El modo real requiere la autorización explícita del usuario "
                "para cada orden y no está implementado." % URL_PAPER)
        if not key or not secret:
            raise RuntimeError("Faltan las claves de Alpaca Paper (GitHub Secrets).")
        self.base = base.rstrip("/")
        self._h = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
                   "Content-Type": "application/json", "Accept": "application/json"}
        self._http = http or self._http_real

    # ------------------------------------------------------------ transporte
    def _http_real(self, metodo, ruta, params=None, cuerpo=None):
        url = self.base + ruta + ("?" + urllib.parse.urlencode(params) if params else "")
        data = json.dumps(cuerpo).encode() if cuerpo is not None else None
        req = urllib.request.Request(url, data=data, method=metodo, headers=self._h)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                txt = r.read()
                return json.loads(txt) if txt else None
        except urllib.error.HTTPError as e:
            raise ErrorAlpaca(e.code, "%s %s: %s" % (metodo, ruta, e.read().decode()[:300]))

    # ------------------------------------------------------------ consultas
    def reloj(self):
        return self._http("GET", "/v2/clock")

    def cuenta(self):
        return self._http("GET", "/v2/account")

    def posiciones(self):
        out = {}
        for p in self._http("GET", "/v2/positions") or []:
            out[p["symbol"]] = {"qty": float(p["qty"]), "avg": float(p["avg_entry_price"]),
                                "valor": float(p.get("market_value") or 0)}
        return out

    def posicion(self, simbolo):
        try:
            p = self._http("GET", "/v2/positions/" + simbolo)
        except ErrorAlpaca as e:
            if e.codigo == 404:
                return None
            raise
        return {"qty": float(p["qty"]), "avg": float(p["avg_entry_price"]),
                "valor": float(p.get("market_value") or 0)}

    def orden(self, oid, con_patas=True):
        return self._http("GET", "/v2/orders/" + oid, params={"nested": "true"} if con_patas else None)

    # ------------------------------------------------------------ operaciones
    def colocar_bracket(self, simbolo, qty, take_profit, stop_loss):
        """Compra a mercado con take-profit y stop-loss en el servidor (orden bracket).
        time_in_force gtc: el stop y el objetivo NO vencen al cierre, así que si falla el cierre
        horario la posición sigue protegida (y se cierra de arrastre en la apertura siguiente)."""
        return self._http("POST", "/v2/orders", cuerpo={
            "symbol": simbolo, "qty": str(int(qty)), "side": "buy", "type": "market",
            "time_in_force": "gtc", "order_class": "bracket",
            "take_profit": {"limit_price": "%.2f" % float(take_profit)},
            "stop_loss": {"stop_price": "%.2f" % float(stop_loss)}})

    def esperar_fill(self, oid, intentos=30, pausa=1.0):
        for _ in range(intentos):
            o = self.orden(oid, con_patas=False)
            if o["status"] == "filled":
                return float(o["filled_avg_price"])
            if o["status"] in ("canceled", "expired", "rejected"):
                raise ErrorAlpaca(422, "orden %s quedó %s" % (oid, o["status"]))
            time.sleep(pausa)
        return None

    def cancelar_ordenes(self, simbolo):
        for o in self._http("GET", "/v2/orders", params={"status": "open", "symbols": simbolo, "nested": "true"}) or []:
            try:
                self._http("DELETE", "/v2/orders/" + o["id"])
            except ErrorAlpaca as e:
                if e.codigo not in (404, 422):
                    raise

    def cerrar_posicion(self, simbolo):
        o = self._http("DELETE", "/v2/positions/" + simbolo)
        return (o or {}).get("id") or ((o or {}).get("body") or {}).get("id")
