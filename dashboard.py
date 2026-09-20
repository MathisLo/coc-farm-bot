"""Public entry point for the desktop interface."""
from dashboard_layout import build
from ui_theme import COLORS, apply_theme
from ui_widgets import Panel, label


def style(app):
    apply_theme(app.root)


__all__ = ["build", "COLORS", "Panel", "label", "style"]
