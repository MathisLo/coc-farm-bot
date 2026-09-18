from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
import json
import logging
import queue
import re
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, ttk, messagebox

from PIL import Image, ImageTk


APP_DIR = Path.home() / "CoCFarmBot"
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "bot.log"
USER32 = ctypes.WinDLL("user32", use_last_error=True)
GDI32 = ctypes.WinDLL("gdi32", use_last_error=True)

USER32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
USER32.FindWindowW.restype = wintypes.HWND
USER32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
USER32.GetClientRect.restype = wintypes.BOOL
USER32.GetDC.argtypes = (wintypes.HWND,)
USER32.GetDC.restype = wintypes.HDC
USER32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
USER32.ReleaseDC.restype = ctypes.c_int
USER32.PrintWindow.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT)
USER32.PrintWindow.restype = wintypes.BOOL
USER32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
USER32.PostMessageW.restype = wintypes.BOOL
USER32.IsWindow.argtypes = (wintypes.HWND,)
USER32.IsWindow.restype = wintypes.BOOL
GDI32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
GDI32.CreateCompatibleDC.restype = wintypes.HDC
GDI32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
GDI32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
GDI32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
GDI32.SelectObject.restype = wintypes.HGDIOBJ
GDI32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
GDI32.DeleteObject.restype = wintypes.BOOL
GDI32.DeleteDC.argtypes = (wintypes.HDC,)
GDI32.DeleteDC.restype = wintypes.BOOL
GDI32.GetDIBits.argtypes = (wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT)
GDI32.GetDIBits.restype = ctypes.c_int

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001
PW_CLIENTONLY = 0x00000001


@dataclass
class Rect:
    x: int = 0
    y: int = 0
    width: int = 320
    height: int = 80


@dataclass
class Settings:
    window_title: str = ""
    gold_roi: Rect = field(default_factory=lambda: Rect(20, 20, 260, 75))
    elixir_roi: Rect = field(default_factory=lambda: Rect(20, 95, 260, 75))
    min_gold: int = 500000
    min_elixir: int = 500000
    use_and_rule: bool = True
    dragon_points: list[list[int]] = field(default_factory=lambda: [[40, 500], [90, 500], [140, 500], [190, 500], [240, 500]])
    delay_between_dragons_ms: int = 180
    poll_interval_seconds: int = 3
    dry_run: bool = True


def _rect_to_dict(value: Rect) -> dict:
    return asdict(value)


def load_settings() -> Settings:
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        raw["gold_roi"] = Rect(**raw.get("gold_roi", {}))
        raw["elixir_roi"] = Rect(**raw.get("elixir_roi", {}))
        return Settings(**raw)
    except (OSError, ValueError, TypeError):
        return Settings()


def save_settings(settings: Settings) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    payload = asdict(settings)
    CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class WindowDriver:
    """Capture et clics ciblés par handle Windows, sans souris globale."""

    @staticmethod
    def list_windows() -> list[str]:
        titles: list[str] = []
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd: int, _: int) -> bool:
            if USER32.IsWindowVisible(hwnd):
                length = USER32.GetWindowTextLengthW(hwnd)
                if length:
                    title = ctypes.create_unicode_buffer(length + 1)
                    USER32.GetWindowTextW(hwnd, title, length + 1)
                    if title.value.strip():
                        titles.append(title.value)
            return True

        USER32.EnumWindows(callback_type(callback), 0)
        return sorted(set(titles), key=str.casefold)

    @staticmethod
    def find(title: str) -> int:
        if not title:
            return 0
        return USER32.FindWindowW(None, title)

    @staticmethod
    def client_size(hwnd: int) -> tuple[int, int]:
        rect = wintypes.RECT()
        if not USER32.GetClientRect(hwnd, ctypes.byref(rect)):
            raise OSError("Impossible de lire la taille de la fenêtre.")
        return rect.right - rect.left, rect.bottom - rect.top

    @staticmethod
    def capture(hwnd: int) -> Image.Image:
        width, height = WindowDriver.client_size(hwnd)
        if width < 10 or height < 10:
            raise OSError("La fenêtre du jeu est réduite ou indisponible.")
        hdc = USER32.GetDC(hwnd)
        memdc = GDI32.CreateCompatibleDC(hdc)
        bitmap = GDI32.CreateCompatibleBitmap(hdc, width, height)
        old = GDI32.SelectObject(memdc, bitmap)
        try:
            if not USER32.PrintWindow(hwnd, memdc, PW_CLIENTONLY):
                raise OSError("La fenêtre ne fournit pas d'image en arrière-plan.")
            bmi = ctypes.create_string_buffer(40)
            ctypes.memmove(bmi, ctypes.byref(ctypes.c_uint32(40)), 4)
            ctypes.memmove(ctypes.addressof(bmi) + 4, ctypes.byref(ctypes.c_int32(width)), 4)
            ctypes.memmove(ctypes.addressof(bmi) + 8, ctypes.byref(ctypes.c_int32(-height)), 4)
            ctypes.memmove(ctypes.addressof(bmi) + 12, ctypes.byref(ctypes.c_uint16(1)), 2)
            ctypes.memmove(ctypes.addressof(bmi) + 14, ctypes.byref(ctypes.c_uint16(32)), 2)
            buffer = ctypes.create_string_buffer(width * height * 4)
            copied = GDI32.GetDIBits(memdc, bitmap, 0, height, buffer, bmi, 0)
            if copied != height:
                raise OSError("Capture Windows incomplète.")
            return Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1).convert("RGB")
        finally:
            GDI32.SelectObject(memdc, old)
            GDI32.DeleteObject(bitmap)
            GDI32.DeleteDC(memdc)
            USER32.ReleaseDC(hwnd, hdc)

    @staticmethod
    def click(hwnd: int, x: int, y: int) -> None:
        if not USER32.IsWindow(hwnd):
            raise OSError("La fenêtre ciblée a été fermée.")
        lparam = (y << 16) | (x & 0xFFFF)
        USER32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
        USER32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)


async def _read_windows_ocr(image_path: str) -> str:
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage import FileAccessMode, StorageFile

    file = await StorageFile.get_file_from_path_async(image_path)
    stream = await file.open_async(FileAccessMode.READ)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError("Aucune langue OCR Windows n'est installée.")
    result = await engine.recognize_async(bitmap)
    return result.text


def read_number(crop: Image.Image) -> int | None:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        crop.resize((crop.width * 2, crop.height * 2)).save(path)
        text = asyncio.run(_read_windows_ocr(str(path)))
        digits = re.sub(r"[^0-9]", "", text)
        return int(digits) if digits else None
    finally:
        path.unlink(missing_ok=True)


def crop(image: Image.Image, roi: Rect) -> Image.Image:
    left = max(0, roi.x)
    top = max(0, roi.y)
    right = min(image.width, left + max(1, roi.width))
    bottom = min(image.height, top + max(1, roi.height))
    return image.crop((left, top, right, bottom))


class BotApp:
    def __init__(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format="%(asctime)s %(message)s")
        self.settings = load_settings()
        self.root = Tk()
        self.root.title("CoC Farm Bot — V1")
        self.root.geometry("880x720")
        self.events: queue.Queue[str] = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.preview: ImageTk.PhotoImage | None = None
        self.window_title = StringVar(value=self.settings.window_title)
        self.gold_roi = StringVar(value=self._roi_text(self.settings.gold_roi))
        self.elixir_roi = StringVar(value=self._roi_text(self.settings.elixir_roi))
        self.min_gold = StringVar(value=str(self.settings.min_gold))
        self.min_elixir = StringVar(value=str(self.settings.min_elixir))
        self.points = StringVar(value="; ".join(f"{x},{y}" for x, y in self.settings.dragon_points))
        self.dry_run = BooleanVar(value=self.settings.dry_run)
        self.and_rule = BooleanVar(value=self.settings.use_and_rule)
        self._build()
        self._pump_events()

    @staticmethod
    def _roi_text(roi: Rect) -> str:
        return f"{roi.x},{roi.y},{roi.width},{roi.height}"

    def _build(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="Fenêtre Google Play Jeux").grid(row=0, column=0, sticky="w")
        self.windows = ttk.Combobox(main, textvariable=self.window_title, width=65)
        self.windows.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(main, text="Actualiser", command=self.refresh_windows).grid(row=0, column=2)
        ttk.Button(main, text="Capturer et lire", command=self.capture_once).grid(row=1, column=1, sticky="w", pady=8)
        ttk.Label(main, text="Or  x,y,largeur,hauteur").grid(row=2, column=0, sticky="w")
        ttk.Entry(main, textvariable=self.gold_roi).grid(row=2, column=1, sticky="ew", padx=6)
        ttk.Label(main, text="Élixir  x,y,largeur,hauteur").grid(row=3, column=0, sticky="w")
        ttk.Entry(main, textvariable=self.elixir_roi).grid(row=3, column=1, sticky="ew", padx=6)
        ttk.Label(main, text="Seuil or / élixir").grid(row=4, column=0, sticky="w")
        threshold = ttk.Frame(main)
        threshold.grid(row=4, column=1, sticky="w", padx=6)
        ttk.Entry(threshold, textvariable=self.min_gold, width=14).pack(side="left")
        ttk.Entry(threshold, textvariable=self.min_elixir, width=14).pack(side="left", padx=6)
        ttk.Checkbutton(main, text="Les deux seuils sont obligatoires", variable=self.and_rule).grid(row=5, column=1, sticky="w")
        ttk.Label(main, text="Dragons  x,y ; x,y").grid(row=6, column=0, sticky="w")
        ttk.Entry(main, textvariable=self.points).grid(row=6, column=1, sticky="ew", padx=6)
        ttk.Checkbutton(main, text="Simulation — aucun clic envoyé", variable=self.dry_run).grid(row=7, column=1, sticky="w", pady=8)
        actions = ttk.Frame(main)
        actions.grid(row=8, column=1, sticky="w")
        ttk.Button(actions, text="Enregistrer", command=self.persist).pack(side="left")
        ttk.Button(actions, text="Démarrer", command=self.start).pack(side="left", padx=6)
        ttk.Button(actions, text="Arrêter", command=self.stop).pack(side="left")
        self.status = StringVar(value="Prêt. La simulation est activée.")
        ttk.Label(main, textvariable=self.status).grid(row=9, column=0, columnspan=3, sticky="w", pady=8)
        self.log = __import__("tkinter").Text(main, height=10, state="disabled")
        self.log.grid(row=10, column=0, columnspan=3, sticky="nsew")
        self.preview_label = ttk.Label(main)
        self.preview_label.grid(row=11, column=0, columnspan=3, pady=8)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(10, weight=1)
        self.refresh_windows()

    def refresh_windows(self) -> None:
        values = WindowDriver.list_windows()
        self.windows["values"] = values
        candidates = [v for v in values if "google play" in v.casefold() or "clash" in v.casefold()]
        if not self.window_title.get() and candidates:
            self.window_title.set(candidates[0])
        self.write(f"{len(values)} fenêtres détectées.")

    def parse_settings(self) -> Settings:
        def parse_roi(value: str) -> Rect:
            x, y, w, h = (int(part.strip()) for part in value.split(","))
            return Rect(x, y, w, h)

        points = []
        for pair in self.points.get().split(";"):
            x, y = (int(part.strip()) for part in pair.split(","))
            points.append([x, y])
        return Settings(self.window_title.get(), parse_roi(self.gold_roi.get()), parse_roi(self.elixir_roi.get()),
                        int(self.min_gold.get()), int(self.min_elixir.get()), self.and_rule.get(), points,
                        self.settings.delay_between_dragons_ms, self.settings.poll_interval_seconds, self.dry_run.get())

    def persist(self) -> bool:
        try:
            self.settings = self.parse_settings()
            save_settings(self.settings)
            self.write("Configuration enregistrée.")
            return True
        except ValueError as exc:
            messagebox.showerror("Valeur invalide", "Vérifie les coordonnées et les seuils.\n" + str(exc))
            return False

    def capture_once(self) -> None:
        if not self.persist():
            return
        hwnd = WindowDriver.find(self.settings.window_title)
        if not hwnd:
            messagebox.showerror("Fenêtre introuvable", "Choisis une fenêtre Google Play Jeux ouverte.")
            return
        try:
            image = WindowDriver.capture(hwnd)
            gold = read_number(crop(image, self.settings.gold_roi))
            elixir = read_number(crop(image, self.settings.elixir_roi))
            preview = image.copy(); preview.thumbnail((640, 360))
            self.preview = ImageTk.PhotoImage(preview)
            self.preview_label.configure(image=self.preview)
            self.write(f"Lecture OCR — or: {gold if gold is not None else '?'} | élixir: {elixir if elixir is not None else '?'}")
        except Exception as exc:
            self.write(f"Capture/lecture impossible : {exc}")

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not self.persist():
            return
        self.stop_event.clear()
        self.worker = threading.Thread(target=self.run_bot, daemon=True)
        self.worker.start()
        self.status.set("Bot démarré.")

    def stop(self) -> None:
        self.stop_event.set()
        self.status.set("Arrêt demandé.")

    def run_bot(self) -> None:
        self.events.put("Boucle autonome active.")
        while not self.stop_event.is_set():
            try:
                hwnd = WindowDriver.find(self.settings.window_title)
                if not hwnd:
                    raise OSError("Fenêtre Google Play Jeux introuvable.")
                image = WindowDriver.capture(hwnd)
                gold = read_number(crop(image, self.settings.gold_roi))
                elixir = read_number(crop(image, self.settings.elixir_roi))
                if gold is None or elixir is None:
                    self.events.put("OCR illisible : nouvelle vérification dans quelques secondes.")
                else:
                    accepted = (gold >= self.settings.min_gold and elixir >= self.settings.min_elixir) if self.settings.use_and_rule else (gold >= self.settings.min_gold or elixir >= self.settings.min_elixir)
                    self.events.put(f"Butin lu : or {gold:,}, élixir {elixir:,}. Décision : {'déployer' if accepted else 'attendre'}.")
                    if accepted:
                        for x, y in self.settings.dragon_points:
                            if self.stop_event.is_set():
                                break
                            if self.settings.dry_run:
                                self.events.put(f"Simulation : dragon à {x},{y}")
                            else:
                                WindowDriver.click(hwnd, x, y)
                                self.events.put(f"Dragon envoyé à {x},{y}")
                            time.sleep(self.settings.delay_between_dragons_ms / 1000)
                        self.events.put("Déploiement terminé ; arrêt de la V1 après une attaque.")
                        self.stop_event.set()
            except Exception as exc:
                self.events.put(f"Boucle arrêtée : {exc}")
                self.stop_event.set()
            self.stop_event.wait(self.settings.poll_interval_seconds)
        self.events.put("Bot arrêté.")

    def _pump_events(self) -> None:
        try:
            while True:
                self.write(self.events.get_nowait())
        except queue.Empty:
            pass
        self.root.after(250, self._pump_events)

    def write(self, message: str) -> None:
        logging.info(message)
        self.status.set(message)
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        from PIL import ImageDraw, ImageFont

        sample = Image.new("RGB", (500, 120), "white")
        ImageDraw.Draw(sample).text(
            (10, 10), "123456", fill="black", font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 80)
        )
        value = read_number(sample)
        if value != 123456:
            raise SystemExit(f"OCR self-test failed: {value!r}")
        print("OCR self-test passed")
    else:
        BotApp().run()
