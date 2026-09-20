"""Layout of the desktop console. Bot operations remain owned by BotApp."""
import tkinter as tk
from tkinter import ttk

from ui_theme import COLORS, apply_theme
from ui_widgets import Panel, check, field, label


def build(app):
    apply_theme(app.root)
    app.colors = COLORS.copy()
    root = tk.Frame(app.root, bg=COLORS["background"], padx=20, pady=16)
    root.pack(fill="both", expand=True)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(2, weight=1)

    _header(app, root)
    _metrics(app, root)

    workspace = tk.Frame(root, bg=COLORS["background"])
    workspace.grid(row=2, column=0, sticky="nsew", pady=(12, 12))
    workspace.columnconfigure(1, weight=1)
    workspace.rowconfigure(0, weight=1)
    _settings(app, workspace)
    _activity(app, workspace)
    _commands(app, root)
    app.refresh()


def _header(app, root):
    header = tk.Frame(root, bg=COLORS["background"])
    header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
    insignia = tk.Canvas(header, width=46, height=46, bg=COLORS["surface_raised"],
                         highlightthickness=0)
    insignia.pack(side="left", padx=(0, 13))
    insignia.create_polygon(13, 10, 33, 10, 33, 28, 23, 38, 13, 28,
                            outline=COLORS["gold"], fill="", width=2)
    insignia.create_line(18, 19, 28, 29, fill=COLORS["gold"], width=2)
    insignia.create_line(28, 19, 18, 29, fill=COLORS["gold"], width=2)
    identity = tk.Frame(header, bg=COLORS["background"])
    identity.pack(side="left")
    label(identity, "COC FARM BOT  /  CONSOLE", size=9, bold=True,
          color=COLORS["gold"]).pack(anchor="w")
    label(identity, "Pilote de raid", size=22, bold=True).pack(anchor="w")
    state = tk.Frame(header, bg=COLORS["surface_raised"], padx=12, pady=9)
    state.pack(side="right")
    label(state, "●", size=9, color=COLORS["mint"]).pack(side="left", padx=(0, 7))
    label(state, variable=app.run_state, size=10, bold=True).pack(side="left")
    label(header, variable=app.stats_count, size=9, color=COLORS["muted"]).pack(
        side="right", padx=(0, 16))


def _metrics(app, root):
    strip = tk.Frame(root, bg=COLORS["background"])
    strip.grid(row=1, column=0, sticky="ew")
    app.stat_panels = []
    metrics = (("gold", "OR RÉCOLTÉ", COLORS["gold"]),
               ("elixir", "ÉLIXIR RÉCOLTÉ", COLORS["elixir"]),
               ("dark_elixir", "ÉLIXIR NOIR RÉCOLTÉ", COLORS["dark_elixir"]))
    for column, (key, title, accent) in enumerate(metrics):
        strip.columnconfigure(column, weight=1, uniform="metrics")
        panel = Panel(strip, padding=12)
        panel.grid(row=0, column=column, sticky="ew",
                   padx=(0 if column == 0 else 6, 6 if column < 2 else 0))
        app.stat_panels.append(panel)
        line = tk.Frame(panel.body, bg=accent, height=3)
        line.pack(fill="x", pady=(0, 9))
        label(panel.body, title, size=9, bold=True, color=accent).pack(anchor="w")
        label(panel.body, variable=app.stats_vars[key], size=21, bold=True).pack(anchor="w")


def _settings(app, workspace):
    panel = Panel(workspace, padding=16, width=350)
    panel.grid(row=0, column=0, sticky="ns", padx=(0, 12))
    panel.grid_propagate(False)
    body = panel.body
    label(body, "Réglages", size=15, bold=True).pack(anchor="w")
    label(body, "Fenêtre et critères du prochain raid", size=9,
          color=COLORS["muted"]).pack(anchor="w", pady=(1, 12))
    label(body, "Fenêtre du jeu", size=9, color=COLORS["muted"]).pack(anchor="w")
    connection = tk.Frame(body, bg=COLORS["surface"])
    connection.pack(fill="x", pady=(5, 14))
    app.windows = ttk.Combobox(connection, textvariable=app.window_title,
                               style="Console.TCombobox", width=17)
    app.windows.pack(side="left", fill="x", expand=True)
    ttk.Button(connection, text="↻", width=3, command=app.refresh,
               style="Secondary.TButton").pack(side="left", padx=(6, 0))

    tabs = ttk.Notebook(body, style="Console.TNotebook")
    tabs.pack(fill="both", expand=True)
    app.settings_tabs = tabs
    loot = _page(tabs, "Butin")
    _paired_fields(loot, ("Or minimum", app.min_gold),
                   ("Élixir minimum", app.min_elixir))
    field(loot, "Marge (%)", app.loot_margin)
    check(loot, "Exiger les deux ressources", app.and_rule)

    army = _page(tabs, "Armée")
    _paired_fields(army, ("Électrodragons prévus", app.electrodragon_count),
                   ("Dragons prévus", app.dragon_count))
    check(army, "Déployer les héros", app.deploy_heroes)
    label(army, "Le bot envoie toutes les unités présentes dans la barre de combat.",
          size=9, color=COLORS["muted"], wraplength=280,
          justify="left").pack(anchor="w", pady=(10, 0))

    cycle = _page(tabs, "Cycle")
    check(cycle, "Enchaîner les attaques", app.chain_attacks)
    check(cycle, "Améliorer les bâtiments", app.upgrade_recommended)
    check(cycle, "Améliorer les remparts", app.upgrade_wall)
    check(cycle, "Simulation sans déploiement", app.dry_run)
    label(cycle, "Bâtiments : garder 1 ouvrier libre. Remparts : garder 1 M de chaque ressource.",
          size=9, color=COLORS["muted"], wraplength=280,
          justify="left").pack(anchor="w", pady=(10, 0))


def _page(tabs, title):
    page = tk.Frame(tabs, bg=COLORS["surface"], padx=5, pady=14)
    tabs.add(page, text=title)
    return page


def _paired_fields(parent, first, second):
    row = tk.Frame(parent, bg=COLORS["surface"])
    row.pack(fill="x")
    for index, (title, variable) in enumerate((first, second)):
        row.columnconfigure(index, weight=1, uniform="fields")
        cell = tk.Frame(row, bg=COLORS["surface"])
        cell.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 5,
                                                         5 if index == 0 else 0))
        field(cell, title, variable)


def _activity(app, workspace):
    panel = Panel(workspace, padding=16)
    panel.grid(row=0, column=1, sticky="nsew")
    body = panel.body
    label(body, "Suivi en direct", size=15, bold=True).pack(anchor="w")
    label(body, "Journal, capture et actions ponctuelles", size=9,
          color=COLORS["muted"]).pack(anchor="w", pady=(1, 12))
    tools = tk.Frame(body, bg=COLORS["surface"])
    tools.pack(side="bottom", fill="x", pady=(10, 0))
    app.inspect_button = ttk.Button(tools, text="Lire l’écran", command=app.inspect_game,
                                    style="Secondary.TButton")
    app.inspect_button.pack(side="left")
    app.profile_button = ttk.Button(tools, text="Relever le profil", command=app.scan_profile,
                                    style="Secondary.TButton")
    app.profile_button.pack(side="left", padx=(7, 0))
    app.calibrate_button = ttk.Button(tools, text="Calibrer les positions",
                                      command=app.calibrate, style="Quiet.TButton")
    app.calibrate_button.pack(side="right")
    tabs = ttk.Notebook(body, style="Console.TNotebook")
    tabs.pack(fill="both", expand=True)
    app.activity_tabs = tabs
    journal = _page(tabs, "Journal")
    preview = _page(tabs, "Aperçu du jeu")
    actions = _page(tabs, "Actions")
    _journal(app, journal)
    app.preview = tk.Label(preview, text="Aucune capture. Cliquez sur « Lire l'écran ».",
                           bg=COLORS["field"], fg=COLORS["muted"],
                           font=("Segoe UI", 11), anchor="center", justify="center")
    app.preview.pack(fill="both", expand=True)
    _one_off_actions(app, actions)

def _journal(app, parent):
    toolbar = tk.Frame(parent, bg=COLORS["surface"])
    toolbar.pack(fill="x", pady=(0, 8))
    label(toolbar, "Événements du cycle", size=9,
          color=COLORS["muted"]).pack(side="left")
    app.export_log_button = ttk.Button(toolbar, text="Exporter le diagnostic",
                                       command=app.export_log, style="Quiet.TButton")
    app.export_log_button.pack(side="right")
    log_area = tk.Frame(parent, bg=COLORS["field"])
    log_area.pack(fill="both", expand=True)
    app.log = tk.Text(log_area, height=6, width=30, state="disabled", wrap="word",
                      bg=COLORS["field"], fg=COLORS["text"], relief="flat",
                      padx=12, pady=11, insertbackground=COLORS["text"],
                      font=("Cascadia Mono", 10), spacing1=4, spacing3=4)
    scrollbar = ttk.Scrollbar(log_area, command=app.log.yview,
                              style="Console.Vertical.TScrollbar")
    scrollbar.pack(side="right", fill="y")
    app.log.configure(yscrollcommand=scrollbar.set)
    app.log.pack(fill="both", expand=True)


def _one_off_actions(app, parent):
    label(parent, "Action ponctuelle", size=13, bold=True).pack(anchor="w", pady=(0, 9))
    app.independent_buttons = []
    for title, action in (("Lancer une attaque", "attack"),
                          ("Améliorer les bâtiments", "buildings")):
        button = ttk.Button(parent, text=title,
                            command=lambda name=action: app.start_independent(name),
                            style="Secondary.TButton")
        button.pack(fill="x", pady=(0, 5))
        app.independent_buttons.append(button)
    button = ttk.Button(parent, text="Améliorer les remparts",
                        command=app.start_walls, style="Secondary.TButton")
    button.pack(fill="x")
    app.independent_buttons.append(button)
    app.reset_data_button = ttk.Button(parent, text="Effacer les données du bot",
                                       command=app.reset_all_data, style="Danger.TButton")
    app.reset_data_button.pack(anchor="e", pady=(9, 0))


def _commands(app, root):
    bar = Panel(root, background=COLORS["surface_raised"], padding=10)
    bar.grid(row=3, column=0, sticky="ew")
    body = bar.body
    label(body, variable=app.status, size=9, color=COLORS["muted"],
          wraplength=400, justify="left").pack(side="left", fill="x", expand=True)
    app.stop_button = ttk.Button(body, text="Arrêter", command=app.stop,
                                 style="Danger.TButton")
    app.stop_button.pack(side="right")
    app.stop_button.state(["disabled"])
    app.start_button = ttk.Button(body, text="Lancer le cycle", command=app.start_farm,
                                  style="Primary.TButton")
    app.start_button.pack(side="right", padx=(0, 8))
    app.walls_button = ttk.Button(body, text="Remparts", command=app.start_walls,
                                  style="Secondary.TButton")
    app.walls_button.pack(side="right", padx=(0, 8))
    app.save_button = ttk.Button(body, text="Enregistrer", command=app.persist,
                                 style="Secondary.TButton")
    app.save_button.pack(side="right", padx=(0, 8))
