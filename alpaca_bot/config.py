"""Configuracion del bot Turtle long-only para Alpaca (cuenta PAPER,
fondos ficticios). Copia de Bot-Intradia-Cripto/alpaca_bot/config.py,
sin cambios de estrategia (misma que el backtest validado)."""

# Alpaca cripto: solo BTC/USD y ETH/USD de los 3 pares de trabajo (BNB no existe en Alpaca)
SIMBOLOS = ["BTC/USD", "ETH/USD"]

# --- estrategia (Turtle Rules originales, calibradas en horas reales) ---
TIMEFRAME_ALPACA = "4Hour"
MINUTOS_VELA = 240
HORAS_ENTRADA = 480        # 20 dias: canal de ruptura de entrada
HORAS_SALIDA = 240         # 10 dias: canal de salida
ATR_PERIODO = 14
ATR_MULT_STOP = 2.0
SOLO_LARGOS = True         # Alpaca NO permite vender en corto cripto

# --- riesgo ---
RIESGO_POR_OPERACION = 0.02   # 2% del patrimonio de la "manga" de cada par
NOCIONAL_MINIMO_USD = 10.0

# --- costos simulados (solo para replay): Alpaca cripto taker 0.25% + slippage ---
COMISION_SIM = 0.0025
SLIPPAGE_SIM = 0.0005

# --- operacion ---
SEGUNDOS_ENTRE_REVISIONES = 300   # referencia; en GitHub Actions el cron del workflow reemplaza el loop
BARRAS_HISTORIA = 300              # velas que se piden para calcular canal y ATR

URL_TRADING_PAPER = "https://paper-api.alpaca.markets"   # SIEMPRE paper; nunca se usa la URL de dinero real
URL_DATOS = "https://data.alpaca.markets"
