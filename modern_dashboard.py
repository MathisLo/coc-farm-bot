"""Desktop WebView facade around the existing Python bot controller.

Tk and all BotApp variables stay on one backend thread. WebView API calls cross
through a queue so the browser never touches Tk objects from another thread.
"""
import base64
import gc
from concurrent.futures import Future
import io
import json
from pathlib import Path
import queue
import sys
import threading
import traceback

from app_meta import APP_NAME, APP_VERSION


FIELDS = {
    "window_title": "window_title", "min_gold": "min_gold",
    "min_elixir": "min_elixir", "loot_margin": "loot_margin",
    "electrodragon_count": "electrodragon_count", "dragon_count": "dragon_count",
    "rage_count": "rage_count",
    "hero_count": "hero_count",
    "delay_between_dragons": "delay_between_dragons",
    "and_rule": "and_rule", "dry_run": "dry_run",
    "upgrade_wall": "upgrade_wall",
    "upgrade_recommended": "upgrade_recommended", "upgrade_heroes": "upgrade_heroes",
    "upgrade_hero_eradicator": "upgrade_hero_eradicator",
    "upgrade_explosive_catapult": "upgrade_explosive_catapult",
    "upgrade_firespitter": "upgrade_firespitter",
    "chain_attacks": "chain_attacks",
}


class Bridge:
    def __init__(self):
        self.requests = queue.Queue()
        self.ready = threading.Event()
        self.app = None
        self.error = None
        self.preview_image_id = None
        self.preview_revision = 0
        self.preview_data = None
        self.thread = threading.Thread(target=self._backend, name="BotBackend", daemon=True)
        self.thread.start()
        if not self.ready.wait(20):
            raise RuntimeError("Le moteur du bot ne répond pas.")
        if self.error:
            raise self.error

    def _backend(self):
        try:
            from main import BotApp
            self.app = BotApp(hidden=True)
            self.app.root.after(50, self._drain)
        except Exception as exc:
            self.error = exc
            self.ready.set()
            return
        self.ready.set()
        self.app.run()
        app = self.app
        self.app = None
        del app
        gc.collect()

    def _drain(self):
        for _ in range(30):
            try:
                name, payload, future = self.requests.get_nowait()
            except queue.Empty:
                break
            try:
                future.set_result(self._execute(name, payload))
            except Exception:
                self.app._trace("ERREUR", traceback.format_exc())
                future.set_result({"ok": False, "error": "Erreur de communication avec le moteur Python."})
        if not getattr(self.app, "_closed", False):
            self.app.root.after(50, self._drain)

    def _snapshot(self, request):
        from main import ACCOUNT_SNAPSHOT_PATH
        app = self.app
        image = getattr(app, "_last_capture", None)
        if image is not None and id(image) != self.preview_image_id:
            thumb = image.copy()
            thumb.thumbnail((1050, 650))
            buffer = io.BytesIO()
            thumb.save(buffer, format="PNG")
            self.preview_data = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
            self.preview_image_id = id(image)
            self.preview_revision += 1

        profile = None
        if ACCOUNT_SNAPSHOT_PATH.exists():
            try:
                profile = json.loads(ACCOUNT_SNAPSHOT_PATH.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                app._trace("ERREUR", "Relevé du profil enregistré illisible")

        with app.journal._lock:
            log_seq = app.journal.recent_seq
            logs = list(app.journal.recent)[-100:] if request.get("log_seq") != log_seq else None
        stats = dict(app.farm_stats.data)
        return {
            "ok": True,
            "version": APP_VERSION,
            "values": {key: getattr(app, attr).get() for key, attr in FIELDS.items()},
            "windows": list(app.windows["values"]),
            "stats": {key: stats[key] for key in ("gold", "elixir", "dark_elixir", "battles")},
            "pending_battle": bool(stats.get("pending")),
            "profile": profile,
            "status": app.status.get(), "run_state": app.run_state.get(),
            "busy": app._busy(), "log_seq": log_seq, "logs": logs,
            "preview_revision": self.preview_revision,
            "preview": self.preview_data if request.get("preview_revision") != self.preview_revision else None,
            "calibration_count": len(app.settings.layout_overrides),
        }

    def _set_values(self, values):
        app = self.app
        if app._busy():
            return False
        for key, value in values.items():
            if key in FIELDS:
                getattr(app, FIELDS[key]).set(value)
        return True

    def _execute(self, name, payload):
        from main import LAYOUT_DEFAULTS, layout_labels
        app = self.app
        if name == "snapshot":
            return self._snapshot(payload)
        if name == "calibration_info":
            return {"ok": True, "defaults": LAYOUT_DEFAULTS,
                    "labels": layout_labels(), "overrides": app.settings.layout_overrides,
                    "ratio": app.settings.layout_aspect_ratio,
                    "preview_revision": self.preview_revision,
                    "preview": self.preview_data}
        if name == "close":
            app.close()
            return {"ok": True}
        if name == "save_calibration":
            try:
                app.save_calibration(payload.get("overrides", {}), float(payload.get("ratio", 0)))
            except (OSError, ValueError) as exc:
                return {"ok": False, "error": str(exc)}
            return {"ok": True, "status": app.status.get()}
        if name == "export_to":
            destination = Path(payload["path"])
            if destination.suffix.lower() != ".zip":
                destination = destination.with_suffix(".zip")
            try:
                app.export_diagnostic(destination)
            except (OSError, ValueError) as exc:
                app._trace("ERREUR", f"Export impossible : {exc}")
                return {"ok": False, "error": "Export impossible. Consultez le diagnostic du bot."}
            app.write(f"Diagnostic enregistré : {destination}")
            return {"ok": True, "path": str(destination)}
        if name == "reset":
            return {"ok": bool(app.reset_all_data(confirmed=True, show_errors=False))}
        if name == "stop":
            if not app._busy():
                return {"ok": False, "error": "Aucune opération en cours."}
            app.stop()
            return {"ok": True, "status": app.status.get()}
        if name == "refresh":
            app.refresh()
            return {"ok": True, "count": len(app.windows["values"])}
        if name in ("save", "start", "walls", "attack", "buildings"):
            if not self._set_values(payload.get("values", {})):
                return {"ok": False, "error": "Une opération est déjà en cours."}
            if name == "save":
                ok = app.persist()
                return {"ok": ok, "status": app.status.get(),
                        "error": None if ok else app.status.get()}
            if name == "start":
                app.start_farm()
            elif name == "walls":
                app.start_walls()
            else:
                app.start_independent(name)
            ok = app._busy() and app.run_state.get() == "EN COURS"
            return {"ok": ok, "status": app.status.get(),
                    "error": None if ok else app.status.get()}
        if name in ("inspect", "profile", "calibration_capture"):
            if app._busy():
                return {"ok": False, "error": "Une opération est déjà en cours."}
            if name == "inspect":
                app.inspect_game()
            elif name == "profile":
                app.scan_profile()
            else:
                app.capture_for_web_calibration()
            return {"ok": True, "status": app.status.get()}
        raise ValueError("Action inconnue")

    def call(self, name, payload=None):
        if name == "export":
            import webview
            from datetime import datetime
            selected = webview.windows[0].create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=f"CoCFarmBot-diagnostic-{datetime.now():%Y%m%d-%H%M%S}.zip",
                file_types=("Archive ZIP (*.zip)",))
            if not selected:
                return {"ok": False, "cancelled": True}
            name, payload = "export_to", {"path": selected[0]}
        if name == "close" and not self.thread.is_alive():
            return {"ok": True}
        future = Future()
        self.requests.put((name, payload or {}, future))
        result = future.result(timeout=90)
        if name == "close":
            self.thread.join(timeout=5)
        if name == "reset" and result.get("ok"):
            import webview
            webview.windows[0].destroy()
        return result


def run():
    import webview
    import ctypes
    import time

    class Rect(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    bridge = Bridge()
    # PyInstaller one-file runs from a temporary extraction directory. Resolve
    # resources from that directory first so the logo and window icon do not
    # depend on the current working directory or how the app was opened.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    page = base / "web_dashboard.html"
    icon = base / "assets" / "kit" / "app" / "app.ico"
    if not icon.is_file():
        fallback = Path(__file__).resolve().parent / "assets" / "kit" / "app" / "app.ico"
        if fallback.is_file():
            icon = fallback

    def apply_windows_icon(icon_path):
        """Apply the packaged icon to the native WebView window.

        pywebview's ``icon`` option is backend-dependent on Windows.  The
        explicit WM_SETICON call keeps the title bar, taskbar and Alt+Tab
        entry consistent when EdgeChromium creates the native window later.
        """
        if sys.platform != "win32" or not icon_path.is_file():
            return
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "CoCFarmBot.Desktop"
            )
            user32 = ctypes.windll.user32
            user32.FindWindowW.restype = ctypes.c_void_p
            user32.LoadImageW.restype = ctypes.c_void_p
            for _ in range(100):
                hwnd = user32.FindWindowW(None, APP_NAME)
                if hwnd:
                    flags = 0x00000010 | 0x00000040  # LR_LOADFROMFILE | LR_DEFAULTSIZE
                    big = user32.LoadImageW(None, str(icon_path), 1, 256, 256, flags)
                    small = user32.LoadImageW(None, str(icon_path), 1, 16, 16, flags)
                    if big:
                        user32.SendMessageW(hwnd, 0x0080, 1, big)  # WM_SETICON / ICON_BIG
                    if small:
                        user32.SendMessageW(hwnd, 0x0080, 0, small)  # WM_SETICON / ICON_SMALL
                    return
                time.sleep(0.1)
        except (AttributeError, OSError):
            # The UI remains usable on non-Windows WebView backends.
            return
    work = Rect()
    if not ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(work), 0):
        work.left = work.top = 0
        work.right = ctypes.windll.user32.GetSystemMetrics(0)
        work.bottom = ctypes.windll.user32.GetSystemMetrics(1)
    work_width, work_height = work.right - work.left, work.bottom - work.top
    width = min(1586, max(1080, work_width - 60), work_width)
    height = min(1000, max(710, work_height - 30), work_height)
    x = work.left + (work_width - width) // 2
    y = work.top + (work_height - height) // 2
    webview.create_window(APP_NAME, page.as_uri(), js_api=bridge,
                          width=width, height=height, x=x, y=y,
                          min_size=(min(1080, width), min(710, height)),
                          background_color="#0b1526")
    threading.Thread(target=apply_windows_icon, args=(icon,), daemon=True,
                     name="ApplyWindowIcon").start()
    try:
        webview.start(
            gui="edgechromium",
            private_mode=True,
            icon=str(icon) if icon.is_file() else None,
        )
    finally:
        if bridge.thread.is_alive():
            try:
                bridge.call("close")
            except Exception:
                pass
