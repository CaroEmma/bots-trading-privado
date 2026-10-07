"""
Tracker del dry-run de funding-carry (cash-and-carry delta-neutral:
spot largo + perpetuo corto del mismo simbolo) para GitHub Actions.

Reemplaza el seguimiento MANUAL que se hacia leyendo la pantalla de
Binance Demo Trading (demo.binance.com) - ver
Bot-FundingCarry-Cripto/dry_run/registro_dry_run.md -, que nunca pudo
ser automatico porque Binance Demo Trading no tiene API propia.

Este script en cambio SOLO usa la API PUBLICA real de Binance (sin
login, sin API key, de solo lectura):
  - GET https://api.binance.com/api/v3/ticker/price      (precio spot)
  - GET https://fapi.binance.com/fapi/v1/premiumIndex    (marca/funding actual del perpetuo)
  - GET https://fapi.binance.com/fapi/v1/fundingRate      (historial de funding real liquidado)

Simula la MISMA posicion delta-neutral BTC/ETH/XRP/LTC/ADA que se abrio
a mano en el dry-run del demo el 03/04-oct-2026 (cantidades y precios
de apertura tomados de registro_dry_run.md, sección "Datos de apertura
completados"). A partir de ahi, en cada corrida:
  1. suma el funding REAL liquidado desde la ultima corrida (fapi/v1/fundingRate),
  2. revalua el PnL no realizado del corto perpetuo contra la marca actual,
  3. revalua el spot contra su precio actual,
  4. guarda todo en estado_funding_carry.json (que el workflow commitea).

LIMITACION HONESTA (documentada, no oculta): el funding real liquidado
se multiplica por el NOCIONAL DE ENTRADA (qty * precio de entrada), no
por el nocional exacto en el momento de cada liquidacion de 8h (eso
requeriria el precio de marca historico minuto a minuto, que la API
publica gratuita no ofrece por kline de futuros con esa granularidad
antigua). Es la misma aproximacion que ya usa el motor de backtest del
proyecto (Bot-FundingCarry-Cripto/backtest/motor_backtest_carry.py):
aproxima el precio del perpetuo con el spot/entrada cuando no hay dato
mejor, y lo deja documentado como limite en vez de inventar un numero.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

RUTA_ESTADO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estado_funding_carry.json")
HISTORIAL_MAXIMO = 500  # corridas a conservar en el JSON (acota el tamano del archivo)

URL_SPOT = "https://api.binance.com/api/v3/ticker/price"
URL_PREMIUM_INDEX = "https://fapi.binance.com/fapi/v1/premiumIndex"
URL_FUNDING_RATE = "https://fapi.binance.com/fapi/v1/fundingRate"

# Posicion abierta a mano en el dry-run del demo (registro_dry_run.md,
# "Datos de apertura completados", ~00:32-00:47 UTC del 04-oct-2026 -
# hora local de pantalla 03-oct ~21:32-21:47 ART, UTC = ART+3h).
# Timestamps verificados con calendar.timegm (UTC) sobre la hora de
# ejecucion de cada orden que registra el dry-run manual.
# qty_spot_neto = cantidad comprada menos la comision spot (cobrada en la moneda).
ENTRADA = {
    "BTCUSDT": {"qty_perp": 0.0120, "qty_spot_neto": 0.011988, "entrada_perp": 84827.00,
                "costo_spot_total": 1018.02612, "comision_perp": 0.40716960, "entrada_ts": 1791073920000},
    "ETHUSDT": {"qty_perp": 0.334, "qty_spot_neto": 0.333666, "entrada_perp": 2690.36,
                "costo_spot_total": 898.54684, "comision_perp": 0.35943209, "entrada_ts": 1791074761000},
    "XRPUSDT": {"qty_perp": 600, "qty_spot_neto": 599.40, "entrada_perp": 1.4885,
                "costo_spot_total": 893.70, "comision_perp": 0.35724015, "entrada_ts": 1791074784000},
    "LTCUSDT": {"qty_perp": 12.7, "qty_spot_neto": 12.6873, "entrada_perp": 70.52,
                "costo_spot_total": 895.604, "comision_perp": 0.35824160, "entrada_ts": 1791074808000},
    "ADAUSDT": {"qty_perp": 3700, "qty_spot_neto": 3696.30, "entrada_perp": 0.24380,
                "costo_spot_total": 902.80, "comision_perp": 0.36082400, "entrada_ts": 1791074831000},
}


def _get(url, params):
    full = url + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(full, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Binance {e.code} en {url}: {e.read().decode()[:300]}")


def _cargar_estado():
    if os.path.exists(RUTA_ESTADO):
        return json.load(open(RUTA_ESTADO, encoding="utf-8"))
    return {"ultimo_funding_ts": {}, "funding_acumulado_usdt": {}, "historial": []}


def _guardar_estado(estado):
    estado["historial"] = estado["historial"][-HISTORIAL_MAXIMO:]
    json.dump(estado, open(RUTA_ESTADO, "w", encoding="utf-8"), indent=1)


def _funding_nuevo(simbolo, desde_ms):
    """Trae del historial REAL de Binance todas las liquidaciones de
    funding (cada 8h) con fundingTime > desde_ms, paginando si hace falta."""
    nuevos = []
    start = desde_ms + 1
    while True:
        lote = _get(URL_FUNDING_RATE, {"symbol": simbolo, "startTime": start, "limit": 1000})
        if not lote:
            break
        nuevos.extend(lote)
        if len(lote) < 1000:
            break
        start = lote[-1]["fundingTime"] + 1
    return nuevos


def actualizar_simbolo(simbolo, datos_entrada, estado):
    desde = estado["ultimo_funding_ts"].get(simbolo, datos_entrada["entrada_ts"])
    nuevos = _funding_nuevo(simbolo, desde)
    acumulado = estado["funding_acumulado_usdt"].get(simbolo, 0.0)
    notional_entrada = datos_entrada["qty_perp"] * datos_entrada["entrada_perp"]
    for liquidacion in nuevos:
        tasa = float(liquidacion["fundingRate"])
        acumulado += tasa * notional_entrada  # corto cobra cuando la tasa es positiva
        estado["ultimo_funding_ts"][simbolo] = liquidacion["fundingTime"]
    estado["funding_acumulado_usdt"][simbolo] = acumulado

    spot_ahora = float(_get(URL_SPOT, {"symbol": simbolo})["price"])
    premium = _get(URL_PREMIUM_INDEX, {"symbol": simbolo})
    marca_ahora = float(premium["markPrice"])

    pnl_perp = (datos_entrada["entrada_perp"] - marca_ahora) * datos_entrada["qty_perp"]
    valor_spot_ahora = datos_entrada["qty_spot_neto"] * spot_ahora
    pnl_spot = valor_spot_ahora - datos_entrada["costo_spot_total"]
    base_usdt = marca_ahora - spot_ahora
    neto = acumulado + pnl_perp + pnl_spot - datos_entrada["comision_perp"]

    return {
        "simbolo": simbolo,
        "funding_acumulado_usdt": round(acumulado, 6),
        "cobros_nuevos_esta_corrida": len(nuevos),
        "marca_perp": marca_ahora,
        "spot": spot_ahora,
        "base_usdt": round(base_usdt, 4),
        "base_pct": round(base_usdt / spot_ahora * 100, 4),
        "pnl_perp_usdt": round(pnl_perp, 4),
        "valor_spot_usdt": round(valor_spot_ahora, 4),
        "pnl_spot_usdt": round(pnl_spot, 4),
        "neto_usdt": round(neto, 4),
    }


def main():
    estado = _cargar_estado()
    resultados = [actualizar_simbolo(sim, datos, estado) for sim, datos in ENTRADA.items()]
    total_funding = sum(r["funding_acumulado_usdt"] for r in resultados)
    total_neto = sum(r["neto_usdt"] for r in resultados)
    snapshot = {
        "ts": int(time.time() * 1000),
        "fecha_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) + " UTC",
        "por_simbolo": resultados,
        "total_funding_acumulado_usdt": round(total_funding, 4),
        "total_neto_usdt": round(total_neto, 4),
    }
    estado["historial"].append(snapshot)
    _guardar_estado(estado)

    print(snapshot["fecha_utc"])
    for r in resultados:
        print(f"  {r['simbolo']}: funding_acum={r['funding_acumulado_usdt']:.4f} USDT "
              f"({r['cobros_nuevos_esta_corrida']} cobros nuevos) | base={r['base_pct']:.3f}% | "
              f"pnl_perp={r['pnl_perp_usdt']:.2f} | pnl_spot={r['pnl_spot_usdt']:.2f} | neto={r['neto_usdt']:.2f}")
    print(f"  TOTAL: funding_acum={total_funding:.4f} USDT | neto={total_neto:.2f} USDT")


if __name__ == "__main__":
    main()
