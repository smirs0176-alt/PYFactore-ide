"""Озвучка через ElevenLabs: Ctrl+Shift+V — озвучить выделенное (или весь файл), Ctrl+Shift+K — сменить API-ключ."""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from tkinter import messagebox, simpledialog

from pyfactor.config import HOME, SETTINGS_F
from pyfactor.core.secure_store import delete_secret, get_secret, set_secret, take_warning
from pyfactor.core.utils import save_json


class VoiceMixin:
    def init_voice(self):
        t = self.editor.text
        t.bind("<Control-Shift-V>", lambda e: self.speak() or "break")
        t.bind("<Control-Shift-K>", lambda e: self.voice_key(True) or "break")

    def voice_key(self, force=False):
        k = get_secret("eleven_key", self.settings.get("eleven_key", ""))     # ключ — в защищённом хранилище, не в settings.json
        if force or not k:
            k = (simpledialog.askstring("ElevenLabs", "Вставь API-ключ ElevenLabs:", show="*", parent=self) or "").strip() or k
            if k:
                self.settings.pop("eleven_key", None)
                set_secret("eleven_key", k)
                save_json(SETTINGS_F, self.settings, private=True)
                warn = take_warning()
                if warn:
                    messagebox.showwarning("PyFactor", warn, parent=self)
        return k

    def speak(self):
        t = self.editor.text
        text = (t.get("sel.first", "sel.last") if t.tag_ranges("sel") else self.editor.get_code()).strip()[:2500]
        if not text:
            return self.toast("Нечего озвучивать")
        key = self.voice_key()
        if not key:
            return
        voice = self.settings.get("eleven_voice", "21m00Tcm4TlvDq8ikWAM")
        model = self.settings.get("eleven_model", "eleven_multilingual_v2")
        self.toast("Озвучиваю…")

        def work():
            try:
                req = urllib.request.Request(  # noqa: S310
                    "https://api.elevenlabs.io/v1/text-to-speech/%s?output_format=mp3_44100_128" % voice,
                    data=json.dumps({"text": text, "model_id": model}).encode("utf-8"),
                    headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
                with urllib.request.urlopen(req, timeout=90) as r:  # noqa: S310
                    data = r.read()
                d = os.path.join(HOME, "voice")
                os.makedirs(d, exist_ok=True)
                p = os.path.join(d, time.strftime("%Y%m%d-%H%M%S") + ".mp3")
                with open(p, "wb") as f:
                    f.write(data)
                self.ui(lambda: self.toast("Озвучено: " + os.path.basename(p)))
                self._play(p)
            except urllib.error.HTTPError as ex:
                code, body = ex.code, ex.read().decode("utf-8", "ignore")[:120]
                if code == 401:
                    delete_secret("eleven_key")                  # ключ не подошёл — забываем его, при следующем запуске спросим снова
                self.ui(lambda: self.toast("ElevenLabs %s: %s" % (code, body)))
            except Exception as ex:
                msg = str(ex)
                self.ui(lambda: self.toast("Озвучка: " + msg))
        threading.Thread(target=work, daemon=True).start()

    def _play(self, p):
        if sys.platform == "win32":
            os.startfile(p)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["afplay", p])  # noqa: S603, S607
        else:
            for cmd in (["mpg123", "-q"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"], ["xdg-open"]):
                if shutil.which(cmd[0]):
                    subprocess.Popen(cmd + [p])  # noqa: S603
                    break
