"""Visual tokens and ttk styles for the desktop console."""
from tkinter import ttk

COLORS = {
    "background": "#101923",
    "surface": "#192633",
    "surface_raised": "#203140",
    "field": "#14212C",
    "border": "#334958",
    "text": "#EDF3F1",
    "muted": "#A7B9C0",
    "gold": "#F2C875",
    "elixir": "#D5A5EC",
    "dark_elixir": "#A9A8E8",
    "mint": "#79D6C1",
    "danger": "#EE858B",
}


def apply_theme(root):
    root.configure(bg=COLORS["background"])
    root.option_add("*TCombobox*Listbox.background", COLORS["field"])
    root.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure("Console.TEntry", fieldbackground=COLORS["field"],
                    foreground=COLORS["text"], insertcolor=COLORS["text"],
                    bordercolor=COLORS["border"], lightcolor=COLORS["border"],
                    darkcolor=COLORS["border"], padding=(9, 8))
    style.map("Console.TEntry", bordercolor=[("focus", COLORS["mint"])])
    style.configure("Console.TCombobox", fieldbackground=COLORS["field"],
                    background=COLORS["field"], foreground=COLORS["text"],
                    arrowcolor=COLORS["mint"], bordercolor=COLORS["border"],
                    lightcolor=COLORS["border"], darkcolor=COLORS["border"],
                    padding=(9, 7))
    style.map("Console.TCombobox", fieldbackground=[("readonly", COLORS["field"])],
              foreground=[("readonly", COLORS["text"])])
    style.configure("Console.TCheckbutton", background=COLORS["surface"],
                    foreground=COLORS["text"], font=("Segoe UI", 10), padding=(0, 6))
    style.map("Console.TCheckbutton", background=[("active", COLORS["surface"])],
              foreground=[("active", COLORS["text"])],
              indicatorbackground=[("selected", COLORS["mint"])])

    buttons = {
        "Primary": (COLORS["gold"], COLORS["background"]),
        "Secondary": (COLORS["surface_raised"], COLORS["text"]),
        "Danger": ("#563740", "#FFE3E5"),
        "Quiet": (COLORS["surface"], COLORS["muted"]),
    }
    for name, (background, foreground) in buttons.items():
        style.configure(f"{name}.TButton", background=background,
                        foreground=foreground, borderwidth=0,
                        font=("Segoe UI Semibold", 10), padding=(14, 10))
        style.map(f"{name}.TButton",
                  background=[("disabled", "#27333E"), ("active", COLORS["border"])],
                  foreground=[("disabled", "#80919A"), ("active", COLORS["text"])])

    style.configure("Console.TNotebook", background=COLORS["surface"],
                    borderwidth=0, bordercolor=COLORS["surface"],
                    lightcolor=COLORS["surface"], darkcolor=COLORS["surface"])
    style.configure("Console.TNotebook.Tab", background=COLORS["surface"],
                    foreground=COLORS["muted"], font=("Segoe UI Semibold", 10),
                    padding=(15, 9), borderwidth=0,
                    bordercolor=COLORS["surface"], lightcolor=COLORS["surface"],
                    darkcolor=COLORS["surface"])
    style.map("Console.TNotebook.Tab",
              background=[("selected", COLORS["surface_raised"])],
              foreground=[("selected", COLORS["gold"])],
              lightcolor=[("selected", COLORS["surface_raised"])],
              darkcolor=[("selected", COLORS["surface_raised"])],
              bordercolor=[("selected", COLORS["surface_raised"])])
    style.configure("Console.Vertical.TScrollbar", background=COLORS["surface_raised"],
                    troughcolor=COLORS["surface"], borderwidth=0, width=9,
                    arrowcolor=COLORS["muted"], lightcolor=COLORS["surface_raised"],
                    darkcolor=COLORS["surface_raised"])
    style.layout("Console.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {
        "sticky": "ns", "children": [("Vertical.Scrollbar.thumb", {
            "expand": "1", "sticky": "nswe"})]})])
