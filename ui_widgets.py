"""Small reusable Tk widgets for the desktop console."""
import tkinter as tk
from tkinter import ttk

from ui_theme import COLORS


class Panel(tk.Frame):
    def __init__(self, parent, background=None, padding=18, **kwargs):
        fill = background or COLORS["surface"]
        super().__init__(parent, bg=fill, highlightbackground=COLORS["border"],
                         highlightthickness=1, **kwargs)
        self.body = tk.Frame(self, bg=fill, padx=padding, pady=padding)
        self.body.pack(fill="both", expand=True)


def label(parent, text=None, variable=None, size=10, color=None, bold=False, **kwargs):
    options = {"textvariable": variable} if variable is not None else {"text": text}
    return tk.Label(parent, bg=parent.cget("bg"), fg=color or COLORS["text"],
                    font=("Segoe UI Semibold" if bold else "Segoe UI", size),
                    anchor="w", **options, **kwargs)


def field(parent, title, variable):
    label(parent, title, size=9, color=COLORS["muted"]).pack(anchor="w")
    entry = ttk.Entry(parent, textvariable=variable, style="Console.TEntry")
    entry.pack(fill="x", pady=(5, 10))
    return entry


def check(parent, title, variable):
    widget = ttk.Checkbutton(parent, text=title, variable=variable,
                             style="Console.TCheckbutton")
    widget.pack(anchor="w")
    return widget
