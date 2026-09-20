"""Suggested village upgrades, preserving one regular builder and reserves."""
import re
import unicodedata
import sys

def engine():
    module = sys.modules.get("main") or sys.modules["__main__"]
    if hasattr(module, 'Roi'):
        return module
    import importlib
    return importlib.import_module('main')



def normal(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn').replace('ressorc', 'ressort')


def is_town_hall(title):
    label = re.sub(r'[^a-z]', '', normal(title).replace('0','o'))
    # Also reject the OCR variants observed on the recommendation row.
    return any(word in label for word in ('hotel', 'hobel', 'ville', 'hdv'))


def confirmation_headings(image):
    m = engine()
    return [normal(m.read_text(m.crop_percent(image, roi), scale=scale))
            for roi, scale in ((m.Roi(15,3,85,10),1), (m.Roi(20,4,80,9),2))]


def builder_count(image, with_total=False):
    m = engine()
    from PIL import Image, ImageDraw, ImageFont
    # Remove the enclosing horizontal rules, then add neutral OCR context.
    # Windows OCR otherwise treats this tiny isolated fraction as decoration.
    digits = m.white_text_mask(m.crop_percent(image,m.Roi(49.3,3.3,52.7,6.1)))
    digits = digits.resize((81,46))
    context = Image.new('RGB',(256,46),'white')
    context.paste(digits,(170,0))
    ImageDraw.Draw(context).text((0,5),'Ouvriers',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',30),fill='black')
    raw = m.read_text(context,scale=3)
    match = re.search(r'(?<!\d)([0-6])/([1-6])(?!\d)',raw)
    if match and int(match[1]) <= int(match[2]):
        return (int(match[1]),int(match[2])) if with_total else int(match[1])
    # The selected-building view slightly changes glyph rasterization. Trim
    # mask padding and match text height before a second contextual OCR pass.
    from PIL import ImageOps
    ink = m.white_text_mask(m.crop_percent(image,m.Roi(49.3,3.3,52.7,6.1)))
    bounds = ImageOps.invert(ink).getbbox()
    if bounds:
        ink = ink.crop(bounds)
        for height,canvas_height,scale in ((36,60,2),(24,70,3)):
            digits = ink.resize((round(ink.width*height/ink.height),height))
            context = Image.new('RGB',(180+digits.width,canvas_height),'white')
            context.paste(digits,(170,15))
            ImageDraw.Draw(context).text((0,10),'Ouvriers',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',30),fill='black')
            raw = m.read_text(context,scale=scale)
            match = re.search(r'(?<!\d)([0-6])/([1-6])(?!\d)',raw)
            if match and int(match[1]) <= int(match[2]):
                return (int(match[1]),int(match[2])) if with_total else int(match[1])
    crop = m.crop_percent(image, m.Roi(49, 2, 53, 7))
    for variant, scale in ((m.white_text_mask(crop),3),(crop,1),(crop,2),(crop,3)):
        raw = m.read_text(variant, scale=scale)
        ratio = m.parse_worker_ratio(raw)
        if ratio:
            free, total = map(int, ratio.split('/'))
            if 0 <= free <= total <= 6:
                return (free,total) if with_total else free
    return None


def stable_builders(app, window):
    previous = None
    for _ in range(4):
        current = builder_count(app._capture(window))
        if current is not None and current == previous:
            return current
        previous = current
        app._wait(.25)
    return None


def can_start_upgrade(free, balance, cost):
    return (type(free) is int and free >= 2 and type(balance) is int and
            type(cost) is int and cost > 0 and balance-cost >= 1_000_000)


def resource_icon(image, roi):
    m = engine()
    pixels = list(m.crop_percent(image, roi).convert('RGB').get_flattened_data())
    gold = sum(r > 180 and g > 130 and b < 100 for r,g,b in pixels)
    elixir = sum(r > 130 and b > 120 and g < min(r,b)*.75 for r,g,b in pixels)
    if max(gold, elixir) < len(pixels)*.1 or min(gold,elixir)*3 > max(gold,elixir):
        return None
    return 'or' if gold > elixir else 'élixir'


def suggested_items(image, include_others=False, include_town_hall=False):
    m = engine()
    region = m.Roi(39,12,64,64) if include_others else m.Roi(39,20,64,58)
    words = m.read_word_centers(m.crop_percent(image, region))
    starts = [y for text,x,y in words if 'suggere' in normal(text)]
    ends = [y for text,x,y in words if normal(text).startswith(('autres','aubres'))]
    if not include_others and (len(starts) != 1 or len(ends) != 1):
        return []
    rows = []
    for text,x,y in sorted(words, key=lambda word: word[2]):
        if x > 64:
            continue
        if not include_others and not starts[0]+4 < y < ends[0]-4:
            continue
        if include_others and (y < 4 or y > 96 or any(abs(y-h)<4 for h in starts+ends)):
            continue
        if not rows or abs(y-rows[-1][0]) > 3:
            rows.append((y, []))
        rows[-1][1].append((x,text))
    result = []
    for y, labels in rows:
        title = ' '.join(text for x,text in sorted(labels))
        title = re.sub(r'\s*x\w+\s*$', '', title)
        if normal(title).startswith('remp'):
            continue  # Wall batching has its own immediate-upgrade path.
        screen_y = region.y1 + y*(region.y2-region.y1)/100
        # Re-read only the label; scenery behind the full menu corrupts words.
        focused = m.read_text(m.crop_percent(image,m.Roi(41,screen_y-2,54,screen_y+2)),scale=2)
        if focused:
            title = re.sub(r'\s*x\w+\s*$', '', focused)
        if normal(title).startswith('remp'):
            continue
        if is_town_hall(title) and not include_town_hall:
            continue
        cost = m.read_result_amount(m.crop_percent(image,m.Roi(55.7,screen_y-2,62.7,screen_y+2)))
        resource = resource_icon(image,m.Roi(54.5,screen_y-1.8,57.1,screen_y+1.8))
        if cost and resource:
            result.append((title, screen_y, cost, resource))
    return result


def town_hall_ready(image):
    """Only unlock HDV on a fully readable list containing no other work."""
    m = engine()
    ratio = builder_count(image, with_total=True)
    if ratio is None or ratio[0] != ratio[1]:
        return False  # Other upgrades are still running.
    words = m.read_word_centers(m.crop_percent(image,m.Roi(39,12,64,64)))
    ends = [y for text,x,y in words if normal(text).startswith(('autres','aubres'))]
    if len(ends)>1 or not any('suggere' in normal(t) for t,x,y in words):
        return False
    if ends and any(y>ends[0]+4 for t,x,y in words):
        return False  # Includes walls, unaffordable rows and unreadable labels.
    allowed = {'ameliorations','en','cours','disponible','suggerees','autres','aubres','hotel','hobel','de','ville'}
    labels = [normal(t).strip('!?:.,') for t,x,y in words]
    if not all(t in allowed or t.isdigit() or not t for t in labels):
        return False
    numeric_rows = [y for t,x,y in words if normal(t).strip('!?:.,').isdigit()]
    if not numeric_rows or max(numeric_rows)-min(numeric_rows)>3:
        return False
    return any(t in ('hotel','hobel') for t in labels) and 'ville' in labels


def find_payable_upgrade(app, window, free, balances):
    """Walk the game's order: suggested rows, then other upgrades."""
    m = engine()
    # Reset the retained menu scroll before walking the game's priority order.
    for _ in range(3):
        app._capture(window)
        with app.action_lock:
            app._check_stopped()
            if not m.WindowDriver.scroll_menu(window,delta=1200):
                raise RuntimeError('Retour au début de la liste refusé.')
        app._wait(.2)
    previous = None
    for _ in range(16):
        menu = app._capture(window)
        items = suggested_items(menu, include_others=True)
        for item in items:
            if can_start_upgrade(free, balances[0 if item[3]=='or' else 1], item[2]):
                return item
        # Text equality avoids treating animated scenery as further scrolling.
        signature = normal(m.read_text(m.crop_percent(menu,m.Roi(39,12,64,64)),scale=2))
        if signature and signature == previous:
            if town_hall_ready(menu):
                for item in suggested_items(menu,include_others=True,include_town_hall=True):
                    if is_town_hall(item[0]) and can_start_upgrade(free,balances[0 if item[3]=='or' else 1],item[2]):
                        return item
            return None
        previous = signature
        with app.action_lock:
            app._check_stopped()
            if not m.WindowDriver.scroll_menu(window):
                raise RuntimeError('Défilement de la liste des améliorations refusé.')
        app._wait(.4)
    return None


def upgrade_suggested(app, window):
    m = engine()
    if app.settings.dry_run:
        return 0
    completed = 0
    for _ in range(5):
        free = stable_builders(app, window)
        if free is None or free <= 1:
            app.events.put('Ouvrier réservé : aucune autre amélioration longue lancée.' if free == 1 else
                           'Ouvriers indisponibles ou illisibles : aucune amélioration longue lancée.')
            return completed
        balances = app.stable_reserves(window)
        if balances is None:
            return completed
        if not m.builders_menu_open(app._capture(window)):
            app._wall_click(window, m.BUILDERS_BUTTON, 'liste des ouvriers')
        choice = None
        for _ in range(3):
            candidate = find_payable_upgrade(app,window,free,balances)
            if candidate is None:
                break
            # The menu can keep sliding after a wheel message or a completed
            # upgrade. Re-read the row at its click position before selecting.
            app._wait(.5)
            menu = app._capture(window)
            visible = suggested_items(menu,include_others=True) if m.builders_menu_open(menu) else []
            if any(abs(row[1]-candidate[1]) < .8 and row[2:] == candidate[2:]
                   for row in visible):
                choice = candidate
                break
        if choice is None:
            app.events.put('Aucun bâtiment payable dans la liste : ressources conservées pour les prochaines améliorations ; HDV reporté tant que les autres ne sont pas terminées.')
            app._wall_click(window, m.BUILDERS_BUTTON, 'fermer la liste des ouvriers')
            return completed
        title, y, cost, resource = choice
        town_hall = is_town_hall(title)
        app._wall_click(window, (47,y), title)
        selected = app._capture(window)
        # The world-space building label is occluded by the open builder menu.
        # Verify its identity on the confirmation dialog before any spending.
        labels = m.crop_percent(selected,m.Roi(25,81,76,87))
        buttons = []
        for scale in (1,2):
            buttons = [(25+x*.51,81+y*.06) for text,x,y in m.read_word_centers(labels.resize((labels.width*scale,labels.height*scale)))
                       if normal(text).strip('.,:').replace('0','o').replace('1','l') in ('ameliorer','ameiiorer')]
            if buttons:
                break
        if len(buttons) != 1:
            app.events.put('Bâtiment sélectionné sans bouton Améliorer unique : sélection reportée.')
            return completed
        app._wall_click(window, buttons[0], 'ouvrir la confirmation')
        dialog = app._capture(window)
        headings = confirmation_headings(dialog)
        if any(is_town_hall(heading) for heading in headings) and not town_hall:
            app._wall_click(window,(88.4,7.5),'fermer la confirmation HDV interdite')
            raise RuntimeError('HDV exclu des améliorations automatiques : aucune dépense envoyée.')
        if not any(normal(title) in heading and 'niveau' in heading for heading in headings):
            app._wall_click(window,(88.4,7.5),'fermer la confirmation inattendue')
            app.events.put('Confirmation de bâtiment différente de la ligne lue : aucune dépense envoyée.')
            return completed
        raw = m.read_text(m.crop_percent(dialog,m.Roi(64,85,74,89)),scale=2)
        amount = re.sub(r'\s','',normal(raw).translate(str.maketrans({'s':'5','o':'0'})))
        confirmed_resource = resource_icon(dialog,m.Roi(74.5,85.5,77.5,92))
        if not amount.isdigit() or int(amount)!=cost or confirmed_resource!=resource:
            raise RuntimeError('Coût ou ressource non confirmé : aucune dépense envoyée.')
        # Re-open the same dialog after a fresh builder/reserve check; a user
        # or another client may have assigned a builder during inspection.
        app._wall_click(window,(88.4,7.5),'fermer la confirmation')
        free = stable_builders(app,window)
        balances = app.stable_reserves(window)
        if balances is None or not can_start_upgrade(free,balances[0 if resource=='or' else 1],cost):
            app.events.put(f'Contrôle avant dépense non validé : ouvriers={free}, réserves={balances}, coût={cost}.')
            return completed
        if town_hall:
            app._wall_click(window,m.BUILDERS_BUTTON,'revérifier les autres améliorations avant HDV')
            ready = town_hall_ready(app._capture(window))
            app._wall_click(window,m.BUILDERS_BUTTON,'fermer la liste des ouvriers')
            if not ready:
                app.events.put('HDV reporté : les autres améliorations ne sont pas toutes confirmées terminées.')
                return completed
        app._wall_click(window,buttons[0],'rouvrir la confirmation')
        final = app._capture(window)
        if not any(normal(title) in heading and 'niveau' in heading for heading in confirmation_headings(final)):
            raise RuntimeError('La confirmation a changé : arrêt.')
        final_amount = re.sub(r'\s','',normal(m.read_text(m.crop_percent(final,m.Roi(64,85,74,89)),scale=2)).translate(str.maketrans({'s':'5','o':'0'})))
        if final_amount != amount or resource_icon(final,m.Roi(74.5,85.5,77.5,92)) != resource:
            raise RuntimeError('Le prix ou la ressource a changé : aucune dépense envoyée.')
        app._wall_click(window,(70,87),'confirmer l’amélioration conseillée')
        app._wait(1)
        after = stable_builders(app,window)
        reserves = app.stable_reserves(window)
        index = 0 if resource=='or' else 1
        if after != free-1 or after < 1 or reserves is None or abs(reserves[index]-(balances[index]-cost))>20_000:
            raise RuntimeError('Amélioration envoyée mais non confirmée : arrêt des dépenses.')
        completed += 1
        app.events.put(f'{title} : amélioration lancée pour {cost:,} {resource} ; {after} ouvrier(s) libre(s).')
    return completed
