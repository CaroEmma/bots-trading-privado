"""Estructura de vela OHLCV. Copia minima de Bot-Intradia-Cripto/backtest/velas.py
(solo la parte que usa el bot en vivo; sin CSV, sin dependencias externas)."""
from dataclasses import dataclass


@dataclass
class Vela:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float
