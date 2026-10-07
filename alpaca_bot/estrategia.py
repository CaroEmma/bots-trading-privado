"""Calculo de la señal Turtle sobre velas CERRADAS (sin I/O).
Mismas formulas que el backtest validado: canal de Donchian de las N
velas PREVIAS (excluye la actual) y ATR de Wilder. Adaptado de
Bot-Intradia-Cripto/alpaca_bot/estrategia.py: usa indicadores.py local
en vez de importar desde ../backtest (este repo no incluye esa carpeta)."""
from indicadores import atr

import config


def canales():
    ce = max(2, round(config.HORAS_ENTRADA * 60 / config.MINUTOS_VELA))
    cs = max(2, round(config.HORAS_SALIDA * 60 / config.MINUTOS_VELA))
    return ce, cs


def calcular(velas):
    """velas: lista de Vela CERRADAS, la ultima es la mas reciente.
    Devuelve None si no hay historia suficiente."""
    ce, cs = canales()
    if len(velas) < ce + config.ATR_PERIODO + 1:
        return None
    h = [v.high for v in velas]
    l = [v.low for v in velas]
    c = [v.close for v in velas]
    a = atr(h, l, c, config.ATR_PERIODO)[-1]
    return {
        "ts": velas[-1].ts,
        "close": c[-1],
        "max_entrada": max(h[-ce - 1:-1]),
        "min_salida": min(l[-cs - 1:-1]),
        "atr": a,
    }
