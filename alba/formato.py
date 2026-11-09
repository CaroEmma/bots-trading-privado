"""Mensajes de Telegram de ALBA y del Turtle: en español, ordenados, con tablas en letra monoespaciada.

Se mandan con parse_mode=HTML (Telegram acepta <b>, <i>, <code>, <pre>). Todo texto que no sea de este módulo
(símbolos, motivos, errores, titulares) se escapa con esc(). Solo formatea datos que ya existen: no inventa ninguno.
Los números van al estilo rioplatense: punto de miles y coma decimal (US$ 1.234,50).
"""
import html
import re

LIMITE = 3900  # Telegram admite 4096 caracteres; el HTML cortado a la mitad es inválido, por eso no se corta.

ETIQUETAS_SALIDA = {
    "objetivo": ("🎯", "OBJETIVO", "Objetivo alcanzado"),
    "stop": ("🛑", "STOP", "Stop activado"),
    "cierre_horario": ("⏰", "CIERRE POR HORARIO", "Cierre por horario (15:40 hora de Nueva York)"),
    "arrastre": ("⏰", "CIERRE DE ARRASTRE", "Cierre de arrastre (apertura siguiente)"),
}


def esc(x):
    return html.escape(str(x), quote=False)


def num(x, dec=2, con_signo=False):
    """1234.5 -> '1.234,50'. Con con_signo agrega '+' a los positivos. Evita el '-0,00'."""
    if round(x, dec) == 0:
        x = 0.0
    signo = "-" if x < 0 else ("+" if con_signo and x > 0 else "")
    cuerpo = "{:,.{d}f}".format(abs(x), d=dec).replace(",", "\0").replace(".", ",").replace("\0", ".")
    return signo + cuerpo


def usd(x, con_signo=False):
    if round(x, 2) == 0:
        x = 0.0
    signo = "-" if x < 0 else ("+" if con_signo and x > 0 else "")
    return "%sUS$ %s" % (signo, num(abs(x)))


def pct(p):
    return "n/d" if p is None else "%s %%" % num(p * 100, 0)


def tabla(filas):
    """Lista de (etiqueta, valor) -> bloque <pre> con etiquetas a la izquierda y valores alineados a la derecha."""
    filas = [(str(a), str(b)) for a, b in filas]
    ancho_a = max(len(a) for a, _ in filas)
    ancho_b = max(len(b) for _, b in filas)
    return "<pre>%s</pre>" % esc("\n".join("%s  %s" % (a.ljust(ancho_a), b.rjust(ancho_b)) for a, b in filas))


def horas(ahora_ny, ahora_ar=None):
    """'09:50 Nueva York · 11:50 Argentina'."""
    txt = "%s Nueva York" % ahora_ny.strftime("%H:%M")
    if ahora_ar is not None:
        txt += " · %s Argentina" % ahora_ar.strftime("%H:%M")
    return txt


def senal_es(razon):
    """Traduce la razón en inglés del skill de entrada. Si no la reconoce, no la inventa: usa el texto genérico."""
    m = re.search(r"the (\d{1,2}:\d{2}) bar closed above the range high", razon or "")
    if m:
        return "la vela de las %s cerró por encima del máximo del rango de apertura" % m.group(1)
    return "ruptura del rango de apertura"


def _recortar(texto):
    return texto if len(texto) <= LIMITE else None  # None: el Notificador usa el texto plano


def compra(sistema, sym, qty, fill, stop, target, hora, senal, tm=None, titulares=None, qty_dec=0):
    rr = (target - fill) / (fill - stop) if fill > stop else None
    filas = [("Cantidad", num(qty, qty_dec)), ("Entrada", usd(fill)), ("Stop", usd(stop)), ("Objetivo", usd(target)),
             ("Pérdida al stop", usd(-qty * (fill - stop))),
             ("Ganancia al objetivo", usd(qty * (target - fill), True)),
             ("Relación G/R", "n/d" if rr is None else num(rr, 1) + " a 1")]
    t = ["🟢 <b>COMPRA %s</b>" % esc(sym),
         "<i>%s · %s · dinero ficticio (paper)</i>" % (esc(sistema), esc(hora)), "", tabla(filas), "",
         "<b>Señal:</b> %s" % esc(senal)]
    if tm:
        t += ["", "<b>Simulación de la estrategia</b>",
              tabla([("Objetivo primero", pct(tm.get("p_target"))), ("Stop primero", pct(tm.get("p_stop"))),
                     ("R promedio simulado", num(tm["mc_avg_R"], 3, True) if tm.get("mc_avg_R") is not None else "n/d"),
                     ("Historial: disparos", str(tm.get("hist_disparos") if tm.get("hist_disparos") is not None else "n/d")),
                     ("Historial: R promedio",
                      num(tm["hist_avg_R"], 3, True) if tm.get("hist_avg_R") is not None else "n/d")])]
        if tm.get("hist_avg_R") is not None and tm["hist_avg_R"] < 0:
            t.append("⚠️ El historial de esta regla es negativo: es una prueba, no una señal confiable.")
    if titulares is not None:
        t += ["", "<b>Noticias de las últimas 24 h</b> (titulares originales, en inglés)"]
        t += ["• " + esc(x[:110]) for x in titulares[:3]] if titulares else ["Sin titulares."]
    t += ["", "<i>Prueba en dinero ficticio. No es asesoramiento financiero.</i>"]
    return _recortar("\n".join(t))


def venta(sistema, sym, motivo, qty, entrada, salida, pnl, r, hora, acumulado=None, qty_dec=0, nota=None):
    emoji, titulo, detalle = ETIQUETAS_SALIDA.get(motivo, ("🔔", str(motivo).upper(), str(motivo)))
    if pnl is not None and motivo not in ("objetivo", "stop"):
        emoji = "✅" if pnl >= 0 else "❌"   # cierres por horario o arrastre: el color lo da el resultado
    veredicto = "" if pnl is None else (" — %s %s" % ("GANÓ" if pnl >= 0 else "PERDIÓ", usd(abs(pnl))))
    filas = [("Cantidad", num(qty, qty_dec)), ("Entrada", usd(entrada)), ("Salida", usd(salida))]
    if pnl is not None:
        filas.append(("Resultado", usd(pnl, True)))
    if r is not None:
        filas.append(("Resultado en R", num(r, 2, True)))
    t = ["%s <b>%s %s</b>%s" % (emoji, esc(titulo), esc(sym), esc(veredicto)),
         "<i>%s · %s · dinero ficticio (paper)</i>" % (esc(sistema), esc(hora)), "", tabla(filas), "",
         "<b>Motivo:</b> %s" % esc(detalle)]
    if nota:
        t.append(esc(nota))
    if acumulado is not None:
        t += ["", "<b>Acumulado</b>", bloque_acumulado(acumulado)]
    return _recortar("\n".join(t))


def bloque_acumulado(e):
    if not e.get("n"):
        return "Todavía no hay operaciones cerradas."
    fb = "n/d" if e["factor_beneficio"] is None else num(e["factor_beneficio"], 2)
    s = tabla([("Operaciones", str(e["n"])),
               ("Ganadoras / perdedoras", "%d / %d" % (e["ganadoras"], e["perdedoras"])),
               ("Tasa de acierto", pct(e["tasa_acierto"])), ("R promedio", num(e["r_promedio"], 3, True)),
               ("Resultado total", usd(e["pnl"], True)), ("Factor de beneficio", fb),
               ("Caída máxima", usd(e["caida_maxima"]))])
    if e["n"] < 30:
        s += "\n⚠️ Muestra chica (%d %s): con tan pocos casos el resultado NO permite concluir si la " \
             "estrategia funciona." % (e["n"], "operación" if e["n"] == 1 else "operaciones")
    return s


def informe_diario(fecha, ops, descartes, resultado_dia, acumulado):
    t = ["📊 <b>INFORME DIARIO ALBA</b> · %s" % esc(fecha), "<i>Dinero ficticio (paper)</i>", ""]
    if ops:
        t.append("<b>Operaciones del día: %d</b>" % len(ops))
        filas = []
        for o in ops:
            motivo = ETIQUETAS_SALIDA.get(o["motivo"], ("", "", o["motivo"]))[2].split(" (")[0]
            filas += [(o["simbolo"], "%s → %s" % (num(o["entrada"]), num(o["salida"]))),
                      ("  " + motivo, "%s R · %s" % (num(o["r"], 2, True), usd(o["pnl"], True)))]
        t.append(tabla(filas))
    else:
        t.append("<b>Operaciones del día:</b> ninguna")
    t += ["", "<b>Resultado del día:</b> %s" % usd(resultado_dia, True)]
    total = sum(descartes.values())
    t += ["", "<b>Candidatos descartados: %d</b>" % total]
    if descartes:
        t.append(tabla([(k[:28], str(v)) for k, v in sorted(descartes.items())]))
    t += ["", "<b>Acumulado</b>", bloque_acumulado(acumulado), "",
          "<i>Un backtest o una racha corta no prueban que la estrategia funcione.</i>"]
    return _recortar("\n".join(t))


def alerta(titulo, detalle, pie=None, emoji="⚠️"):
    t = ["%s <b>%s</b>" % (emoji, esc(titulo)), "", "<code>%s</code>" % esc(detalle)]
    if pie:
        t += ["", esc(pie)]
    return _recortar("\n".join(t))


def diagnostico(lineas):
    """lineas: lista de (nombre, resultado). Un resultado con ' | ' se parte en varias filas (ancho de celular)."""
    filas = []
    for nombre, valor in lineas:
        partes = str(valor).split(" | ")
        filas.append((nombre, partes[0]))
        filas += [("", p) for p in partes[1:]]
    return _recortar("\n".join(["🔌 <b>ALBA · Diagnóstico de conexiones</b>", "", tabla(filas)]))


def _precio(x, dec=2):
    return "n/d" if x is None else num(float(x), dec)


def turtle_compra(sym, qty, fill, stop, dist_stop, cierre, max_entrada, min_salida, hora, qty_dec=6):
    filas = [("Cantidad", num(qty, qty_dec)), ("Entrada", usd(fill)), ("Stop", usd(stop)),
             ("Dist. al stop (2 ATR)", usd(dist_stop))]
    t = ["🟢 <b>COMPRA %s</b>" % esc(sym), "<i>TURTLE · %s · Alpaca Paper, dinero ficticio</i>" % esc(hora), "",
         tabla(filas), "",
         "<b>Señal:</b> el cierre (%s) superó el máximo de 20 días (%s)." % (_precio(cierre), _precio(max_entrada)),
         "<b>Sale por:</b> cierre por debajo de %s (mínimo de 10 días) o precio en el stop." % _precio(min_salida)]
    return _recortar("\n".join(t))


def turtle_venta(sym, motivo, entrada, salida, pnl_pct, hora):
    emoji = "🔔" if pnl_pct is None else ("✅" if pnl_pct >= 0 else "❌")
    veredicto = "" if pnl_pct is None else (" — %s %s %%" % ("GANÓ" if pnl_pct >= 0 else "PERDIÓ", num(abs(pnl_pct))))
    filas = [("Entrada", _precio(entrada)), ("Salida", _precio(salida))]
    if pnl_pct is not None:
        filas.append(("Resultado s/ precio", num(pnl_pct, 2, True) + " %"))
    t = ["%s <b>VENTA %s</b>%s" % (emoji, esc(sym), esc(veredicto)),
         "<i>TURTLE · %s · Alpaca Paper, dinero ficticio</i>" % esc(hora), "", tabla(filas), "",
         "<b>Motivo:</b> %s" % esc(motivo), "<i>Resultado sin costos.</i>"]
    return _recortar("\n".join(t))


def estado(hora, mercado_abierto, equity, variacion_dia, posiciones, compras, cierres, descartados):
    """Foto del momento (pedida a mano). posiciones: dicts sym/qty/entrada/actual/stop/target (datos en vivo de Alpaca);
    compras: (hora, sym, qty, precio); cierres: (hora, sym, motivo, r, pnl) — estos dos vienen del último guardado."""
    t = ["📌 <b>ESTADO DE ALBA</b>", "<i>%s · dinero ficticio (paper)</i>" % esc(hora), "",
         "<b>Mercado:</b> %s" % ("abierto" if mercado_abierto else "cerrado")]
    filas = [("Patrimonio (equity)", "n/d" if equity is None else usd(equity)),
             ("Cambio vs. cierre previo", "n/d" if variacion_dia is None else usd(variacion_dia, True))]
    t.append(tabla(filas))
    t += ["", "<b>Posiciones abiertas: %d</b>" % len(posiciones)]
    for p in posiciones:
        f = [(p["sym"], "%s acciones" % num(p["qty"], 0)), ("Entrada", usd(p["entrada"]))]
        if p.get("actual") is not None:
            pnl = (p["actual"] - p["entrada"]) * p["qty"]
            f += [("Precio actual", usd(p["actual"])),
                  ("Resultado ahora", "%s (%s %%)" % (usd(pnl, True), num((p["actual"] / p["entrada"] - 1) * 100, 2, True)))]
        f += [("Stop", "n/d" if p.get("stop") is None else usd(p["stop"])),
              ("Objetivo", "n/d" if p.get("target") is None else usd(p["target"]))]
        t.append(tabla(f))
    t += ["", "<b>Operaciones de hoy</b> (horas de Nueva York)"]
    filas = []
    for h, sym, qty, precio in compras:
        filas.append(("%s COMPRA %s" % (h, sym), "%s x %s" % (num(qty, 0), num(precio))))
    for h, sym, motivo, r, pnl in cierres:
        etiqueta = ETIQUETAS_SALIDA.get(motivo, ("", str(motivo).upper(), ""))[1]
        filas += [("%s %s %s" % (h, etiqueta, sym), "%s R" % num(r, 2, True)), ("", usd(pnl, True))]
    t.append(tabla(filas) if filas else "Todavía no hubo compras ni ventas.")
    t += ["", "<b>Candidatos descartados hoy:</b> %d" % descartados, "",
          "<i>Posiciones, precio y cuenta: en vivo desde Alpaca. Compras y ventas del día: según el último guardado "
          "(hasta 10 minutos de atraso).</i>"]
    return _recortar("\n".join(t))


def _lado_txt(lado):
    return ("🟢", "LARGO") if lado == "largo" else ("🔻", "CORTO")


def halcon_entrada(sym, lado, qty, entrada, stop, dist, real, hora, manga, qty_dec=6):
    emoji, nombre = _lado_txt(lado)
    donde = "real en Alpaca Paper" if real else "VIRTUAL (libro propio, no hay orden en Alpaca)"
    t = ["%s <b>HALCÓN · ENTRADA %s %s</b>" % (emoji, nombre, esc(sym)), "<i>%s · %s · dinero ficticio</i>" % (esc(hora), esc(donde)), "",
         tabla([("Cantidad", num(qty, qty_dec)), ("Entrada", usd(entrada)), ("Stop (2 ATR)", usd(stop)),
                ("Riesgo hasta el stop", usd(-qty * dist)), ("Manga del par", usd(manga))]), "",
         "<b>Sale por:</b> %s o por el stop." % ("cierre bajo el mínimo de 10 días" if lado == "largo" else "cierre sobre el máximo de 10 días"),
         "<i>Experimento hacia adelante. No es asesoramiento financiero.</i>"]
    return _recortar("\n".join(t))


def halcon_salida(sym, lado, motivo, qty, entrada, salida, pnl_usd, r, real, hora, resumen, tardia=False, estimado=False):
    emoji, nombre = _lado_txt(lado)
    cab = "✅" if pnl_usd >= 0 else "❌"
    motivos = {"stop": "Stop activado", "canal": "Cierre del canal de salida (10 días)"}
    t = ["%s <b>HALCÓN · SALIDA %s %s</b> — %s %s" % (cab, nombre, esc(sym), "GANÓ" if pnl_usd >= 0 else "PERDIÓ", usd(abs(pnl_usd))),
         "<i>%s · %s · dinero ficticio</i>" % (esc(hora), "real en Alpaca Paper" if real else "VIRTUAL"), "",
         tabla([("Cantidad", num(qty, 6)), ("Entrada", usd(entrada)), ("Salida", usd(salida)),
                ("Resultado", usd(pnl_usd, True)), ("Resultado en R", num(r, 2, True))]), "",
         "<b>Motivo:</b> %s%s" % (esc(motivos.get(motivo, motivo)), " (detectado con atraso)" if tardia else "")]
    if estimado:
        t.append("⚠️ Precio de salida estimado en el stop: no pude leer el fill real.")
    t += ["", "<b>Acumulado del experimento</b>", tabla(resumen)]
    return _recortar("\n".join(t))


def halcon_estado(hora, equity, pnl_total, abiertas, n_cerradas, perdidas, ultima_vela):
    t = ["📌 <b>ESTADO DE HALCÓN</b>", "<i>%s · dinero ficticio</i>" % esc(hora), "",
         tabla([("Capital virtual", usd(equity)), ("Resultado acumulado", usd(pnl_total, True)),
                ("Operaciones cerradas", str(n_cerradas)), ("Entradas perdidas*", str(perdidas)),
                ("Última vela evaluada", esc(ultima_vela))]), "", "<b>Posiciones abiertas: %d</b>" % len(abiertas)]
    for p in abiertas:
        _, nombre = _lado_txt(p["lado"])
        filas = [("%s %s" % (nombre, p["sym"]), "real" if p["real"] else "virtual"), ("Entrada", usd(p["entrada"])),
                 ("Stop", usd(p["stop"]))]
        if p.get("actual") is not None:
            pnl = (p["actual"] - p["entrada"]) * p["qty"] * (1 if p["lado"] == "largo" else -1)
            filas += [("Precio actual", usd(p["actual"])), ("Resultado ahora", usd(pnl, True))]
        t.append(tabla(filas))
    t += ["", "<i>*Entradas perdidas: señales de entrada que el bot vio tarde porque GitHub no lo corrió a tiempo.</i>"]
    return _recortar("\n".join(t))
