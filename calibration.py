"""Edit named click points and OCR regions on a captured image, never in-game."""
import math
from tkinter import Canvas, StringVar, Toplevel, ttk, filedialog, messagebox

from PIL import Image, ImageTk


def validate_overrides(defaults, overrides):
    if not isinstance(overrides, dict):
        raise ValueError("Le calibrage doit contenir des positions nommées.")
    clean = {}
    for key, values in overrides.items():
        if key not in defaults or not isinstance(values, (list, tuple)) or len(values) != len(defaults[key]):
            raise ValueError(f"Position de calibrage inconnue ou invalide : {key}")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 100 for v in values):
            raise ValueError(f"Coordonnées invalides : {key}")
        if len(values) == 4 and not (values[0] < values[2] and values[1] < values[3]):
            raise ValueError(f"Rectangle vide ou inversé : {key}")
        clean[key] = list(values)
    return clean


class CalibrationDialog:
    def __init__(self, parent, image, defaults, overrides, on_save, on_close, on_refresh, labels=None):
        self.defaults = defaults
        self.overrides = validate_overrides(defaults, overrides)
        self.on_save, self.on_close = on_save, on_close
        self.window = Toplevel(parent)
        self.window.title("Calibrer les positions du jeu")
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.image = image.copy()
        self.anchor = None
        self.keys = {(labels or {}).get(key, key): key for key in defaults}
        self.selection = StringVar(value=next(iter(self.keys)))
        self.instructions = StringVar()
        self.coordinates = StringVar()
        self.resolution = StringVar()
        body = ttk.Frame(self.window, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Choisir un élément, puis cliquer pour un point ou tracer un rectangle pour une zone de lecture.", wraplength=900).pack(anchor="w")
        ttk.Label(body, text="Utiliser une capture du menu concerné. Les clics sur cet aperçu ne sont jamais envoyés au jeu.", wraplength=900).pack(anchor="w", pady=(0, 8))
        combo = ttk.Combobox(body, values=list(self.keys), textvariable=self.selection, state="readonly", width=65)
        combo.pack(fill="x")
        combo.bind("<<ComboboxSelected>>", self.redraw)
        ttk.Label(body, textvariable=self.instructions).pack(anchor="w", pady=6)
        ttk.Label(body, textvariable=self.resolution).pack(anchor="w")
        max_width = min(1000, parent.winfo_screenwidth() - 80)
        max_height = min(560, parent.winfo_screenheight() - 300)
        self.preview_size = (max(300, max_width), max(180, max_height))
        self.canvas = Canvas(body, highlightthickness=0, background="#101B2A")
        self.canvas.pack()
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        ttk.Label(body, textvariable=self.coordinates).pack(anchor="w", pady=4)
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(6, 0))
        ttk.Button(actions, text="Actualiser la capture", command=on_refresh).pack(side="left")
        ttk.Button(actions, text="Charger une capture…", command=self.load_image).pack(side="left", padx=6)
        ttk.Button(actions, text="Réinitialiser cet élément", command=self.reset).pack(side="left")
        ttk.Button(actions, text="Enregistrer", command=self.save).pack(side="right")
        ttk.Button(actions, text="Annuler", command=self.close).pack(side="right", padx=6)
        self.set_image(image)

    def set_image(self, image):
        if self.overrides and abs(image.width / image.height / (self.image.width / self.image.height) - 1) > .02:
            messagebox.showerror("Format différent", "Les captures d’un même calibrage doivent avoir le même format. Annuler puis rouvrir le calibrage pour changer de format.", parent=self.window)
            return
        self.image = image.copy()
        self.resolution.set(f"Fenêtre de jeu : {image.width} x {image.height} pixels (format enregistré avec le calibrage)")
        preview = image.copy()
        preview.thumbnail(self.preview_size)
        self.photo = ImageTk.PhotoImage(preview, master=self.window)
        self.canvas.configure(width=preview.width, height=preview.height)
        self.redraw()

    def redraw(self, _event=None):
        key = self.keys[self.selection.get()]
        values = self.overrides.get(key, self.defaults[key])
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        pixels = [v * (self.photo.width() if index % 2 == 0 else self.photo.height()) / 100 for index, v in enumerate(values)]
        if len(values) == 2:
            x, y = pixels
            self.canvas.create_oval(x - 6, y - 6, x + 6, y + 6, outline="#66C6D8", width=3)
        else:
            self.canvas.create_rectangle(*pixels, outline="#66C6D8", width=3)
        self.instructions.set("Point de clic : cliquer sur sa nouvelle position." if len(values) == 2 else "Zone OCR : tracer un rectangle autour du texte ou de l’icône.")
        self.coordinates.set(" / ".join(f"{v:.2f} %" for v in values))

    def percent(self, event):
        return (max(0, min(100, event.x * 100 / self.photo.width())),
                max(0, min(100, event.y * 100 / self.photo.height())))

    def press(self, event):
        self.anchor = self.percent(event)

    def drag(self, event):
        if self.anchor is None or len(self.defaults[self.keys[self.selection.get()]]) != 4:
            return
        self.canvas.delete("draft")
        end = self.percent(event)
        self.canvas.create_rectangle(self.anchor[0] * self.photo.width() / 100, self.anchor[1] * self.photo.height() / 100,
                                     end[0] * self.photo.width() / 100, end[1] * self.photo.height() / 100,
                                     outline="#FACC15", width=2, tags="draft")

    def release(self, event):
        if self.anchor is None: return
        end, start = self.percent(event), self.anchor
        self.anchor = None
        key = self.keys[self.selection.get()]
        values = list(end) if len(self.defaults[key]) == 2 else [min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1])]
        try:
            self.overrides.update(validate_overrides(self.defaults, {key: values}))
        except ValueError:
            return
        self.redraw()

    def reset(self):
        self.overrides.pop(self.keys[self.selection.get()], None)
        self.redraw()

    def load_image(self):
        path = filedialog.askopenfilename(parent=self.window, filetypes=[("Captures", "*.png *.jpg *.jpeg")])
        if path:
            try:
                with Image.open(path) as image:
                    self.set_image(image.convert("RGB"))
            except (OSError, ValueError) as exc:
                messagebox.showerror("Capture illisible", str(exc), parent=self.window)

    def save(self):
        try:
            self.on_save(validate_overrides(self.defaults, self.overrides), self.image.width / self.image.height)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Calibrage non enregistré", str(exc), parent=self.window)
            return
        self.close()

    def close(self):
        self.window.destroy()
        self.on_close()
