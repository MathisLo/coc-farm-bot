"""CoC Farm Bot V1: capture Windows, calibration locale et entrée sans souris."""
from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
import json
import logging
import math
import queue
import re
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, ttk, messagebox

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

APP_DIR = Path.home() / "CoCFarmBot"
CONFIG_PATH = APP_DIR / "config-v2.json"
LOG_PATH = APP_DIR / "bot.log"
CAPTURE_PATH = APP_DIR / "last_capture.png"
ACCOUNT_SNAPSHOT_PATH = APP_DIR / "account_snapshot.json"
USER32 = ctypes.WinDLL("user32", use_last_error=True)
GDI32 = ctypes.WinDLL("gdi32", use_last_error=True)
PW_RENDERFULLCONTENT, WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON = 2, 0x0201, 0x0202, 1

USER32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT)); USER32.GetWindowRect.restype = wintypes.BOOL
USER32.GetWindowDC.argtypes = (wintypes.HWND,); USER32.GetWindowDC.restype = wintypes.HDC
USER32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC); USER32.ReleaseDC.restype = ctypes.c_int
USER32.PrintWindow.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT); USER32.PrintWindow.restype = wintypes.BOOL
USER32.IsWindow.argtypes = (wintypes.HWND,); USER32.IsWindow.restype = wintypes.BOOL
USER32.IsWindowVisible.argtypes = (wintypes.HWND,); USER32.IsWindowVisible.restype = wintypes.BOOL
USER32.GetWindowTextLengthW.argtypes = (wintypes.HWND,); USER32.GetWindowTextLengthW.restype = ctypes.c_int
USER32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int); USER32.GetWindowTextW.restype = ctypes.c_int
USER32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM); USER32.PostMessageW.restype = wintypes.BOOL
GDI32.CreateCompatibleDC.argtypes = (wintypes.HDC,); GDI32.CreateCompatibleDC.restype = wintypes.HDC
GDI32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int); GDI32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
GDI32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ); GDI32.SelectObject.restype = wintypes.HGDIOBJ
GDI32.DeleteObject.argtypes = (wintypes.HGDIOBJ,); GDI32.DeleteObject.restype = wintypes.BOOL
GDI32.DeleteDC.argtypes = (wintypes.HDC,); GDI32.DeleteDC.restype = wintypes.BOOL
GDI32.GetDIBits.argtypes = (wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT); GDI32.GetDIBits.restype = ctypes.c_int


class BitmapInfoHeader(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BitmapInfo(ctypes.Structure):
    _fields_ = [("bmiHeader", BitmapInfoHeader), ("bmiColors", wintypes.DWORD * 3)]


@dataclass
class Roi:
    x1: float = 0; y1: float = 0; x2: float = 0; y2: float = 0
    def valid(self): return 0 <= self.x1 < self.x2 <= 100 and 0 <= self.y1 < self.y2 <= 100
    def text(self): return f"{self.x1:.1f}, {self.y1:.1f} → {self.x2:.1f}, {self.y2:.1f} %"


@dataclass
class Settings:
    version: int = 3
    window_title: str = ""
    gold_roi: Roi = field(default_factory=Roi)
    elixir_roi: Roi = field(default_factory=Roi)
    min_gold: int = 500000
    min_elixir: int = 500000
    loot_margin_percent: float = 5.0
    use_and_rule: bool = True
    dragon_select_point: list[float] | None = None
    dragon_points: list[list[float]] = field(default_factory=list)
    delay_between_dragons_ms: int = 180
    poll_interval_seconds: int = 3
    dry_run: bool = False


@dataclass(frozen=True)
class AccountSnapshot:
    account_name: str | None
    level: int | None
    gold: int | None
    elixir: int | None
    dark_elixir: int | None
    gems: int | None
    laboratory_builders: str | None
    builders: str | None
    captured_at: float
    raw: dict[str, str]


@dataclass(frozen=True)
class EnemyLoot:
    gold: int | None
    elixir: int | None
    dark_elixir: int | None
    raw: dict[str, str]


# Zones relatives de l'interface du village Google Play Jeux PC. Elles sont
# calculées depuis la capture de la fenêtre, donc restent valides au redimensionnement.
PROFILE_ROIS = {
    "account_name": Roi(5.47, 0.93, 19.01, 7.41), "level": Roi(1.0, 0.7, 6.0, 9.5),
    "laboratory_builders": Roi(33.333333333, 0, 45.3125, 9.259259259), "builders": Roi(44.0, 0, 58.0, 10.0),
    "gold": Roi(82.03125, 1.851851852, 95.572916667, 6.944444444), "elixir": Roi(82.03125, 10.185185185, 95.833333333, 15.277777778),
    "dark_elixir": Roi(85.9375, 17.592592593, 96.09375, 23.148148148), "gems": Roi(86.71875, 25, 95.833333333, 30.555555556),
}

# Parcours vérifié sur Google Play Jeux PC, exprimé en pourcentage de la
# fenêtre capturée. Aucun déplacement du curseur Windows n'est nécessaire.
ATTACK_HOME_BUTTON = (5.2, 90.3)
FIND_MATCH_BUTTON = (14.2, 70.4)
START_SEARCH_BUTTON = (84.0, 85.2)
NEXT_BASE_BUTTON = (91.9, 75.8)
ELECTRODRAGON_SLOT = (23.2, 92.5)
# Positions extérieures, réparties de chaque côté du terrain. Elles évitent
# le carré central de la base : Clash n'autorise la pose des troupes que sur
# le pourtour jouable. Les points personnalisés ne sont employés que s'ils
# respectent eux aussi cette couronne extérieure.
ELECTRODRAGON_PERIMETER_POINTS = [
    (15.0, 31.0), (15.0, 31.0), (15.0, 40.0), (15.0, 49.0),
    (85.0, 31.0), (85.0, 31.0), (85.0, 40.0), (85.0, 49.0),
]
ENEMY_LOOT_ROIS = {
    "gold": Roi(3.8, 10.2, 15.0, 15.5), "elixir": Roi(3.90625, 15.277777778, 13.020833333, 19.907407407), "dark_elixir": Roi(3.8, 19.0, 15.0, 25.0),
}
ENEMY_LOOT_LABEL_ROI = Roi(3.5, 7.5, 17.0, 11.5)


def load_settings() -> Settings:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        # The previous version saved Simulation=true by default. That made a
        # launched farm stop before deployment; migrate it to the real mode
        # requested for V1.7 while retaining the explicit checkbox.
        if data.get("version", 0) < 3:
            data["version"] = 3; data["dry_run"] = False; data.setdefault("loot_margin_percent", 5.0)
        data["gold_roi"] = Roi(**data.get("gold_roi", {})); data["elixir_roi"] = Roi(**data.get("elixir_roi", {}))
        return Settings(**data)
    except (OSError, TypeError, ValueError): return Settings()


def save_settings(settings: Settings):
    APP_DIR.mkdir(parents=True, exist_ok=True); CONFIG_PATH.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


def is_perimeter_point(point: list[float] | tuple[float, float]) -> bool:
    """Return whether a relative point is outside the central base area."""
    x, y = point
    return 8.0 <= x <= 92.0 and 14.0 <= y <= 76.0 and (x <= 27.0 or x >= 73.0 or y <= 25.0 or y >= 75.0)


def electrodragon_drop_points(settings: Settings) -> list[tuple[float, float]]:
    """Use an eight-point perimeter configuration, else the verified default ring."""
    configured = [tuple(point) for point in settings.dragon_points]
    if len(configured) >= 8 and all(is_perimeter_point(point) for point in configured[:8]):
        return configured[:8]
    return ELECTRODRAGON_PERIMETER_POINTS


def effective_minimum(minimum: int, margin_percent: float) -> int:
    """Lower a configured loot threshold by a bounded tolerance percentage."""
    margin = max(0.0, min(25.0, margin_percent))
    return math.ceil(minimum * (1.0 - margin / 100.0))


def loot_is_accepted(gold: int, elixir: int, settings: Settings) -> tuple[bool, int, int]:
    gold_minimum = effective_minimum(settings.min_gold, settings.loot_margin_percent)
    elixir_minimum = effective_minimum(settings.min_elixir, settings.loot_margin_percent)
    accepted = (gold >= gold_minimum and elixir >= elixir_minimum) if settings.use_and_rule else (gold >= gold_minimum or elixir >= elixir_minimum)
    return accepted, gold_minimum, elixir_minimum


@dataclass(frozen=True)
class GameWindow:
    hwnd: int; title: str; width: int; height: int


class WindowDriver:
    """Approche de l'inspiration NullMacro : fenêtre entière + PostMessage."""
    @staticmethod
    def list_windows() -> list[GameWindow]:
        result = []; callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _):
            if not USER32.IsWindowVisible(hwnd): return True
            length = USER32.GetWindowTextLengthW(hwnd)
            if not length: return True
            title = ctypes.create_unicode_buffer(length + 1); USER32.GetWindowTextW(hwnd, title, length + 1)
            rect = wintypes.RECT()
            if USER32.GetWindowRect(hwnd, ctypes.byref(rect)):
                width, height = rect.right - rect.left, rect.bottom - rect.top
                if width > 200 and height > 150: result.append(GameWindow(int(hwnd), title.value, width, height))
            return True
        USER32.EnumWindows(callback_type(callback), 0)
        return sorted(result, key=lambda w: (not w.title.casefold().startswith("clash of clans"), -(w.width * w.height)))

    @staticmethod
    def resolve(title: str) -> GameWindow | None:
        windows = WindowDriver.list_windows()
        return next((w for w in windows if w.title == title), next((w for w in windows if w.title.casefold().startswith("clash of clans")), None))

    @staticmethod
    def capture(window: GameWindow) -> Image.Image:
        hwnd = wintypes.HWND(window.hwnd)
        if not USER32.IsWindow(hwnd): raise RuntimeError("La fenêtre Clash a été fermée.")
        rect = wintypes.RECT(); USER32.GetWindowRect(hwnd, ctypes.byref(rect)); width, height = rect.right - rect.left, rect.bottom - rect.top
        source_dc = USER32.GetWindowDC(hwnd); memory_dc = GDI32.CreateCompatibleDC(source_dc); bitmap = GDI32.CreateCompatibleBitmap(source_dc, width, height); previous = GDI32.SelectObject(memory_dc, bitmap)
        try:
            if not USER32.PrintWindow(hwnd, memory_dc, PW_RENDERFULLCONTENT): raise RuntimeError("Google Play Jeux a refusé la capture.")
            info = BitmapInfo(); info.bmiHeader.biSize = ctypes.sizeof(BitmapInfoHeader); info.bmiHeader.biWidth = width; info.bmiHeader.biHeight = -height; info.bmiHeader.biPlanes = 1; info.bmiHeader.biBitCount = 32
            data = ctypes.create_string_buffer(width * height * 4)
            if GDI32.GetDIBits(memory_dc, bitmap, 0, height, data, ctypes.byref(info), 0) != height: raise RuntimeError("Capture Windows incomplète.")
            image = Image.frombuffer("RGB", (width, height), data, "raw", "BGRX", 0, 1).copy()
            if image.convert("L").getextrema() == (0, 0): raise RuntimeError("Capture noire : Google Play Jeux n'expose pas son rendu en arrière-plan.")
            return image
        finally:
            GDI32.SelectObject(memory_dc, previous); GDI32.DeleteObject(bitmap); GDI32.DeleteDC(memory_dc); USER32.ReleaseDC(hwnd, source_dc)

    @staticmethod
    def click_percent(window: GameWindow, x: float, y: float) -> bool:
        px, py = round(window.width * x / 100), round(window.height * y / 100); lp = (py << 16) | (px & 0xFFFF)
        return bool(USER32.PostMessageW(window.hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp) and USER32.PostMessageW(window.hwnd, WM_LBUTTONUP, 0, lp))


def crop_percent(image: Image.Image, roi: Roi) -> Image.Image:
    if not roi.valid(): raise ValueError("Zone non calibrée.")
    return image.crop((round(image.width * roi.x1 / 100), round(image.height * roi.y1 / 100), round(image.width * roi.x2 / 100), round(image.height * roi.y2 / 100)))


async def _ocr_file(path: str) -> str:
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage import FileAccessMode, StorageFile
    stream = await (await StorageFile.get_file_from_path_async(path)).open_async(FileAccessMode.READ)
    bitmap = await (await BitmapDecoder.create_async(stream)).get_software_bitmap_async()
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None: raise RuntimeError("OCR Windows indisponible.")
    return (await engine.recognize_async(bitmap)).text


def read_number(image: Image.Image) -> int | None:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as file: path = Path(file.name)
    try:
        image.resize((image.width * 3, image.height * 3)).save(path)
        digits = re.sub(r"[^0-9]", "", asyncio.run(_ocr_file(str(path))))
        return int(digits) if digits else None
    finally: path.unlink(missing_ok=True)


def read_text(image: Image.Image, scale: int = 5) -> str:
    """OCR a local UI crop while keeping the raw reading for diagnostics."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as file: path = Path(file.name)
    try:
        image.resize((image.width * scale, image.height * scale)).save(path)
        return asyncio.run(_ocr_file(str(path))).strip()
    finally: path.unlink(missing_ok=True)


def parse_clash_number(text: str) -> int | None:
    # Windows OCR occasionally reads the stylised level digits as letters.
    digits = re.sub(r"[^0-9]", "", text.translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "i": "1", "Z": "7", "z": "7", "S": "5", "s": "5", "B": "8", "E": "3"})))
    return int(digits) if digits else None


def read_resource_number(image: Image.Image) -> tuple[int | None, str]:
    """Try normal and high-contrast OCR; keep the most complete valid amount."""
    normal = read_text(image)
    binary = read_text(ImageOps.grayscale(image).point(lambda pixel: 255 if pixel > 150 else 0))
    binary_value = parse_clash_number(binary)
    if binary_value is not None and binary_value <= 2_500_000: return binary_value, binary
    normal_value = parse_clash_number(normal)
    return (normal_value, normal) if normal_value is not None and normal_value <= 2_500_000 else (None, normal)


def parse_worker_ratio(text: str) -> str | None:
    normal = text.translate(str.maketrans({"S": "5", "s": "5", "O": "0", "o": "0", "I": "1", "l": "1", "i": "1", "Z": "7", "z": "7", "T": "/", "t": "/"}))
    parts = re.findall(r"\d+", normal)
    if "/" in normal and len(parts) >= 2:
        return f"{parts[0][0]}/{parts[-1][-1]}"
    digits = "".join(parts)
    # The slash is sometimes recognised as a second copy of the left digit:
    # e.g. the visible 1/2 becomes the OCR string 112.
    if len(digits) == 3 and (digits[0] == digits[1] or digits[0] == digits[2]): return f"{digits[0]}/{digits[2]}"
    return None


def read_account_snapshot(image: Image.Image) -> AccountSnapshot:
    raw = {key: read_text(crop_percent(image, roi)) for key, roi in PROFILE_ROIS.items()}
    # On the white worker counter, Windows OCR needs the surrounding top bar.
    # Its usual `Sts` output maps to 5/5 through parse_worker_ratio().
    if not raw["builders"]:
        whole_top = read_text(image, scale=1)
        match = re.search(r"\b[5Ss][Tt/][5Ss]\b", whole_top)
        raw["builders"] = match.group(0) if match else ""
    return AccountSnapshot(
        account_name=raw["account_name"] or None, level=parse_clash_number(raw["level"]),
        gold=parse_clash_number(raw["gold"]), elixir=parse_clash_number(raw["elixir"]),
        dark_elixir=parse_clash_number(raw["dark_elixir"]), gems=parse_clash_number(raw["gems"]),
        laboratory_builders=parse_worker_ratio(raw["laboratory_builders"]), builders=parse_worker_ratio(raw["builders"]),
        captured_at=time.time(), raw=raw,
    )


def read_enemy_loot(image: Image.Image) -> EnemyLoot:
    readings = {key: read_resource_number(crop_percent(image, roi)) for key, roi in ENEMY_LOOT_ROIS.items()}
    return EnemyLoot(gold=readings["gold"][0], elixir=readings["elixir"][0], dark_elixir=readings["dark_elixir"][0], raw={key: text for key, (_, text) in readings.items()})


def enemy_loot_screen_ready(image: Image.Image) -> bool:
    label = read_text(crop_percent(image, ENEMY_LOOT_LABEL_ROI)).casefold()
    return "butin" in label or "loot" in label


class BotApp:
    def __init__(self):
        APP_DIR.mkdir(parents=True, exist_ok=True); logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format="%(asctime)s %(message)s", encoding="utf-8")
        self.settings = load_settings(); self.root = Tk(); self.root.title("CoC Farm Bot — V1 calibrable"); self.root.geometry("1040x810")
        self.events = queue.Queue(); self.stop_event = threading.Event(); self.worker = None; self.image = None; self.photo = None; self.origin = (0, 0); self.preview_size = (1, 1); self.drag_start = None
        self.mode = StringVar(value="Or"); self.window_title = StringVar(value=self.settings.window_title); self.min_gold = StringVar(value=str(self.settings.min_gold)); self.min_elixir = StringVar(value=str(self.settings.min_elixir)); self.loot_margin = StringVar(value=str(self.settings.loot_margin_percent)); self.and_rule = BooleanVar(value=self.settings.use_and_rule); self.dry_run = BooleanVar(value=self.settings.dry_run)
        self.gold_text = StringVar(value=self.settings.gold_roi.text() if self.settings.gold_roi.valid() else "À sélectionner"); self.elixir_text = StringVar(value=self.settings.elixir_roi.text() if self.settings.elixir_roi.valid() else "À sélectionner"); self.select_text = StringVar(value=self._select_text()); self.points_text = StringVar(value=self._points_text()); self.status = StringVar(value="Capture la fenêtre Clash puis calibre les zones.")
        self._build(); self._pump()

    def _build(self):
        root = ttk.Frame(self.root, padding=12); root.pack(fill="both", expand=True); root.columnconfigure(1, weight=1); root.rowconfigure(8, weight=1)
        ttk.Label(root, text="Fenêtre Clash").grid(row=0,column=0,sticky="w"); self.windows = ttk.Combobox(root,textvariable=self.window_title,width=70); self.windows.grid(row=0,column=1,sticky="ew",padx=6); ttk.Button(root,text="Détecter",command=self.refresh).grid(row=0,column=2); ttk.Button(root,text="Capturer",command=self.capture).grid(row=1,column=1,sticky="w",pady=8)
        box = ttk.LabelFrame(root,text="Calibration sur l'aperçu",padding=8); box.grid(row=2,column=0,columnspan=3,sticky="ew")
        for text,value in (("Tracer zone Or","Or"),("Tracer zone Élixir","Élixir"),("Choisir le bouton dragons","Sélection"),("Ajouter un point dragon","Dragon")): ttk.Radiobutton(box,text=text,variable=self.mode,value=value).pack(side="left",padx=6)
        ttk.Button(box,text="Effacer dragons",command=self.clear_dragons).pack(side="right")
        ttk.Label(root,text="Zone Or").grid(row=3,column=0,sticky="w"); ttk.Label(root,textvariable=self.gold_text).grid(row=3,column=1,sticky="w")
        ttk.Label(root,text="Zone Élixir").grid(row=4,column=0,sticky="w"); ttk.Label(root,textvariable=self.elixir_text).grid(row=4,column=1,sticky="w")
        ttk.Label(root,text="Bouton dragons").grid(row=5,column=0,sticky="w"); ttk.Label(root,textvariable=self.select_text).grid(row=5,column=1,sticky="w")
        ttk.Label(root,text="Points dragons").grid(row=6,column=0,sticky="w"); ttk.Label(root,textvariable=self.points_text).grid(row=6,column=1,sticky="w")
        limits=ttk.Frame(root); limits.grid(row=7,column=0,columnspan=3,sticky="ew",pady=8)
        ttk.Label(limits,text="Seuil or").pack(side="left"); ttk.Entry(limits,textvariable=self.min_gold,width=10).pack(side="left",padx=4); ttk.Label(limits,text="Seuil élixir").pack(side="left",padx=(8,0)); ttk.Entry(limits,textvariable=self.min_elixir,width=10).pack(side="left",padx=4); ttk.Label(limits,text="Marge %").pack(side="left",padx=(8,0)); ttk.Entry(limits,textvariable=self.loot_margin,width=5).pack(side="left",padx=4); ttk.Checkbutton(limits,text="Or ET élixir",variable=self.and_rule).pack(side="left",padx=8); ttk.Checkbutton(limits,text="Mode simulation (sans pose)",variable=self.dry_run).pack(side="left",padx=8)
        self.canvas=__import__("tkinter").Canvas(root,background="#1d1d1d",highlightthickness=0); self.canvas.grid(row=8,column=0,columnspan=3,sticky="nsew"); self.canvas.bind("<ButtonPress-1>",self.press); self.canvas.bind("<B1-Motion>",self.drag); self.canvas.bind("<ButtonRelease-1>",self.release)
        actions=ttk.Frame(root); actions.grid(row=9,column=0,columnspan=3,pady=8)
        for text,command in (("Relever le profil",self.scan_profile),("Tester l'OCR",self.test_ocr),("Enregistrer",self.persist),("Tester calibration",self.start),("Lancer farm",self.start_farm),("Arrêter",self.stop)): ttk.Button(actions,text=text,command=command).pack(side="left",padx=3)
        ttk.Label(root,textvariable=self.status).grid(row=10,column=0,columnspan=3,sticky="w"); self.log=__import__("tkinter").Text(root,height=7,state="disabled"); self.log.grid(row=11,column=0,columnspan=3,sticky="nsew",pady=(6,0)); self.refresh()

    def refresh(self):
        windows=WindowDriver.list_windows(); self.windows["values"]=[w.title for w in windows]
        if not self.window_title.get() and windows: self.window_title.set(windows[0].title)
        self.write(f"{len(windows)} fenêtres détectées.")

    def capture(self):
        window=WindowDriver.resolve(self.window_title.get())
        if not window: self.write("Fenêtre Clash introuvable."); return
        self.window_title.set(window.title)
        try:
            self.image=WindowDriver.capture(window); self.image.save(CAPTURE_PATH); self.draw(); self.write(f"Capture {self.image.width}×{self.image.height} reçue. Trace les zones.")
        except Exception as exc: self.write(f"Capture impossible : {exc}")

    def draw(self):
        if self.image is None: return
        self.canvas.delete("all"); scale=min(960/self.image.width,500/self.image.height); width,height=int(self.image.width*scale),int(self.image.height*scale); preview=self.image.resize((width,height)); self.photo=ImageTk.PhotoImage(preview); ox,oy=(960-width)//2,(500-height)//2; self.origin,self.preview_size=(ox,oy),(width,height); self.canvas.config(width=960,height=500); self.canvas.create_image(ox,oy,image=self.photo,anchor="nw")
        self.draw_roi(self.settings.gold_roi,"#e6b800","Or"); self.draw_roi(self.settings.elixir_roi,"#bb50ff","Élixir")
        for i,(x,y) in enumerate(self.settings.dragon_points,1):
            px,py=self.to_canvas(x,y); self.canvas.create_oval(px-6,py-6,px+6,py+6,outline="#4cd3ff",width=2); self.canvas.create_text(px+10,py,text=str(i),fill="#4cd3ff",anchor="w")
        if self.settings.dragon_select_point:
            px,py=self.to_canvas(*self.settings.dragon_select_point); self.canvas.create_rectangle(px-7,py-7,px+7,py+7,outline="#ff8c42",width=2); self.canvas.create_text(px+10,py,text="D",fill="#ff8c42",anchor="w")

    def draw_roi(self,roi,color,label):
        if roi.valid():
            x1,y1=self.to_canvas(roi.x1,roi.y1); x2,y2=self.to_canvas(roi.x2,roi.y2); self.canvas.create_rectangle(x1,y1,x2,y2,outline=color,width=3); self.canvas.create_text(x1+4,y1+4,text=label,fill=color,anchor="nw")

    def to_canvas(self,x,y):
        return round(self.origin[0]+self.preview_size[0]*x/100),round(self.origin[1]+self.preview_size[1]*y/100)
    def to_percent(self,x,y):
        ox,oy=self.origin; width,height=self.preview_size
        return None if not (ox<=x<=ox+width and oy<=y<=oy+height) else ((x-ox)/width*100,(y-oy)/height*100)
    def press(self,event):
        point=self.to_percent(event.x,event.y)
        if point is None or self.image is None:return
        if self.mode.get()=="Sélection": self.settings.dragon_select_point=[round(point[0],2),round(point[1],2)]; self.select_text.set(self._select_text()); self.draw()
        elif self.mode.get()=="Dragon": self.settings.dragon_points.append([round(point[0],2),round(point[1],2)]); self.points_text.set(self._points_text()); self.draw()
        else:self.drag_start=(event.x,event.y)
    def drag(self,event):
        if self.drag_start: self.draw(); self.canvas.create_rectangle(*self.drag_start,event.x,event.y,outline="#fff",dash=(4,3),width=2)
    def release(self,event):
        if not self.drag_start:return
        start,end=self.to_percent(*self.drag_start),self.to_percent(event.x,event.y); self.drag_start=None
        if start is None or end is None:self.draw();return
        roi=Roi(round(min(start[0],end[0]),2),round(min(start[1],end[1]),2),round(max(start[0],end[0]),2),round(max(start[1],end[1]),2))
        if not roi.valid():self.write("Zone trop petite.");self.draw();return
        if self.mode.get()=="Or":self.settings.gold_roi=roi;self.gold_text.set(roi.text())
        else:self.settings.elixir_roi=roi;self.elixir_text.set(roi.text())
        self.draw()
    def clear_dragons(self): self.settings.dragon_points=[];self.points_text.set(self._points_text());self.draw()
    def _select_text(self): return f"{self.settings.dragon_select_point[0]:.1f} %, {self.settings.dragon_select_point[1]:.1f} %" if self.settings.dragon_select_point else "À sélectionner"
    def _points_text(self): return f"{len(self.settings.dragon_points)} point(s)" if self.settings.dragon_points else "À placer"

    def scan_profile(self):
        window = WindowDriver.resolve(self.window_title.get())
        if not window: self.write("Fenêtre Clash introuvable."); return
        try:
            image = WindowDriver.capture(window); self.image = image; self.window_title.set(window.title); self.draw()
            snapshot = read_account_snapshot(image); APP_DIR.mkdir(parents=True, exist_ok=True)
            ACCOUNT_SNAPSHOT_PATH.write_text(json.dumps(asdict(snapshot), indent=2, ensure_ascii=False), encoding="utf-8")
            values = [
                f"Pseudo : {snapshot.account_name or '?'}", f"Niveau : {snapshot.level or '?'}",
                f"Or : {snapshot.gold:,}" if snapshot.gold is not None else "Or : ?",
                f"Élixir : {snapshot.elixir:,}" if snapshot.elixir is not None else "Élixir : ?",
                f"Élixir noir : {snapshot.dark_elixir:,}" if snapshot.dark_elixir is not None else "Élixir noir : ?",
                f"Gemmes : {snapshot.gems:,}" if snapshot.gems is not None else "Gemmes : ?",
                f"Ouvriers laboratoire : {snapshot.laboratory_builders or '?'}", f"Ouvriers : {snapshot.builders or '?'}",
            ]
            self.write(" | ".join(values)); self.write(f"Relevé enregistré : {ACCOUNT_SNAPSHOT_PATH}")
        except Exception as exc: self.write(f"Relevé du profil impossible : {exc}")

    def persist(self):
        try:
            self.settings.window_title=self.window_title.get();self.settings.min_gold=int(self.min_gold.get().replace(" ",""));self.settings.min_elixir=int(self.min_elixir.get().replace(" ",""));self.settings.loot_margin=float(self.loot_margin.get().replace(",","."));self.settings.use_and_rule=self.and_rule.get();self.settings.dry_run=self.dry_run.get()
            if not 0 <= self.settings.loot_margin_percent <= 25: raise ValueError
            save_settings(self.settings);self.write(f"Configuration enregistrée : attaque dès {effective_minimum(self.settings.min_gold, self.settings.loot_margin_percent):,} or / {effective_minimum(self.settings.min_elixir, self.settings.loot_margin_percent):,} élixir.");return True
        except ValueError: messagebox.showerror("Valeur invalide","Les seuils doivent être entiers et la marge comprise entre 0 et 25 %.");return False
    def valid_run(self):
        if not (self.settings.gold_roi.valid() and self.settings.elixir_roi.valid()):self.write("Calibre Or et Élixir.");return False
        if not self.settings.dragon_select_point:self.write("Sélectionne le bouton des électro-dragons.");return False
        if not self.settings.dragon_points:self.write("Place au moins un point dragon.");return False
        return True
    def test_ocr(self):
        if self.image is None:self.capture()
        if self.image is None or not (self.settings.gold_roi.valid() and self.settings.elixir_roi.valid()):self.write("Capture et calibration requises.");return
        try:self.write(f"OCR : or {read_number(crop_percent(self.image,self.settings.gold_roi)) or '?'} | élixir {read_number(crop_percent(self.image,self.settings.elixir_roi)) or '?'}")
        except Exception as exc:self.write(f"Test OCR impossible : {exc}")
    def start(self):
        if self.worker and self.worker.is_alive():return
        if not self.persist() or not self.valid_run():return
        self.stop_event.clear();self.worker=threading.Thread(target=self.run_loop,daemon=True);self.worker.start();self.write("Boucle V1 démarrée.")
    def start_farm(self):
        if self.worker and self.worker.is_alive(): return
        if not self.persist(): return
        if self.settings.dry_run: self.write("Simulation active : recherche et lecture uniquement, aucune pose ne sera envoyée.")
        else: self.write("Mode réel actif : les 8 électro-dragons seront posés sur les flancs d'une base retenue.")
        self.stop_event.clear(); self.worker=threading.Thread(target=self.farm_loop,daemon=True); self.worker.start(); self.write("Recherche automatique démarrée.")
    def stop(self):self.stop_event.set();self.write("Arrêt demandé.")
    def run_loop(self):
        while not self.stop_event.is_set():
            try:
                window=WindowDriver.resolve(self.settings.window_title)
                if not window:raise RuntimeError("Fenêtre Clash introuvable.")
                image=WindowDriver.capture(window);gold=read_number(crop_percent(image,self.settings.gold_roi));elixir=read_number(crop_percent(image,self.settings.elixir_roi))
                if gold is None or elixir is None:self.events.put("OCR non lisible : aucune action envoyée.")
                else:
                    accepted,gold_minimum,elixir_minimum=loot_is_accepted(gold,elixir,self.settings);self.events.put(f"Butin : or {gold:,}, élixir {elixir:,} | seuils avec marge : {gold_minimum:,}/{elixir_minimum:,} → {'attaque' if accepted else 'attente'}.")
                    if accepted:
                        sx,sy=self.settings.dragon_select_point
                        if self.settings.dry_run:self.events.put(f"Simulation : sélection dragons {sx:.1f} %, {sy:.1f} %")
                        elif not WindowDriver.click_percent(window,sx,sy):raise RuntimeError("Clic de sélection dragons refusé.")
                        else:self.events.put("Électro-dragons sélectionnés.")
                        time.sleep(self.settings.delay_between_dragons_ms/1000)
                        for x,y in self.settings.dragon_points:
                            if self.stop_event.is_set():break
                            if self.settings.dry_run:self.events.put(f"Simulation : dragon {x:.1f} %, {y:.1f} %")
                            elif not WindowDriver.click_percent(window,x,y):raise RuntimeError("Clic en arrière-plan refusé.")
                            else:self.events.put(f"Dragon envoyé à {x:.1f} %, {y:.1f} %")
                            time.sleep(self.settings.delay_between_dragons_ms/1000)
                        self.events.put("Déploiement V1 terminé.");self.stop_event.set()
            except Exception as exc:self.events.put(f"Boucle arrêtée : {exc}");self.stop_event.set()
            self.stop_event.wait(self.settings.poll_interval_seconds)
        self.events.put("Bot arrêté.")
    def farm_loop(self):
        """Open multiplayer, reject low loot, then select and deploy electro-dragons."""
        try:
            window=WindowDriver.resolve(self.settings.window_title)
            if not window: raise RuntimeError("Fenêtre Clash introuvable.")
            for point,delay,label in ((ATTACK_HOME_BUTTON,1.0,"Ouverture du menu Attaquer"),(FIND_MATCH_BUTTON,1.0,"Ouverture de la sélection d'armée"),(START_SEARCH_BUTTON,6.0,"Recherche d'une base adverse")):
                if not WindowDriver.click_percent(window,*point): raise RuntimeError(f"Clic refusé : {label}.")
                self.events.put(label); self.stop_event.wait(delay)
                if self.stop_event.is_set(): return
            while not self.stop_event.is_set():
                image=WindowDriver.capture(window); loot=read_enemy_loot(image)
                if not enemy_loot_screen_ready(image):
                    self.events.put("Attente de l'affichage complet de la base adverse."); self.stop_event.wait(.5); continue
                if loot.gold is None or loot.elixir is None:
                    self.events.put("Butin adverse illisible : aucune action envoyée."); self.stop_event.wait(1); continue
                accepted,gold_minimum,elixir_minimum=loot_is_accepted(loot.gold,loot.elixir,self.settings)
                self.events.put(f"Base adverse : or {loot.gold:,}, élixir {loot.elixir:,} | seuils avec marge : {gold_minimum:,}/{elixir_minimum:,} → {'attaque' if accepted else 'suivant'}.")
                if not accepted:
                    if not WindowDriver.click_percent(window,*NEXT_BASE_BUTTON): raise RuntimeError("Clic Suivant refusé.")
                    self.stop_event.wait(3); continue
                drop_points=electrodragon_drop_points(self.settings)
                if self.settings.dry_run:
                    self.events.put("Simulation : base retenue ; les 8 électro-dragons ne sont pas envoyés."); return
                if not WindowDriver.click_percent(window,*ELECTRODRAGON_SLOT): raise RuntimeError("Sélection électro-dragons refusée.")
                self.stop_event.wait(self.settings.delay_between_dragons_ms/1000)
                for x,y in drop_points:
                    if self.stop_event.is_set(): return
                    if not WindowDriver.click_percent(window,x,y): raise RuntimeError("Pose électro-dragon refusée.")
                    self.events.put(f"Électro-dragon posé : {x:.1f} %, {y:.1f} %")
                    self.stop_event.wait(self.settings.delay_between_dragons_ms/1000)
                self.events.put("Déploiement des 8 électro-dragons sur le pourtour terminé."); return
        except Exception as exc: self.events.put(f"Recherche arrêtée : {exc}")
        finally:
            self.stop_event.set(); self.events.put("Bot arrêté.")
    def _pump(self):
        try:
            while True:self.write(self.events.get_nowait())
        except queue.Empty:pass
        self.root.after(250,self._pump)
    def write(self,text):
        logging.info(text);self.status.set(text);self.log.configure(state="normal");self.log.insert("end",text+"\n");self.log.see("end");self.log.configure(state="disabled")
    def run(self):self.root.mainloop()


def self_test():
    assert Roi(1,2,3,4).valid() and not Roi(3,2,1,4).valid()
    assert parse_clash_number("loz") == 107 and parse_worker_ratio("112") == "1/2" and parse_worker_ratio("SIS") == "5/5"
    image=Image.new("RGB",(600,150),"white");ImageDraw.Draw(image).text((12,12),"123456",fill="black",font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf",90));assert read_number(image)==123456;print("Self-test passed")


def profile_test():
    window = WindowDriver.resolve("")
    if not window: raise RuntimeError("Fenêtre Clash introuvable pour le test de profil.")
    snapshot = read_account_snapshot(WindowDriver.capture(window))
    required = (snapshot.account_name, snapshot.level, snapshot.gold, snapshot.elixir, snapshot.dark_elixir, snapshot.gems, snapshot.laboratory_builders, snapshot.builders)
    if any(value is None for value in required): raise RuntimeError(f"Relevé incomplet : {asdict(snapshot)}")
    print(json.dumps(asdict(snapshot), ensure_ascii=False))

if __name__ == "__main__":
    profile_test() if "--profile-test" in sys.argv else (self_test() if "--self-test" in sys.argv else BotApp().run())
