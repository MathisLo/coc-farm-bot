"""CoC Farm Bot: capture Windows et commandes en arrière-plan."""
from __future__ import annotations

import asyncio
import argparse
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
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, ttk, messagebox

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, ImageStat, ImageTk
from calibration import CalibrationDialog, validate_overrides
from farm_stats import FarmStats

APP_DIR = Path.home() / "CoCFarmBot"
CONFIG_PATH = APP_DIR / "config-v2.json"
LOG_PATH = APP_DIR / "bot.log"
ACCOUNT_SNAPSHOT_PATH = APP_DIR / "account_snapshot.json"
STATS_PATH = APP_DIR / "farm-stats.json"
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
def operation_context(stop_event, settings):
    previous = vars(_operation).copy()
    _operation.stop_event = stop_event
    _operation.settings = settings
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
    version: int = 7
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
    "Électro-dragon": Roi(23.7, 85.19, 26.3, 89.35),
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
        data["version"] = 7
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
    for scale in (3, 5):
        raw = read_text(white_text_mask(counter), scale=scale).casefold().translate(str.maketrans({"o": "0", "l": "1", "i": "1"}))
        match = re.fullmatch(r"[x×]\s*(\d{1,2})", raw.strip())
        if match:
            return int(match.group(1))
    for shift in (0, .5, 1, -.5, -1):
        for top in (roi.y1, roi.y1 - .46):
            candidate = Roi(max(0, roi.x1 + shift), max(0, top), min(100, roi.x2 + shift), min(100, roi.y2))
            if not candidate.valid(): continue
            crop = crop_percent(image, candidate)
            for variant in (crop, ImageOps.grayscale(crop)):
                raw = read_text(variant, scale=5).casefold().translate(str.maketrans({"o": "0", "l": "1", "i": "1"}))
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


def village_home_ready(image: Image.Image) -> bool:
    return (connection_retry_point(image) is None
            and has_screen_text(crop_percent(image, Roi(0, 82, 20, 100)), "attaquer")
            and has_screen_text(crop_percent(image, Roi(85, 82, 100, 100)), "magasin"))


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
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as file: path = Path(file.name)
    try:
        image.save(path)
        return [(word, x * 100 / image.width, y * 100 / image.height) for word, x, y in asyncio.run(bounded_ocr(_ocr_words_file(str(path))))]
    finally: path.unlink(missing_ok=True)


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
    if not builders_menu_open(image):
        return None
    menu_roi = layout_roi("SCREEN_ROIS", "wall_menu")
    menu = crop_percent(image, menu_roi)
    for scale in (1,2):
        for word, x, y in read_word_centers(menu.resize((menu.width*scale,menu.height*scale))):
            if word.casefold().startswith(("rempar", "rempamt")) and x < 65:
                point=(menu_roi.x1 + x * (menu_roi.x2 - menu_roi.x1) / 100,
                       menu_roi.y1 + y * (menu_roi.y2 - menu_roi.y1) / 100)
                if wall_menu_row_matches(image,point[1]):
                    return point
    # A selected wall shifts the camera and the full-screen OCR can lose the
    # row even though a narrow crop still reads "Rempart x…" clearly.
    exact_rows = []
    partial_rows = []
    for y in range(math.ceil(menu_roi.y1 + 3), math.floor(menu_roi.y2 - 3) + 1, 2):
        row = read_text(crop_percent(image, Roi(menu_roi.x1, y - 3, menu_roi.x2, y + 3)), scale=2).casefold()
        if "rempar" in row:
            if re.search(r"x\s*\d{1,3}\b", row):
                exact_rows.append(y)
            else:
                partial_rows.append(y)
    rows = [y for y in exact_rows if wall_menu_row_matches(image,y)]
    return ((menu_roi.x1 + menu_roi.x2) / 2, float(rows[len(rows) // 2])) if rows else None


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
    for offset in (0, 2, -2):
        roi = Roi(max(0, x - 4), max(0, y + offset - 2.5), min(100, x + 9), min(100, y + offset + 2.5))
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
    return "remp" in text and any(token in text for token in ("aj", "aiou", "supp", "rimer"))


def wall_price_readings(image, expected=None):
    readings = []
    for variant in (image, white_text_mask(image)):
        for scale in (2, 3):
            raw = read_text(variant, scale=scale).strip(" +.,'\"*[]()").replace('O', '0').replace('o', '0')
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
            if target is not None and not any(abs(px-x)<.5 for px,py in target):
                target.append((x,y))
    payments = {}
    for x,y in upgrades:
        resource = resource_icon(image,Roi(x+2,y-9.2,x+3.7,y-6.4))
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
        # A lone larger OCR artifact must not overrule repeated complete
        # readings (600 000 can coexist with one spurious 6 601 000).
        if price is None and not readings:
            for price_crop in price_crops:
                price = read_result_amount(price_crop,main_result=True)
                if price is not None:
                    break
        if price is not None and price > 0:
            if resource in payments:
                return None
            payments[resource] = ((x,y-3),price)
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
        return {'add':(add_x,add_y), 'remove':remove, 'payments':payments}
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
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as file: path = Path(file.name)
    try:
        image.resize((image.width * 3, image.height * 3)).save(path)
        digits = re.sub(r"[^0-9]", "", asyncio.run(bounded_ocr(_ocr_file(str(path)))))
        return int(digits) if digits else None
    finally: path.unlink(missing_ok=True)


def read_text(image: Image.Image, scale: int = 5) -> str:
    """OCR a local UI crop while keeping the raw reading for diagnostics."""
    check_cancelled()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as file: path = Path(file.name)
    try:
        image.resize((image.width * scale, image.height * scale)).save(path)
        return asyncio.run(bounded_ocr(_ocr_file(str(path)))).strip()
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


def read_account_snapshot(image: Image.Image) -> AccountSnapshot:
    raw = {key: read_text(crop_percent(image, layout_roi("PROFILE_ROIS", key))) for key in PROFILE_ROIS}
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
    readings = {key: read_resource_number(crop_percent(image, layout_roi("ENEMY_LOOT_ROIS", key))) for key in ENEMY_LOOT_ROIS}
    return EnemyLoot(gold=readings["gold"][0], elixir=readings["elixir"][0], dark_elixir=readings["dark_elixir"][0], raw={key: text for key, (_, text) in readings.items()})


def enemy_loot_screen_ready(image: Image.Image) -> bool:
    label = read_text(crop_percent(image, layout_roi("ENEMY_LOOT_LABEL_ROI")), scale=2).casefold()
    return "butin" in label or "disponible" in label or "loot" in label


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
        message=read_text(crop_percent(image,Roi(28,46,70,51)),scale=1).casefold()
        button=read_text(crop_percent(image,Roi(28,54,45,59)),scale=1).casefold()
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
    bonus = [read_result_amount(crop_percent(image, roi)) for roi in bonus_rois]
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
    for edge_y, label_top, label_bottom, click_y in ((30.5, 52, 66, 53.), (33.4, 63, 74, 60.)):
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
    if layout is None:
        return None
    label_top, label_bottom, click_y = layout
    tickets = None
    for x in centers:
        readings = [read_text(crop_percent(image, Roi(x-7, label_top, x+7, label_bottom)), scale=scale) for scale in (2,1)]
        for raw in readings:
            text = "".join(c for c in unicodedata.normalize("NFD", raw.casefold()) if unicodedata.category(c) != "Mn")
            if re.search(r"\b[o0]r\b|\belixir\b", text):
                return (x, click_y), raw
            if re.search(r"\btickets?\b", text):
                tickets = ((x, click_y), raw)
    return tickets  # An unreadable card or a troop never authorises a click.


class BotApp:
    def __init__(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format="%(asctime)s %(message)s", encoding="utf-8")
        self.settings = load_settings()
        self.root = Tk()
        self.root.title("CoC Farm Bot")
        self.root.geometry("1200x900")
        self.root.minsize(1040, 860)
        self.events = queue.Queue()
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

    def _check_stopped(self):
        if self.stop_event.is_set():
            raise OperationCancelled("Arrêt demandé.")

    def _capture(self, window):
        self._check_stopped()
        image = WindowDriver.capture(window)
        self._check_stopped()
        if connection_retry_point(image) is not None:
            self._reconnect_pending = True
            raise ReconnectRequired()
        return image

    def _click(self, window, x, y):
        # Stop and click share a lock: after stop() returns no new press is sent.
        with self.action_lock:
            self._check_stopped()
            return WindowDriver.click_percent(window, x, y)

    def _wait(self, seconds):
        if self.stop_event.wait(seconds):
            raise OperationCancelled("Arrêt demandé.")
        return False

    def _run_operation(self, target):
        try:
            validate_layout(self.settings)
            while not self.stop_event.is_set():
                try:
                    with operation_context(self.stop_event, self.settings):
                        target()
                    break
                except ReconnectRequired:
                    with operation_context(self.stop_event, self.settings):
                        self.reconnect_game()
                    self._reconnect_pending = False
        except OperationCancelled:
            self.events.put("Opération interrompue.")
        except Exception as exc:
            self.events.put(f"Opération arrêtée : {exc}")
        finally:
            self._reconnect_pending = False

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
        self.stop()
        self.root.destroy()

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

    def _show_calibration(self, image):
        if self.calibration_dialog:
            self.calibration_dialog.set_image(image)
            return
        def save(overrides, ratio):
            # Do not save a moving target while a refresh is still in flight.
            if self.inspection_worker and self.inspection_worker.is_alive():
                raise ValueError("Attendre la fin de l’actualisation avant d’enregistrer.")
            candidate = replace(self.settings, layout_overrides=overrides, layout_aspect_ratio=ratio)
            validate_layout(candidate)
            save_settings(candidate)
            self.settings = candidate
            self.write(f"Calibrage enregistré : {len(overrides)} position(s) personnalisée(s).")
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
        except Exception as exc: self.events.put(f"Lecture impossible : {exc}")

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
            snapshot = read_account_snapshot(image); APP_DIR.mkdir(parents=True, exist_ok=True)
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
        except Exception as exc: self.events.put(f"Relevé du profil impossible : {exc}")

    def persist(self):
        if self._busy():
            self.write("Arrêter l’opération avant de changer les réglages.")
            return False
        try:
            candidate = replace(self.settings, window_title=self.window_title.get(),
                min_gold=int(self.min_gold.get().replace(" ", "")), min_elixir=int(self.min_elixir.get().replace(" ", "")),
                loot_margin_percent=float(self.loot_margin.get().replace(",", ".")),
                electrodragon_count=int(self.electrodragon_count.get()), dragon_count=int(self.dragon_count.get()),
                use_and_rule=self.and_rule.get(), dry_run=self.dry_run.get(), deploy_heroes=self.deploy_heroes.get(),
                upgrade_wall_between_attacks=self.upgrade_wall.get(), upgrade_recommended=self.upgrade_recommended.get(), chain_attacks=self.chain_attacks.get())
            if not 0 <= candidate.min_gold <= 2_500_000 or not 0 <= candidate.min_elixir <= 2_500_000 or not 0 <= candidate.loot_margin_percent <= 25 or not 0 <= candidate.electrodragon_count <= 50 or not 0 <= candidate.dragon_count <= 50: raise ValueError
            save_settings(candidate)
            self.settings = candidate
            self.write(f"Configuration enregistrée : attaque dès {effective_minimum(candidate.min_gold, candidate.loot_margin_percent):,} or / {effective_minimum(candidate.min_elixir, candidate.loot_margin_percent):,} élixir.")
            return True
        except ValueError: messagebox.showerror("Valeur invalide","Seuils : 0 à 2 500 000 ; marge : 0 à 25 % ; troupes : 0 à 50.");return False
        except OSError as exc: messagebox.showerror("Sauvegarde impossible", str(exc)); return False
    def start_farm(self):
        if self._busy(): return
        if not self.persist(): return
        if self.settings.dry_run: self.write("Simulation active : recherche et lecture uniquement, aucune pose ne sera envoyée.")
        else: self.write("Mode réel actif : toutes les troupes disponibles seront posées et vérifiées sur une base retenue.")
        self.stop_event.clear(); self.worker=threading.Thread(target=self._run_operation,args=(self.farm_loop,),daemon=True); self.worker.start(); self.run_state.set("EN COURS"); self.write("Recherche automatique démarrée.")
    def start_walls(self):
        if self._busy(): return
        if not self.persist(): return
        self.stop_event.clear(); self.worker=threading.Thread(target=self._run_operation,args=(self.wall_loop,),daemon=True); self.worker.start(); self.run_state.set("EN COURS"); self.write("Amélioration des remparts démarrée.")

    def start_independent(self, action):
        if self._busy() or not self.persist():
            return
        self.stop_event.clear()
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
        except Exception as exc: self.events.put(f"Remparts arrêtés : {exc}")
        finally:
            if not getattr(self,'_reconnect_pending',False):
                self.stop_event.set(); self.events.put("Amélioration des remparts terminée.")

    def stable_reserves(self, window):
        """Require two agreeing home-village readings before authorising spending."""
        previous = None
        for _ in range(5):
            image = self._capture(window)
            values = (read_safe_reserve(image, "gold"), read_safe_reserve(image, "elixir"))
            if None not in values and previous is not None and all(abs(a - b) <= 20_000 for a, b in zip(values, previous)):
                return tuple(min(a, b) for a, b in zip(values, previous))
            previous = values if None not in values else None
            if self._wait(.4): break
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
        for _ in range(16 if price_above is not None else 8):
            controls = wall_group_controls(self._capture(window),single=single,
                                           expected_price=expected_price,expected_resource=resource)
            if controls is not None and resource is not None and resource not in controls["payments"]:
                controls = None
            if (controls is not None and price_above is not None and
                    controls['payments'][resource][1] <= price_above):
                controls = None
            if controls is not None and previous is not None:
                same_prices = {r:p[1] for r,p in controls['payments'].items()} == {r:p[1] for r,p in previous['payments'].items()}
                same_add = single or all(abs(a-b)<.5 for a,b in zip(controls['add'],previous['add']))
                if same_prices and same_add:
                    return controls
            previous = controls
            self._wait(.15)
        return None

    def upgrade_walls_to_reserve(self, window, independent=False):
        """Upgrade available walls while keeping both village reserves at or above 1 M."""
        if (not independent and not self.settings.upgrade_wall_between_attacks) or self.settings.dry_run:
            return 0
        if not independent and self.settings.upgrade_recommended:
            from upgrades import stable_builders
            free = stable_builders(self, window)
            if free is None or free < 1:
                self.events.put(f'Ouvriers libres={free} : remparts reportés faute d’ouvrier confirmé.')
                return 0
        upgraded = 0
        while not self.stop_event.is_set():
            balances = self.stable_reserves(window)
            if balances is None:
                self.events.put("Réserves instables ou illisibles : aucune dépense envoyée.")
                return upgraded
            gold, elixir = balances
            if gold <= WALL_RESERVE and elixir <= WALL_RESERVE:
                self.events.put(f"Réserves préservées : or {gold:,}, élixir {elixir:,}.")
                return upgraded
            menu = self._capture(window)
            if not builders_menu_open(menu):
                self._wall_click(window, layout_values("BUILDERS_BUTTON"), "ouvriers")
            available = None
            for _ in range(16):
                menu = self._capture(window)
                item = find_wall_menu_item(menu)
                available = read_wall_available(menu, item) if item else None
                if item and available is None:
                    available = 1  # Select and verify only one wall when xN is unreadable.
                if available is not None: break
                if builders_menu_open(menu):
                    with self.action_lock:
                        self._check_stopped()
                        if not WindowDriver.scroll_menu(window):
                            raise RuntimeError('Défilement des remparts refusé.')
                if self._wait(.4): break
            if self.stop_event.is_set() or item is None or available is None:
                self.events.put("Liste des remparts indisponible ou illisible : arrêt prudent.")
                return upgraded
            selected = False
            for _ in range(3):
                # Opening/closing a dialog can reset the menu scroll position.
                # Never reuse the row retained before reading its quantity.
                current_item = find_wall_menu_item(self._capture(window))
                if current_item is None:
                    self._wait(.4)
                    continue
                item = current_item
                self._wall_click(window, item, "rempart")
                wall_image = self._capture(window)
                if wall_selected(wall_image) or (available == 1 and wall_group_controls(wall_image,single=True) is not None):
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
            if controls is None:
                raise RuntimeError("Boutons du groupe de remparts non confirmés : cycle arrêté avant l’attaque.")
            payments = controls['payments']
            gold_cost = payments.get('or', (None,None))[1]
            elixir_cost = payments.get('élixir', (None,None))[1]
            options = [(wall_batch_size(gold if resource=='or' else elixir,price,available),resource,price)
                       for resource,(_,price) in payments.items()]
            count, resource, unit_cost = max(options, key=lambda option:(option[0],gold if option[1]=='or' else elixir))
            if count == 0:
                self.events.put(f"Aucun rempart payable en conservant 1 M : or {gold:,}, élixir {elixir:,}.")
                return upgraded
            selected_count = 1
            while selected_count < count:
                # Each addition can remove +10 and shift the whole row.
                # Wait for a price change, not just two stale but matching
                # frames after the click. A click without effect can be retried
                # only while the same group and price are still confirmed.
                previous_total = selected_count*unit_cost
                for attempt in range(3):
                    self._wall_click(window, controls['add'], "ajouter un rempart identifié")
                    changed = self.stable_wall_group(window, resource, single=single,
                                                     price_above=previous_total,expected_price=previous_total+unit_cost)
                    if changed is not None:
                        controls = changed
                        break
                    current = self.stable_wall_group(window, resource, single=single)
                    current_payment = current['payments'].get(resource) if current else None
                    if current_payment is None:
                        raise RuntimeError("Groupe de remparts illisible après Ajouter : cycle arrêté avant l’attaque.")
                    if current_payment[1] != previous_total:
                        if current_payment[1] > previous_total:
                            controls = current
                            break
                        raise RuntimeError("Prix du groupe incohérent après Ajouter : cycle arrêté avant l’attaque.")
                    if attempt == 2:
                        raise RuntimeError("Ajouter un rempart sans effet après trois essais : cycle arrêté avant l’attaque.")
                    controls = current
                    self.events.put("Ajouter un rempart sans effet confirmé : nouvel essai avant toute dépense.")
                    self._wait(.6)
                payment = controls['payments'].get(resource) if controls else None
                observed_total = payment[1] if payment else None
                observed_count, remainder = divmod(observed_total, unit_cost) if observed_total else (0, 0)
                if remainder or not selected_count < observed_count <= count:
                    raise RuntimeError(f"Ajout de rempart non confirmé : prix lu={observed_total}, prix unitaire={unit_cost}, quantité précédente={selected_count}, maximum payable={count}. Cycle arrêté avant l’attaque.")
                selected_count = observed_count
            total = selected_count*unit_cost
            fresh = self.stable_reserves(window)
            if fresh is None or min(fresh) < WALL_RESERVE or fresh[0 if resource=='or' else 1]-total < WALL_RESERVE:
                raise RuntimeError("Réserves insuffisantes ou incertaines : aucune dépense envoyée, cycle arrêté avant l’attaque.")
            gold, elixir = fresh
            controls = self.stable_wall_group(window, resource, single=single,expected_price=total)
            payment = controls['payments'].get(resource) if controls else None
            if payment is None or payment[1] != total:
                raise RuntimeError("Bouton de paiement ou coût modifié : aucune dépense envoyée, cycle arrêté avant l’attaque.")
            self._wall_click(window, payment[0], f"amélioration groupée {resource} identifiée")
            confirmation=self._capture(window)
            matches = single_wall_confirmation_matches(confirmation,total,resource) if single else wall_batch_confirmation_matches(confirmation,total,resource)
            if self.stop_event.is_set() or not matches:
                raise RuntimeError("Montant, rempart ou ressource de la confirmation non vérifié : cycle arrêté avant l’attaque.")
            confirm_button = "WALL_CONFIRM_BUTTON" if single else "WALL_MULTI_CONFIRM_BUTTON"
            self._wall_click(window, layout_values(confirm_button), "confirmation remparts")
            self._wait(.8)
            after = self.stable_reserves(window)
            before_spend = gold if resource == "or" else elixir
            after_spend = after[0] if resource == "or" and after else (after[1] if after else None)
            if after_spend is None or abs(before_spend - after_spend - total) > 50_000:
                raise RuntimeError("Dépense groupée non vérifiée sur les réserves : cycle arrêté avant l’attaque.")
            if after[0] < WALL_RESERVE or after[1] < WALL_RESERVE:
                raise RuntimeError("Une réserve est passée sous le plancher : cycle arrêté avant l’attaque.")
            upgraded += count
            self.events.put(f"{count} rempart(s) amélioré(s) avec {total:,} {resource} ({upgraded} au total).")
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
        if remaining is None: raise RuntimeError(f"Quantité de {label} illisible : pose non vérifiable.")
        if remaining == 0: return 0
        initial = remaining
        expected = self.settings.electrodragon_count if label == "Électro-dragon" else self.settings.dragon_count
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
                    raise RuntimeError(f"Compteur de {label} non confirmé après le clic : arrêt de la pose.")
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
                    self._check_stopped()
                    if observed is not None and observed == previous:
                        return observed
                    previous = observed
                    self._wait(.04)
        except TimeoutError:
            return None
        return None

    def _battle_capture(self, window):
        image = self._capture(window)
        deadline = time.monotonic() + 12
        clicked = False
        chosen_label = None
        while battle_reward_open(image):
            if time.monotonic() >= deadline:
                raise RuntimeError("Récompense de bataille toujours affichée après 12 secondes.")
            if not clicked:
                choice = battle_reward_choice(image)
                if choice is not None:
                    point, label = choice
                    if not self._click(window, *point):
                        raise RuntimeError("Sélection de la récompense refusée.")
                    clicked = True
                    chosen_label = label
            self._wait(.15)
            image = self._capture(window)
        if chosen_label is not None:
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
        for _ in range(16):
            with self.action_lock:
                self._check_stopped()
                if not WindowDriver.zoom_out_step(window):
                    raise RuntimeError("Commande de dézoom refusée.")
            self._wait(.06)
        self._wait(.35)
        self._capture(window)
        self.events.put("Dézoom maximal envoyé avant le déploiement.")

    def wait_for_battle_return(self, window):
        """Wait for Clash's result screen, return home, then allow the next cycle."""
        deadline=time.monotonic()+240
        self.events.put("Attente de la fin de bataille avant le prochain cycle.")
        while not self.stop_event.is_set() and time.monotonic()<deadline:
            image=self._battle_capture(window)
            if village_home_ready(image): return True
            if has_screen_text(image,"retour au village","victoire","défaite"):
                self.record_battle_earnings(window)
                self._click(window, *layout_values("RETURN_HOME_BUTTON")); self._wait(4)
            else: self._wait(.35)
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
            (layout_values("FIND_MATCH_BUTTON"), "Ouverture de la sélection d'armée", "mon armée"),
        ):
            if not self._click(window, *point): raise RuntimeError(f"Clic refusé : {label}.")
            self.events.put(label); self._wait(1)
            if self.stop_event.is_set(): return False
            dismiss_daily_reward()
            screen = self._capture(window)
            header = Roi(2,2,50,12) if expected == "multijoueur" else Roi(20,0,80,20)
            if not has_screen_text(screen, expected) and not has_screen_text(crop_percent(screen, header), expected):
                raise RuntimeError(f"Écran attendu absent après : {label}.")
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
                    self.collect_village_resources(window)
                if self.settings.upgrade_recommended and not self.settings.dry_run:
                    from upgrades import upgrade_suggested
                    upgrade_suggested(self, window)
                self.upgrade_walls_to_reserve(window)
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
                    self.events.put(f"Déploiement interrompu : {exc} Suivi du combat jusqu’au résultat.")
                    self.wait_for_battle_return(window)
                    return
                if not self.wait_for_battle_return(window) or not self.settings.chain_attacks: return
        except ReconnectRequired: raise
        except OperationCancelled: self.events.put("Recherche interrompue.")
        except Exception as exc: self.events.put(f"Recherche arrêtée : {exc}")
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
                else:
                    self.write(event)
        except queue.Empty:pass
        running=self._busy()
        self.start_button.state(["disabled"] if running else ["!disabled"])
        self.walls_button.state(["disabled"] if running else ["!disabled"])
        self.stop_button.state(["!disabled"] if running else ["disabled"])
        for button in (self.inspect_button, self.profile_button, self.save_button, self.calibrate_button):
            button.state(["disabled"] if running else ["!disabled"])
        for button in getattr(self,'independent_buttons',[]):
            button.state(['disabled'] if running else ['!disabled'])
        if not running and self.run_state.get() in ("EN COURS", "LECTURE"): self.run_state.set("PRÊT")
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
        BotApp().run()
