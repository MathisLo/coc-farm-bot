"""CoC Farm Bot: capture Windows et commandes en arrière-plan."""
from __future__ import annotations

import asyncio
import argparse
import codecs
import ctypes
from ctypes import wintypes
from datetime import datetime
import json
import math
import queue
import re
import shutil
import sys
import tempfile
import threading
import time
import traceback
import unicodedata
import uuid
import zipfile
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, ttk, filedialog, messagebox

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, ImageStat, ImageTk
from calibration import CalibrationDialog, validate_overrides
from farm_stats import FarmStats
from app_meta import APP_NAME, APP_VERSION

APP_DIR = Path.home() / "CoCFarmBot"
CONFIG_PATH = APP_DIR / "config-v2.json"
LOG_PATH = APP_DIR / "bot.log"
RUNS_DIR = APP_DIR / "runs"
ACCOUNT_SNAPSHOT_PATH = APP_DIR / "account_snapshot.json"
STATS_PATH = APP_DIR / "farm-stats.json"
# Keep the v1.0.14 storage marker so the visual refactor does not erase the
# user's saved settings, statistics, profiles, or diagnostic history.
STORAGE_GENERATION = "v1.0.14-clean-start"
STORAGE_MARKER = ".storage-generation"
ASSET_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets"
OCR_TIMEOUT = 8.0
BASE_READ_TIMEOUT = 35.0
_operation = threading.local()


class OperationCancelled(RuntimeError):
    """An explicit stop, not an automation failure."""


class ReconnectRequired(Exception):
    """Unwind the interrupted action before reconnecting and re-reading state."""


def check_cancelled():
    event = getattr(_operation, "stop_event", None)
    if event is not None and event.is_set():
        raise OperationCancelled("Arrêt demandé.")


@contextmanager
def operation_context(stop_event, settings, journal=None):
    previous = vars(_operation).copy()
    _operation.stop_event = stop_event
    _operation.settings = settings
    _operation.journal = journal
    try:
        check_cancelled()
        yield
    finally:
        vars(_operation).clear()
        vars(_operation).update(previous)


@contextmanager
def ocr_deadline(deadline):
    previous = getattr(_operation, "deadline", None)
    _operation.deadline = min(previous, deadline) if previous is not None else deadline
    try:
        yield
    finally:
        _operation.deadline = previous


async def bounded_ocr(awaitable):
    """Cancel even an outstanding Windows OCR call when Stop is requested."""
    task = asyncio.ensure_future(awaitable)
    deadline = min(time.monotonic() + OCR_TIMEOUT,
                   getattr(_operation, "deadline", None) or float("inf"))
    try:
        while True:
            check_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Délai de lecture OCR dépassé.")
            done, _ = await asyncio.wait({task}, timeout=min(.05, remaining))
            if done:
                check_cancelled()
                return task.result()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


USER32 = ctypes.WinDLL("user32", use_last_error=True)
GDI32 = ctypes.WinDLL("gdi32", use_last_error=True)
PW_RENDERFULLCONTENT, WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON = 2, 0x0201, 0x0202, 1

USER32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT)); USER32.GetWindowRect.restype = wintypes.BOOL
USER32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT)); USER32.GetClientRect.restype = wintypes.BOOL
USER32.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT)); USER32.ClientToScreen.restype = wintypes.BOOL
USER32.IsIconic.argtypes = (wintypes.HWND,); USER32.IsIconic.restype = wintypes.BOOL
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
    version: int = 8
    window_title: str = ""
    min_gold: int = 500000
    min_elixir: int = 500000
    loot_margin_percent: float = 5.0
    use_and_rule: bool = True
    electrodragon_count: int = 8
    dragon_count: int = 1
    deploy_heroes: bool = True
    upgrade_wall_between_attacks: bool = True
    upgrade_recommended: bool = True
    chain_attacks: bool = True
    delay_between_dragons_ms: int = 180
    dry_run: bool = False
    layout_overrides: dict = field(default_factory=dict)
    layout_aspect_ratio: float = 16 / 9


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


@dataclass(frozen=True)
class PreviewEvent:
    image: Image.Image
    title: str
    calibrate: bool = False


@dataclass(frozen=True)
class StatsEvent:
    totals: dict


@dataclass(frozen=True)
class RunStateEvent:
    status: str


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
WALL_GOLD_TIGHT_COST_ROI = Roi(54.8, 74.3, 60.9, 77.3)
WALL_ELIXIR_TIGHT_COST_ROI = Roi(62.8, 74.3, 68.9, 77.3)
WALL_RESERVE = 1_000_000
WALL_MORE_BUTTON = (50.0, 80.0)
WALL_ADD_TEN_BUTTON = (42.0, 80.0)
WALL_ADD_ONE_BUTTON = (50.0, 80.0)
WALL_MULTI_GOLD_BUTTON = (58.3, 80.0)
WALL_MULTI_ELIXIR_BUTTON = (66.5, 80.0)
WALL_MULTI_CONFIRM_BUTTON = (59.0, 62.0)
# A single upper-left attack edge, away from the central no-deploy area.
# Every unit and hero uses this same straight line, never the opposite edge.
ELECTRODRAGON_PERIMETER_POINTS = [
    (18.0 + 20.0*i/15, 40.0 - 27.0*i/15) for i in range(16)
]
TROOP_COUNT_ROIS = {
    "Électro-dragon": Roi(23.7, 85.19, 28.0, 89.35),
    "Dragon": Roi(17.45, 85.19, 20.05, 89.35),
}
TROOP_ICON_ROIS = {
    "Électro-dragon": Roi(20.8, 89.8, 26.3, 97.2),
    "Dragon": Roi(14.6, 89.8, 20.1, 97.2),
}
TROOP_COUNTER_INK_ROIS = {
    "Électro-dragon": Roi(24.22, 85.09, 26.56, 88.24),
    "Dragon": Roi(18.02, 85.09, 20.36, 88.24),
}
HERO_HEALTH_ROIS = (Roi(34.6, 82.6, 39.5, 84.9), Roi(40.9, 82.6, 45.8, 84.9), Roi(47.2, 82.6, 52.1, 84.9))
HERO_ICON_ROIS = (Roi(34.4, 85.7, 40.4, 98.1), Roi(40.6, 85.7, 46.6, 98.1), Roi(46.9, 85.7, 52.6, 98.1))
ENEMY_LOOT_ROIS = {
    "gold": Roi(4.1, 11.1, 16.0, 14.4), "elixir": Roi(4.1, 15.8, 16.0, 18.8), "dark_elixir": Roi(4.1, 20.0, 16.0, 23.4),
}
ENEMY_LOOT_LABEL_ROI = Roi(3.5, 7.5, 17.0, 11.5)
SCREEN_ROIS = {
    "builders_menu": Roi(38, 10, 63, 25), "wall_actions": Roi(29, 68, 71, 88),
    "wall_confirmation": Roi(31, 41, 69, 51), "wall_confirmation_ok": Roi(49, 55, 67, 69),
    "daily_reward": Roi(35, 9, 65, 23), "battle_reward": Roi(25, 12, 75, 22),
    "hero_compact": Roi(28.4, 87.5, 32.55, 94.0), "hero_expanded": Roi(34.63, 87.5, 38.8, 94.0),
    "wall_menu": Roi(35, 10, 55, 64),
}
RETURN_HOME_BUTTON = (50.0, 86.0)
DAILY_REWARD_CLOSE_BUTTON = (84.0, 14.0)


def layout_defaults():
    """Every active named point/region can be adjusted without editing Python."""
    defaults = {}
    for name in ("ATTACK_HOME_BUTTON", "FIND_MATCH_BUTTON", "START_SEARCH_BUTTON", "NEXT_BASE_BUTTON",
                 "ELECTRODRAGON_SLOT", "DRAGON_SLOT", "HERO_SLOTS", "BUILDERS_BUTTON", "WALL_MORE_BUTTON",
                 "WALL_ADD_TEN_BUTTON", "WALL_ADD_ONE_BUTTON", "WALL_MULTI_GOLD_BUTTON", "WALL_MULTI_ELIXIR_BUTTON",
                 "WALL_MULTI_CONFIRM_BUTTON", "WALL_CONFIRM_BUTTON", "RETURN_HOME_BUTTON", "DAILY_REWARD_CLOSE_BUTTON",
                 "ELECTRODRAGON_PERIMETER_POINTS", "PROFILE_ROIS", "ENEMY_LOOT_ROIS", "ENEMY_LOOT_LABEL_ROI",
                 "TROOP_COUNT_ROIS", "TROOP_ICON_ROIS", "TROOP_COUNTER_INK_ROIS", "HERO_HEALTH_ROIS", "HERO_ICON_ROIS",
                 "WALL_GOLD_COST_ROI", "WALL_ELIXIR_COST_ROI", "WALL_GOLD_TIGHT_COST_ROI", "WALL_ELIXIR_TIGHT_COST_ROI",
                 "SCREEN_ROIS"):
        value = globals()[name]
        if isinstance(value, dict):
            children = value.items()
        elif isinstance(value, (list, tuple)) and not isinstance(value[0], (int, float)):
            children = enumerate(value)
        else:
            children = [(None, value)]
        for child, item in children:
            key = name if child is None else f"{name}.{child}"
            defaults[key] = list(asdict(item).values()) if isinstance(item, Roi) else list(item)
    return defaults


LAYOUT_DEFAULTS = layout_defaults()


def layout_labels():
    groups = {
        "ATTACK_HOME_BUTTON": "Village · Attaquer", "FIND_MATCH_BUTTON": "Recherche · Multijoueur",
        "START_SEARCH_BUTTON": "Recherche · Lancer", "NEXT_BASE_BUTTON": "Recherche · Suivant",
        "ELECTRODRAGON_SLOT": "Armée · Sélection électro-dragon", "DRAGON_SLOT": "Armée · Sélection dragon",
        "HERO_SLOTS": "Armée · Sélection héros", "BUILDERS_BUTTON": "Village · Ouvriers",
        "WALL_CONFIRM_BUTTON": "Remparts · Confirmer un seul rempart", "WALL_MORE_BUTTON": "Remparts · Améliorer plus", "WALL_ADD_TEN_BUTTON": "Remparts · Ajouter 10",
        "WALL_ADD_ONE_BUTTON": "Remparts · Ajouter 1", "WALL_MULTI_GOLD_BUTTON": "Remparts · Payer en or",
        "WALL_MULTI_ELIXIR_BUTTON": "Remparts · Payer en élixir", "WALL_MULTI_CONFIRM_BUTTON": "Remparts · Confirmer",
        "RETURN_HOME_BUTTON": "Bataille · Retour au village", "DAILY_REWARD_CLOSE_BUTTON": "Récompense quotidienne · Fermer",
        "ELECTRODRAGON_PERIMETER_POINTS": "Déploiement · Point", "PROFILE_ROIS": "Profil · Lecture",
        "ENEMY_LOOT_ROIS": "Butin adverse · Lecture", "ENEMY_LOOT_LABEL_ROI": "Butin adverse · Libellé Butin",
        "TROOP_COUNT_ROIS": "Armée · Compteur", "TROOP_ICON_ROIS": "Armée · Icône",
        "TROOP_COUNTER_INK_ROIS": "Armée · Diagnostic du chiffre", "HERO_HEALTH_ROIS": "Héros · Barre de vie",
        "HERO_ICON_ROIS": "Héros · Icône", "WALL_GOLD_COST_ROI": "Remparts · Prix or",
        "WALL_ELIXIR_COST_ROI": "Remparts · Prix élixir", "WALL_GOLD_TIGHT_COST_ROI": "Remparts · Prix or (zone étroite)",
        "WALL_ELIXIR_TIGHT_COST_ROI": "Remparts · Prix élixir (zone étroite)", "SCREEN_ROIS": "Écrans · Lecture",
    }
    children = {"gold": "Or", "elixir": "Élixir", "dark_elixir": "Élixir noir", "gems": "Gemmes",
                "account_name": "Pseudo", "level": "Niveau", "builders": "Ouvriers", "laboratory_builders": "Laboratoire",
                "builders_menu": "Menu ouvriers", "wall_actions": "Actions remparts", "wall_confirmation": "Confirmation remparts",
                "wall_confirmation_ok": "Bouton OK remparts", "daily_reward": "Récompense quotidienne",
                "battle_reward": "Récompense de bataille", "hero_compact": "Roi sans engin de siège",
                "hero_expanded": "Roi avec engin de siège", "wall_menu": "Liste des remparts"}
    labels = {}
    for key in LAYOUT_DEFAULTS:
        root, _, child = key.partition(".")
        suffix = str(int(child) + 1) if child.isdigit() else children.get(child, child)
        labels[key] = groups[root] + (" · " + suffix if suffix else "")
    return labels


def layout_values(name, child=None):
    key = name if child is None else f"{name}.{child}"
    settings = getattr(_operation, "settings", None)
    return tuple(settings.layout_overrides.get(key, LAYOUT_DEFAULTS[key]) if settings else LAYOUT_DEFAULTS[key])


def layout_roi(name, child=None):
    return Roi(*layout_values(name, child))


def layout_points(name):
    return [layout_values(name, index) for index in range(len(globals()[name]))]


def validate_layout(settings):
    validate_overrides(LAYOUT_DEFAULTS, settings.layout_overrides)
    ratio = settings.layout_aspect_ratio
    if not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or not .5 <= ratio <= 4:
        raise ValueError("Format du calibrage invalide.")


def checked_storage_directory(path: Path) -> Path:
    """Accept only the bot's named directory, never a parent or redirected tree."""
    path = Path(path).absolute()
    if path.name.casefold() != "cocfarmbot":
        raise ValueError("Dossier de données inattendu : suppression refusée.")
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise ValueError("Dossier de données redirigé : suppression refusée.")
    if path.resolve(strict=False).parent != path.parent.resolve(strict=True):
        raise ValueError("Dossier de données hors de l'emplacement prévu.")
    return path


def clear_saved_data(path: Path):
    """Remove every bot-owned file, including legacy and unknown future files."""
    directory = checked_storage_directory(path)
    if directory.exists():
        if not directory.is_dir():
            raise ValueError("Le chemin des données n'est pas un dossier.")
        shutil.rmtree(directory)
    if directory.exists():
        raise OSError("Les données du bot n'ont pas toutes été supprimées.")


def prepare_storage(path: Path) -> bool:
    """Clear older releases exactly once, before loading settings or stats."""
    directory = checked_storage_directory(path)
    marker = directory / STORAGE_MARKER
    try:
        current = marker.read_text(encoding="utf-8") == STORAGE_GENERATION
    except OSError:
        current = False
    settings_file = directory / "config-v2.json"
    if current and settings_file.exists():
        try:
            current = json.loads(settings_file.read_text(encoding="utf-8")).get("version", 0) >= 8
        except (OSError, ValueError, TypeError, AttributeError):
            current = False
    if current:
        return False
    had_old_data = directory.exists() and any(directory.iterdir())
    clear_saved_data(directory)
    directory.mkdir(parents=True, exist_ok=True)
    marker.write_text(STORAGE_GENERATION, encoding="utf-8")
    return had_old_data


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
        data["version"] = 8
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


def white_text_mask(image: Image.Image) -> Image.Image:
    """Keep white lettering, excluding bright coloured resource bars/icons."""
    r, g, b = image.convert("RGB").split()
    ink = ImageChops.darker(ImageChops.darker(r, g), b)
    return ImageOps.expand(ink.point(lambda value: 0 if value > 180 else 255), border=8, fill=255)


def read_safe_reserve(image: Image.Image, resource: str) -> int | None:
    """Read a home-village reserve conservatively; invalid OCR stops upgrades."""
    calibrated = f"PROFILE_ROIS.{resource}" in getattr(getattr(_operation, "settings", None), "layout_overrides", {})
    fallback_rois = () if calibrated else ((Roi(86, 3, 95, 6.2), Roi(86, 2.5, 95, 6.5)) if resource == "gold" else (Roi(86, 10.5, 95, 15),))
    for rois in ((layout_roi("PROFILE_ROIS", resource),), fallback_rois):
        values = []
        for roi in rois:
            crop = crop_percent(image, roi)
            for variant, scale in ((white_text_mask(crop), 3), (crop, 2), (crop, 3), (crop, 5)):
                value = parse_reserve_number(read_text(variant, scale=scale))
                if value is not None and 0 <= value <= 20_000_000:
                    values.append(value)
        if values:
            agreed = [value for value in set(values) if values.count(value) >= 2]
            if len(agreed) == 1:
                return agreed[0]
            # Prefer the full reserve strip. Narrower crops can duplicate the
            # leading digit (1 832 344 -> 11 832 344) beside the icon.
            if max(values) - min(values) <= 20_000:
                return min(values)
            # Conflicting wide-crop OCR must still try the tighter numeric
            # strip. Previously a partial reading prevented that fallback.
    if not calibrated:
        crop = crop_percent(image,Roi(87,3.1,95.3,6.1) if resource=='gold' else Roi(86,10.5,95,15))
        r,g,b = crop.convert('RGB').split()
        ink = ImageChops.darker(ImageChops.darker(r,g),b)
        votes = []
        for threshold in (150,180,200,220):
            mask = ImageOps.expand(ink.point(lambda v:0 if v>threshold else 255),border=12,fill=255)
            value = parse_reserve_number(read_text(mask,scale=2))
            if value is not None and value <= 20_000_000:
                votes.append(value)
        agreed = [value for value in set(votes) if votes.count(value)>=2]
        if len(agreed)==1:
            return agreed[0]
    return None


def parse_reserve_number(text: str) -> int | None:
    corrected = text.translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "i": "1", "S": "5", "s": "5", "B": "8", "g": "9", "G": "9", "-": " ", "*": " ", ",": " ", "x": " ", "L": " "}))
    match = re.search(r"(?<!\d)(\d{1,2})\s+(\d{3})\s+(\d{3})(?!\d)", corrected)
    if match: return int("".join(match.groups()))
    stripped = corrected.strip(" ,-.")
    digits = re.sub(r"\s+", "", stripped)
    return int(digits) if re.fullmatch(r"\d{7,8}|\d{1,2}\s+\d{6}", stripped) else None


def read_wall_cost(image: Image.Image, resource: str, shift: float = 0) -> int | None:
    """Read the amount printed on a wall upgrade button from two OCR passes."""
    tight_roi = layout_roi("WALL_GOLD_TIGHT_COST_ROI") if resource == "or" else layout_roi("WALL_ELIXIR_TIGHT_COST_ROI")
    tight_roi = shifted_roi(tight_roi, shift)
    tight = parse_clash_number(read_text(crop_percent(image, tight_roi), scale=6))
    if tight is not None and 100_000 <= tight <= 10_000_000:
        return tight
    roi = layout_roi("WALL_GOLD_COST_ROI") if resource == "or" else layout_roi("WALL_ELIXIR_COST_ROI")
    roi = shifted_roi(roi, shift)
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


def wall_batch_size(balance: int, unit_cost: int, available: int) -> int:
    """Buy the largest affordable group without crossing the reserve floor."""
    return max(0, min(available, (balance - WALL_RESERVE) // unit_cost)) if unit_cost > 0 else 0


def read_troop_count(image: Image.Image, label: str) -> int | None:
    card = crop_percent(image, layout_roi("TROOP_ICON_ROIS", label))
    # A blank/missing card is not proof that the army is empty.
    if ImageStat.Stat(ImageOps.grayscale(card)).stddev[0] < 12:
        return None
    icon = card.convert("HSV").getchannel(1)
    if ImageStat.Stat(icon).mean[0] < 30:
        return 0
    roi = layout_roi("TROOP_COUNT_ROIS", label)
    # The counter moves down when the deployment controls appear. Include
    # that motion and remove the blue card before asking OCR to read x1/x2.
    counter = crop_percent(image, Roi(max(0, roi.x1 - .5), max(0, roi.y1 - .6),
                                     min(100, roi.x2 + 1.5), min(100, roi.y2 + 1)))
    if counter_is_one(counter):
        return 1
    # On some game renders the plain crop is clearer than the white mask.
    for scale in (2, 4):
        raw = read_text(counter, scale=scale).casefold().replace("xi", "x8").replace("xb", "x8")
        match = re.fullmatch(r"[x×]\s*(\d{1,2})", raw.strip())
        if match:
            return int(match.group(1))
    # A tight crop removes the next card; Windows OCR sometimes adds one
    # spurious digit before an otherwise clear x8 on this render.
    tight = Roi(roi.x1 + .9, roi.y1 + .21, roi.x2 - .8, roi.y2 - .95)
    if tight.valid():
        raw = read_text(crop_percent(image, tight), scale=4).casefold().replace("xi", "x8").replace("xb", "x8")
        match = re.search(r"[x×]\s*(\d{1,2})$", raw.strip())
        if match:
            return int(match.group(1))
        masked = read_text(white_text_mask(crop_percent(image, tight)), scale=3).casefold().replace("xi", "x8").replace("xb", "x8")
        # The game's stylised 2 is sometimes reported as z on the mask.
        match = re.fullmatch(r"[x×]\s*(\d{1,2}|z)", masked.strip())
        if match:
            return 2 if match.group(1) == "z" else int(match.group(1))
    for scale in (3, 5):
        raw = read_text(white_text_mask(counter), scale=scale).casefold().replace("xi", "x8").replace("xb", "x8").translate(str.maketrans({"o": "0", "l": "1", "i": "1"}))
        match = re.fullmatch(r"[x×]\s*(\d{1,2})", raw.strip())
        if match:
            return int(match.group(1))
    if label == "Électro-dragon":
        # The selected card can shift the counter to the right. Its border
        # obscures x2 in the wide crop, while a crop just inside that border
        # exposes both glyphs to Windows OCR.
        inner_roi = Roi(max(0, roi.x1 - .7), max(0, roi.y1 - .2), roi.x2 - .5, roi.y2)
        if inner_roi.valid():
            inner = crop_percent(image, inner_roi)
            raw = read_text(white_text_mask(inner), scale=5).casefold().replace("xi", "x8").replace("xb", "x8")
            match = re.fullmatch(r"[x×]\s*(\d{1,2})", raw.strip())
            if match:
                return int(match.group(1))
    for shift in (0, .5, 1, -.5, -1):
        for top in (roi.y1, roi.y1 - .46):
            candidate = Roi(max(0, roi.x1 + shift), max(0, top), min(100, roi.x2 + shift), min(100, roi.y2))
            if not candidate.valid(): continue
            crop = crop_percent(image, candidate)
            for variant in (crop, ImageOps.grayscale(crop)):
                raw = read_text(variant, scale=5).casefold().replace("xi", "x8").replace("xb", "x8").translate(str.maketrans({"o": "0", "l": "1", "i": "1"}))
                match = re.search(r"x\s*(\d{1,2})", raw)
                if match:
                    return int(match.group(1))
    return None


def counter_is_one(counter: Image.Image) -> bool:
    """Match both glyphs of x1; Windows OCR drops this short selected token.

    Templates are white lettering from the confirmed 1920x1080 game capture,
    normalised to 12x20. Require separate adjacent x and 1 components; a visual
    change or an arbitrary narrow mark never counts as a remaining troop.
    """
    templates = (
        "011100001110011100001111011110011110011110011110011111111110011111111100001111111100001111111100001111111000000111110000000111110000001111111000001111111100001111111100011111111100011110011110111110011110111100011110111100001110011000000000",
        "000000000110111111111111111111111111111111111111111111111111001111111111001111111111001111111100001111111100000111111100000111111100000111111100000111111100000111111100000111111100000111111100000111111100000111111100000111111100000111111000",
    )
    mask = white_text_mask(counter)
    pixels = mask.load()
    pending = {(x, y) for y in range(mask.height) for x in range(mask.width) if pixels[x, y] == 0}
    glyphs = []
    while pending:
        seed = pending.pop()
        stack, component = [seed], [seed]
        while stack:
            x, y = stack.pop()
            for neighbour in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if neighbour in pending:
                    pending.remove(neighbour); stack.append(neighbour); component.append(neighbour)
        xs, ys = zip(*component)
        box = min(xs), min(ys), max(xs)+1, max(ys)+1
        w, h = box[2]-box[0], box[3]-box[1]
        if h < counter.height * .2 or h > counter.height * .8 or not .2 <= w/h <= 1.2:
            continue
        bits = tuple(v < 128 for v in mask.crop(box).resize((12,20)).get_flattened_data())
        scores = [sum(bit != (ref == '1') for bit, ref in zip(bits, template))/240 for template in templates]
        glyphs.append((box, scores))
    for left, ls in glyphs:
        for right, rs in glyphs:
            if (ls[0] < .15 and rs[1] < .15 and
                    0 <= right[0]-left[2] <= (left[3]-left[1])*.5 and
                    abs(right[3]-left[3]) <= (left[3]-left[1])*.3):
                return True
    return False


def troop_counter_visually_changed(before: Image.Image, after: Image.Image, label: str) -> bool:
    """Diagnostic only: a visual change does not prove a numeric decrement."""
    roi = layout_roi("TROOP_COUNTER_INK_ROIS", label)
    width, height = before.size
    if after.size != before.size:
        return False
    x = round(width * roi.x1 / 100)
    y = round(height * roi.y1 / 100)
    w = round(width * (roi.x2 - roi.x1) / 100)
    h = round(height * (roi.y2 - roi.y1) / 100)
    # The army bar moves a few pixels when spell and hero controls appear.
    # Match the same white lettering after a small translation first.
    before_rgb, after_rgb = before.convert("RGB"), after.convert("RGB")
    def ink(image, left, top):
        card = image.crop((left, top, left + w, top + h))
        return tuple(min(pixel) > 200 for pixel in card.get_flattened_data())
    original = ink(before_rgb, x, y)
    differences = (
        sum(a != b for a, b in zip(original, ink(after_rgb, x + dx, y + dy)))
        for dx in range(-max(1, round(width * .16 / 100)), max(1, round(width * .16 / 100)) + 1)
        for dy in range(-max(1, round(height * .75 / 100)), max(1, round(height * .75 / 100)) + 1)
    )
    return min(differences) > round(w * h * .05)


def shifted_roi(roi: Roi, shift: float) -> Roi:
    return Roi(roi.x1 + shift, roi.y1, roi.x2 + shift, roi.y2)


def hero_layout_shift(image: Image.Image) -> float:
    """The siege slot may be absent; locate the king card before hero clicks."""
    overrides = getattr(getattr(_operation, "settings", None), "layout_overrides", {})
    if all(f"{group}.{index}" in overrides for group in ("HERO_SLOTS", "HERO_HEALTH_ROIS", "HERO_ICON_ROIS") for index in range(3)):
        return 0.0  # Explicit calibrated slots/regions already include the shift.
    def skin_pixels(roi):
        pixels = crop_percent(image, roi).convert("RGB").get_flattened_data()
        return sum(r > 140 and 75 < g < 210 and b < 110 and r > g * 1.12 and g > b * 1.2 for r, g, b in pixels)
    compact = skin_pixels(layout_roi("SCREEN_ROIS", "hero_compact"))
    expanded = skin_pixels(layout_roi("SCREEN_ROIS", "hero_expanded"))
    area_scale = image.width * image.height / (1920 * 1080)
    if max(compact, expanded) < 1_000 * area_scale or abs(compact - expanded) < 350 * area_scale:
        raise RuntimeError("Position des héros incertaine dans la barre d'armée.")
    return -6.25 if compact > expanded else 0.0


def hero_health_visible(image: Image.Image, index: int, shift: float = 0) -> bool:
    crop = crop_percent(image, hero_region("HERO_HEALTH_ROIS", index, shift)).convert("RGB")
    pixels = crop.load()
    def green(x, y):
        r, g, b = pixels[x, y]
        return g > 180 and g > r * 1.4 and g > b * 1.3
    # Grass behind an unraised hero card used to count as a health bar.
    # Require a bright horizontal fill, aligned with the card's left side,
    # at least two rows thick and immediately underneath a dark frame.
    for y in range(2, crop.height - 1):
        start = None
        for x in range(crop.width + 1):
            if x < crop.width and green(x, y):
                if start is None: start = x
                continue
            if start is not None:
                length = x - start
                if start <= crop.width * .25 and length >= crop.width * .35:
                    second = sum(green(k, y+1) for k in range(start, x))
                    border = max(sum(max(pixels[k, row]) < 100 for k in range(start, x))
                                 for row in range(max(0, y-7), y))
                    if second >= length * .8 and border >= length * .6:
                        return True
                start = None
    return False


def hero_icon_saturation(image: Image.Image, index: int, shift: float = 0) -> float:
    icon = crop_percent(image, hero_region("HERO_ICON_ROIS", index, shift)).convert("HSV").getchannel(1)
    return ImageStat.Stat(icon).mean[0]


def hero_placeholder_slot(image: Image.Image, index: int, shift: float = 0) -> bool:
    """Recognize the repeated pale dashes at an empty hero-card border."""
    roi = hero_region("HERO_ICON_ROIS", index, shift)
    x = min(image.width - 1, round(image.width * (roi.x1 + .5) / 100))
    top = round(image.height * roi.y1 / 100)
    bottom = round(image.height * (roi.y2 - 1.1) / 100)
    pixels = image.convert("RGB").load()
    runs = []
    length = 0
    for y in range(top, bottom):
        color = pixels[x, y]
        dash = min(color) > 120 and max(color) - min(color) < 35
        if dash:
            length += 1
        elif length:
            runs.append(length)
            length = 0
    if length:
        runs.append(length)
    shortest = max(3, round(image.height * 5 / 1080))
    longest = max(shortest, round(image.height * 12 / 1080))
    return sum(shortest <= run <= longest for run in runs) >= 5


def hero_region(group, index, shift):
    overrides = getattr(getattr(_operation, "settings", None), "layout_overrides", {})
    roi = layout_roi(group, index)
    return roi if f"{group}.{index}" in overrides else shifted_roi(roi, shift)


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


def battle_result_return_ready(image: Image.Image) -> bool:
    button = crop_percent(image, Roi(38, 80, 62, 95))
    return any("rentrer" in read_text(button, scale=scale).casefold() for scale in (2, 3))


def village_home_ready(image: Image.Image) -> bool:
    if connection_retry_point(image) is not None:
        return False
    # The full-screen OCR pass is unreliable on the reduced VM capture. Read
    # the two fixed village controls independently and accept the same
    # tolerant prefixes used by has_screen_text.
    left_roi = crop_percent(image, Roi(0, 82, 20, 100))
    right_roi = crop_percent(image, Roi(85, 82, 100, 100))
    left = normalized_screen_text(left_roi)
    right = normalized_screen_text(right_roi)
    left_raw = ' '.join(read_text(left_roi, scale=scale).casefold() for scale in (1, 2, 3))
    right_raw = ' '.join(read_text(right_roi, scale=scale).casefold() for scale in (1, 2, 3))
    return ("attaquer" in left or "attaqu" in left or "attaqu" in left_raw) and ("magasin" in right or "magasi" in right or "magasi" in right_raw)


@dataclass(frozen=True)
class GameWindow:
    hwnd: int; title: str; width: int; height: int


@dataclass(frozen=True)
class ClientGeometry:
    width: int
    height: int
    offset_x: int
    offset_y: int
    outer_width: int
    outer_height: int


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
        # Never silently switch accounts when the selected window disappears.
        if title:
            return next((w for w in windows if w.title == title), None)
        return next((w for w in windows if w.title.casefold().startswith("clash of clans")), None)

    @staticmethod
    def client_geometry(window: GameWindow) -> ClientGeometry:
        hwnd = wintypes.HWND(window.hwnd)
        if not USER32.IsWindow(hwnd) or USER32.IsIconic(hwnd):
            raise RuntimeError("Fenêtre Clash fermée ou réduite.")
        outer, client, origin = wintypes.RECT(), wintypes.RECT(), wintypes.POINT(0, 0)
        if not (USER32.GetWindowRect(hwnd, ctypes.byref(outer))
                and USER32.GetClientRect(hwnd, ctypes.byref(client))
                and USER32.ClientToScreen(hwnd, ctypes.byref(origin))):
            raise RuntimeError("Dimensions de la fenêtre Clash indisponibles.")
        geometry = ClientGeometry(client.right - client.left, client.bottom - client.top,
                                  origin.x - outer.left, origin.y - outer.top,
                                  outer.right - outer.left, outer.bottom - outer.top)
        if (geometry.width <= 0 or geometry.height <= 0 or geometry.offset_x < 0 or geometry.offset_y < 0
                or geometry.offset_x + geometry.width > geometry.outer_width
                or geometry.offset_y + geometry.height > geometry.outer_height):
            raise RuntimeError("Zone de jeu invalide.")
        return geometry

    @staticmethod
    def capture(window: GameWindow) -> Image.Image:
        check_cancelled()
        hwnd = wintypes.HWND(window.hwnd)
        geometry = WindowDriver.client_geometry(window)
        width, height = geometry.outer_width, geometry.outer_height
        source_dc = USER32.GetWindowDC(hwnd); memory_dc = GDI32.CreateCompatibleDC(source_dc); bitmap = GDI32.CreateCompatibleBitmap(source_dc, width, height); previous = GDI32.SelectObject(memory_dc, bitmap)
        try:
            if not USER32.PrintWindow(hwnd, memory_dc, PW_RENDERFULLCONTENT): raise RuntimeError("Google Play Jeux a refusé la capture.")
            info = BitmapInfo(); info.bmiHeader.biSize = ctypes.sizeof(BitmapInfoHeader); info.bmiHeader.biWidth = width; info.bmiHeader.biHeight = -height; info.bmiHeader.biPlanes = 1; info.bmiHeader.biBitCount = 32
            data = ctypes.create_string_buffer(width * height * 4)
            if GDI32.GetDIBits(memory_dc, bitmap, 0, height, data, ctypes.byref(info), 0) != height: raise RuntimeError("Capture Windows incomplète.")
            image = Image.frombuffer("RGB", (width, height), data, "raw", "BGRX", 0, 1).copy()
            image = image.crop((geometry.offset_x, geometry.offset_y,
                                geometry.offset_x + geometry.width, geometry.offset_y + geometry.height))
            if image.convert("L").getextrema() == (0, 0): raise RuntimeError("Capture noire : Google Play Jeux n'expose pas son rendu en arrière-plan.")
            if WindowDriver.client_geometry(window) != geometry:
                raise RuntimeError("Fenêtre redimensionnée pendant la capture : relancer la lecture.")
            _operation.last_capture = (window.hwnd, geometry)
            check_cancelled()
            return image
        finally:
            GDI32.SelectObject(memory_dc, previous); GDI32.DeleteObject(bitmap); GDI32.DeleteDC(memory_dc); USER32.ReleaseDC(hwnd, source_dc)

    @staticmethod
    def zoom_out_step(window: GameWindow) -> bool:
        check_cancelled()
        geometry = WindowDriver.client_geometry(window)
        if getattr(_operation, "last_capture", None) != (window.hwnd, geometry):
            raise RuntimeError("Fenêtre modifiée avant le dézoom : commande annulée.")
        # WM_MOUSEWHEEL uses screen coordinates, unlike WM_LBUTTONDOWN.
        point = wintypes.POINT(geometry.width // 2, geometry.height // 2)
        if not USER32.ClientToScreen(window.hwnd, ctypes.byref(point)):
            raise RuntimeError("Position du jeu indisponible pour le dézoom.")
        coordinates = ((point.y & 0xFFFF) << 16) | (point.x & 0xFFFF)
        check_cancelled()
        return bool(USER32.PostMessageW(window.hwnd, 0x020A, ((-120 & 0xFFFF) << 16), coordinates))

    @staticmethod
    def scroll_menu(window, x=50, y=48, delta=-120):
        check_cancelled()
        geometry = WindowDriver.client_geometry(window)
        if getattr(_operation, 'last_capture', None) != (window.hwnd, geometry):
            raise RuntimeError('Fenêtre modifiée avant le défilement.')
        point = wintypes.POINT(round(geometry.width*x/100),round(geometry.height*y/100))
        if not USER32.ClientToScreen(window.hwnd,ctypes.byref(point)):
            raise RuntimeError('Position de la liste indisponible.')
        return bool(USER32.PostMessageW(window.hwnd,0x020A,((delta & 0xFFFF)<<16),
                                       ((point.y & 0xFFFF)<<16)|(point.x & 0xFFFF)))

    @staticmethod
    def click_percent(window: GameWindow, x: float, y: float) -> bool:
        check_cancelled()
        geometry = WindowDriver.client_geometry(window)
        if getattr(_operation, "last_capture", None) != (window.hwnd, geometry):
            raise RuntimeError("Fenêtre modifiée depuis la lecture : aucun clic envoyé. Relancer le bot.")
        settings = getattr(_operation, "settings", None)
        if settings and abs(geometry.width / geometry.height / settings.layout_aspect_ratio - 1) > .02:
            raise RuntimeError("Format de fenêtre différent du calibrage : utiliser Calibrer avant de relancer.")
        if not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= 100 and 0 <= y <= 100):
            raise ValueError("Coordonnées de clic invalides.")
        px, py = min(geometry.width - 1, round(geometry.width * x / 100)), min(geometry.height - 1, round(geometry.height * y / 100))
        lp = (py << 16) | (px & 0xFFFF)
        check_cancelled()
        pressed = USER32.PostMessageW(window.hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp)
        # Always release a pressed button, including a stop requested mid-click.
        released = USER32.PostMessageW(window.hwnd, WM_LBUTTONUP, 0, lp)
        return bool(pressed and released)


def crop_percent(image: Image.Image, roi: Roi) -> Image.Image:
    if not roi.valid(): raise ValueError("Zone de lecture invalide.")
    return image.crop((round(image.width * roi.x1 / 100), round(image.height * roi.y1 / 100), round(image.width * roi.x2 / 100), round(image.height * roi.y2 / 100)))


async def _ocr_file(path: str) -> str:
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage import FileAccessMode, StorageFile
    stream = await (await StorageFile.get_file_from_path_async(path)).open_async(FileAccessMode.READ)
    bitmap = None
    try:
        bitmap = await (await BitmapDecoder.create_async(stream)).get_software_bitmap_async()
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None: raise RuntimeError("OCR Windows indisponible.")
        return (await engine.recognize_async(bitmap)).text
    finally:
        if bitmap is not None: bitmap.close()
        stream.close()


async def _ocr_words_file(path: str) -> list[tuple[str, float, float]]:
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage import FileAccessMode, StorageFile

    stream = await (await StorageFile.get_file_from_path_async(path)).open_async(FileAccessMode.READ)
    bitmap = None
    try:
        bitmap = await (await BitmapDecoder.create_async(stream)).get_software_bitmap_async()
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None: raise RuntimeError("OCR Windows indisponible.")
        result = await engine.recognize_async(bitmap)
        return [(word.text, word.bounding_rect.x + word.bounding_rect.width / 2, word.bounding_rect.y + word.bounding_rect.height / 2)
                for line in result.lines for word in line.words]
    finally:
        if bitmap is not None: bitmap.close()
        stream.close()


def read_word_centers(image: Image.Image) -> list[tuple[str, float, float]]:
    check_cancelled()
    trace_ocr("mots demandés", image, 1)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as file: path = Path(file.name)
    try:
        image.save(path)
        words = [(word, x * 100 / image.width, y * 100 / image.height)
                 for word, x, y in asyncio.run(bounded_ocr(_ocr_words_file(str(path))))]
        trace_ocr("mots lus", image, 1, words)
        return words
    finally: path.unlink(missing_ok=True)


def trace_ocr(step, image, scale, result=None):
    journal = getattr(_operation, "journal", None)
    if journal is not None:
        details = {"étape": step, "taille": [image.width,image.height], "agrandissement": scale}
        if result is not None:
            details["lecture"] = result
        journal.record("OCR", json.dumps(details, ensure_ascii=False))


def _collector_reference(resource):
    with Image.open(ASSET_DIR / f"collector_{resource}.png") as asset:
        return asset.convert("RGB")


def _collector_score(pixels, x, y, samples):
    return sum(sum(abs(a - b) for a, b in zip(rgb, pixels[x + dx, y + dy]))
               for dx, dy, rgb in samples) / (len(samples) * 3)


def find_collectible_icons(image: Image.Image):
    """Locate the gold/elixir bubbles over village collectors, excluding dark elixir."""
    normal = image.convert("RGB").resize((1920, 1080), Image.Resampling.BILINEAR)
    pixels = normal.load()
    found = []

    def pale_border(rgb):
        r, g, b = rgb
        return 145 < r < 245 and r - 17 < g < r + 26 and 75 < b < r - 17

    for resource in ("gold", "elixir"):
        reference = _collector_reference(resource).load()
        samples = [(dx, dy, reference[dx + 14, dy + 14])
                   for dx in range(-14, 15, 4) for dy in range(-14, 15, 4)]
        coarse = samples[::4]
        for y in range(80, 900, 4):
            for x in range(192, 1720, 4):
                r, g, b = pixels[x, y]
                center = (r > 170 and g > 110 and b < 110) if resource == "gold" else (
                    r > 130 and b > 120 and g < 130 and r > g * 1.35 and b > g * 1.3)
                if not center:
                    continue
                if not (any(pale_border(pixels[x - 18 + shift, y]) for shift in (-4, 0, 4))
                        and any(pale_border(pixels[x + 18 + shift, y]) for shift in (-4, 0, 4))):
                    continue
                if _collector_score(pixels, x, y, coarse) > 80:
                    continue
                score, point = min((_collector_score(pixels, x + dx, y + dy, samples), (x + dx, y + dy))
                                   for dy in range(-4, 5) for dx in range(-4, 5))
                if score < 34 and not any(kind == resource and abs(point[0] - px) < 25 and abs(point[1] - py) < 25
                                          for kind, px, py, _ in found):
                    found.append((resource, *point, score))
    return sorted(found, key=lambda icon: icon[3])


def collectible_icon_still_visible(image, resource, x, y):
    normal = image.convert("RGB").resize((1920, 1080), Image.Resampling.BILINEAR)
    reference = _collector_reference(resource)
    template = reference.load()
    samples = [(dx, dy, template[dx + 14, dy + 14])
               for dx in range(-14, 15, 4) for dy in range(-14, 15, 4)]
    pixels = normal.load()
    return min(_collector_score(pixels, x + dx, y + dy, samples)
               for dx in (-2, 0, 2) for dy in (-2, 0, 2)) < 38


def wall_menu_row_matches(image,y):
    # The builder menu is translucent: a village label visible through it
    # is not a menu row. Require its green upgrade tag and the row caption.
    for tag_roi, label_roi in ((Roi(39.3,y-1.4,40.9,y+1.4), Roi(41.1,y-1.4,50,y+1.4)),
                               (Roi(38.0,y-1.4,39.05,y+1.4), Roi(39.6,y-1.4,50.5,y+1.4))):
        pixels=list(crop_percent(image,tag_roi).convert("RGB").get_flattened_data())
        if sum(g>100 and g>r*1.2 and g>b*1.4 for r,g,b in pixels)<len(pixels)*.2:
            continue
        crop=crop_percent(image,label_roi)
        for scale in (2,1):
            text=read_text(crop,scale=scale).casefold().strip(" .,:;!'\"")
            if text.startswith(("rempar","rempamt")):
                return True
    return False


def find_wall_menu_item(image: Image.Image) -> tuple[float, float] | None:
    rows = find_wall_menu_items(image)
    return rows[0] if rows else None


def find_wall_menu_items(image: Image.Image) -> list[tuple[float, float]]:
    """Return each visible wall row after checking its menu tag and caption."""
    menu_roi = layout_roi("SCREEN_ROIS", "wall_menu")
    menu = crop_percent(image, menu_roi)
    candidates = []
    for scale in (1,2):
        for word, x, y in read_word_centers(menu.resize((menu.width*scale,menu.height*scale))):
            if word.casefold().startswith(("rempar", "rempamt")) and x < 65:
                point=(menu_roi.x1 + x * (menu_roi.x2 - menu_roi.x1) / 100,
                       menu_roi.y1 + y * (menu_roi.y2 - menu_roi.y1) / 100)
                if wall_menu_row_matches(image,point[1]):
                    candidates.append(point)
    # Full-list OCR can miss a row even when its narrow caption is readable.
    for y in range(math.ceil(menu_roi.y1 + 5), math.floor(menu_roi.y2 - 2)):
        if any(abs(y - point[1]) < 1.5 for point in candidates):
            continue
        if wall_menu_row_matches(image, y):
            candidates.append((44.0, float(y)))
    rows = []
    for point in sorted(candidates, key=lambda point: point[1]):
        if not rows or point[1] - rows[-1][1] >= 1.5:
            rows.append(point)
    return rows


def builders_menu_open(image: Image.Image) -> bool:
    # The menu can be scrolled past its heading. Both pale vertical borders
    # remain visible and distinguish its rows from labels in the village.
    rgb=image.convert("RGB")
    for xs, ys, brightness, spread in (((38.65,63.45),range(15,61),140,60),
                                       ((36.85,65.15),range(13,63),130,70)):
        borders=[]
        for x in xs:
            hits=0
            for y in ys:
                px,py=round(image.width*x/100),round(image.height*y/100)
                pixels=[rgb.getpixel((max(0,min(image.width-1,px+dx)),py)) for dx in (-1,0,1)]
                hits+=any(min(p)>brightness and max(p)-min(p)<spread for p in pixels)
            borders.append(hits/len(ys))
        if min(borders)>.8:
            return True
    for roi in (layout_roi("SCREEN_ROIS", "builders_menu"), layout_roi("SCREEN_ROIS", "wall_menu")):
        text = read_text(crop_percent(image, roi), scale=2).casefold()
        if "disponible" in text or "amélioration" in text or re.search(r"rempar\w*\s*x\s*\d+", text):
            return True
    return False


def read_wall_available(image: Image.Image, item: tuple[float, float]) -> int | None:
    x, y = item
    values = []
    # Keep each read inside one row: adjacent wall entries can have different counts.
    for height in (1.4, 1.8):
        roi = Roi(max(0, x - 4), max(0, y - height), min(100, x + 9), min(100, y + height))
        raw = read_text(crop_percent(image, roi), scale=2).casefold().translate(str.maketrans({"l": "1", "i": "1", "g": "6", "s": "5", "o": "0", "b": "8"}))
        match = re.search(r"x\s*(\d{1,3})", raw)
        if match: values.append(int(match.group(1)))
        elif raw.strip(" .,:;!'\"") in ("rempart", "rempamt"):
            values.append(1)  # The game omits x1 on the last wall row.
    return max(values) if values else None


def find_wall_remove_button(image, shift=0):
    roi=shifted_roi(Roi(25,80,44,87),shift)
    matches=[]
    for text,x,y in read_word_centers(crop_percent(image,roi)):
        if text.casefold().strip('.,:')=='supprimer':
            matches.append((roi.x1+x*(roi.x2-roi.x1)/100,roi.y1+y*(roi.y2-roi.y1)/100))
    return matches[0] if len(matches)==1 else None


def wall_selected(image: Image.Image) -> bool:
    return find_wall_more_button(image) is not None


def find_wall_more_button(image: Image.Image):
    # A wall-ring button changes the entire row's horizontal alignment.
    # Locate the actual "Améliorer plus" label instead of clicking its old slot.
    roi = layout_roi("SCREEN_ROIS", "wall_actions")
    labels = Roi(roi.x1, roi.y1 + (roi.y2-roi.y1)*.7, roi.x2, roi.y2 - (roi.y2-roi.y1)*.05)
    for region, masked in ((labels, False), (Roi(20,79,80,87), False), (roi, True)):
        crop = crop_percent(image, region)
        if masked:
            crop = white_text_mask(crop).crop((8, 8, crop.width + 8, crop.height + 8))
        for scale in (2,1,3):
            for text, x, y in read_word_centers(crop.resize((crop.width * scale, crop.height * scale))):
                text = unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode().strip(".,:!")
                if text in ("plus", "pluse", "plvs", "p1us", "pius"):
                    return (region.x1 + x * (region.x2 - region.x1) / 100,
                            region.y1 + y * (region.y2 - region.y1) / 100)
    return None


def wall_multi_mode(image: Image.Image) -> bool:
    crop = white_text_mask(crop_percent(image, layout_roi("SCREEN_ROIS", "wall_actions")))
    text = ' '.join(read_text(crop, scale=scale).casefold() for scale in (1, 2, 3))
    if "remp" in text and any(token in text for token in ("aj", "aiou", "supp", "rimer")):
        return True
    # On the VM the stylised button labels are often returned as separate
    # words (AMéli0ReR / 1ReMpaRt) and the full-line OCR above misses them.
    # A wall row plus one add/remove label is enough to identify the batch
    # panel; prices are still independently verified before any click.
    crop = crop_percent(image, layout_roi("SCREEN_ROIS", "wall_actions"))
    labels = [word for word, _x, _y in read_word_centers(crop)]
    words = [re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode().casefold().replace("0", "o").replace("1", "l")) for word in labels]
    return any(word.startswith(("amelio", "ameiio")) for word in words) and any(
        word.startswith(("remp", "ajout", "aiout", "sup")) for word in words)


def wall_price_readings(image, expected=None):
    readings = []
    for variant in (image, white_text_mask(image)):
        for scale in (2, 3):
            raw = (read_text(variant, scale=scale).strip(" +.,'\"*[]()")
                   .translate(str.maketrans({'O':'0','o':'0','I':'1','l':'1','B':'8','S':'5','s':'5'})))
            if re.fullmatch(r"\d[\d\s]*", raw):
                value=int(re.sub(r"\s", "", raw))
                if 0 < value <= 20_000_000:
                    readings.append(value)
            elif expected is not None and re.fullmatch(r"[sS][\d\s]*",raw):
                # The first 6 in the game's wall-price font is sometimes
                # read as s. Use this only when the amount after a confirmed
                # +1 click is already known from the previous unit price.
                for digit in ('5','6'):
                    if int(re.sub(r"\s", "", digit+raw[1:])) == expected:
                        readings.append(expected)
                        break
    return readings


def wall_group_controls(image, single=False, expected_price=None, expected_resource=None):
    """Locate the controls in the current row; never reuse a row offset.

    The +10 button disappears for small remaining groups and every other
    button moves. Resource icons distinguish gold/elixir from wall rings.
    """
    from upgrades import normal, resource_icon
    if single:
        heading = crop_percent(image,Roi(30,68,70,74))
        if not has_all_screen_text(heading,"rempart","niveau"):
            return None
    elif not wall_multi_mode(image):
        return None
    roi = Roi(20,81,80,87)
    crop = crop_percent(image, roi)
    adds, removes, upgrades = [], [], []
    for scale in (2,1,3):
        words = read_word_centers(crop.resize((crop.width*scale,crop.height*scale)))
        for text, x, y in words:
            label = re.sub(r'[^a-z]', '', normal(text).replace('0','o').replace('1','l'))
            x, y = roi.x1+x*.6, roi.y1+y*.06
            target = None
            if label.startswith(('ajout','aiout')):
                target = adds
            elif label.startswith('sup') and ('rim' in label or 'prim' in label):
                target = removes
            elif label.startswith(('amelio','ameiio','amelioa','ameiioa')):
                target = upgrades
            elif 50 <= x <= 75 and len(label) >= 6 and label.startswith(('am','ak','apa')):
                # Reduced VM OCR can lose the accented middle of
                # AMÉLIORER (for example "Ak�Ii0ReR"). Its position is still
                # constrained to the payment-card labels and the price/icon
                # checks below remain authoritative.
                target = upgrades
            if target is not None and not any(abs(px-x)<.5 for px,py in target):
                target.append((x,y))
    payments = {}
    for x,y in upgrades:
        # The third card is dark elixir / magic and is not a supported wall
        # payment. Ignore it before applying the gold/elixir icon fallback.
        if x >= 67:
            continue
        resource = resource_icon(image,Roi(x+2,y-9.2,x+3.7,y-6.4))
        # The small gold coin is frequently lost by OCR when the card is on
        # top of village scenery. The two payment cards have fixed order in
        # this panel, and the upgrade label itself was already detected, so
        # use its x position only as an icon fallback. The price is still
        # independently read and verified below.
        if resource is None:
            resource = 'or' if x < 58 else 'élixir'
        if resource is None:
            continue
        readings = []
        price_crops = []
        # Seven-digit prices extend left of the tight crops. Try the full
        # button label first so 1 200 000 is not accepted as 200 000.
        for price_roi in (Roi(x-3.6,y-9.5,x+2.1,y-6.2), Roi(x-4.9,y-9.5,x+2.1,y-5.9),
                          Roi(x-5.1,y-9.4,x+2.3,y-6.0), Roi(x-3,y-8.7,x+2.1,y-6.7),
                          Roi(x-2.7,75,x+2.1,77)):
            price_crop = crop_percent(image,price_roi)
            price_crops.append(price_crop)
            expected = expected_price if resource == expected_resource else None
            readings.extend(wall_price_readings(price_crop,expected))
        agreed = [value for value in set(readings) if readings.count(value) >= 2]
        price = max(agreed) if agreed else None
        if price is None and readings:
            # One crop can lose the leading digit while another contains the
            # complete amount. Prefer the expected total when available;
            # otherwise the largest valid reading is the complete card value.
            price = (min(readings, key=lambda value: abs(value - expected_price))
                     if expected_price is not None else max(readings))
        # A lone larger OCR artifact must not overrule repeated complete
        # readings (600 000 can coexist with one spurious 6 601 000).
        if price is None and not readings:
            for price_crop in price_crops:
                price = read_result_amount(price_crop,main_result=True)
                if price is not None:
                    break
        if price is not None and expected_price is not None and abs(price - expected_price) <= 150_000:
            # The VM OCR occasionally drops a leading/inner digit on a large
            # seven digit card. Once the expected total is derived from a
            # confirmed unit price and the +1/+10 action, snap only a close
            # reading to that exact total.
            price = expected_price
        if price is not None and price > 0:
            if resource in payments:
                return None
            payments[resource] = ((x,y-3),price)
    # Gold and elixir use the same wall unit price. When the gold amount is
    # obscured by the village background, OCR can still resolve the button
    # label and the elixir card. Reconstruct only the missing fixed-position
    # peer from that confirmed price; the final confirmation and reserve
    # delta remain mandatory before spending.
    if len(payments) == 1:
        known_resource, (_point, known_price) = next(iter(payments.items()))
        for x, y in upgrades:
            if x < 58 and 'or' not in payments:
                payments['or'] = ((x, y - 3), known_price)
            elif 58 <= x < 67 and 'élixir' not in payments:
                payments['élixir'] = ((x, y - 3), known_price)
    if expected_price is not None and expected_resource in payments:
        # Both supported wall cards use the same total. If OCR returned a
        # clearly truncated peer (for example 3 000 000 beside 9 000 000),
        # retain its detected button position but align its amount to the
        # expected total so the final payment lookup remains deterministic.
        for peer in ('or', 'élixir'):
            if peer in payments and abs(payments[peer][1] - expected_price) <= 6_000_000:
                if payments[peer][1] != expected_price:
                    payments[peer] = (payments[peer][0], expected_price)
        point, observed = payments[expected_resource]
        peer_confirms = any(resource != expected_resource and value[1] == expected_price
                            for resource, value in payments.items())
        if peer_confirms and str(observed) == f"{expected_price}1":
            # A card-edge pixel can be OCR'd as a final 1. The other payment
            # card and the prior confirmed unit cost must agree first.
            payments[expected_resource] = (point, expected_price)
    if payments:
        if single:
            return {'add':None, 'remove':None, 'payments':payments}
        # The +1 card sits one card left of the gold payment (two left of
        # elixir). OCR may see only +10, especially when that card is greyed
        # out; choosing the rightmost OCR hit would then click +10 again.
        if 'or' in payments:
            payment_x,payment_y=payments['or'][0]
            add_x=payment_x-8.2
        elif 'élixir' in payments:
            payment_x,payment_y=payments['élixir'][0]
            add_x=payment_x-16.4
        else:
            return None
        add_y=payment_y-.9
        plus_pixels=list(crop_percent(image,Roi(add_x-1.5,add_y-3.8,add_x+1.5,add_y+1.2)).convert('RGB').get_flattened_data())
        active_plus=sum(g>110 and g>r*1.25 and g>b*1.3 for r,g,b in plus_pixels)
        if active_plus < len(plus_pixels)*.06:
            return None
        remove = (removes[0][0],removes[0][1]-3) if len(removes)==1 else None
        # When both add cards are visible, the leftmost one is +10 and the
        # rightmost one is +1. Keep both coordinates so large payable batches
        # do not require one OCR round-trip per wall.
        add_ten = None
        if adds:
            # The +10 card is left of +1. OCR often merges both "Ajouter"
            # labels into one word, so keep the calibrated card center as a
            # fallback; it is used only when the payable batch is at least
            # ten walls, where the card is present and enabled.
            left = min(adds, key=lambda point: point[0])
            add_ten = (min(left[0], 37.8), left[1] - 3)
        return {'add':(add_x,add_y), 'add_ten':add_ten, 'remove':remove, 'payments':payments}
    return None


def single_wall_confirmation_matches(image,total,resource):
    from upgrades import resource_icon
    heading=crop_percent(image,Roi(15,3,85,10))
    prices=[]
    for scale in (2,3):
        raw=read_text(crop_percent(image,Roi(64,85,74,89)),scale=scale).casefold().translate(str.maketrans({'s':'5','o':'0','l':'1'}))
        if re.fullmatch(r"[0-9\s]+",raw.strip()):
            prices.append(int(re.sub(r"\s","",raw)))
    price=prices[0] if len(prices)==2 and prices[0]==prices[1] else None
    return (has_all_screen_text(heading,"rempart","niveau") and price==total and
            resource_icon(image,Roi(74.5,85.5,77.5,92))==resource)


def wall_batch_confirmation_matches(image: Image.Image, total: int, resource: str) -> bool:
    text = read_text(crop_percent(image, layout_roi("SCREEN_ROIS", "wall_confirmation")), scale=2).casefold()
    amount = re.search(r"pour\s*([\d\s]+)", text)
    payment = "lixir" if resource == "élixir" else "or"
    ok = read_text(crop_percent(image, layout_roi("SCREEN_ROIS", "wall_confirmation_ok")), scale=2).casefold()
    return bool("rempart" in text and amount and parse_clash_number(amount.group(1)) == total and payment in text[amount.end():] and "ok" in ok)


def read_number(image: Image.Image) -> int | None:
    check_cancelled()
    trace_ocr("nombre demandé", image, 3)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as file: path = Path(file.name)
    try:
        image.resize((image.width * 3, image.height * 3)).save(path)
        raw = asyncio.run(bounded_ocr(_ocr_file(str(path))))
        digits = re.sub(r"[^0-9]", "", raw)
        trace_ocr("nombre lu", image, 3, {"brut":raw,"valeur":int(digits) if digits else None})
        return int(digits) if digits else None
    finally: path.unlink(missing_ok=True)


def read_text(image: Image.Image, scale: int = 5) -> str:
    """OCR a local UI crop while keeping the raw reading for diagnostics."""
    check_cancelled()
    trace_ocr("texte demandé", image, scale)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as file: path = Path(file.name)
    try:
        image.resize((image.width * scale, image.height * scale)).save(path)
        result = asyncio.run(bounded_ocr(_ocr_file(str(path)))).strip()
        trace_ocr("texte lu", image, scale, result)
        return result
    finally: path.unlink(missing_ok=True)


def parse_clash_number(text: str) -> int | None:
    # Windows OCR occasionally reads the stylised level digits as letters.
    digits = re.sub(r"[^0-9]", "", text.translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "i": "1", "Z": "7", "z": "7", "S": "5", "s": "5", "B": "8", "E": "3"})))
    return int(digits) if digits else None


def read_resource_number(image: Image.Image) -> tuple[int | None, str]:
    """Try normal and high-contrast OCR; keep the most complete valid amount."""
    normal = read_text(image)
    binary = read_text(white_text_mask(image), scale=3)
    candidates = [(parse_clash_number(raw), raw) for raw in (binary, normal)]
    valid = [(value, raw) for value, raw in candidates if value is not None and value <= 20_000_000]
    # The mask can lose a thin leading 1. Do not replace a complete reading
    # with its truncated suffix merely because it came from the mask.
    if valid:
        return max(valid, key=lambda reading: reading[0])
    # Different font sizes/backgrounds can defeat both original OCR passes.
    # On the live 1323x744 client the gold row is occasionally read as
    # ``il 447=585`` at scale 2/3 and correctly as ``1 447 585`` at scale 4.
    # Include the intermediate scales and reject a spurious leading OCR digit
    # when the candidates differ by an order of magnitude.
    scaled_values = []
    for scale in (2, 3, 4):
        raw = read_text(image, scale=scale)
        value = parse_clash_number(raw)
        if value is not None and value <= 20_000_000:
            scaled_values.append((value, raw))
    if scaled_values:
        values = [value for value, _ in scaled_values]
        if max(values) >= min(values) * 3:
            return min(scaled_values, key=lambda reading: reading[0])
        return max(scaled_values, key=lambda reading: reading[0])

    # Different font sizes/backgrounds can defeat all OCR passes.
    values = []
    for variant in (image, white_text_mask(image)):
        for scale in (1,2,4):
            raw = read_text(variant, scale=scale)
            cleaned = raw.strip().translate(str.maketrans({"o":"0", "O":"0", "l":"1", "I":"1"}))
            if re.fullmatch(r"[0-9\s]+", cleaned):
                value = int(re.sub(r"\s", "", cleaned))
                if value <= 20_000_000:
                    values.append(value)
                    if values.count(value) >= 2:
                        return value, raw
    return None, normal


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


def read_laboratory_ratio(image: Image.Image, raw: str) -> str | None:
    ratio = parse_worker_ratio(raw)
    if ratio or "PROFILE_ROIS.laboratory_builders" in getattr(getattr(_operation, "settings", None), "layout_overrides", {}):
        return ratio
    # The tiny 1/1 is skipped on some village backgrounds. Place only its
    # white glyphs next to a label so Windows OCR can resolve the slash.
    ink = white_text_mask(crop_percent(image, Roi(39.3, 2.7, 42.7, 6.7)))
    bounds = ImageOps.invert(ink.convert("L")).getbbox()
    if not bounds:
        return None
    ink = ink.crop(bounds)
    ink = ink.resize((round(ink.width * 42 / ink.height), 42))
    context = Image.new("RGB", (400, 90), "white")
    ImageDraw.Draw(context).text((0, 15), "Lab", font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 40), fill="black")
    context.paste(ink, (90, 18))
    return parse_worker_ratio(read_text(context, scale=1))


def read_account_snapshot(image: Image.Image) -> AccountSnapshot:
    raw = {key: read_text(crop_percent(image, layout_roi("PROFILE_ROIS", key))) for key in PROFILE_ROIS}
    from upgrades import builder_count
    builders = builder_count(image, with_total=True)
    return AccountSnapshot(
        account_name=raw["account_name"] or None, level=parse_clash_number(raw["level"]),
        gold=read_safe_reserve(image, "gold"), elixir=read_safe_reserve(image, "elixir"),
        dark_elixir=read_resource_number(crop_percent(image, layout_roi("PROFILE_ROIS", "dark_elixir")))[0],
        gems=parse_clash_number(raw["gems"]),
        laboratory_builders=read_laboratory_ratio(image, raw["laboratory_builders"]),
        builders=f"{builders[0]}/{builders[1]}" if builders is not None else None,
        captured_at=time.time(), raw=raw,
    )


def read_complete_account_snapshot(image: Image.Image, capture) -> AccountSnapshot:
    snapshot = read_account_snapshot(image)
    names = ("account_name", "level", "gold", "elixir", "dark_elixir", "gems",
             "laboratory_builders", "builders")
    for _ in range(2):
        missing = [name for name in names if getattr(snapshot, name) is None]
        if not missing:
            break
        retry = read_account_snapshot(capture())
        snapshot = replace(snapshot, **{name: getattr(retry, name) for name in missing
                                         if getattr(retry, name) is not None})
    return snapshot


def read_enemy_loot(image: Image.Image) -> EnemyLoot:
    readings = {key: read_resource_number(crop_percent(image, layout_roi("ENEMY_LOOT_ROIS", key))) for key in ENEMY_LOOT_ROIS}
    return EnemyLoot(gold=readings["gold"][0], elixir=readings["elixir"][0], dark_elixir=readings["dark_elixir"][0], raw={key: text for key, (_, text) in readings.items()})


def enemy_loot_screen_ready(image: Image.Image) -> bool:
    label = read_text(crop_percent(image, layout_roi("ENEMY_LOOT_LABEL_ROI")), scale=2).casefold()
    if "butin" in label or "disponible" in label or "loot" in label:
        return True
    # The game can render the loot label one row lower while the search
    # animation settles. A full-frame fallback prevents overlooking a ready
    # attack and waiting until the 35 second search deadline.
    full = read_text(image, scale=1).casefold()
    return "butin" in full or "disponible" in full or "fin de la bataille" in full


def daily_reward_open(image: Image.Image) -> bool:
    return has_screen_text(crop_percent(image, layout_roi("SCREEN_ROIS", "daily_reward")), "quotidienne")


def battle_reward_open(image: Image.Image) -> bool:
    for roi in (layout_roi("SCREEN_ROIS", "battle_reward"), Roi(30, 24, 70, 31)):
        heading = read_text(crop_percent(image, roi), scale=2).casefold().replace("0", "o")
        if "choisissez" in heading:
            return True
    return False


def connection_retry_point(image):
    # Observed Google Play Games connection dialog; fast background check
    # avoids an extra OCR pass on every ordinary combat capture.
    if any(max(image.getpixel((round(image.width*x/100),round(image.height*y/100)))[:3])>65
           for x,y in ((29.3,42.5),(70,42.5),(69.5,57.5))):
        return None
    heading=read_text(crop_percent(image,Roi(29,41,71,47)),scale=2).casefold()
    if not re.search(r'connexion\s+perdue',heading):
        # The VM renders the inactivity dialog higher and wider than the
        # original 1080p calibration. Read a generous center band so the
        # reconnect path still sees the message at reduced client sizes.
        message=read_text(crop_percent(image,Roi(25,38,75,55)),scale=2).casefold()
        button=read_text(crop_percent(image,Roi(29,54,71,60)),scale=1).casefold()
        if 'inactivit' in message and 'recharger le jeu' in button:
            return (35,56.2)
        return None
    for text,x,y in read_word_centers(crop_percent(image,Roi(29,54,71,60))):
        label=''.join(c for c in unicodedata.normalize('NFD',text.casefold()) if unicodedata.category(c)!='Mn')
        if label.strip('!?.:')=='reessayer':
            return (29+x*.42,54+y*.06)
    return None


def read_result_amount(image, main_result=False):
    values = []
    variants = []
    if main_result:
        r,g,b = image.convert('RGB').split()
        ink = ImageChops.darker(ImageChops.darker(r,g),b)
        for threshold in (160,180):
            variants.append((ImageOps.expand(ink.point(lambda v:0 if v>threshold else 255),border=12,fill=255),2))
    variants.extend(((image, 2), (image, 3), (white_text_mask(image), 3), (image, 1)))
    for crop, scale in variants:
        raw = read_text(crop, scale=scale).strip(" +.,'\"*")
        raw = raw.translate(str.maketrans({"O": "0", "o": "0", "Ç": "4", "ç": "4"}))
        if re.fullmatch(r"\d[\d\s]*", raw):
            digits = re.sub(r"\s", "", raw)
            if len(digits) > 1 and digits.startswith("0"):
                continue  # A missing leading digit must not become a smaller gain.
            value = int(digits)
            if value <= 20_000_000:
                values.append(value)
                if values.count(value) >= 2:
                    return value
    return None


def read_battle_earnings(image):
    if not has_screen_text(crop_percent(image, Roi(40,24,59,33)), "victoire", "défaite"):
        return None
    rois = (Roi(39,43.5,52.5,49), Roi(39,50,52.5,56), Roi(43,57,52.5,62.5))
    amounts = [read_result_amount(crop_percent(image, roi), main_result=True) for roi in rois]
    # Scenery behind short dark-elixir amounts can erase the leading digits
    # in one crop. Require agreement across distinct crop boundaries.
    dark_readings = [read_result_amount(crop_percent(image,Roi(x,57.3,52.5,61.3)),main_result=True)
                     for x in (41,42,43,44)]
    dark_agreed = [value for value in set(dark_readings) if value is not None and dark_readings.count(value)>=2]
    amounts[2] = dark_agreed[0] if len(dark_agreed)==1 else None
    if None in amounts:
        # A zero-loot defeat omits the dark-elixir row and centres two rows.
        zero_rows = [result_zero_visible(crop_percent(image, roi)) for roi in
                     (Roi(49.8,47,52.5,51.5), Roi(49.8,54.5,52.5,59))]
        if all(zero_rows):
            amounts = [0, 0, 0]
        else:
            return None
    bonus_rois = (Roi(72,49.3,79,52.5), Roi(72,54,79,58), Roi(72,59,79,63))
    # The leading + is sometimes read as 4, turning +30 000 into 430 000.
    # A tighter crop starts inside that sign and can verify the actual digits.
    bonus_inner_rois = (Roi(73,49.4,79,52), Roi(73,54,79,58), Roi(73,59,79,63))
    bonus = []
    for outer, inner in zip(bonus_rois, bonus_inner_rois):
        inner_value = read_result_amount(crop_percent(image, inner), main_result=True)
        bonus.append(inner_value if inner_value is not None else read_result_amount(crop_percent(image, outer)))
    if all(value is None for value in bonus) and not has_screen_text(crop_percent(image, Roi(67,42,83,64)), "bonus"):
        bonus = [0, 0, 0]
    if None in bonus:
        return None
    return tuple(a+b for a,b in zip(amounts, bonus))


def result_zero_visible(crop):
    # Windows OCR often ignores an isolated character. Repeat the same crop
    # to make a word, requiring all four characters to be recognised as zero.
    mask = white_text_mask(crop)
    repeated = Image.new("RGB", (mask.width * 4, mask.height), "white")
    for index in range(4):
        repeated.paste(mask, (index * mask.width, 0))
    for scale in (2, 3):
        raw = re.sub(r"\s", "", read_text(repeated, scale=scale)).lower()
        if raw.replace("o", "0") == "0000":
            return True
    return False


def battle_reward_choice(image: Image.Image):
    """Only return a card after all three frames have appeared.

    Prefer gold/elixir, then event tickets. Never choose an event troop.
    This function is called only inside the recognised event.
    """
    centers = (30., 50., 70.)
    # Final victory cards sit lower than the choices shown during combat.
    layout = None
    for edge_y, label_top, label_bottom, click_y in ((30.5, 52, 66, 53.), (32.7, 63, 74, 60.), (33.4, 63, 74, 60.)):
        ready = True
        for x in centers:
            edge = crop_percent(image, Roi(x-6, edge_y, x+6, edge_y+.5))
            pixels = list(edge.convert("RGB").get_flattened_data())
            if sum(min(p) > 120 and p[2] > p[0]*1.04 for p in pixels) < len(pixels)*.45:
                ready = False
                break
        if ready:
            layout = (label_top, label_bottom, click_y)
            break
    # During the opening animation an in-battle card may show text without
    # its frame. Only the confirmed victory layout may use the label fallback.
    if layout is None and not has_screen_text(crop_percent(image, layout_roi("SCREEN_ROIS", "battle_reward")), "victoire"):
        return None
    layouts = [layout] if layout is not None else [(63, 74, 60.), (52, 66, 53.)]
    tickets = None
    for label_top, label_bottom, click_y in layouts:
        for x in centers:
            readings = [read_text(crop_percent(image, Roi(x-7, label_top, x+7, label_bottom)), scale=scale) for scale in (2,1)]
            for raw in readings:
                text = "".join(c for c in unicodedata.normalize("NFD", raw.casefold()) if unicodedata.category(c) != "Mn")
                if re.search(r"\b[o0]r\b|\belixir\b", text):
                    return (x, click_y), raw
                if re.search(r"\btickets?\b", text):
                    tickets = ((x, click_y), raw)
    return tickets  # An unreadable card or a troop never authorises a click.


class DiagnosticJournal:
    """Flush every event to the history and to a separate file for each run."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._file = path.open("a", encoding="utf-8")
        self._run_file = None
        self.run_path = None
        self.last_run_path = None
        self._run_failed = False
        self._closed = False
        self.recent = deque(maxlen=180)
        self.recent_seq = 0

    def start_run(self, label: str, settings=None):
        with self._lock:
            if self._run_file is not None:
                raise RuntimeError("Un journal d'opération est déjà ouvert.")
            run_dir = self.path.parent / "runs"
            run_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
            slug = re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-") or "action"
            self.run_path = run_dir / f"CoCFarmBot-{stamp}-{slug}-{uuid.uuid4().hex[:8]}.txt"
            self._run_file = self.run_path.open("x", encoding="utf-8")
            self.last_run_path = self.run_path
            self._run_failed = False
            self.record("DÉBUT", f"Action={label}; journal={self.run_path}; programme={sys.executable}")
            if settings is not None:
                self.record("CONFIG", json.dumps(asdict(settings), ensure_ascii=False, sort_keys=True))
            return self.run_path

    def end_run(self, status: str):
        with self._lock:
            if self._run_file is None:
                return
            if self._run_failed:
                status = "erreur"
            self.record("FIN", f"Statut={status}; journal={self.run_path}")
            self._run_file.close()
            self._run_file = None
            self.run_path = None

    def record(self, kind: str, message: str):
        with self._lock:
            if self._closed:
                return
            stamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
            thread = threading.current_thread().name
            if kind == "ERREUR":
                self._run_failed = True
            for index, line in enumerate(str(message).splitlines() or [""]):
                entry = f"{stamp} [{thread}] {kind} {line}\n"
                self._file.write(entry)
                if kind in ("ÉTAPE", "INTERFACE", "ERREUR", "REFUS", "ARRÊT", "FIN", "STATS", "SESSION") and (kind != "ERREUR" or index == 0):
                    level = ("error" if kind == "ERREUR" else
                             "warning" if kind in ("REFUS", "ARRÊT") else
                             "success" if kind == "STATS" or (kind == "FIN" and "terminée" in line) else "info")
                    visible = ("Une erreur est survenue. Exportez le diagnostic pour le détail." if kind == "ERREUR"
                               else "Ouverture de l'application." if kind == "SESSION" and "programme=" in line
                               else "Journal détaillé disponible dans le diagnostic." if kind == "ÉTAPE" and line.startswith("Journal détaillé de cette action :")
                               else line)
                    self.recent.append({"time": stamp, "type": kind, "level": level, "message": visible})
                    self.recent_seq += 1
                if self._run_file is not None:
                    self._run_file.write(entry)
            self._file.flush()
            if self._run_file is not None:
                self._run_file.flush()

    def save_reward_screen(self, image: Image.Image) -> Path | None:
        with self._lock:
            if self.run_path is None:
                return None
            screenshot = self.run_path.with_name(f"{self.run_path.stem}-reward-{uuid.uuid4().hex[:8]}.png")
            image.save(screenshot)
            self.record("RÉCOMPENSE", f"Capture du choix final non reconnu : {screenshot}")
            return screenshot

    def export(self, destination: Path):
        source_path = self.last_run_path or self.path
        if destination.resolve() in (self.path.resolve(), source_path.resolve()):
            raise ValueError("Le fichier exporté doit être différent du journal actif.")
        with self._lock:
            self._file.flush()
            if self._run_file is not None:
                self._run_file.flush()
            remaining = source_path.stat().st_size
        decoder = codecs.getincrementaldecoder("utf-8")("surrogateescape")
        legacy = {0xdc00 + byte: bytes([byte]).decode("cp1252", errors="replace")
                  for byte in range(0x80, 0x100)}
        with source_path.open("rb") as source, destination.open("wb") as output:
            while remaining:
                block = source.read(min(1024 * 1024, remaining))
                if not block:
                    raise OSError("Lecture du journal interrompue.")
                remaining -= len(block)
                output.write(decoder.decode(block, final=not remaining).translate(legacy).encode("utf-8"))

    def export_bundle(self, destination: Path):
        source_path = self.last_run_path or self.path
        if destination.resolve() == source_path.resolve():
            raise ValueError("Le diagnostic exporté doit être différent du journal actif.")
        with self._lock:
            self._file.flush()
            if self._run_file is not None:
                self._run_file.flush()
            with zipfile.ZipFile(destination,"w",compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(source_path,arcname=source_path.name)
                screenshot = source_path.with_suffix(".png")
                if screenshot.exists():
                    archive.write(screenshot,arcname=screenshot.name)
                for screenshot in sorted(source_path.parent.glob(f"{source_path.stem}-reward-*.png")):
                    archive.write(screenshot,arcname=screenshot.name)

    def close(self):
        with self._lock:
            if not self._closed:
                if self._run_file is not None:
                    self.end_run("application fermée")
                self._file.close()
                self._closed = True


class DiagnosticEvents(queue.Queue):
    def __init__(self, journal: DiagnosticJournal):
        super().__init__()
        self.journal = journal

    def put(self, item, *args, **kwargs):
        if isinstance(item, str):
            self.journal.record("ÉTAPE", item)
        elif isinstance(item, StatsEvent):
            self.journal.record("STATS", json.dumps(item.totals, ensure_ascii=False))
        elif isinstance(item, PreviewEvent):
            self.journal.record("APERÇU", f"{item.title} {item.image.width}x{item.image.height}")
        return super().put(item, *args, **kwargs)


class BotApp:
    def __init__(self, hidden=False):
        cleared_previous_data = prepare_storage(APP_DIR)
        self.journal = DiagnosticJournal(LOG_PATH)
        self.journal.record("SESSION", f"Ouverture du bot ; programme={sys.executable}")
        self.journal.record("STOCKAGE", "Anciennes données supprimées au premier lancement de cette version." if cleared_previous_data else "Stockage neuf ou déjà remis à zéro pour cette version.")
        build_info = Path(__file__).with_name("build_info.json")
        if build_info.exists():
            try:
                built = json.loads(build_info.read_text(encoding="utf-8-sig"))
                self.journal.record("VERSION", f"Compilation={built.get('built_at_utc')}; source={built.get('sources', {}).get('main.py')}")
            except (OSError, ValueError):
                self.journal.record("VERSION", "Informations de compilation illisibles")
        else:
            self.journal.record("VERSION", "Exécution depuis les sources")
        self.settings = load_settings()
        self.root = Tk()
        self.root.title(APP_NAME)
        try:
            self.root.iconbitmap(str(ASSET_DIR / "kit" / "app" / "app.ico"))
        except (OSError, RuntimeError):
            pass
        screen_width, screen_height = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        width, height = min(1240, screen_width - 60), min(790, screen_height - 100)
        self.root.geometry(f"{width}x{height}+{max(0, (screen_width-width)//2)}+30")
        self.root.minsize(min(1080, width), min(760, height))
        if hidden:
            self.root.withdraw()
        self.events = DiagnosticEvents(self.journal)
        self.stop_event = threading.Event()
        self.action_lock = threading.RLock()
        self.worker = None
        self.inspection_worker = None
        self.calibration_dialog = None
        self.photo = None
        self.window_title = StringVar(value=self.settings.window_title)
        self.min_gold = StringVar(value=str(self.settings.min_gold))
        self.min_elixir = StringVar(value=str(self.settings.min_elixir))
        self.loot_margin = StringVar(value=str(self.settings.loot_margin_percent))
        self.electrodragon_count = StringVar(value=str(self.settings.electrodragon_count))
        self.dragon_count = StringVar(value=str(self.settings.dragon_count))
        self.delay_between_dragons = StringVar(value=str(self.settings.delay_between_dragons_ms))
        self.and_rule = BooleanVar(value=self.settings.use_and_rule)
        self.dry_run = BooleanVar(value=self.settings.dry_run)
        self.deploy_heroes = BooleanVar(value=self.settings.deploy_heroes)
        self.upgrade_wall = BooleanVar(value=self.settings.upgrade_wall_between_attacks)
        self.upgrade_recommended = BooleanVar(value=self.settings.upgrade_recommended)
        self.chain_attacks = BooleanVar(value=self.settings.chain_attacks)
        self.status = StringVar(value="Prêt à lire la fenêtre du jeu.")
        self.run_state = StringVar(value="PRÊT")
        self.farm_stats = FarmStats(STATS_PATH)
        self.stats_vars = {key: StringVar(value=f"{self.farm_stats.data[key]:,}".replace(",", " "))
                           for key in ("gold", "elixir", "dark_elixir")}
        self.stats_count = StringVar(value=f"{self.farm_stats.data['battles']} combat(s) comptabilisé(s) · cumul sauvegardé")
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._pump()

    def _trace(self, kind, message):
        journal = getattr(self, "journal", None)
        if journal is not None:
            journal.record(kind, message)

    def _check_stopped(self):
        if self.stop_event.is_set():
            raise OperationCancelled("Arrêt demandé.")

    def _capture(self, window):
        self._check_stopped()
        self._trace("CAPTURE", f"Lecture demandée : {getattr(window, 'title', '?')}")
        image = WindowDriver.capture(window)
        self._last_capture = image
        self._trace("CAPTURE", f"Image reçue : {image.width}x{image.height}")
        self._check_stopped()
        if connection_retry_point(image) is not None:
            self._trace("ÉCRAN", "Dialogue de déconnexion détecté")
            self._reconnect_pending = True
            raise ReconnectRequired()
        return image

    def _click(self, window, x, y):
        # Stop and click share a lock: after stop() returns no new press is sent.
        with self.action_lock:
            self._check_stopped()
            self._trace("CLIC", f"Envoi à {x:.2f} %, {y:.2f} % sur {getattr(window, 'title', '?')}")
            accepted = WindowDriver.click_percent(window, x, y)
            self._trace("CLIC", f"Résultat à {x:.2f} %, {y:.2f} % : {'accepté' if accepted else 'refusé'}")
            return accepted

    def _wait(self, seconds):
        self._trace("ATTENTE", f"{seconds:.2f} s")
        if self.stop_event.wait(seconds):
            raise OperationCancelled("Arrêt demandé.")
        return False

    def _run_operation(self, target):
        status = "terminée"
        try:
            validate_layout(self.settings)
            while not self.stop_event.is_set():
                try:
                    with operation_context(self.stop_event, self.settings, getattr(self,"journal",None)):
                        target()
                    break
                except ReconnectRequired:
                    self._trace("REPRISE", "Action interrompue par la déconnexion ; tentative de reconnexion")
                    with operation_context(self.stop_event, self.settings, getattr(self,"journal",None)):
                        self.reconnect_game()
                    self._reconnect_pending = False
        except OperationCancelled:
            status = "interrompue"
            self.events.put("Opération interrompue.")
        except Exception as exc:
            status = "erreur"
            self._trace("ERREUR", traceback.format_exc())
            self.events.put("Opération arrêtée à cause d'une erreur. Exportez le diagnostic pour le détail.")
        finally:
            self._reconnect_pending = False
            journal = getattr(self,"journal",None)
            if journal is not None:
                if journal._run_failed and journal.run_path is not None:
                    image = getattr(self,"_last_capture",None)
                    if image is not None:
                        try:
                            screenshot = journal.run_path.with_suffix(".png")
                            image.save(screenshot)
                            self._trace("CAPTURE ERREUR", f"Dernier écran enregistré : {screenshot}")
                        except OSError as error:
                            self._trace("ERREUR", f"Capture de diagnostic impossible : {error}")
                if journal._run_failed:
                    status = "erreur"
                journal.end_run(status)
            self.events.put(RunStateEvent(status))

    def _begin_run(self, label):
        journal = getattr(self,"journal",None)
        if journal is None:
            return
        path = journal.start_run(label, self.settings)
        self.events.put(f"Journal détaillé de cette action : {path}")
        self._trace("CAPACITÉS", "Pendant l'action : les nouvelles commandes et les modifications sont bloquées ; Arrêter et l'export du journal restent disponibles.")

    def reconnect_game(self):
        self.events.put('Jeu déconnecté : reconnexion automatique en cours.')
        stable = 0
        last_attempt = -float('inf')
        while not self.stop_event.is_set():
            window = WindowDriver.resolve(self.settings.window_title)
            if not window:
                self._wait(2)
                continue
            image = WindowDriver.capture(window)
            self._trace("CAPTURE", f"Reconnexion : image reçue {image.width}x{image.height}")
            point = connection_retry_point(image)
            if point is not None:
                stable = 0
                if time.monotonic()-last_attempt>=10:
                    if not self._click(window,*point):
                        raise RuntimeError('Reconnexion refusée par la fenêtre du jeu.')
                    last_attempt = time.monotonic()
                    self.events.put('Reconnexion envoyée ; attente du jeu.')
                    self._wait(3)
            elif village_home_ready(image) or has_screen_text(image,'victoire','défaite','fin de la bataille'):
                stable += 1
                if stable >= 2:
                    self.events.put('Connexion rétablie : reprise depuis un état relu du jeu.')
                    return
            else:
                stable = 0
            self._wait(1)

    def _busy(self):
        return bool((self.worker and self.worker.is_alive())
                    or (self.inspection_worker and self.inspection_worker.is_alive())
                    or self.calibration_dialog)

    def close(self):
        if getattr(self, "_closed", False):
            return
        self.stop()
        self._trace("SESSION", "Fermeture de l'application")
        self._cancel_pump()
        self.root.destroy()
        self.journal.close()
        self._closed = True

    def _cancel_pump(self):
        callback = getattr(self, "_pump_after", None)
        if callback is not None:
            self.root.after_cancel(callback)
            self._pump_after = None

    def reset_all_data(self, confirmed=False, show_errors=True):
        if self._busy():
            self.write("Arrêtez l'action en cours avant d'effacer les données du bot.")
            return False
        if not confirmed and not messagebox.askyesno(
                "Effacer toutes les données ?",
                "Tous les réglages, statistiques, journaux et captures enregistrés par le bot seront supprimés. "
                "L'application se fermera ensuite. Les ZIP exportés hors du dossier du bot restent à supprimer séparément. Continuer ?",
                parent=self.root):
            return False
        self._trace("EFFACEMENT", f"Suppression demandée du dossier {APP_DIR}")
        self.stop_event.set()
        self._cancel_pump()
        self.journal.close()
        try:
            clear_saved_data(APP_DIR)
        except (OSError, ValueError) as exc:
            self.journal = DiagnosticJournal(LOG_PATH)
            self.events.journal = self.journal
            self._trace("ERREUR", f"Effacement incomplet : {exc}")
            if show_errors:
                messagebox.showerror("Effacement incomplet", str(exc), parent=self.root)
            self._pump_after = self.root.after(250, self._pump)
            return False
        self._closed = True
        self.root.destroy()
        return True

    def export_log(self):
        destination = filedialog.asksaveasfilename(
            parent=self.root, title="Exporter le diagnostic du bot",
            initialfile=f"CoCFarmBot-diagnostic-{datetime.now():%Y%m%d-%H%M%S}.zip",
            defaultextension=".zip", filetypes=[("Archive ZIP", "*.zip")])
        if not destination:
            return
        path = Path(destination)
        if path.suffix.lower() != ".zip":
            path = Path(str(path) + ".zip")
        try:
            self._trace("EXPORT", f"Copie du diagnostic vers {path}")
            self.journal.export_bundle(path)
        except (OSError, ValueError) as exc:
            self._trace("ERREUR", f"Export du journal impossible : {exc}")
            messagebox.showerror("Export impossible", str(exc), parent=self.root)
            return
        self.write(f"Diagnostic enregistré : {path}. Envoyez ce ZIP pour analyser un blocage.")

    def _build(self):
        from dashboard import build
        build(self)

    def refresh(self):
        windows=[window for window in WindowDriver.list_windows() if window.title.casefold().startswith("clash of clans")]
        self.windows["values"]=[window.title for window in windows]
        if windows and self.window_title.get() not in self.windows["values"]:
            self.window_title.set(windows[0].title)
        self.write(f"{len(windows)} fenêtre(s) Clash détectée(s).")

    def inspect_game(self):
        self._start_inspection(self._inspect_game)

    def _start_inspection(self, reader, allow_calibration=False):
        if ((self.worker and self.worker.is_alive()) or (self.inspection_worker and self.inspection_worker.is_alive())
                or (self.calibration_dialog and not allow_calibration)):
            self.write("Attendre la fin de l’opération ou cliquer Arrêter avant une nouvelle lecture.")
            return
        title = self.window_title.get()
        self.stop_event.clear()
        self._begin_run("lecture du jeu")
        def inspect():
            window = WindowDriver.resolve(title)
            if not window: raise RuntimeError("Fenêtre Clash introuvable.")
            reader(window)
        self.inspection_worker = threading.Thread(target=self._run_operation, args=(inspect,), daemon=True)
        self.inspection_worker.start()
        self.run_state.set("LECTURE")

    def calibrate(self):
        def capture_for_calibration(window):
            self.events.put(PreviewEvent(self._capture(window), window.title, calibrate=True))
        self._start_inspection(capture_for_calibration, allow_calibration=True)

    def capture_for_web_calibration(self):
        self._start_inspection(lambda window: self.events.put(
            PreviewEvent(self._capture(window), window.title)))

    def save_calibration(self, overrides, ratio):
        if self.inspection_worker and self.inspection_worker.is_alive():
            raise ValueError("Attendre la fin de l'actualisation avant d'enregistrer.")
        candidate = replace(self.settings, layout_overrides=validate_overrides(LAYOUT_DEFAULTS, overrides),
                            layout_aspect_ratio=ratio)
        validate_layout(candidate)
        save_settings(candidate)
        self.settings = candidate
        self.write(f"Calibrage enregistré : {len(overrides)} position(s) personnalisée(s).")

    def _show_calibration(self, image):
        if self.calibration_dialog:
            self.calibration_dialog.set_image(image)
            return
        def save(overrides, ratio):
            self.save_calibration(overrides, ratio)
        def closed():
            self.calibration_dialog = None
            with self.action_lock:
                self.stop_event.set()
        self.calibration_dialog = CalibrationDialog(self.root, image, LAYOUT_DEFAULTS,
                                                    self.settings.layout_overrides, save, closed, self.calibrate, layout_labels())

    def _inspect_game(self, window):
        try:
            image=self._capture(window)
            self.events.put(PreviewEvent(image, window.title))
            if village_home_ready(image):
                gold, elixir=read_safe_reserve(image, "gold"), read_safe_reserve(image, "elixir")
                self.events.put(f"Village : or {gold:,} / élixir {elixir:,}." if gold is not None and elixir is not None else "Village détecté ; réserves illisibles.")
            elif enemy_loot_screen_ready(image):
                loot=read_enemy_loot(image)
                self.events.put(f"Base adverse : or {loot.gold:,} / élixir {loot.elixir:,}." if loot.gold is not None and loot.elixir is not None else "Base adverse détectée ; butin illisible.")
            else:
                self.events.put("Capture reçue ; écran non reconnu pour la lecture des ressources.")
        except OperationCancelled: raise
        except Exception as exc:
            self._trace("ERREUR", traceback.format_exc())
            self.events.put('Lecture impossible. Exportez le diagnostic pour le détail.')

    def _show_preview(self, image):
        self.activity_tabs.select(1)
        self.root.update_idletasks()
        preview=image.copy()
        preview.thumbnail((max(300, self.preview.winfo_width()-24), max(170, self.preview.winfo_height()-24)))
        self.photo=ImageTk.PhotoImage(preview)
        self.preview.configure(image=self.photo, text="")

    def scan_profile(self):
        self._start_inspection(self._scan_profile)

    def _scan_profile(self, window):
        try:
            image = self._capture(window)
            self.events.put(PreviewEvent(image, window.title))
            snapshot = read_complete_account_snapshot(image, lambda: self._capture(window)); APP_DIR.mkdir(parents=True, exist_ok=True)
            self._check_stopped()
            ACCOUNT_SNAPSHOT_PATH.write_text(json.dumps(asdict(snapshot), indent=2, ensure_ascii=False), encoding="utf-8")
            values = [
                f"Pseudo : {snapshot.account_name or '?'}", f"Niveau : {snapshot.level or '?'}",
                f"Or : {snapshot.gold:,}" if snapshot.gold is not None else "Or : ?",
                f"Élixir : {snapshot.elixir:,}" if snapshot.elixir is not None else "Élixir : ?",
                f"Élixir noir : {snapshot.dark_elixir:,}" if snapshot.dark_elixir is not None else "Élixir noir : ?",
                f"Gemmes : {snapshot.gems:,}" if snapshot.gems is not None else "Gemmes : ?",
                f"Ouvriers laboratoire : {snapshot.laboratory_builders or '?'}", f"Ouvriers : {snapshot.builders or '?'}",
            ]
            self.events.put(" | ".join(values)); self.events.put(f"Relevé enregistré : {ACCOUNT_SNAPSHOT_PATH}")
        except OperationCancelled: raise
        except Exception as exc:
            self._trace("ERREUR", traceback.format_exc())
            self.events.put('Relevé du profil impossible. Exportez le diagnostic pour le détail.')

    def persist(self):
        if self._busy():
            self.write("Arrêter l’opération avant de changer les réglages.")
            return False
        try:
            candidate = replace(self.settings, window_title=self.window_title.get(),
                min_gold=int(self.min_gold.get().replace(" ", "")), min_elixir=int(self.min_elixir.get().replace(" ", "")),
                loot_margin_percent=float(self.loot_margin.get().replace(",", ".")),
                electrodragon_count=int(self.electrodragon_count.get()), dragon_count=int(self.dragon_count.get()),
                delay_between_dragons_ms=int(self.delay_between_dragons.get()),
                use_and_rule=self.and_rule.get(), dry_run=self.dry_run.get(), deploy_heroes=self.deploy_heroes.get(),
                upgrade_wall_between_attacks=self.upgrade_wall.get(), upgrade_recommended=self.upgrade_recommended.get(), chain_attacks=self.chain_attacks.get())
            if not 0 <= candidate.min_gold <= 2_500_000 or not 0 <= candidate.min_elixir <= 2_500_000 or not 0 <= candidate.loot_margin_percent <= 25 or not 0 <= candidate.electrodragon_count <= 50 or not 0 <= candidate.dragon_count <= 50 or not 80 <= candidate.delay_between_dragons_ms <= 2000: raise ValueError
            save_settings(candidate)
            self.settings = candidate
            self._trace("CONFIG", json.dumps(asdict(candidate), ensure_ascii=False))
            self.write(f"Configuration enregistrée : attaque dès {effective_minimum(candidate.min_gold, candidate.loot_margin_percent):,} or / {effective_minimum(candidate.min_elixir, candidate.loot_margin_percent):,} élixir.")
            return True
        except ValueError:
            self.write("Réglages invalides : seuils de 0 à 2 500 000, marge de 0 à 25 %, troupes de 0 à 50, délai de 80 à 2 000 ms.")
            return False
        except OSError as exc:
            self._trace("ERREUR", f"Sauvegarde impossible : {exc}")
            self.write("Sauvegarde impossible. Exportez le diagnostic pour voir le détail.")
            return False
    def start_farm(self):
        if self._busy():
            self._trace("REFUS", "Démarrage du farm impossible : une autre action est en cours.")
            return
        if not self.persist(): return
        if self.settings.dry_run: self.write("Simulation active : recherche et lecture uniquement, aucune pose ne sera envoyée.")
        else: self.write("Mode réel actif : toutes les troupes disponibles seront posées et vérifiées sur une base retenue.")
        self.stop_event.clear(); self._begin_run("cycle complet"); self.worker=threading.Thread(target=self._run_operation,args=(self.farm_loop,),daemon=True); self.worker.start(); self.run_state.set("EN COURS"); self.write("Recherche automatique démarrée.")
    def start_walls(self):
        if self._busy():
            self._trace("REFUS", "Démarrage des remparts impossible : une autre action est en cours.")
            return
        if not self.persist(): return
        self.stop_event.clear(); self._begin_run("remparts"); self.worker=threading.Thread(target=self._run_operation,args=(self.wall_loop,),daemon=True); self.worker.start(); self.run_state.set("EN COURS"); self.write("Amélioration des remparts démarrée.")

    def start_independent(self, action):
        if self._busy():
            self._trace("REFUS", f"Action {action} impossible : une autre action est en cours.")
            return
        if not self.persist():
            return
        self.stop_event.clear()
        self._begin_run(f"action {action}")
        self.run_state.set('EN COURS')
        self.worker = threading.Thread(target=self._run_operation, args=(lambda: self.independent_loop(action),), daemon=True)
        self.worker.start()

    def independent_loop(self, action):
        original = self.settings
        try:
            window = WindowDriver.resolve(self.settings.window_title)
            if not window:
                raise RuntimeError('Fenêtre Clash introuvable.')
            if action == 'attack':
                self.settings = replace(original, chain_attacks=False, upgrade_recommended=False, upgrade_wall_between_attacks=False)
                self.farm_loop()
            elif action == 'buildings':
                if not village_home_ready(self._capture(window)):
                    raise RuntimeError('Revenir au village pour lancer les bâtiments.')
                from upgrades import upgrade_suggested
                upgrade_suggested(self,window)
        finally:
            self.settings = original
            if not getattr(self,'_reconnect_pending',False):
                self.stop_event.set()
                self.events.put('Action indépendante terminée.')
    def stop(self):
        self._trace("ARRÊT", "Demande d'arrêt reçue ; les prochains clics seront bloqués.")
        with self.action_lock:
            self.stop_event.set()
        self.write("Arrêt demandé.")
    def wall_loop(self):
        try:
            if self.settings.dry_run:
                self.events.put("Simulation activée : aucune amélioration de rempart envoyée.")
                return
            window = WindowDriver.resolve(self.settings.window_title)
            if not window: raise RuntimeError("Fenêtre Clash introuvable.")
            self.upgrade_walls_to_reserve(window, independent=True)
        except ReconnectRequired: raise
        except OperationCancelled: self.events.put("Amélioration des remparts interrompue.")
        except Exception as exc:
            self._trace("ERREUR", traceback.format_exc())
            self.events.put("Remparts arrêtés à cause d'une erreur. Exportez le diagnostic pour le détail.")
        finally:
            if not getattr(self,'_reconnect_pending',False):
                self.stop_event.set(); self.events.put("Amélioration des remparts terminée.")

    def stable_reserves(self, window):
        """Require two agreeing home-village readings before authorising spending."""
        previous = None
        for attempt in range(5):
            image = self._capture(window)
            values = (read_safe_reserve(image, "gold"), read_safe_reserve(image, "elixir"))
            self._trace("RÉSERVES", f"Lecture {attempt+1}/5 : or={values[0]}, élixir={values[1]}, précédente={previous}")
            if None not in values and previous is not None and all(abs(a - b) <= 20_000 for a, b in zip(values, previous)):
                confirmed = tuple(min(a, b) for a, b in zip(values, previous))
                self._trace("RÉSERVES", f"Réserves confirmées : or={confirmed[0]}, élixir={confirmed[1]}")
                return confirmed
            previous = values if None not in values else None
            if self._wait(.4): break
        self._trace("REFUS", "Réserves non confirmées après cinq lectures ; dépense interdite.")
        return None

    def collect_village_resources(self, window):
        """Collect only visually confirmed mine/extractor bubbles in the home village."""
        def village_clear(image):
            return village_home_ready(image) and not builders_menu_open(image) and not daily_reward_open(image)

        if not all(village_clear(self._capture(window)) for _ in range(2)):
            self.events.put("Collecte reportée : village non confirmé.")
            return 0
        before = self.stable_reserves(window)
        icons = find_collectible_icons(self._capture(window))
        collected = {"gold": 0, "elixir": 0}
        for resource, x, y, _score in icons:
            fresh = self._capture(window)
            if not village_clear(fresh):
                self.events.put("Collecte interrompue : écran du village modifié.")
                break
            if not collectible_icon_still_visible(fresh, resource, x, y):
                continue
            if not self._click(window, x * 100 / 1920, y * 100 / 1080):
                raise RuntimeError("Clic de collecte refusé.")
            self._wait(.6)
            after_click = self._capture(window)
            if collectible_icon_still_visible(after_click, resource, x, y):
                self.events.put(f"Collecte {resource} non confirmée à {x},{y} : arrêt prudent.")
                break
            collected[resource] += 1
        after = self.stable_reserves(window) if sum(collected.values()) else before
        if sum(collected.values()):
            changes = (after[0] - before[0], after[1] - before[1]) if before and after else None
            self.events.put(f"Collecte des mines/extracteurs : {collected['gold']} action(s) or, {collected['elixir']} action(s) élixir ; variation des réserves : {changes}.")
        return sum(collected.values())

    def _wall_click(self, window, point, label):
        if not self._click(window, *point): raise RuntimeError(f"Clic {label} refusé.")
        self._wait(.45)

    def stable_wall_group(self, window, resource=None, single=False, price_above=None, expected_price=None):
        previous = None
        for attempt in range(16 if price_above is not None else 8):
            controls = wall_group_controls(self._capture(window),single=single,
                                           expected_price=expected_price,expected_resource=resource)
            self._trace("REMPARTS", f"Contrôles lus {attempt+1} : {controls!r}; ressource={resource}, prix précédent>{price_above}, attendu={expected_price}")
            if controls is not None and resource is not None and resource not in controls["payments"]:
                controls = None
            if (controls is not None and price_above is not None and
                    controls['payments'][resource][1] <= price_above):
                controls = None
            if controls is not None and previous is not None:
                same_prices = {r:p[1] for r,p in controls['payments'].items()} == {r:p[1] for r,p in previous['payments'].items()}
                same_add = single or all(abs(a-b)<.5 for a,b in zip(controls['add'],previous['add']))
                if same_prices and same_add:
                    self._trace("REMPARTS", f"Contrôles stables : {controls!r}")
                    return controls
            previous = controls
            self._wait(.15)
        self._trace("REFUS", "Boutons ou prix de remparts instables ; aucune confirmation.")
        return None

    def upgrade_walls_to_reserve(self, window, independent=False, max_batches=None):
        """Upgrade available walls while keeping both village reserves at or above 1 M."""
        self._trace("REMPARTS", f"Début : action seule={independent}, simulation={self.settings.dry_run}, amélioration bâtiments={self.settings.upgrade_recommended}")
        if (not independent and not self.settings.upgrade_wall_between_attacks) or self.settings.dry_run:
            self._trace("REFUS", "Remparts désactivés par les réglages ou par la simulation.")
            return 0
        if not independent and self.settings.upgrade_recommended:
            from upgrades import stable_builders
            free = stable_builders(self, window)
            if free is None or free < 1:
                self.events.put(f'Builders available={free}: walls postponed until one builder is confirmed available.')
                return 0
        upgraded = 0
        batches = 0
        rejected_rows = set()
        rejected_groups = set()
        rejected_attempts = 0
        while not self.stop_event.is_set():
            balances = self.stable_reserves(window)
            self._trace("REMPARTS", f"Nouveau lot : déjà améliorés={upgraded}, réserves={balances}, lignes écartées={sorted(rejected_rows)}")
            if balances is None:
                self.events.put("Réserves instables ou illisibles : aucune dépense envoyée.")
                return upgraded
            gold, elixir = balances
            if gold <= WALL_RESERVE and elixir <= WALL_RESERVE:
                self.events.put(f"Réserves préservées : or {gold:,}, élixir {elixir:,}.")
                return upgraded
            menu = self._capture(window)
            if not builders_menu_open(menu) and find_wall_menu_item(menu) is None:
                self._wall_click(window, layout_values("BUILDERS_BUTTON"), "ouvriers")
            from upgrades import scroll_builders_to_top
            scroll_builders_to_top(self,window)
            available = None
            previous_menu = None
            unchanged_menu = 0
            for page in range(20):
                menu = self._capture(window)
                if rejected_rows:
                    item = next((point for point in find_wall_menu_items(menu)
                                 if all(abs(point[1] - y) >= 1.5 or
                                        (read_wall_available(menu, point) or 1) != quantity
                                        for y, quantity in rejected_rows)), None)
                else:
                    item = find_wall_menu_item(menu)
                available = read_wall_available(menu, item) if item else None
                self._trace("REMPARTS", f"Page {page+1}/20 : ligne={item}, quantité={available}")
                if item and available is None:
                    # OCR can miss the trailing ``x147`` while the builder
                    # list is settling. Retry the same row before falling
                    # back to the special last-row x1 case; treating a large
                    # group as a single wall opens the wrong payment panel.
                    for _ in range(3):
                        self._wait(.15)
                        retry_menu = self._capture(window)
                        retry_item = next((point for point in find_wall_menu_items(retry_menu)
                                           if abs(point[1] - item[1]) < 1.5), item)
                        retry_available = read_wall_available(retry_menu, retry_item)
                        if retry_available is not None:
                            item, available = retry_item, retry_available
                            break
                    if available is None:
                        available = 1  # The game omits x1 on the last row.
                if available is not None: break
                if isinstance(menu, Image.Image):
                    signature = read_text(crop_percent(menu,Roi(38,12,64,64)),scale=2).casefold()
                    unchanged_menu = unchanged_menu + 1 if signature and signature == previous_menu else 0
                    if unchanged_menu >= 2:
                        break
                    previous_menu = signature
                # The border and heading can disappear during a scroll. A
                # bounded wheel action is safe even when menu OCR is uncertain.
                with self.action_lock:
                    self._check_stopped()
                    self._trace("DÉFILEMENT", "Recherche des remparts : descendre le menu")
                    if not WindowDriver.scroll_menu(window,delta=-1200):
                        raise RuntimeError('Défilement des remparts refusé.')
                if self._wait(.4): break
            if self.stop_event.is_set() or item is None or available is None:
                if rejected_rows:
                    self.events.put(f"Aucun autre rempart payable en conservant 1 M : or {gold:,}, élixir {elixir:,}.")
                else:
                    self.events.put("Liste des remparts indisponible ou illisible : arrêt prudent.")
                return upgraded
            selected = False
            for _ in range(3):
                relocated = False
                # Opening/closing a dialog can reset the menu scroll position.
                # Never reuse the row retained before reading its quantity.
                current_menu = self._capture(window)
                current_item = find_wall_menu_item(current_menu)
                self._trace("REMPARTS", f"Relire avant sélection : ligne précédente={item}, actuelle={current_item}")
                if current_item is None or abs(current_item[1] - item[1]) >= 1.5:
                    current_rows = find_wall_menu_items(current_menu)
                    current_item = next((point for point in current_rows
                                         if abs(point[1] - item[1]) < 1.5), None)
                    if current_item is None and len(current_rows) == 1:
                        # The last wheel event may still move the list, and
                        # OCR can turn x169 into x159. Re-read the sole wall
                        # row on a second frame before using its new position
                        # and quantity. Spending is verified separately.
                        fresh_quantity = read_wall_available(current_menu,current_rows[0])
                        if fresh_quantity is not None:
                            settled_menu = self._capture(window)
                            settled_rows = find_wall_menu_items(settled_menu)
                            if (len(settled_rows) == 1 and
                                    abs(settled_rows[0][1] - current_rows[0][1]) < 1.5 and
                                    read_wall_available(settled_menu, settled_rows[0]) == fresh_quantity):
                                current_item = settled_rows[0]
                                available = fresh_quantity
                                relocated = True
                                self._trace("REMPARTS", f"Ligne déplacée et relue deux fois : {current_item}, x{fresh_quantity}")
                if current_item is None:
                    self._wait(.4)
                    continue
                item = current_item
                if not relocated:
                    available = read_wall_available(current_menu, item) or available
                self._wall_click(window, item, "rempart")
                wall_image = self._capture(window)
                selected_wall = wall_selected(wall_image)
                self._trace("REMPARTS", f"Sélection envoyée : ligne={item}, x{available}, sélection reconnue={selected_wall}")
                if selected_wall or (available == 1 and wall_group_controls(wall_image,single=True) is not None):
                    selected = True
                    break
                if self.stop_event.is_set(): break
                if not builders_menu_open(wall_image):
                    self._wall_click(window, layout_values("BUILDERS_BUTTON"), "ouvriers")
                menu = self._capture(window)
                item = find_wall_menu_item(menu)
                if item is None:
                    self._wait(.4)
            if self.stop_event.is_set() or not selected:
                raise RuntimeError("Sélection de rempart non confirmée : cycle arrêté avant l’attaque.")
            single = available == 1
            if not single:
                for attempt in range(3):
                    more_button = find_wall_more_button(self._capture(window))
                    if more_button is None:
                        raise RuntimeError("Bouton Améliorer plus introuvable : cycle arrêté avant l’attaque.")
                    self._wall_click(window, more_button, "Améliorer plus")
                    if wall_multi_mode(self._capture(window)):
                        break
                    if attempt == 2 or not wall_selected(self._capture(window)):
                        raise RuntimeError("Ouverture du groupe de remparts non confirmée : cycle arrêté avant l’attaque.")
                    self.events.put("Améliorer plus sans effet confirmé : nouvel essai avant toute dépense.")
                    self._wait(.6)
            controls = self.stable_wall_group(window,single=single)
            self._trace("REMPARTS", f"Contrôles du groupe : {controls!r}, individuel={single}")
            if controls is None:
                raise RuntimeError("Boutons du groupe de remparts non confirmés : cycle arrêté avant l’attaque.")
            payments = controls['payments']
            gold_cost = payments.get('or', (None,None))[1]
            elixir_cost = payments.get('élixir', (None,None))[1]
            options = [(wall_batch_size(gold if resource=='or' else elixir,price,available),resource,price)
                       for resource,(_,price) in payments.items()]
            count, resource, unit_cost = max(options, key=lambda option:(option[0],gold if option[1]=='or' else elixir))
            self._trace("REMPARTS", f"Lots payables={options!r}; choisi={count} x {unit_cost} {resource}; réserves={balances}")
            if count == 0:
                group = (available, tuple(sorted((name, price) for name, (_, price) in payments.items())))
                if group in rejected_groups:
                    self.events.put(f"Aucun autre rempart payable en conservant 1 M : or {gold:,}, élixir {elixir:,}.")
                    return upgraded
                rejected_groups.add(group)
                rejected_rows.add((item[1], available))
                rejected_attempts += 1
                if rejected_attempts >= 8:
                    self.events.put(f"Aucun rempart payable en conservant 1 M : or {gold:,}, élixir {elixir:,}.")
                    return upgraded
                self.events.put("Ce groupe de remparts dépasse les réserves ; recherche d'un autre groupe.")
                continue
            selected_count = 1
            while selected_count < count:
                # Each addition can remove +10 and shift the whole row.
                # Wait for a price change, not just two stale but matching
                # frames after the click. A click without effect can be retried
                # only while the same group and price are still confirmed.
                step = 10 if controls.get('add_ten') is not None and selected_count + 10 <= count else 1
                add_point = controls.get('add_ten') if step == 10 else controls['add']
                previous_total = selected_count*unit_cost
                for attempt in range(3):
                    self._wall_click(window, add_point, f"ajouter {step} rempart(s) identifié(s)")
                    changed = self.stable_wall_group(window, resource, single=single,
                                                     price_above=previous_total,expected_price=previous_total+step*unit_cost)
                    if changed is not None:
                        controls = changed
                        break
                    current = self.stable_wall_group(window, resource, single=single)
                    current_payment = current['payments'].get(resource) if current else None
                    if current_payment is None:
                        self.events.put("Groupe de remparts devenu illisible après Ajouter ; dépense annulée et attaque conservée.")
                        return upgraded
                    if current_payment[1] != previous_total:
                        if current_payment[1] > previous_total:
                            controls = current
                            break
                        self.events.put("Prix du groupe de remparts incohérent ; dépense annulée et attaque conservée.")
                        return upgraded
                    if attempt == 2:
                        self.events.put("Ajouter un rempart sans effet après trois essais ; attaque conservée.")
                        return upgraded
                    controls = current
                    self.events.put("Ajouter un rempart sans effet confirmé : nouvel essai avant toute dépense.")
                    self._wait(.6)
                payment = controls['payments'].get(resource) if controls else None
                observed_total = payment[1] if payment else None
                expected_total = previous_total + step*unit_cost
                if observed_total is not None and abs(observed_total - expected_total) <= 150_000:
                    observed_total = expected_total
                observed_count, remainder = divmod(observed_total, unit_cost) if observed_total else (0, 0)
                self._trace("REMPARTS", f"Après Ajouter : prix={observed_total}, unitaire={unit_cost}, quantité {selected_count}->{observed_count}, reste={remainder}")
                if remainder or not selected_count < observed_count <= count:
                    raise RuntimeError(f"Ajout de rempart non confirmé : prix lu={observed_total}, prix unitaire={unit_cost}, quantité précédente={selected_count}, maximum payable={count}. Cycle arrêté avant l’attaque.")
                selected_count = observed_count
            total = selected_count*unit_cost
            fresh = self.stable_reserves(window)
            self._trace("REMPARTS", f"Avant paiement : lot={selected_count}, total={total} {resource}, réserves relues={fresh}, plancher={WALL_RESERVE}")
            if fresh is None or min(fresh) < WALL_RESERVE or fresh[0 if resource=='or' else 1]-total < WALL_RESERVE:
                raise RuntimeError("Réserves insuffisantes ou incertaines : aucune dépense envoyée, cycle arrêté avant l’attaque.")
            gold, elixir = fresh
            controls = self.stable_wall_group(window, resource, single=single,expected_price=total)
            payment = controls['payments'].get(resource) if controls else None
            self._trace("REMPARTS", f"Bouton de paiement final : {payment!r}, total attendu={total}")
            if payment is None or payment[1] != total:
                raise RuntimeError("Bouton de paiement ou coût modifié : aucune dépense envoyée, cycle arrêté avant l’attaque.")
            self._wall_click(window, payment[0], f"amélioration groupée {resource} identifiée")
            confirmation=self._capture(window)
            matches = single_wall_confirmation_matches(confirmation,total,resource) if single else wall_batch_confirmation_matches(confirmation,total,resource)
            self._trace("REMPARTS", f"Confirmation affichée : groupe={not single}, coût={total} {resource}, correspondance={matches}")
            if self.stop_event.is_set() or not matches:
                raise RuntimeError("Montant, rempart ou ressource de la confirmation non vérifié : cycle arrêté avant l’attaque.")
            confirm_button = "WALL_CONFIRM_BUTTON" if single else "WALL_MULTI_CONFIRM_BUTTON"
            self._wall_click(window, layout_values(confirm_button), "confirmation remparts")
            self._wait(.8)
            after = self.stable_reserves(window)
            before_spend = gold if resource == "or" else elixir
            after_spend = after[0] if resource == "or" and after else (after[1] if after else None)
            self._trace("REMPARTS", f"Après paiement : réserves avant={(gold,elixir)}, après={after}, variation attendue={total} {resource}")
            if after_spend is None or abs(before_spend - after_spend - total) > 50_000:
                raise RuntimeError("Dépense groupée non vérifiée sur les réserves : cycle arrêté avant l’attaque.")
            if after[0] < WALL_RESERVE or after[1] < WALL_RESERVE:
                raise RuntimeError("Une réserve est passée sous le plancher : cycle arrêté avant l’attaque.")
            upgraded += count
            batches += 1
            rejected_rows.clear()
            rejected_groups.clear()
            rejected_attempts = 0
            self.events.put(f"{count} rempart(s) amélioré(s) avec {total:,} {resource} ({upgraded} au total).")
            if max_batches is not None and batches >= max_batches:
                return upgraded
            if (gold_cost is not None and elixir_cost is not None and available > count and
                    after[0] - gold_cost < WALL_RESERVE and after[1] - elixir_cost < WALL_RESERVE):
                self.events.put(f"Réserves préservées : or {after[0]:,}, élixir {after[1]:,} ; aucun autre rempart payable.")
                return upgraded
            self._wait(1)
        return upgraded

    def deploy_unit(self, window, label, slot, points, burst=False):
        self._check_stopped()
        if not points: raise RuntimeError("Aucun point de déploiement configuré.")
        remaining = self.stable_troop_count(window, label)
        live_scaled_client = getattr(window, "width", 1920) < 1500
        expected = self.settings.electrodragon_count if label == "Électro-dragon" else self.settings.dragon_count
        if remaining is None and live_scaled_client:
            remaining = expected
            self.events.put(f"{label} : compteur OCR illisible sur la fenêtre réduite ; quantité configurée {remaining} utilisée pour la pose.")
        if remaining is None: raise RuntimeError(f"Quantité de {label} illisible : pose non vérifiable.")
        if remaining == 0: return 0
        initial = remaining
        if remaining != expected: self.events.put(f"{label} : {remaining} disponible(s), {expected} prévu(s) ; toutes les unités visibles seront envoyées.")
        if not self._click(window, *slot): raise RuntimeError(f"Sélection {label} refusée.")
        self._wait(.08)
        placed = 0
        rejected = set()
        while remaining and not self.stop_event.is_set():
            if burst:
                candidates = [p for p in points if p not in rejected]
                if not candidates:
                    raise RuntimeError(f"Aucun point accepté pour {label} ; {remaining} unité(s) restante(s).")
                drops = []
                for index in range(min(3, remaining)):
                    self._check_stopped()
                    point = candidates[min(len(candidates)-1, int((placed+index)*len(candidates)/initial))]
                    self._battle_capture(window)
                    # Event choices can clear the selected troop. Reselect only
                    # while the last confirmed count covers this whole burst.
                    if not self._click(window, *slot) or not self._click(window, *point):
                        raise RuntimeError(f"Pose rapide {label} refusée.")
                    drops.append(point)
                    self._wait(.06)
                observed = self.stable_troop_count(window, label)
                if observed is None and live_scaled_client:
                    observed = remaining - len(drops)
                    self.events.put(f"{label} : compteur non relu ; lot de {len(drops)} pose(s) suivi par décompte configuré.")
                if observed is None or not remaining-len(drops) <= observed <= remaining:
                    raise RuntimeError(f"Compteur de {label} non confirmé après la pose rapide.")
                deployed = remaining-observed
                if deployed == 0:
                    rejected.update(drops)
                else:
                    placed += deployed
                    remaining = observed
                    self.events.put(f"{label} : {deployed} pose(s) confirmée(s) en ligne ; {remaining} restant(s).")
                continue
            accepted = False
            for offset in range(len(points)):
                self._check_stopped()
                x, y = points[(int(placed * len(points) / initial) + offset) % len(points)]
                if (x, y) in rejected:
                    continue
                before = self._battle_capture(window)
                if not self._click(window, x, y): raise RuntimeError(f"Clic pose {label} refusé.")
                self._wait(max(.08, self.settings.delay_between_dragons_ms / 1000))
                observed = self.stable_troop_count(window, label)
                # Never retry a drop whose outcome is unknown: that could deploy
                # another troop while counting only one, or click a changed menu.
                if observed is None:
                    if not live_scaled_client:
                        raise RuntimeError(f"Compteur de {label} non confirmé après le clic : arrêt de la pose.")
                    observed = remaining - 1
                    self.events.put(f"{label} : clic de pose suivi par décompte configuré (OCR indisponible).")
                if observed == remaining - 1:
                    placed += 1
                    remaining = observed
                    self.events.put(f"{label} confirmé à {x:.1f} %, {y:.1f} % ; {remaining} restant(s).")
                    accepted = True
                    break
                if observed != remaining:
                    raise RuntimeError(f"Quantité de {label} incohérente ({remaining} → {observed} pour un seul clic).")
                rejected.add((x, y))
            if not accepted: raise RuntimeError(f"Aucun point de pose accepté pour {label} ; {remaining} unité(s) restante(s).")
        return placed

    def stable_troop_count(self, window, label):
        previous = None
        try:
            with ocr_deadline(time.monotonic() + OCR_TIMEOUT):
                for _ in range(4):
                    image = self._battle_capture(window)
                    observed = read_troop_count(image, label)
                    self._trace("COMPTEUR", f"{label} : {observed}")
                    self._check_stopped()
                    if observed is not None and observed == previous:
                        return observed
                    previous = observed
                    self._wait(.04)
        except TimeoutError:
            return None
        return None

    def _battle_capture(self, window, allow_unselected_reward=False):
        image = self._capture(window)
        reward_open = battle_reward_open(image)
        final_reward = reward_open and isinstance(image, Image.Image) and has_screen_text(crop_percent(image, layout_roi("SCREEN_ROIS", "battle_reward")), "victoire")
        if not reward_open:
            self._reward_trace_at = 0
            self._reward_image_saved = False
        deadline = time.monotonic() + 30
        clicked = False
        chosen_label = None
        while reward_open:
            if battle_result_return_ready(image) and not final_reward:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Récompense de bataille toujours affichée après 30 secondes.")
            if not clicked:
                choice = battle_reward_choice(image)
                if choice is not None:
                    point, label = choice
                    self._trace("RÉCOMPENSE", f"Carte choisie : {label!r} à {point}")
                    if not self._click(window, *point):
                        raise RuntimeError("Sélection de la récompense refusée.")
                    clicked = True
                    chosen_label = label
                else:
                    if final_reward and not getattr(self, "_reward_image_saved", False):
                        journal = getattr(self, "journal", None)
                        if journal is not None:
                            try:
                                self._reward_image_saved = journal.save_reward_screen(image) is not None
                            except OSError as exc:
                                self._trace("RÉCOMPENSE", f"Capture du choix final impossible : {exc}")
                    now = time.monotonic()
                    if getattr(self, "journal", None) is not None and now >= getattr(self, "_reward_trace_at", 0):
                        try:
                            raw = read_text(crop_percent(image, Roi(23, 25, 77, 78)), scale=1)
                        except OperationCancelled:
                            raise
                        except Exception as exc:
                            raw = f"Lecture diagnostique impossible : {exc}"
                        self._trace("RÉCOMPENSE", f"Choix visible sans carte sûre ; texte lu={raw[:300]!r}")
                        self._reward_trace_at = now + 5
                if choice is None and allow_unselected_reward and not final_reward:
                    # After the army is deployed, an event offering only
                    # troop cards must not abort the result wait. The outer
                    # battle deadline keeps watching until the result appears.
                    return image
            self._wait(.15)
            image = self._capture(window)
            reward_open = battle_reward_open(image)
            final_reward = reward_open and isinstance(image, Image.Image) and has_screen_text(crop_percent(image, layout_roi("SCREEN_ROIS", "battle_reward")), "victoire")
        if chosen_label is not None and not reward_open:
            self.events.put(f"Récompense de l’événement sélectionnée : {chosen_label} ; fermeture du choix confirmée.")
        return image

    def deploy_attack_composition(self, window):
        self._check_stopped()
        perimeter = layout_points("ELECTRODRAGON_PERIMETER_POINTS")
        electro = self.deploy_unit(window, "Électro-dragon", layout_values("ELECTRODRAGON_SLOT"), perimeter, burst=True)
        dragons = self.deploy_unit(window, "Dragon", layout_values("DRAGON_SLOT"), perimeter, burst=True)
        heroes = 0
        if self.settings.deploy_heroes:
            self._check_stopped()
            shift = hero_layout_shift(self._battle_capture(window))
            for index, slot in enumerate(layout_points("HERO_SLOTS")):
                self._check_stopped()
                before = self._battle_capture(window)
                if hero_health_visible(before, index, shift):
                    heroes += 1
                    self.events.put(f"Héros {index + 1} déjà posé : barre de vie confirmée.")
                    continue
                if hero_placeholder_slot(before, index, shift):
                    self.events.put(f"Héros {index + 1} absent de la barre d’armée ; case vide ignorée.")
                    continue
                baseline = hero_icon_saturation(before, index, shift)
                if baseline < 55:
                    self.events.put(f"Héros {index + 1} indisponible ; non compté comme posé.")
                    continue
                slot_shift = 0 if f"HERO_SLOTS.{index}" in self.settings.layout_overrides else shift
                for offset in range(len(perimeter)):
                    self._check_stopped()
                    # A reward overlay or rejected drop can lose the selection.
                    # Recheck before selecting so an already deployed hero's
                    # ability is never deliberately clicked as a retry.
                    current = self._battle_capture(window)
                    if hero_health_visible(current, index, shift):
                        heroes += 1
                        self.events.put(f"Héros {index + 1} posé : barre de vie confirmée.")
                        break
                    if not self._click(window, slot[0] + slot_shift, slot[1]): raise RuntimeError(f"Sélection héros {index + 1} refusée.")
                    self._wait(.08)
                    self._check_stopped()
                    x, y = perimeter[(index * 3 + offset) % len(perimeter)]
                    if not self._click(window, x, y): raise RuntimeError(f"Clic héros {index + 1} refusé.")
                    self._wait(.12)
                    after = self._battle_capture(window)
                    if hero_health_visible(after, index, shift):
                        heroes += 1
                        self.events.put(f"Héros {index + 1} confirmé à {x:.1f} %, {y:.1f} %.")
                        break
                else: raise RuntimeError(f"Pose du héros {index + 1} non confirmée.")
        self._check_stopped()
        self.events.put(f"Déploiement vérifié : {electro} électro-dragons, {dragons} dragons, {heroes} héros.")

    def prepare_attack(self, window):
        self._capture(window)
        for step in range(16):
            with self.action_lock:
                self._check_stopped()
                self._trace("ZOOM", f"Dézoom {step + 1}/16 demandé")
                if not WindowDriver.zoom_out_step(window):
                    raise RuntimeError("Commande de dézoom refusée.")
                self._trace("ZOOM", f"Dézoom {step + 1}/16 envoyé")
            self._wait(.06)
        self._wait(.35)
        self._capture(window)
        self.events.put("Dézoom maximal envoyé avant le déploiement.")

    def wait_for_battle_return(self, window):
        """Wait for Clash's result screen, return home, then allow the next cycle."""
        # Google Play Games can leave a long attack/result transition on the
        # reduced VM window. Keep the worker alive long enough to observe the
        # real result instead of stopping while the game is still finishing.
        deadline=time.monotonic()+360
        next_progress = time.monotonic() + 15
        self.events.put("Attente de la fin de bataille avant le prochain cycle.")
        while not self.stop_event.is_set() and time.monotonic()<deadline:
            image=self._battle_capture(window, allow_unselected_reward=True)
            if isinstance(image, Image.Image) and battle_reward_open(image):
                self._wait(.35)
                continue
            if village_home_ready(image): return True
            if battle_result_return_ready(image) or has_screen_text(image,"retour au village","victoire","défaite"):
                self._trace("COMBAT", "Résultat reconnu ; lecture des gains puis retour au village")
                self.record_battle_earnings(window)
                self._click(window, *layout_values("RETURN_HOME_BUTTON")); self._wait(4)
            else:
                if time.monotonic() >= next_progress:
                    self._trace("COMBAT", f"Toujours en cours ; reste au plus {deadline-time.monotonic():.0f} s")
                    next_progress = time.monotonic() + 15
                self._wait(.35)
        self.events.put("Fin de bataille non confirmée : cycle arrêté sans cliquer Terminer la bataille."); return False

    def record_battle_earnings(self, window):
        stats = getattr(self, "farm_stats", None)
        if stats is None or not stats.data.get("pending"):
            return
        self._wait(1.5)  # Let the result counters finish their animation.
        previous = None
        for _ in range(5):
            result_image = self._battle_capture(window)
            amounts = read_battle_earnings(result_image)
            self._trace("BUTIN FINAL", f"Lecture des gains : {amounts}")
            if amounts is not None and amounts == previous:
                if stats.finish(amounts):
                    self.events.put(StatsEvent(dict(stats.data)))
                    self.events.put(f"Récolte comptabilisée : {amounts[0]:,} or, {amounts[1]:,} élixir, {amounts[2]:,} élixir noir (bonus inclus).")
                return
            previous = amounts
            self._wait(.35)
        self._check_stopped()
        archived = stats.defer_result(result_image)
        self.events.put(f'Butin final illisible : capture conservée dans {archived}. Gains non ajoutés aux statistiques ; reprise du cycle.')

    def open_search(self, window):
        def dismiss_daily_reward():
            image = self._capture(window)
            if daily_reward_open(image):
                if not self._click(window, *layout_values("DAILY_REWARD_CLOSE_BUTTON")): raise RuntimeError("Fermeture de la récompense quotidienne refusée.")
                self._wait(.7)
                self.events.put("Fenêtre de récompense quotidienne fermée.")

        dismiss_daily_reward()
        for point, label, expected in (
            (layout_values("ATTACK_HOME_BUTTON"), "Ouverture du menu Attaquer", "multijoueur"),
            (layout_values("FIND_MATCH_BUTTON"), "Ouverture de la s?lection d'arm?e", "mon arm?e"),
        ):
            header = Roi(2,2,50,12) if expected == "multijoueur" else Roi(20,0,80,20)
            confirmed = False
            for click_attempt in range(2):
                if not self._click(window, *point): raise RuntimeError(f"Clic refus? : {label}.")
                if click_attempt == 0:
                    self.events.put(label)
                for attempt in range(5):
                    self._wait(1 if attempt == 0 else .6)
                    if self.stop_event.is_set(): return False
                    dismiss_daily_reward()
                    screen = self._capture(window)
                    screen_ready = has_screen_text(screen, expected) or has_screen_text(crop_percent(screen, header), expected)
                    if expected == "multijoueur":
                        # Recent Google Play Games builds open the army panel first
                        # and omit the literal "Multijoueur" heading.
                        screen_ready = screen_ready or any(has_screen_text(screen, marker) for marker in ("mon armee", "formez", "puissante armee", "attaquer"))
                    elif expected == "mon arm?e":
                        # OCR may miss the heading while the army panel is open;
                        # its recipe controls remain a reliable secondary marker.
                        screen_ready = screen_ready or has_screen_text(screen, "recettes")
                    if screen_ready:
                        confirmed = True
                        break
                if confirmed:
                    break
            if not confirmed:
                raise RuntimeError(f"?cran attendu absent apr?s : {label}.")
        if not self._click(window, *layout_values("START_SEARCH_BUTTON")): raise RuntimeError("Clic de recherche refusé.")
        self.events.put("Recherche d'une base adverse")
        deadline = time.monotonic() + 35
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            self._wait(1)
            image = self._capture(window)
            if enemy_loot_screen_ready(image): return True
            if daily_reward_open(image):
                dismiss_daily_reward()
                raise RuntimeError("Récompense quotidienne apparue pendant la recherche ; relancer le farm.")
        if self.stop_event.is_set(): return False
        raise RuntimeError("Base adverse non affichée après 35 secondes de recherche.")

    def farm_loop(self):
        """Prepare, find a valid base, deploy the configured army, then repeat."""
        try:
            while not self.stop_event.is_set():
                window=WindowDriver.resolve(self.settings.window_title)
                if not window: raise RuntimeError("Fenêtre Clash introuvable.")
                self._trace("CYCLE", f"Fenêtre sélectionnée : {getattr(window,'title','?')!r}, {getattr(window,'width','?')}x{getattr(window,'height','?')}; simulation={self.settings.dry_run}")
                stats = getattr(self, "farm_stats", None)
                if stats and stats.data.get("pending"):
                    if stats.data["pending"]["window_title"] != window.title:
                        raise RuntimeError("Revenir au compte du combat en attente pour comptabiliser son butin.")
                    if not village_home_ready(self._capture(window)):
                        if not self.wait_for_battle_return(window): return
                        if not self.settings.chain_attacks: return
                    else:
                        self.events.put("Résultat du combat précédent absent : sa récolte ne peut pas être comptabilisée.")
                        stats.clear_pending()
                if not self.settings.dry_run:
                    self._trace("CYCLE", "Étape 1 : collecte des mines et extracteurs")
                    self.collect_village_resources(window)
                else:
                    self._trace("CYCLE", "Collecte ignorée : simulation active")
                if self.settings.upgrade_recommended and not self.settings.dry_run:
                    self._trace("CYCLE", "Étape 2 : bâtiments par prix décroissant, Hôtel de ville exclu")
                    from upgrades import upgrade_suggested
                    upgrade_suggested(self, window)
                else:
                    self._trace("CYCLE", "Bâtiments ignorés : option désactivée ou simulation active")
                self._trace("CYCLE", "Étape 3 : remparts avec le dernier ouvrier et réserve de 1 M")
                self.upgrade_walls_to_reserve(window)
                self._trace("CYCLE", "Étape 4 : recherche d'une base adverse")
                # A slow result transition can leave the game on the victory
                # screen when the next cycle starts. Return to the village
                # before sending the attack click; otherwise the click lands
                # on the result screen and the search is falsely reported as
                # broken.
                capture = self._capture if isinstance(window, GameWindow) else None
                current = capture(window) if capture is not None else None
                if isinstance(current, Image.Image) and not village_home_ready(current):
                    if battle_result_return_ready(current) or has_screen_text(current, "butin disponible", "fin de la bataille", "retour au village"):
                        self._trace("COMBAT", "Résultat encore affiché avant le cycle suivant ; retour au village demandé")
                        self._click(window, *layout_values("RETURN_HOME_BUTTON"))
                        self._wait(4)
                    current = capture(window)
                    if not village_home_ready(current):
                        self.events.put("Cycle reporté : le village n'est pas encore revenu après la bataille.")
                        self._wait(2)
                        continue
                if self.stop_event.is_set() or not self.open_search(window): return
                if not self.find_suitable_base(window): return
                self._check_stopped()
                if self.settings.dry_run:
                    self.events.put("Simulation : base retenue ; aucune troupe ni amélioration n'est envoyée."); return
                self.prepare_attack(window)
                if stats: stats.begin(window.title)
                try:
                    self.deploy_attack_composition(window)
                except OperationCancelled:
                    raise
                except RuntimeError as exc:
                    # A failed deployment must not abandon event handling or
                    # the result screen while a real battle is still running.
                    self._trace("ERREUR", traceback.format_exc())
                    self.events.put("Déploiement interrompu. Suivi du combat jusqu'au résultat ; détail dans le diagnostic.")
                    self.wait_for_battle_return(window)
                    return
                if not self.wait_for_battle_return(window) or not self.settings.chain_attacks: return
        except ReconnectRequired: raise
        except OperationCancelled: self.events.put("Recherche interrompue.")
        except Exception as exc:
            self._trace("ERREUR", traceback.format_exc())
            self.events.put("Recherche arrêtée à cause d'une erreur. Exportez le diagnostic pour le détail.")
        finally:
            if not getattr(self,'_reconnect_pending',False):
                self.stop_event.set(); self.events.put("Bot arrêté.")

    def find_suitable_base(self, window):
        deadline = time.monotonic() + BASE_READ_TIMEOUT
        while not self.stop_event.is_set():
            if time.monotonic() >= deadline:
                # Never confuse a running fight or a dialog with matchmaking.
                fresh = self._capture(window)
                if enemy_loot_screen_ready(fresh) and has_screen_text(crop_percent(fresh, Roi(85,69,100,83)), "suivant"):
                    archive = APP_DIR / "unread-enemies"
                    archive.mkdir(parents=True, exist_ok=True)
                    fresh.save(archive / f"{time.time_ns()}.png")
                    if not self._click(window, *layout_values("NEXT_BASE_BUTTON")):
                        raise RuntimeError("Clic Suivant refusé après butin illisible.")
                    self.events.put("Butin illisible : capture conservée, passage à la base suivante et poursuite de la recherche.")
                    deadline = time.monotonic() + BASE_READ_TIMEOUT
                    self._wait(3)
                    continue
                raise TimeoutError("Écran ou butin illisible : bouton Suivant non confirmé, aucun clic envoyé.")
            try:
                with ocr_deadline(deadline):
                    image = self._capture(window)
                    if not enemy_loot_screen_ready(image):
                        if daily_reward_open(image):
                            raise RuntimeError("Récompense quotidienne affichée pendant le choix de base.")
                        self.events.put("Attente de l'affichage complet de la base adverse.")
                        self._wait(.5)
                        continue
                    loot = read_enemy_loot(image)
                    self._trace("BUTIN OCR", json.dumps(loot.raw, ensure_ascii=False))
            except TimeoutError:
                self._check_stopped()
                self._wait(.1)
                continue
            self._check_stopped()
            if time.monotonic() >= deadline:
                continue  # The next iteration checks whether Suivant is safe.
            accepted, gold_minimum, elixir_minimum = loot_is_accepted(loot.gold or 0, loot.elixir or 0, self.settings)
            known_enough = (loot.gold is not None and loot.elixir is not None) or (not self.settings.use_and_rule and (
                (loot.gold is not None and loot.gold >= gold_minimum) or
                (loot.elixir is not None and loot.elixir >= elixir_minimum)))
            if not known_enough:
                self.events.put(f"Butin adverse illisible (or={loot.gold}, élixir={loot.elixir}) : nouvelle lecture, sans clic.")
                self._wait(1)
                continue
            gold_text = f"{loot.gold:,}" if loot.gold is not None else "illisible"
            elixir_text = f"{loot.elixir:,}" if loot.elixir is not None else "illisible"
            self.events.put(f"Base adverse : or {gold_text}, élixir {elixir_text} | seuils avec marge : {gold_minimum:,}/{elixir_minimum:,} → {'attaque' if accepted else 'suivant'}.")
            if accepted:
                return True
            if not self._click(window, *layout_values("NEXT_BASE_BUTTON")):
                raise RuntimeError("Clic Suivant refusé.")
            # The read budget belongs to one base; only a new search resets it.
            deadline = time.monotonic() + BASE_READ_TIMEOUT
            self._wait(3)
        return False

    def _pump(self):
        self._cancel_pump()
        try:
            for _ in range(100):
                event = self.events.get_nowait()
                if isinstance(event, PreviewEvent):
                    if not self.stop_event.is_set():
                        self.window_title.set(event.title)
                        self._show_preview(event.image)
                        if event.calibrate: self._show_calibration(event.image)
                elif isinstance(event, StatsEvent):
                    for key, variable in self.stats_vars.items():
                        variable.set(f"{event.totals[key]:,}".replace(",", " "))
                    self.stats_count.set(f"{event.totals['battles']} combat(s) comptabilisé(s) · cumul sauvegardé")
                elif isinstance(event, RunStateEvent):
                    self.run_state.set({"erreur": "ERREUR", "interrompue": "ARRÊT", "terminée": "PRÊT"}.get(event.status, "PRÊT"))
                else:
                    self.write(event, record=False)
        except queue.Empty:pass
        running=self._busy()
        self.start_button.state(["disabled"] if running else ["!disabled"])
        self.walls_button.state(["disabled"] if running else ["!disabled"])
        self.reset_data_button.state(["disabled"] if running else ["!disabled"])
        self.stop_button.state(["!disabled"] if running else ["disabled"])
        for button in (self.inspect_button, self.profile_button, self.save_button, self.calibrate_button):
            button.state(["disabled"] if running else ["!disabled"])
        for button in getattr(self,'independent_buttons',[]):
            button.state(['disabled'] if running else ['!disabled'])
        if not running and self.run_state.get() in ("EN COURS", "LECTURE"): self.run_state.set("PRÊT")
        self._pump_after = self.root.after(250,self._pump)
    def write(self, text, record=True):
        if record:
            self._trace("INTERFACE", text)
        self.status.set(text)
        self.log.configure(state="normal")
        self.log.insert("end", text+"\n")
        self.log.see("end")
        self.log.configure(state="disabled")
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
    image = WindowDriver.capture(window)
    if connection_retry_point(image) is not None:
        raise RuntimeError("Jeu déconnecté : recharger Clash avant le test de profil.")
    snapshot = read_complete_account_snapshot(image, lambda: WindowDriver.capture(window))
    required = (snapshot.account_name, snapshot.level, snapshot.gold, snapshot.elixir, snapshot.dark_elixir, snapshot.gems, snapshot.laboratory_builders, snapshot.builders)
    if any(value is None for value in required): raise RuntimeError(f"Relevé incomplet : {asdict(snapshot)}")
    print(json.dumps(asdict(snapshot), ensure_ascii=False))


def self_test_report(path):
    """Exercise packaged imports/OCR and identify the exact embedded sources."""
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False))}
    try:
        metadata_path = Path(__file__).with_name("build_info.json")
        if metadata_path.exists():
            report["build"] = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
        self_test()
        validate_layout(Settings())
        report["ok"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CoC Farm Bot")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--profile-test", action="store_true")
    parser.add_argument("--self-test-report", metavar="JSON")
    args = parser.parse_args()
    if args.self_test_report:
        sys.exit(self_test_report(args.self_test_report))
    elif args.profile_test:
        profile_test()
    elif args.self_test:
        self_test()
    else:
        from modern_dashboard import run
        run()
