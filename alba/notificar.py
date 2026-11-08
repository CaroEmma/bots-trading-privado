"""Avisos de ALBA. Nunca rompen el ciclo: un aviso que falla se registra y listo.

Canales (todos opcionales, se usan los que estén configurados):
1. Resumen del job de GitHub Actions ($GITHUB_STEP_SUMMARY) y consola: siempre.
2. Issue en el repo ($GITHUB_TOKEN + $GITHUB_REPOSITORY): GitHub avisa por correo / app
   móvil a quien esté mencionado. Es el canal por defecto porque no necesita cuentas extra.
3. Telegram (secrets ALBA_TELEGRAM_TOKEN y ALBA_TELEGRAM_CHAT): aviso instantáneo al celular.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request


def _plano(texto):
    """Telegram sin parse_mode muestra el markdown tal cual: se lo saca (negritas y cursivas de una línea)."""
    texto = texto.replace("**", "")
    return re.sub(r"(?m)^_(.+)_$", r"\1", texto)


def _error_http(e):
    try:
        return json.loads(e.read().decode()).get("description") or str(e)
    except Exception:  # noqa: BLE001
        return str(e)


def telegram_descubrir(token, abrir=urllib.request.urlopen):
    """Devuelve ({chat_id: tipo}, None) con los chats que le escribieron al bot, o ({}, motivo del fallo)."""
    try:
        with abrir("https://api.telegram.org/bot%s/getUpdates" % token, timeout=20) as r:
            datos = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {}, "Telegram respondió %s: %s" % (e.code, _error_http(e))
    except Exception as e:  # noqa: BLE001
        return {}, "no pude conectar con Telegram (%s)" % type(e).__name__
    chats = {}
    for u in datos.get("result", []):
        c = (u.get("message") or u.get("channel_post") or {}).get("chat") or {}
        if "id" in c:
            chats[c["id"]] = c.get("type")
    return chats, None


def telegram_probar(token, chat, texto, abrir=urllib.request.urlopen):
    """Manda un mensaje de prueba. Devuelve (ok, detalle) sin lanzar excepciones."""
    cuerpo = urllib.parse.urlencode({"chat_id": chat, "text": texto}).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % token, data=cuerpo, method="POST")
    try:
        with abrir(req, timeout=20) as r:
            return (json.loads(r.read().decode()).get("ok") is True), "enviado"
    except urllib.error.HTTPError as e:
        return False, "Telegram respondió %s: %s" % (e.code, _error_http(e))
    except Exception as e:  # noqa: BLE001
        return False, "no pude conectar con Telegram (%s)" % type(e).__name__


def _post(url, cuerpo, headers, form=False):
    data = urllib.parse.urlencode(cuerpo).encode() if form else json.dumps(cuerpo).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


class Notificador:
    def __init__(self, mencionar=None, etiqueta="alba", enviar=None, entorno=None):
        self.env = entorno if entorno is not None else os.environ
        self.mencionar = mencionar
        self.etiqueta = etiqueta
        self.enviado = []          # para tests y para el log
        self._enviar = enviar or _post

    def avisar(self, titulo, cuerpo, importante=True):
        self.enviado.append((titulo, cuerpo))
        print("== AVISO: %s\n%s" % (titulo, cuerpo), flush=True)
        self._resumen(titulo, cuerpo)
        if not importante:
            return
        self._issue(titulo, cuerpo)
        self._telegram(titulo, cuerpo)

    def _resumen(self, titulo, cuerpo):
        ruta = self.env.get("GITHUB_STEP_SUMMARY")
        if not ruta:
            return
        try:
            with open(ruta, "a", encoding="utf-8") as f:
                f.write("### %s\n\n%s\n\n" % (titulo, cuerpo))
        except OSError as e:
            print("(aviso) no pude escribir el resumen: %s" % e)

    def _issue(self, titulo, cuerpo):
        token, repo = self.env.get("GITHUB_TOKEN"), self.env.get("GITHUB_REPOSITORY")
        if not token or not repo:
            return
        texto = cuerpo + (("\n\ncc @%s" % self.mencionar) if self.mencionar else "")
        try:
            self._enviar("https://api.github.com/repos/%s/issues" % repo,
                         {"title": titulo, "body": texto, "labels": [self.etiqueta]},
                         {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                          "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
        except Exception as e:  # noqa: BLE001 - un aviso nunca debe romper el ciclo
            print("(aviso) no pude crear el issue: %s" % e)

    def _telegram(self, titulo, cuerpo):
        token, chat = self.env.get("ALBA_TELEGRAM_TOKEN"), self.env.get("ALBA_TELEGRAM_CHAT")
        if not token or not chat:
            return
        try:
            self._enviar("https://api.telegram.org/bot%s/sendMessage" % token,
                         {"chat_id": chat, "text": _plano("%s\n\n%s" % (titulo, cuerpo))[:3900]}, {}, form=True)
        except Exception as e:  # noqa: BLE001
            print("(aviso) no pude enviar a Telegram: %s" % type(e).__name__)
