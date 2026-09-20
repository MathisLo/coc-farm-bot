"""The desktop dashboard. Gameplay stays in BotApp."""
import tkinter as tk
from tkinter import ttk

COLORS = dict(bg="#11131D", card="#1C2030", field="#272C40", text="#F3F0EB",
              muted="#A4A9BE", accent="#EEC879", line="#394058")


class Panel(tk.Canvas):
    def __init__(self, parent, fill=COLORS['card'], **kwargs):
        super().__init__(parent, bg=COLORS['bg'], highlightthickness=0, **kwargs)
        self.fill = fill
        self.body = tk.Frame(self, bg=fill)
        self.window = self.create_window(16, 14, window=self.body, anchor='nw')
        self.bind('<Configure>', self.resize)

    def resize(self, event):
        w, h, r = event.width, event.height, 18
        self.delete('surface')
        self.create_polygon(r, 0, w-r, 0, w, 0, w, r, w, h-r, w, h,
                            w-r, h, r, h, 0, h, 0, h-r, 0, r, 0, 0,
                            smooth=True, fill=self.fill, outline='', tags='surface')
        self.tag_lower('surface')
        self.itemconfigure(self.window, width=max(1, w-32), height=max(1, h-28))


def label(parent, text=None, size=10, color=None, bold=False, **kwargs):
    return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color or COLORS['text'],
                    font=('Segoe UI Semibold' if bold else 'Segoe UI', size), anchor='w', **kwargs)


def style(app):
    app.colors = COLORS.copy()
    app.root.configure(bg=COLORS['bg'])
    app.root.option_add('*TCombobox*Listbox.background', COLORS['field'])
    app.root.option_add('*TCombobox*Listbox.foreground', COLORS['text'])
    s = ttk.Style(app.root)
    s.theme_use('clam')
    for name, bg in [('App', COLORS['bg']), ('Card', COLORS['card'])]:
        s.configure(name+'.TFrame', background=bg)
        s.configure(name+'.TLabel', background=bg, foreground=COLORS['text'], font=('Segoe UI', 10))
    s.configure('App.TEntry', fieldbackground=COLORS['field'], foreground=COLORS['text'],
                insertcolor=COLORS['text'], bordercolor=COLORS['line'], lightcolor=COLORS['line'], darkcolor=COLORS['line'], padding=8)
    s.configure('App.TCombobox', fieldbackground=COLORS['field'], background=COLORS['field'],
                foreground=COLORS['text'], arrowcolor=COLORS['accent'], bordercolor=COLORS['line'], lightcolor=COLORS['line'], darkcolor=COLORS['line'], padding=8)
    s.map('App.TCombobox', fieldbackground=[('readonly', COLORS['field'])], foreground=[('readonly', COLORS['text'])])
    s.configure('App.TCheckbutton', background=COLORS['card'], foreground=COLORS['text'],
                font=('Segoe UI', 10), padding=(0, 7))
    s.map('App.TCheckbutton', background=[('active', COLORS['card'])],
          indicatorbackground=[('selected', COLORS['accent'])], foreground=[('active', COLORS['text'])])
    for name, bg, fg in [('Quiet', COLORS['field'], COLORS['text']),
                          ('Primary', COLORS['accent'], COLORS['bg']), ('Stop', '#563441', '#FFD5DC')]:
        s.configure(name+'.TButton', background=bg, foreground=fg, borderwidth=0,
                    font=('Segoe UI Semibold', 10), padding=(14, 10))
        s.map(name+'.TButton', background=[('disabled', '#252A39'), ('active', COLORS['line'])],
              foreground=[('disabled', '#747B91'), ('active', COLORS['text'])])
    s.configure('Dash.TNotebook', background=COLORS['card'], borderwidth=0, bordercolor=COLORS['card'], lightcolor=COLORS['card'], darkcolor=COLORS['card'])
    s.configure('Dash.TNotebook.Tab', background=COLORS['card'], foreground=COLORS['muted'],
                font=('Segoe UI Semibold', 10), padding=(14, 8), bordercolor=COLORS['card'], lightcolor=COLORS['card'], darkcolor=COLORS['card'])
    s.map('Dash.TNotebook.Tab', background=[('selected', COLORS['field'])],
          foreground=[('selected', COLORS['accent'])],
          lightcolor=[('selected', COLORS['field']), ('!selected', COLORS['card'])],
          darkcolor=[('selected', COLORS['field']), ('!selected', COLORS['card'])],
          bordercolor=[('selected', COLORS['field']), ('!selected', COLORS['card'])])
    s.configure('Dash.Vertical.TScrollbar', background=COLORS['field'], troughcolor=COLORS['card'],
                borderwidth=0, width=8, arrowcolor=COLORS['muted'], lightcolor=COLORS['field'], darkcolor=COLORS['field'])
    s.map('Dash.Vertical.TScrollbar', background=[('!disabled', COLORS['field'])],
          lightcolor=[('!disabled', COLORS['field'])], darkcolor=[('!disabled', COLORS['field'])],
          bordercolor=[('!disabled', COLORS['card'])])
    s.layout('Dash.Vertical.TScrollbar', [('Vertical.Scrollbar.trough', {
        'sticky': 'ns', 'children': [('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])


def build(app):
    style(app)
    root = tk.Frame(app.root, bg=COLORS['bg'], padx=24, pady=20)
    root.pack(fill='both', expand=True)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(3, weight=1)

    header = tk.Frame(root, bg=COLORS['bg'])
    header.grid(row=0, column=0, sticky='ew', pady=(0, 20))
    label(header, '♜', size=38, color=COLORS['accent']).pack(side='left', padx=(0, 16))
    identity = tk.Frame(header, bg=COLORS['bg'])
    identity.pack(side='left')
    label(identity, 'CLASH OF CLANS  /  FARM', size=9, color=COLORS['accent'], bold=True).pack(anchor='w')
    label(identity, 'Le coffre de guerre', size=26, bold=True).pack(anchor='w')
    state = tk.Frame(header, bg=COLORS['field'], padx=16, pady=10)
    state.pack(side='right')
    label(state, '●', color='#8BD4B1').pack(side='left', padx=(0, 8))
    label(state, textvariable=app.run_state, size=10, bold=True).pack(side='left')

    stats = tk.Frame(root, bg=COLORS['bg'])
    stats.grid(row=1, column=0, sticky='ew')
    app.stat_panels = []
    for i, (key, title, emoji, accent, bg) in enumerate([
            ('gold', 'OR RÉCOLTÉ', '💰', '#F2CD76', '#302A25'),
            ('elixir', 'ÉLIXIR RÉCOLTÉ', '🧪', '#E6A0ED', '#2C253B'),
            ('dark_elixir', 'ÉLIXIR NOIR RÉCOLTÉ', '🖤', '#BCA9F6', '#24273E')]):
        stats.columnconfigure(i, weight=1, uniform='stats')
        panel = Panel(stats, fill=bg, height=154, width=200)
        panel.grid(row=0, column=i, sticky='ew', padx=(0 if i == 0 else 12, 0))
        app.stat_panels.append(panel)
        head = tk.Frame(panel.body, bg=bg)
        head.pack(fill='x')
        label(head, title, size=9, color=accent, bold=True).pack(side='left')
        tk.Label(head, text=emoji, font=('Segoe UI Emoji', 25), bg=bg, fg=accent).pack(side='right')
        label(panel.body, textvariable=app.stats_vars[key], size=27, bold=True).pack(anchor='w')
        label(panel.body, 'Cumul des combats · bonus inclus', size=9, color=COLORS['muted']).pack(anchor='w', pady=(2, 0))
    label(root, textvariable=app.stats_count, size=9, color=COLORS['muted']).grid(row=2, column=0, sticky='w', pady=(10, 18))

    content = tk.Frame(root, bg=COLORS['bg'])
    content.grid(row=3, column=0, sticky='nsew')
    content.columnconfigure(1, weight=1)
    content.rowconfigure(0, weight=1)
    settings = Panel(content, width=350)
    settings.grid(row=0, column=0, sticky='ns', padx=(0, 16))
    left = settings.body
    label(left, 'Préparer le raid', size=16, bold=True).pack(anchor='w')
    label(left, 'Fenêtre du jeu', size=9, color=COLORS['muted']).pack(anchor='w', pady=(10, 0))
    connection = tk.Frame(left, bg=COLORS['card'])
    connection.pack(fill='x', pady=(6, 10))
    app.windows = ttk.Combobox(connection, textvariable=app.window_title, style='App.TCombobox', width=17)
    app.windows.pack(side='left', fill='x', expand=True)
    ttk.Button(connection, text='↻', width=3, command=app.refresh, style='Quiet.TButton').pack(side='left', padx=(6, 0))
    app.save_button = ttk.Button(left, text='Enregistrer les réglages', command=app.persist, style='Quiet.TButton')
    app.save_button.pack(side='bottom', fill='x', pady=(8, 0))
    tabs = ttk.Notebook(left, style='Dash.TNotebook')
    tabs.pack(fill='both', expand=True)
    app.settings_tabs = tabs
    def tab(title):
        page = tk.Frame(tabs, bg=COLORS['card'], padx=4, pady=10)
        tabs.add(page, text=title)
        return page
    def entry(parent, title, variable):
        label(parent, title, size=9, color=COLORS['muted']).pack(anchor='w')
        ttk.Entry(parent, textvariable=variable, style='App.TEntry', width=10).pack(fill='x', pady=(5, 8))
    def check(parent, title, variable):
        ttk.Checkbutton(parent, text=title, variable=variable, style='App.TCheckbutton').pack(anchor='w')
    loot = tab('Butin')
    pair = tk.Frame(loot, bg=COLORS['card'])
    pair.pack(fill='x')
    for i, (title, variable) in enumerate([('💰  Or minimum', app.min_gold), ('🧪  Élixir minimum', app.min_elixir)]):
        pair.columnconfigure(i, weight=1, uniform='inputs')
        cell = tk.Frame(pair, bg=COLORS['card'])
        cell.grid(row=0, column=i, sticky='ew', padx=(0 if i == 0 else 8, 0))
        entry(cell, title, variable)
    margin = tk.Frame(loot, bg=COLORS['card'])
    margin.pack(fill='x', pady=(4, 6))
    label(margin, 'Tolérance (%)', size=9, color=COLORS['muted']).pack(side='left')
    ttk.Entry(margin, textvariable=app.loot_margin, style='App.TEntry', width=7).pack(side='right')
    check(loot, 'Exiger les deux ressources', app.and_rule)
    army = tab('Armée')
    army_pair = tk.Frame(army, bg=COLORS['card'])
    army_pair.pack(fill='x')
    for i, (title, variable) in enumerate([('⚡  Électro-dragons', app.electrodragon_count), ('🐉  Dragons', app.dragon_count)]):
        army_pair.columnconfigure(i, weight=1, uniform='army')
        cell = tk.Frame(army_pair, bg=COLORS['card'])
        cell.grid(row=0, column=i, sticky='ew', padx=(0 if i == 0 else 8, 0))
        entry(cell, title, variable)
    check(army, 'Déployer les trois héros', app.deploy_heroes)
    label(army, 'Toutes les unités disponibles sont envoyées.', color=COLORS['muted'], size=9, justify='left').pack(anchor='w', pady=4)
    cycle = tab('Cycle')
    check(cycle, 'Enchaîner les attaques', app.chain_attacks)
    check(cycle, 'Améliorations conseillées', app.upgrade_recommended)
    check(cycle, 'Améliorer les remparts', app.upgrade_wall)
    label(cycle, 'Au moins 1 ouvrier libre et 1 M de chaque ressource conservés.', color=COLORS['muted'], size=9).pack(anchor='w', pady=(0, 4))
    check(cycle, 'Simulation sans déploiement', app.dry_run)

    activity = Panel(content)
    activity.grid(row=0, column=1, sticky='nsew')
    right = activity.body
    label(right, 'Au cœur du raid', size=16, bold=True).pack(anchor='w')
    label(right, 'Consultez le jeu et suivez chaque action.', size=9, color=COLORS['muted']).pack(anchor='w', pady=(3, 16))
    views = ttk.Notebook(right, style='Dash.TNotebook')
    views.pack(fill='both', expand=True)
    app.activity_tabs = views
    journal = tk.Frame(views, bg=COLORS['card'])
    capture = tk.Frame(views, bg=COLORS['card'])
    views.add(journal, text='≡  Journal')
    views.add(capture, text='▣  Aperçu du jeu')
    separate = tk.Frame(views, bg=COLORS['card'], padx=16, pady=16)
    views.add(separate, text='Actions')
    label(separate, 'Lancer une action seule', size=16, bold=True).pack(anchor='w', pady=(0,12))
    label(separate, 'Les réserves et la protection du dernier ouvrier restent actives.', size=9, color=COLORS['muted'], wraplength=400).pack(anchor='w', pady=(0,12))
    app.independent_buttons = []
    for title, action in (('Améliorer les bâtiments','buildings'),('Lancer une attaque unique','attack')):
        button = ttk.Button(separate, text=title, command=lambda name=action: app.start_independent(name), style='Quiet.TButton')
        button.pack(fill='x', pady=5)
        app.independent_buttons.append(button)
    button = ttk.Button(separate, text='Améliorer les remparts', command=app.start_walls, style='Quiet.TButton')
    button.pack(fill='x', pady=5)
    app.independent_buttons.append(button)
    app.export_log_button = ttk.Button(journal, text='↓  Télécharger le journal (.txt)',
                                       command=app.export_log, style='Quiet.TButton')
    app.export_log_button.pack(anchor='e', padx=8, pady=(8, 0))
    app.log = tk.Text(journal, height=6, width=30, state='disabled', wrap='word',
                      bg=COLORS['card'], fg=COLORS['text'], relief='flat', padx=12, pady=16,
                      font=('Cascadia Mono', 10), spacing1=5, spacing3=5)
    scrollbar = ttk.Scrollbar(journal, command=app.log.yview, style='Dash.Vertical.TScrollbar')
    scrollbar.pack(side='right', fill='y')
    app.log.configure(yscrollcommand=scrollbar.set)
    app.log.pack(fill='both', expand=True)
    app.preview = ttk.Label(capture, text='Votre village apparaîtra ici.\nCliquez sur « Lire l’écran » pour une capture.',
                            anchor='center', justify='center', style='Card.TLabel')
    app.preview.pack(fill='both', expand=True)
    tools = tk.Frame(right, bg=COLORS['card'])
    tools.pack(fill='x', pady=(12, 0))
    app.inspect_button = ttk.Button(tools, text='Lire l’écran', command=app.inspect_game, style='Quiet.TButton')
    app.inspect_button.pack(side='left')
    app.profile_button = ttk.Button(tools, text='Relever le profil', command=app.scan_profile, style='Quiet.TButton')
    app.profile_button.pack(side='left', padx=6)
    app.calibrate_button = ttk.Button(tools, text='Calibrer…', command=app.calibrate, style='Quiet.TButton')
    app.calibrate_button.pack(side='right')

    actions = tk.Frame(root, bg=COLORS['bg'])
    actions.grid(row=4, column=0, sticky='ew', pady=(18, 0))
    app.walls_button = ttk.Button(actions, text='♜  Améliorer les remparts', command=app.start_walls, style='Quiet.TButton')
    app.walls_button.pack(side='left')
    app.stop_button = ttk.Button(actions, text='■  Arrêter', command=app.stop, style='Stop.TButton')
    app.stop_button.pack(side='right')
    app.stop_button.state(['disabled'])
    app.start_button = ttk.Button(actions, text='▶  Cycle complet', command=app.start_farm, style='Primary.TButton')
    app.start_button.pack(side='right', padx=10)
    label(root, textvariable=app.status, size=9, color=COLORS['muted'], wraplength=950).grid(row=5, column=0, sticky='w', pady=(12, 0))
    app.refresh()
