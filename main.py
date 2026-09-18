"""CoC Farm Bot V1: capture Windows, calibration locale et entrée sans souris."""
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

from PIL import Image, ImageDraw, ImageFont, ImageTk

APP_DIR = Path.home() / "CoCFarmBot"
CONFIG_PATH = APP_DIR / "config-v2.json"
LOG_PATH = APP_DIR / "bot.log"
CAPTURE_PATH = APP_DIR / "last_capture.png"
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
    version: int = 2
    window_title: str = ""
    gold_roi: Roi = field(default_factory=Roi)
    elixir_roi: Roi = field(default_factory=Roi)
    min_gold: int = 500000
    min_elixir: int = 500000
    use_and_rule: bool = True
    dragon_points: list[list[float]] = field(default_factory=list)
    delay_between_dragons_ms: int = 180
    poll_interval_seconds: int = 3
    dry_run: bool = True


def load_settings() -> Settings:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        data["gold_roi"] = Roi(**data.get("gold_roi", {})); data["elixir_roi"] = Roi(**data.get("elixir_roi", {}))
        return Settings(**data)
    except (OSError, TypeError, ValueError): return Settings()


def save_settings(settings: Settings):
    APP_DIR.mkdir(parents=True, exist_ok=True); CONFIG_PATH.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


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


class BotApp:
    def __init__(self):
        APP_DIR.mkdir(parents=True, exist_ok=True); logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format="%(asctime)s %(message)s", encoding="utf-8")
        self.settings = load_settings(); self.root = Tk(); self.root.title("CoC Farm Bot — V1 calibrable"); self.root.geometry("1040x810")
        self.events = queue.Queue(); self.stop_event = threading.Event(); self.worker = None; self.image = None; self.photo = None; self.origin = (0, 0); self.preview_size = (1, 1); self.drag_start = None
        self.mode = StringVar(value="Or"); self.window_title = StringVar(value=self.settings.window_title); self.min_gold = StringVar(value=str(self.settings.min_gold)); self.min_elixir = StringVar(value=str(self.settings.min_elixir)); self.and_rule = BooleanVar(value=self.settings.use_and_rule); self.dry_run = BooleanVar(value=self.settings.dry_run)
        self.gold_text = StringVar(value=self.settings.gold_roi.text() if self.settings.gold_roi.valid() else "À sélectionner"); self.elixir_text = StringVar(value=self.settings.elixir_roi.text() if self.settings.elixir_roi.valid() else "À sélectionner"); self.points_text = StringVar(value=self._points_text()); self.status = StringVar(value="Capture la fenêtre Clash puis calibre les zones.")
        self._build(); self._pump()

    def _build(self):
        root = ttk.Frame(self.root, padding=12); root.pack(fill="both", expand=True); root.columnconfigure(1, weight=1); root.rowconfigure(7, weight=1)
        ttk.Label(root, text="Fenêtre Clash").grid(row=0,column=0,sticky="w"); self.windows = ttk.Combobox(root,textvariable=self.window_title,width=70); self.windows.grid(row=0,column=1,sticky="ew",padx=6); ttk.Button(root,text="Détecter",command=self.refresh).grid(row=0,column=2); ttk.Button(root,text="Capturer",command=self.capture).grid(row=1,column=1,sticky="w",pady=8)
        box = ttk.LabelFrame(root,text="Calibration sur l'aperçu",padding=8); box.grid(row=2,column=0,columnspan=3,sticky="ew")
        for text,value in (("Tracer zone Or","Or"),("Tracer zone Élixir","Élixir"),("Ajouter un point dragon","Dragon")): ttk.Radiobutton(box,text=text,variable=self.mode,value=value).pack(side="left",padx=6)
        ttk.Button(box,text="Effacer dragons",command=self.clear_dragons).pack(side="right")
        ttk.Label(root,text="Zone Or").grid(row=3,column=0,sticky="w"); ttk.Label(root,textvariable=self.gold_text).grid(row=3,column=1,sticky="w")
        ttk.Label(root,text="Zone Élixir").grid(row=4,column=0,sticky="w"); ttk.Label(root,textvariable=self.elixir_text).grid(row=4,column=1,sticky="w")
        ttk.Label(root,text="Points dragons").grid(row=5,column=0,sticky="w"); ttk.Label(root,textvariable=self.points_text).grid(row=5,column=1,sticky="w")
        limits=ttk.Frame(root); limits.grid(row=6,column=0,columnspan=3,sticky="ew",pady=8)
        ttk.Label(limits,text="Seuil or").pack(side="left"); ttk.Entry(limits,textvariable=self.min_gold,width=12).pack(side="left",padx=4); ttk.Label(limits,text="Seuil élixir").pack(side="left",padx=(12,0)); ttk.Entry(limits,textvariable=self.min_elixir,width=12).pack(side="left",padx=4); ttk.Checkbutton(limits,text="Or ET élixir",variable=self.and_rule).pack(side="left",padx=12); ttk.Checkbutton(limits,text="Simulation",variable=self.dry_run).pack(side="left")
        self.canvas=__import__("tkinter").Canvas(root,background="#1d1d1d",highlightthickness=0); self.canvas.grid(row=7,column=0,columnspan=3,sticky="nsew"); self.canvas.bind("<ButtonPress-1>",self.press); self.canvas.bind("<B1-Motion>",self.drag); self.canvas.bind("<ButtonRelease-1>",self.release)
        actions=ttk.Frame(root); actions.grid(row=8,column=0,columnspan=3,pady=8)
        for text,command in (("Tester l'OCR",self.test_ocr),("Enregistrer",self.persist),("Démarrer",self.start),("Arrêter",self.stop)): ttk.Button(actions,text=text,command=command).pack(side="left",padx=3)
        ttk.Label(root,textvariable=self.status).grid(row=9,column=0,columnspan=3,sticky="w"); self.log=__import__("tkinter").Text(root,height=7,state="disabled"); self.log.grid(row=10,column=0,columnspan=3,sticky="nsew",pady=(6,0)); self.refresh()

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
        if self.mode.get()=="Dragon": self.settings.dragon_points.append([round(point[0],2),round(point[1],2)]); self.points_text.set(self._points_text()); self.draw()
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
    def _points_text(self): return f"{len(self.settings.dragon_points)} point(s)" if self.settings.dragon_points else "À placer"

    def persist(self):
        try:
            self.settings.window_title=self.window_title.get();self.settings.min_gold=int(self.min_gold.get().replace(" ",""));self.settings.min_elixir=int(self.min_elixir.get().replace(" ",""));self.settings.use_and_rule=self.and_rule.get();self.settings.dry_run=self.dry_run.get();save_settings(self.settings);self.write("Configuration enregistrée.");return True
        except ValueError: messagebox.showerror("Seuil invalide","Les seuils doivent être des nombres entiers.");return False
    def valid_run(self):
        if not (self.settings.gold_roi.valid() and self.settings.elixir_roi.valid()):self.write("Calibre Or et Élixir.");return False
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
    def stop(self):self.stop_event.set();self.write("Arrêt demandé.")
    def run_loop(self):
        while not self.stop_event.is_set():
            try:
                window=WindowDriver.resolve(self.settings.window_title)
                if not window:raise RuntimeError("Fenêtre Clash introuvable.")
                image=WindowDriver.capture(window);gold=read_number(crop_percent(image,self.settings.gold_roi));elixir=read_number(crop_percent(image,self.settings.elixir_roi))
                if gold is None or elixir is None:self.events.put("OCR non lisible : aucune action envoyée.")
                else:
                    accepted=(gold>=self.settings.min_gold and elixir>=self.settings.min_elixir) if self.settings.use_and_rule else (gold>=self.settings.min_gold or elixir>=self.settings.min_elixir);self.events.put(f"Butin : or {gold:,}, élixir {elixir:,} → {'attaque' if accepted else 'attente'}.")
                    if accepted:
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
    image=Image.new("RGB",(600,150),"white");ImageDraw.Draw(image).text((12,12),"123456",fill="black",font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf",90));assert read_number(image)==123456;print("Self-test passed")

if __name__ == "__main__":
    self_test() if "--self-test" in sys.argv else BotApp().run()
