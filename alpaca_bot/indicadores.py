"""Indicador ATR (Average True Range) de Wilder. Copia minima de
Bot-Intradia-Cripto/backtest/indicadores.py (solo la funcion que usa
la estrategia Turtle en vivo)."""
from typing import List, Optional


def true_range(h: List[float], l: List[float], c: List[float]) -> List[float]:
    n = len(c)
    tr = [0.0] * n
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return tr


def atr(h: List[float], l: List[float], c: List[float], periodo: int = 14) -> List[Optional[float]]:
    tr = true_range(h, l, c)
    n = len(tr)
    salida: List[Optional[float]] = [None] * n
    if n < periodo:
        return salida
    prom = sum(tr[:periodo]) / periodo
    salida[periodo - 1] = prom
    for i in range(periodo, n):
        prom = (prom * (periodo - 1) + tr[i]) / periodo
        salida[i] = prom
    return salida
