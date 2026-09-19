"""CoC Farm Bot: capture Windows et commandes en arrière-plan."""
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
import unicodedata
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, ttk, messagebox

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

APP_DIR = Path.home() / "CoCFarmBot"
CONFIG_PATH = APP_DIR / "config-v2.json"
LOG_PATH = APP_DIR / "bot.log"
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


@dataclass
class Settings:
    version: int = 6
    window_title: str = ""
    min_gold: int = 500000
    min_elixir: int = 500000
    loot_margin_percent: float = 5.0
    use_and_rule: bool = True
    electrodragon_count: int = 8
    dragon_count: int = 1
    deploy_heroes: bool = True
    upgrade_wall_between_attacks: bool = True
    chain_attacks: bool = True
    delay_between_dragons_ms: int = 180
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
DRAGON_SLOT = (17.0, 92.5)
HERO_SLOTS = ((36.7, 92.5), (42.5, 92.5), (48.0, 92.5))
HERO_DROP_POINTS = ((15.0, 40.0), (85.0, 40.0), (15.0, 49.0))
BUILDERS_BUTTON = (49.0, 4.5)
WALL_LIST_ITEM = (47.5, 54.0)
WALL_GOLD_UPGRADE_BUTTON = (58.3, 76.5)
WALL_ELIXIR_UPGRADE_BUTTON = (67.5, 76.5)
WALL_CONFIRM_BUTTON = (70.0, 87.0)
WALL_GOLD_COST_ROI = Roi(50.0, 72.0, 60.2, 79.4)
WALL_ELIXIR_COST_ROI = Roi(59.0, 71.0, 69.0, 80.0)
WALL_RESERVE = 1_000_000
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
        if data.get("version", 0) < 4:
            data["version"] = 4
            for key, value in (("electrodragon_count", 8), ("dragon_count", 1), ("deploy_heroes", True), ("upgrade_wall_between_attacks", True), ("chain_attacks", True)):
                data.setdefault(key, value)
        if data.get("version", 0) < 6:
            data["version"] = 6
        kept = {item.name for item in fields(Settings)}
        return Settings(**{key: value for key, value in data.items() if key in kept})
    except (OSError, TypeError, ValueError): return Settings()


def save_settings(settings: Settings):
    APP_DIR.mkdir(parents=True, exist_ok=True); CONFIG_PATH.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


def effective_minimum(minimum: int, margin_percent: float) -> int:
    """Lower a configured loot threshold by a bounded tolerance percentage."""
    margin = max(0.0, min(25.0, margin_percent))
    return math.ceil(minimum * (1.0 - margin / 100.0))


def loot_is_accepted(gold: int, elixir: int, settings: Settings) -> tuple[bool, int, int]:
    gold_minimum = effective_minimum(settings.min_gold, settings.loot_margin_percent)
    elixir_minimum = effective_minimum(settings.min_elixir, settings.loot_margin_percent)
    accepted = (gold >= gold_minimum and elixir >= elixir_minimum) if settings.use_and_rule else (gold >= gold_minimum or elixir >= elixir_minimum)
    return accepted, gold_minimum, elixir_minimum


def read_safe_reserve(image: Image.Image, resource: str) -> int | None:
    """Read a home-village reserve conservatively; invalid OCR stops upgrades."""
    crop = crop_percent(image, PROFILE_ROIS[resource])
    candidates = (parse_clash_number(read_text(crop)), read_number(crop))
    valid = [value for value in candidates if value is not None and 0 <= value <= 20_000_000]
    return min(valid) if valid else None


def read_wall_cost(image: Image.Image, resource: str) -> int | None:
    """Read the amount printed on a wall upgrade button from two OCR passes."""
    roi = WALL_GOLD_COST_ROI if resource == "or" else WALL_ELIXIR_COST_ROI
    crop = crop_percent(image, roi)
    candidates = (parse_clash_number(read_text(crop)), read_number(crop))
    valid = [value for value in candidates if value is not None and 100_000 <= value <= 10_000_000]
    return min(valid) if valid else None


def choose_wall_payment(gold: int, elixir: int, gold_cost: int | None, elixir_cost: int | None) -> tuple[str, int] | None:
    """Choose a displayed wall price without reducing either reserve below 1 M."""
    choices = []
    if gold_cost is not None and gold - gold_cost >= WALL_RESERVE:
        choices.append((gold - WALL_RESERVE, "or", gold_cost))
    if elixir_cost is not None and elixir - elixir_cost >= WALL_RESERVE:
        choices.append((elixir - WALL_RESERVE, "élixir", elixir_cost))
    if not choices:
        return None
    _, resource, cost = max(choices, key=lambda choice: choice[0])
    return resource, cost


def repeated_points(points: tuple[tuple[float, float], ...] | list[tuple[float, float]], count: int) -> list[tuple[float, float]]:
    """Spread a configured troop count over the known valid perimeter points."""
    return [points[index % len(points)] for index in range(max(0, count))] if points else []


def normalized_screen_text(image: Image.Image) -> str:
    raw = read_text(image, scale=1).casefold().translate(str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s"}))
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii"))


def has_screen_text(image: Image.Image, *needles: str) -> bool:
    text = normalized_screen_text(image)
    return any((token := re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", needle.casefold()).encode("ascii", "ignore").decode("ascii"))) in text or token[:max(4, len(token)-3)] in text for needle in needles)


def has_all_screen_text(image: Image.Image, *needles: str) -> bool:
    text = normalized_screen_text(image)
    return all((token := re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", needle.casefold()).encode("ascii", "ignore").decode("ascii"))) in text or token[:max(4, len(token)-3)] in text for needle in needles)


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
    if not roi.valid(): raise ValueError("Zone de lecture invalide.")
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
        APP_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format="%(asctime)s %(message)s", encoding="utf-8")
        self.settings = load_settings()
        self.root = Tk()
        self.root.title("CoC Farm Bot")
        self.root.geometry("1120x900")
        self.root.minsize(940, 840)
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.photo = None
        self.window_title = StringVar(value=self.settings.window_title)
        self.min_gold = StringVar(value=str(self.settings.min_gold))
        self.min_elixir = StringVar(value=str(self.settings.min_elixir))
        self.loot_margin = StringVar(value=str(self.settings.loot_margin_percent))
        self.electrodragon_count = StringVar(value=str(self.settings.electrodragon_count))
        self.dragon_count = StringVar(value=str(self.settings.dragon_count))
        self.and_rule = BooleanVar(value=self.settings.use_and_rule)
        self.dry_run = BooleanVar(value=self.settings.dry_run)
        self.deploy_heroes = BooleanVar(value=self.settings.deploy_heroes)
        self.upgrade_wall = BooleanVar(value=self.settings.upgrade_wall_between_attacks)
        self.chain_attacks = BooleanVar(value=self.settings.chain_attacks)
        self.status = StringVar(value="Prêt à lire la fenêtre du jeu.")
        self.run_state = StringVar(value="PRÊT")
        self._build()
        self._pump()

    def _style(self):
        self.colors = {
            "bg": "#101B2A", "card": "#1B2A3D", "field": "#26394F",
            "text": "#EEF5FB", "muted": "#9EB2C7", "accent": "#66C6D8",
            "line": "#344A60",
        }
        self.root.configure(background=self.colors["bg"])
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=self.colors["bg"])
        style.configure("Card.TFrame", background=self.colors["card"])
        style.configure("App.TLabel", background=self.colors["bg"], foreground=self.colors["text"], font=("Segoe UI", 11))
        style.configure("Card.TLabel", background=self.colors["card"], foreground=self.colors["text"], font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=self.colors["card"], foreground=self.colors["muted"], font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=self.colors["card"], foreground=self.colors["text"], font=("Segoe UI Semibold", 12))
        style.configure("Hero.TLabel", background=self.colors["bg"], foreground=self.colors["text"], font=("Segoe UI Semibold", 23))
        style.configure("Eyebrow.TLabel", background=self.colors["bg"], foreground=self.colors["accent"], font=("Segoe UI Semibold", 9))
        style.configure("State.TLabel", background=self.colors["field"], foreground=self.colors["accent"], font=("Segoe UI Semibold", 9), padding=(12, 6))
        style.configure("App.TEntry", fieldbackground=self.colors["field"], foreground=self.colors["text"], insertcolor=self.colors["text"], bordercolor=self.colors["line"], padding=6)
        style.configure("App.TCombobox", fieldbackground=self.colors["field"], foreground=self.colors["text"], arrowcolor=self.colors["accent"], bordercolor=self.colors["line"], padding=6)
        style.map("App.TCombobox", fieldbackground=[("readonly", self.colors["field"])], foreground=[("readonly", self.colors["text"])])
        style.configure("App.TCheckbutton", background=self.colors["card"], foreground=self.colors["text"], font=("Segoe UI", 10))
        style.map("App.TCheckbutton", background=[("active", self.colors["card"])], foreground=[("active", self.colors["text"])])
        style.configure("Quiet.TButton", background=self.colors["field"], foreground=self.colors["text"], borderwidth=0, padding=(12, 8), font=("Segoe UI Semibold", 10))
        style.map("Quiet.TButton", background=[("active", self.colors["line"])])
        style.configure("Primary.TButton", background=self.colors["accent"], foreground=self.colors["bg"], borderwidth=0, padding=(16, 11), font=("Segoe UI Semibold", 11))
        style.map("Primary.TButton", background=[("active", "#93DBE7"), ("disabled", self.colors["line"])])

    def _card(self, parent, title, subtitle=None):
        frame = ttk.Frame(parent, style="Card.TFrame", padding=10)
        ttk.Label(frame, text=title, style="Section.TLabel").pack(anchor="w")
        if subtitle:
            ttk.Label(frame, text=subtitle, style="Muted.TLabel").pack(anchor="w", pady=(3, 8))
        else:
            ttk.Frame(frame, style="Card.TFrame", height=10).pack()
        return frame

    def _build(self):
        self._style()
        root = ttk.Frame(self.root, style="App.TFrame", padding=18)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(1, weight=1)
        header = ttk.Frame(root, style="App.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="CLASH OF CLANS  /  PILOTAGE", style="Eyebrow.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Pilote de farm", style="Hero.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Label(header, textvariable=self.run_state, style="State.TLabel").grid(row=1, column=1, sticky="e")

        left = ttk.Frame(root, style="App.TFrame", width=430)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
        left.grid_propagate(False)
        left.columnconfigure(0, weight=1)

        connection = self._card(left, "Jeu", "Fenêtre Google Play Jeux PC")
        connection.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        row = ttk.Frame(connection, style="Card.TFrame")
        row.pack(fill="x")
        self.windows = ttk.Combobox(row, textvariable=self.window_title, style="App.TCombobox")
        self.windows.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Détecter", command=self.refresh, style="Quiet.TButton").pack(side="left", padx=(8, 0))

        targets = self._card(left, "Butin recherché", "Valeurs minimales d’une base adverse")
        targets.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        target_grid = ttk.Frame(targets, style="Card.TFrame")
        target_grid.pack(fill="x")
        for index, (label, variable) in enumerate((("Or", self.min_gold), ("Élixir", self.min_elixir), ("Marge %", self.loot_margin))):
            target_grid.columnconfigure(index, weight=1)
            cell = ttk.Frame(target_grid, style="Card.TFrame")
            cell.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 8, 0))
            ttk.Label(cell, text=label, style="Muted.TLabel").pack(anchor="w")
            ttk.Entry(cell, textvariable=variable, style="App.TEntry", width=10).pack(fill="x", pady=(4, 0))
        ttk.Checkbutton(targets, text="Exiger l’or et l’élixir", variable=self.and_rule, style="App.TCheckbutton").pack(anchor="w", pady=(12, 0))

        army = self._card(left, "Armée", "Unités envoyées sur chaque base retenue")
        army.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        army_grid = ttk.Frame(army, style="Card.TFrame")
        army_grid.pack(fill="x")
        for index, (label, variable) in enumerate((("Électro-dragons", self.electrodragon_count), ("Dragons", self.dragon_count))):
            army_grid.columnconfigure(index, weight=1)
            cell = ttk.Frame(army_grid, style="Card.TFrame")
            cell.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 8, 0))
            ttk.Label(cell, text=label, style="Muted.TLabel").pack(anchor="w")
            ttk.Entry(cell, textvariable=variable, style="App.TEntry", width=8).pack(fill="x", pady=(4, 0))
        ttk.Checkbutton(army, text="Déployer les trois héros", variable=self.deploy_heroes, style="App.TCheckbutton").pack(anchor="w", pady=(12, 0))

        cycle = self._card(left, "Cycle", "Préparation et répétition")
        cycle.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        ttk.Checkbutton(cycle, text="Améliorer les remparts jusqu’à 1 M de réserves", variable=self.upgrade_wall, style="App.TCheckbutton").pack(anchor="w")
        ttk.Checkbutton(cycle, text="Enchaîner les attaques", variable=self.chain_attacks, style="App.TCheckbutton").pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(cycle, text="Simulation : rechercher sans déployer", variable=self.dry_run, style="App.TCheckbutton").pack(anchor="w", pady=(6, 0))

        actions = ttk.Frame(left, style="App.TFrame")
        actions.grid(row=4, column=0, sticky="ew", pady=(4, 0))
        actions.columnconfigure(0, weight=1)
        self.start_button = ttk.Button(actions, text="Lancer le farm", command=self.start_farm, style="Primary.TButton")
        self.start_button.grid(row=0, column=0, sticky="ew")
        self.stop_button = ttk.Button(actions, text="Arrêter", command=self.stop, style="Quiet.TButton")
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.stop_button.state(["disabled"])

        right = self._card(root, "Activité", "Capture et messages du bot")
        right.grid(row=1, column=1, sticky="nsew")
        right_body = ttk.Frame(right, style="Card.TFrame")
        right_body.pack(fill="both", expand=True)
        right_body.columnconfigure(0, weight=1)
        right_body.rowconfigure(3, weight=1)
        tools = ttk.Frame(right_body, style="Card.TFrame")
        tools.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(tools, text="Lire l’écran", command=self.inspect_game, style="Quiet.TButton").pack(side="left")
        ttk.Button(tools, text="Relever le profil", command=self.scan_profile, style="Quiet.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(tools, text="Enregistrer", command=self.persist, style="Quiet.TButton").pack(side="right")
        self.preview = ttk.Label(right_body, text="Aucune capture. Cliquez sur « Lire l’écran ».", anchor="center", style="Card.TLabel")
        self.preview.grid(row=1, column=0, sticky="ew", ipady=55)
        ttk.Label(right_body, text="JOURNAL", style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=(14, 6))
        self.log = __import__("tkinter").Text(right_body, height=11, state="disabled", wrap="word", background=self.colors["bg"], foreground=self.colors["text"], insertbackground=self.colors["accent"], relief="flat", padx=12, pady=10, font=("Consolas", 9))
        self.log.grid(row=3, column=0, sticky="nsew")
        ttk.Label(root, textvariable=self.status, style="App.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(14, 0))
        self.refresh()

    def refresh(self):
        windows=[window for window in WindowDriver.list_windows() if window.title.casefold().startswith("clash of clans")]
        self.windows["values"]=[window.title for window in windows]
        if windows and self.window_title.get() not in self.windows["values"]:
            self.window_title.set(windows[0].title)
        self.write(f"{len(windows)} fenêtre(s) Clash détectée(s).")

    def inspect_game(self):
        window=WindowDriver.resolve(self.window_title.get())
        if not window: self.write("Fenêtre Clash introuvable."); return
        self.window_title.set(window.title)
        try:
            image=WindowDriver.capture(window)
            self._show_preview(image)
            if has_all_screen_text(image, "attaquer", "magasin"):
                gold, elixir=read_safe_reserve(image, "gold"), read_safe_reserve(image, "elixir")
                self.write(f"Village : or {gold if gold is not None else '?':,} / élixir {elixir if elixir is not None else '?':,}." if gold is not None and elixir is not None else "Village détecté ; réserves illisibles.")
            elif enemy_loot_screen_ready(image):
                loot=read_enemy_loot(image)
                self.write(f"Base adverse : or {loot.gold:,} / élixir {loot.elixir:,}." if loot.gold is not None and loot.elixir is not None else "Base adverse détectée ; butin illisible.")
            else:
                self.write("Capture reçue ; écran non reconnu pour la lecture des ressources.")
        except Exception as exc: self.write(f"Lecture impossible : {exc}")

    def _show_preview(self, image):
        preview=image.copy()
        preview.thumbnail((430, 242))
        self.photo=ImageTk.PhotoImage(preview)
        self.preview.configure(image=self.photo, text="")

    def scan_profile(self):
        window = WindowDriver.resolve(self.window_title.get())
        if not window: self.write("Fenêtre Clash introuvable."); return
        try:
            image = WindowDriver.capture(window); self.window_title.set(window.title); self._show_preview(image)
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
            self.settings.window_title=self.window_title.get();self.settings.min_gold=int(self.min_gold.get().replace(" ",""));self.settings.min_elixir=int(self.min_elixir.get().replace(" ",""));self.settings.loot_margin_percent=float(self.loot_margin.get().replace(",","."));self.settings.electrodragon_count=int(self.electrodragon_count.get());self.settings.dragon_count=int(self.dragon_count.get());self.settings.use_and_rule=self.and_rule.get();self.settings.dry_run=self.dry_run.get();self.settings.deploy_heroes=self.deploy_heroes.get();self.settings.upgrade_wall_between_attacks=self.upgrade_wall.get();self.settings.chain_attacks=self.chain_attacks.get()
            if not 0 <= self.settings.min_gold <= 2_500_000 or not 0 <= self.settings.min_elixir <= 2_500_000 or not 0 <= self.settings.loot_margin_percent <= 25 or not 0 <= self.settings.electrodragon_count <= 50 or not 0 <= self.settings.dragon_count <= 50: raise ValueError
            save_settings(self.settings);self.write(f"Configuration enregistrée : attaque dès {effective_minimum(self.settings.min_gold, self.settings.loot_margin_percent):,} or / {effective_minimum(self.settings.min_elixir, self.settings.loot_margin_percent):,} élixir.");return True
        except ValueError: messagebox.showerror("Valeur invalide","Seuils : 0 à 2 500 000 ; marge : 0 à 25 % ; troupes : 0 à 50.");return False
    def start_farm(self):
        if self.worker and self.worker.is_alive(): return
        if not self.persist(): return
        if self.settings.dry_run: self.write("Simulation active : recherche et lecture uniquement, aucune pose ne sera envoyée.")
        else: self.write(f"Mode réel actif : {self.settings.electrodragon_count} électro-dragons, {self.settings.dragon_count} dragons et {'3 héros' if self.settings.deploy_heroes else 'aucun héros'} sur une base retenue.")
        self.stop_event.clear(); self.worker=threading.Thread(target=self.farm_loop,daemon=True); self.worker.start(); self.run_state.set("EN COURS"); self.write("Recherche automatique démarrée.")
    def stop(self):self.stop_event.set();self.write("Arrêt demandé.")
    def upgrade_walls_to_reserve(self, window):
        """Upgrade available walls while keeping both village reserves at or above 1 M."""
        if not self.settings.upgrade_wall_between_attacks or self.settings.dry_run:
            return 0
        upgraded = 0
        while not self.stop_event.is_set():
            reserves_image = WindowDriver.capture(window)
            gold = read_safe_reserve(reserves_image, "gold")
            elixir = read_safe_reserve(reserves_image, "elixir")
            if gold is None or elixir is None:
                self.events.put("Réserves illisibles : aucun rempart n’est confirmé.")
                return upgraded
            if gold <= WALL_RESERVE and elixir <= WALL_RESERVE:
                self.events.put(f"Réserves préservées : or {gold:,}, élixir {elixir:,}.")
                return upgraded
            if not WindowDriver.click_percent(window, *BUILDERS_BUTTON):
                raise RuntimeError("Clic ouvriers refusé.")
            self.stop_event.wait(.7)
            if self.stop_event.is_set() or not has_screen_text(WindowDriver.capture(window), "rempart"):
                self.events.put("Aucun rempart disponible à améliorer.")
                return upgraded
            if not WindowDriver.click_percent(window, *WALL_LIST_ITEM):
                raise RuntimeError("Clic rempart refusé.")
            self.stop_event.wait(.7)
            wall_image = WindowDriver.capture(window)
            if self.stop_event.is_set() or not has_screen_text(wall_image, "rempart"):
                self.events.put("Sélection de rempart non confirmée.")
                return upgraded
            choice = choose_wall_payment(gold, elixir, read_wall_cost(wall_image, "or"), read_wall_cost(wall_image, "élixir"))
            if choice is None:
                self.events.put(f"Plancher de 1 M conservé : or {gold:,}, élixir {elixir:,}.")
                return upgraded
            resource, cost = choice
            button = WALL_GOLD_UPGRADE_BUTTON if resource == "or" else WALL_ELIXIR_UPGRADE_BUTTON
            if not WindowDriver.click_percent(window, *button):
                raise RuntimeError(f"Clic amélioration rempart {resource} refusé.")
            self.stop_event.wait(.7)
            if self.stop_event.is_set() or not has_all_screen_text(WindowDriver.capture(window), "confirmer", "rempart"):
                self.events.put("Confirmation du rempart absente : aucun autre clic envoyé.")
                return upgraded
            if not WindowDriver.click_percent(window, *WALL_CONFIRM_BUTTON):
                raise RuntimeError("Confirmation rempart refusée.")
            upgraded += 1
            self.events.put(f"Rempart amélioré avec {cost:,} {resource} ({upgraded} au total).")
            self.stop_event.wait(1)
        return upgraded

    def deploy_unit(self, window, label, slot, points):
        if not points: return
        if not WindowDriver.click_percent(window,*slot): raise RuntimeError(f"Sélection {label} refusée.")
        self.stop_event.wait(self.settings.delay_between_dragons_ms/1000)
        for x,y in points:
            if self.stop_event.is_set(): return
            if not WindowDriver.click_percent(window,x,y): raise RuntimeError(f"Pose {label} refusée.")
            self.events.put(f"{label} posé : {x:.1f} %, {y:.1f} %")
            self.stop_event.wait(self.settings.delay_between_dragons_ms/1000)

    def deploy_attack_composition(self, window):
        perimeter=ELECTRODRAGON_PERIMETER_POINTS
        self.deploy_unit(window,"Électro-dragon",ELECTRODRAGON_SLOT,repeated_points(perimeter,self.settings.electrodragon_count))
        self.deploy_unit(window,"Dragon",DRAGON_SLOT,repeated_points(perimeter,self.settings.dragon_count))
        if self.settings.deploy_heroes:
            for number,(slot,point) in enumerate(zip(HERO_SLOTS,HERO_DROP_POINTS),1): self.deploy_unit(window,f"Héros {number}",slot,[point])
        self.events.put("Composition d'attaque entièrement déployée.")

    def wait_for_battle_return(self, window):
        """Wait for Clash's result screen, return home, then allow the next cycle."""
        deadline=time.monotonic()+240
        self.events.put("Attente de la fin de bataille avant le prochain cycle.")
        while not self.stop_event.is_set() and time.monotonic()<deadline:
            image=WindowDriver.capture(window)
            if has_all_screen_text(image,"attaquer","magasin"): return True
            if has_screen_text(image,"retour au village","victoire","défaite"):
                WindowDriver.click_percent(window,50.0,86.0); self.stop_event.wait(4)
            else: self.stop_event.wait(3)
        self.events.put("Fin de bataille non confirmée : cycle arrêté sans cliquer Terminer la bataille."); return False

    def open_search(self, window):
        for point,delay,label in ((ATTACK_HOME_BUTTON,1.0,"Ouverture du menu Attaquer"),(FIND_MATCH_BUTTON,1.0,"Ouverture de la sélection d'armée"),(START_SEARCH_BUTTON,6.0,"Recherche d'une base adverse")):
            if not WindowDriver.click_percent(window,*point): raise RuntimeError(f"Clic refusé : {label}.")
            self.events.put(label); self.stop_event.wait(delay)
            if self.stop_event.is_set(): return False
        return True

    def farm_loop(self):
        """Prepare, find a valid base, deploy the configured army, then repeat."""
        try:
            while not self.stop_event.is_set():
                window=WindowDriver.resolve(self.settings.window_title)
                if not window: raise RuntimeError("Fenêtre Clash introuvable.")
                self.upgrade_walls_to_reserve(window)
                if self.stop_event.is_set() or not self.open_search(window): return
                accepted=False
                while not self.stop_event.is_set():
                    image=WindowDriver.capture(window); loot=read_enemy_loot(image)
                    if not enemy_loot_screen_ready(image):
                        self.events.put("Attente de l'affichage complet de la base adverse."); self.stop_event.wait(.5); continue
                    if loot.gold is None or loot.elixir is None:
                        self.events.put("Butin adverse illisible : aucune action envoyée."); self.stop_event.wait(1); continue
                    accepted,gold_minimum,elixir_minimum=loot_is_accepted(loot.gold,loot.elixir,self.settings)
                    self.events.put(f"Base adverse : or {loot.gold:,}, élixir {loot.elixir:,} | seuils avec marge : {gold_minimum:,}/{elixir_minimum:,} → {'attaque' if accepted else 'suivant'}.")
                    if accepted: break
                    if not WindowDriver.click_percent(window,*NEXT_BASE_BUTTON): raise RuntimeError("Clic Suivant refusé.")
                    self.stop_event.wait(3)
                if not accepted or self.stop_event.is_set(): return
                if self.settings.dry_run:
                    self.events.put("Simulation : base retenue ; aucune troupe ni amélioration n'est envoyée."); return
                self.deploy_attack_composition(window)
                if not self.settings.chain_attacks or not self.wait_for_battle_return(window): return
        except Exception as exc: self.events.put(f"Recherche arrêtée : {exc}")
        finally:
            self.stop_event.set(); self.events.put("Bot arrêté.")
    def _pump(self):
        try:
            while True:self.write(self.events.get_nowait())
        except queue.Empty:pass
        running=bool(self.worker and self.worker.is_alive())
        self.start_button.state(["disabled"] if running else ["!disabled"])
        self.stop_button.state(["!disabled"] if running else ["disabled"])
        if not running and self.run_state.get()=="EN COURS": self.run_state.set("PRÊT")
        self.root.after(250,self._pump)
    def write(self,text):
        logging.info(text);self.status.set(text);self.log.configure(state="normal");self.log.insert("end",text+"\n");self.log.see("end");self.log.configure(state="disabled")
    def run(self):self.root.mainloop()


def self_test():
    assert Roi(1,2,3,4).valid() and not Roi(3,2,1,4).valid()
    assert parse_clash_number("loz") == 107 and parse_worker_ratio("112") == "1/2" and parse_worker_ratio("SIS") == "5/5"
    image=Image.new("RGB",(600,150),"white");ImageDraw.Draw(image).text((12,12),"123456",fill="black",font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf",90));assert read_number(image)==123456
    assert choose_wall_payment(1_500_000, 1_400_000, 500_000, 500_000) == ("or", 500_000)
    assert choose_wall_payment(1_499_999, 1_500_000, 500_000, 500_000) == ("élixir", 500_000)
    assert choose_wall_payment(1_400_000, 1_400_000, 500_000, 500_000) is None
    print("Self-test passed")


def profile_test():
    window = WindowDriver.resolve("")
    if not window: raise RuntimeError("Fenêtre Clash introuvable pour le test de profil.")
    snapshot = read_account_snapshot(WindowDriver.capture(window))
    required = (snapshot.account_name, snapshot.level, snapshot.gold, snapshot.elixir, snapshot.dark_elixir, snapshot.gems, snapshot.laboratory_builders, snapshot.builders)
    if any(value is None for value in required): raise RuntimeError(f"Relevé incomplet : {asdict(snapshot)}")
    print(json.dumps(asdict(snapshot), ensure_ascii=False))

if __name__ == "__main__":
    profile_test() if "--profile-test" in sys.argv else (self_test() if "--self-test" in sys.argv else BotApp().run())
