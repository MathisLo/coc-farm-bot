"""Village upgrades, preserving one regular builder for walls."""
import re
import unicodedata
import sys
from collections import Counter
from difflib import SequenceMatcher
from PIL import ImageChops, ImageStat

def engine():
    module = sys.modules.get("main") or sys.modules["__main__"]
    if hasattr(module, 'Roi'):
        return module
    import importlib
    return importlib.import_module('main')



def normal(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn').replace('ressorc', 'ressort').replace('ressorb', 'ressort')


def canonical_title(text):
    return ''.join(re.findall(r'[a-z0-9]+', normal(text)))


def same_building_title(a, b):
    a, b = canonical_title(a), canonical_title(b)
    return bool(a and b and (a == b or (min(len(a), len(b)) >= 9 and
                                 SequenceMatcher(None, a, b).ratio() >= .83)))


def title_matches_heading(title, heading):
    text = normal(heading)
    if 'niveau' not in text:
        return False
    before = canonical_title(text.split('niveau', 1)[0])
    if before.endswith('au'):
        before = before[:-2]
    expected = canonical_title(title)
    if not expected:
        return False
    if len(before) >= len(expected) and same_building_title(expected, before[-len(expected):]):
        return True
    tokens = [token for token in re.findall(r'[a-z0-9]+', normal(title)) if len(token) >= 6]
    return any(token in before for token in tokens)


def is_town_hall(title):
    label = re.sub(r'[^a-z]', '', normal(title).replace('0','o'))
    # Also reject the OCR variants observed on the recommendation row.
    return any(word in label for word in ('hotel', 'hobel', 'ville', 'hdv'))


def is_wall_row(title):
    label = canonical_title(title)
    return 'mpart' in label or bool(re.fullmatch(r'x\d+', label))


def confirmation_headings(image):
    m = engine()
    return [normal(m.read_text(m.crop_percent(image, roi), scale=scale))
            for roi, scale in ((m.Roi(15,3,85,10),1), (m.Roi(20,4,80,9),2))]


def direct_upgrade_button(image, title, cost, resource):
    """Find a verified direct confirmation on special building panels."""
    m = engine()
    if not any(title_matches_heading(title, heading) for heading in confirmation_headings(image)):
        return None
    roi = m.Roi(75,18,90,67)
    buttons = []
    for word, x, y in m.read_word_centers(m.crop_percent(image, roi)):
        if not same_building_title(word, 'confirmer'):
            continue
        px = roi.x1 + x * (roi.x2 - roi.x1) / 100
        py = roi.y1 + y * (roi.y2 - roi.y1) / 100
        price_roi = m.Roi(px-5,py+1,px+4,py+5)
        icon_roi = m.Roi(px+2.5,py+.5,px+5.5,py+4.5)
        observed = m.read_result_amount(m.crop_percent(image,price_roi))
        if observed == cost and resource_icon(image,icon_roi) == resource:
            buttons.append((px,py))
    if len(buttons) == 1:
        return buttons[0]
    for px, py, button_roi, price_roi, icon_roi in (
            (83.0, 58.0, m.Roi(78,55,88,64), m.Roi(78,59,87,63), m.Roi(85.5,58.5,88.5,62.5)),
            (83.0, 43.0, m.Roi(78,39,88,47), m.Roi(78,42,86,47), m.Roi(85.5,41,88.5,46))):
        button = m.crop_percent(image, button_roi).convert('RGB')
        pixels = list(button.get_flattened_data())
        green = sum(g > r * 1.3 and g > b * 1.2 and g > 100 for r, g, b in pixels)
        if (green > len(pixels) * .2
                and m.read_result_amount(m.crop_percent(image, price_roi)) == cost
                and resource_icon(image, icon_roi) == resource):
            return (px, py)
    return None


def selected_panel_matches(image, title, cost, resource):
    m = engine()
    if image.width < 1500:
        # The compact title is stylized and unreadable by OCR. The next
        # confirmation dialog must still match the building title and price.
        for rois, icon in (
                ((m.Roi(45,74,54,80), m.Roi(44,73,55,80)), m.Roi(52,74,55,80)),
                ((m.Roi(50,74,59,80), m.Roi(49,73,59,80)), m.Roi(56,75,58,78))):
            readings = []
            for roi in rois:
                raw = m.read_text(m.crop_percent(image,roi),scale=2).strip(" +.,'\"*")
                if re.fullmatch(r'\d[\d\s]*',raw):
                    readings.append(int(re.sub(r'\s','',raw)))
            if readings == [cost,cost] and resource_icon(image,icon) == resource:
                return True
        return False
    if (m.read_result_amount(m.crop_percent(image,m.Roi(50,74,58,78))) != cost
            or resource_icon(image,m.Roi(56,74,58,79)) != resource):
        return False
    heading = ' '.join(normal(m.read_text(m.crop_percent(image, roi), scale=scale))
                       for roi, scale in ((m.Roi(20,68,80,78),1), (m.Roi(20,66,80,81),2)))
    observed = canonical_title(heading)
    tokens = [token for token in re.findall(r'[a-z0-9]+', normal(title)) if len(token) >= 6]
    return bool(tokens and any(
        token in observed or any(
            SequenceMatcher(None, token, observed[start:start+length]).ratio() >= .78
            for length in range(max(4,len(token)-2),len(token)+3)
            for start in range(max(0,len(observed)-length+1)))
        for token in tokens))


def selected_panel_title_matches(image, title):
    """Permit opening a dialog when a shifted button price cannot be read."""
    m = engine()
    expected = canonical_title(title)
    if len(expected) < 6:
        return False
    for scale in (1, 2):
        raw = normal(m.read_text(m.crop_percent(image, m.Roi(20,65,80,82)), scale=scale))
        if 'niveau' not in raw:
            continue
        observed = canonical_title(raw.split('niveau', 1)[0])
        if any(SequenceMatcher(None, expected, observed[start:start+length]).ratio() >= .78
               for length in range(max(4, len(expected)-1), len(expected)+3)
               for start in range(max(0, len(observed)-length+1))):
            return True
    return False


def confirmation_cost(image):
    m = engine()
    readings = []
    rois = (m.Roi(63,87,76,93), m.Roi(63,87,75,93)) if image.width < 1500 else (m.Roi(63,86,75,91),)
    for roi in rois:
        price = m.crop_percent(image,roi)
        for scale in (1,2,3,4):
            raw = m.read_text(price,scale=scale).strip(" +.,'\"*")
            raw = raw.translate(str.maketrans({'S':'5','s':'5','O':'0','o':'0'}))
            if re.fullmatch(r'\d[\d\s]*',raw):
                amount = int(re.sub(r'\s','',raw))
                if 0 < amount <= 20_000_000:
                    readings.append(amount)
    votes = Counter(readings)
    return next((amount for amount,count in votes.items() if count >= 2),None)


def builder_count(image, with_total=False):
    m = engine()
    # The x=41% counter may belong to a temporary Goblin Builder event.
    # Only the regular village counter at x=51% may reserve builders.
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
        for height, scale in ((64,1),(64,2),(46,2)):
            digits = ink.resize((round(ink.width*height/ink.height),height))
            font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf',height)
            label_width = round(height*3.8)
            context = Image.new('RGB',(label_width+10+digits.width,height+16),'white')
            ImageDraw.Draw(context).text((0,0),'Ouvriers',font=font,fill='black')
            context.paste(digits,(label_width+10,8))
            raw = m.read_text(context,scale=scale)
            match = re.search(r'(?<!\d)([0-6])/([1-6])(?!\d)',raw)
            if match and int(match[1]) <= int(match[2]):
                return (int(match[1]),int(match[2])) if with_total else int(match[1])
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
    for attempt in range(4):
        current = builder_count(app._capture(window))
        app._trace('OUVRIERS',f'Lecture {attempt+1}/4 : libres={current}, précédente={previous}')
        if current is not None and current == previous:
            app._trace('OUVRIERS',f'Compteur confirmé : {current} libre(s)')
            return current
        previous = current
        app._wait(.25)
    app._trace('REFUS','Compteur des ouvriers non confirmé après quatre lectures ; aucune dépense.')
    return None


def stable_builder_ratio(app, window):
    """Read the free/total builder ratio twice before a final upgrade."""
    previous = None
    for attempt in range(4):
        current = builder_count(app._capture(window), with_total=True)
        app._trace('OUVRIERS', f'Ratio lecture {attempt + 1}/4 : {current}, precedente={previous}')
        if current is not None and current == previous:
            return current
        previous = current
        app._wait(.25)
    return None


def can_start_upgrade(free, balance, cost):
    return (type(free) is int and free >= 2 and type(balance) is int and
            type(cost) is int and cost > 0 and balance >= cost)


def resource_icon(image, roi):
    m = engine()
    pixels = list(m.crop_percent(image, roi).convert('RGB').get_flattened_data())
    gold = sum(r > 180 and g > 130 and b < 100 for r,g,b in pixels)
    elixir = sum(r > 130 and b > 120 and g < min(r,b)*.75 for r,g,b in pixels)
    if max(gold, elixir) < len(pixels)*.1 or min(gold,elixir)*3 > max(gold,elixir):
        return None
    return 'or' if gold > elixir else 'élixir'


def builder_price_resource(image, y):
    """Read a price across small OCR row offsets without borrowing a neighbor."""
    m = engine()
    price_x1, price_x2 = (56.6, 64.2) if image.width < 1500 else (57, 65)
    costs = [m.read_result_amount(m.crop_percent(image,m.Roi(price_x1,y+offset-2,price_x2,y+offset+2)))
             for offset in (-.4,0,.4)]
    if not any(costs):
        costs = [m.read_result_amount(m.crop_percent(image,m.Roi(55.7,y+offset-2,62.7,y+offset+2)))
                 for offset in (-.4,0,.4)]
    resources = {resource_icon(image, roi) for roi in
                 (m.Roi(54.5,y-1.8,57.1,y+1.8), m.Roi(55,y-1.8,57,y+1.8),
                  m.Roi(56.5,y-1.8,58.5,y+1.8))}
    resources.discard(None)
    votes = Counter(cost for cost in costs if cost)
    if len(resources) != 1 or not votes:
        return None
    return (min(votes, key=lambda cost: (-votes[cost], cost)), resources.pop())


def suggested_items(image, include_others=False, include_town_hall=False):
    m = engine()
    region = m.Roi(39,12,64,64)
    words = m.read_word_centers(m.crop_percent(image, region))
    starts = [y for text,x,y in words if 'suggere' in normal(text)]
    ends = [y for text,x,y in words if re.sub(r'^[^a-z]+', '', normal(text)).startswith(('autres','aubres','ubres'))]
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
        if is_wall_row(title):
            continue  # Wall batching has its own immediate-upgrade path.
        screen_y = region.y1 + y*(region.y2-region.y1)/100
        # Re-read only the label; scenery behind the full menu corrupts words.
        focused = m.read_text(m.crop_percent(image,m.Roi(39,screen_y-2,56,screen_y+2)),scale=2)
        if focused:
            title = re.sub(r"[\s,]+x\S*$", '', focused, flags=re.I).strip(" '•.,:")
        if is_wall_row(title):
            continue
        if len(canonical_title(title)) < 5:
            continue
        if is_town_hall(title) and not include_town_hall:
            continue
        price = builder_price_resource(image,screen_y)
        if price:
            cost, resource = price
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
    if ends:
        for text, _x, y in words:
            if y <= ends[0] + 4:
                continue
            label = normal(text).strip('!?:.,')
            compact = label.replace(' ', '')
            numeric = compact.lstrip('x').replace('.', '')
            if 'remp' in label or (numeric and numeric.isdigit()):
                continue
            return False
    labels = [normal(t).strip('!?:.,') for t, _x, _y in words]
    return any(t in ('hotel','hobel') for t in labels) and 'ville' in labels


def scroll_builders_to_top(app, window):
    """Scroll until the suggested-upgrades heading is actually visible."""
    m = engine()
    previous_menu = None
    for attempt in range(20):
        menu = app._capture(window)
        if not m.builders_menu_open(menu):
            raise RuntimeError('Liste des ouvriers absente : aucun défilement envoyé.')
        # A village with many builders already in progress can push the
        # suggested section below the old 45% crop. Read the full menu band
        # before scrolling; otherwise an already-top menu is needlessly
        # scrolled twenty times and the wall/building pass aborts.
        heading = normal(m.read_text(m.crop_percent(menu,m.Roi(37,11,65,65)),scale=2))
        has_running_header = any(marker in heading for marker in ('en cours', 'encours', 'enpours'))
        app._trace('MENU OUVRIERS',f'Retour en haut {attempt+1}/20 : texte={heading[:500]!r}')
        if 'sugger' in heading and has_running_header and 'disponible' in heading:
            app._trace('MENU OUVRIERS','Début de la liste confirmé.')
            return
        # The live VM can omit the suggested heading for one OCR pass even
        # after the menu reached the top. Require a stable frame and the
        # fixed in-progress/available header before accepting that state.
        if (previous_menu is not None and _menu_image_is_stable(previous_menu, menu)
                and has_running_header and 'disponible' in heading):
            app._trace('MENU OUVRIERS','DÃ©but de la liste confirmÃ© par image stable.')
            return
        previous_menu = menu
        with app.action_lock:
            app._check_stopped()
            app._trace('DÉFILEMENT', 'Améliorations : retour vérifié au début de la liste')
            if not m.WindowDriver.scroll_menu(window,delta=1200):
                raise RuntimeError('Retour au début de la liste refusé.')
        app._wait(.25)
    raise RuntimeError('Début de la liste des ouvriers non confirmé après défilement.')


def _menu_image_is_stable(previous, current):
    if previous is None or not hasattr(previous, 'resize') or not hasattr(current, 'resize'):
        return False
    try:
        box = (0.38, 0.12, 0.64, 0.99)
        def crop(image):
            width, height = image.size
            return image.crop((round(width*box[0]), round(height*box[1]), round(width*box[2]), round(height*box[3]))).resize((260,520))
        difference = ImageChops.difference(crop(previous).convert('RGB'), crop(current).convert('RGB'))
        return max(ImageStat.Stat(difference).mean) < 2.5
    except (AttributeError, ValueError):
        return False


def menu_anchor_rows(image):
    """Read label positions without prices or animated scenery behind the menu."""
    m = engine()
    region = m.Roi(39, 12, 56, 64)
    words = m.read_word_centers(m.crop_percent(image, region))
    rows = []
    for word, _x, y in sorted(words, key=lambda item: item[2]):
        label = canonical_title(word)
        if len(label) < 4:
            continue
        screen_y = region.y1 + y * (region.y2 - region.y1) / 100
        if rows and abs(screen_y - rows[-1][0]) < 1.5:
            rows[-1] = (rows[-1][0], rows[-1][1] + label)
        else:
            rows.append((screen_y, label))
    return rows


def menu_rows_stationary(previous, current):
    """Detect an exhausted scroll despite small OCR changes between frames."""
    if len(previous) < 3 or len(current) < 3:
        return False
    matched = sum(any(abs(y - old_y) < 1.5 and
                      SequenceMatcher(None, label, old_label).ratio() >= .75
                      for old_y, old_label in previous)
                  for y, label in current)
    return matched >= 3 and matched >= min(len(previous), len(current)) * .6


def find_payable_upgrade(app, window, free, balances, include_town_hall=False, excluded_titles=None):
    """Inspect the whole list, then relocate the most expensive payable row."""
    m = engine()
    app._trace('BÂTIMENTS',f'Recherche du plus cher : ouvriers={free}, réserves={balances}, HDV exclu')
    scroll_builders_to_top(app,window)
    previous = None
    previous_image = None
    previous_rows = []
    previous_items = []
    unchanged = 0
    observations = []
    ambiguous_prices = []
    for _ in range(5):
        seen_top = set()
        for item in suggested_items(app._capture(window), include_town_hall=include_town_hall):
            if (any(same_building_title(item[0], title) for title in excluded_titles or ())
                    or not can_start_upgrade(free, balances[0 if item[3]=='or' else 1], item[2])):
                continue
            index = next((index for index, record in enumerate(observations)
                          if record[1] == item[2:] and same_building_title(record[0], item[0])), None)
            if index is None:
                observations.append([item[0], item[2:], 0, item])
                index = len(observations)-1
            if index not in seen_top:
                observations[index][2] += 1
                observations[index][3] = item
                seen_top.add(index)
    for page in range(20):
        menu = app._capture(window)
        items = suggested_items(menu, include_others=True, include_town_hall=include_town_hall)
        app._trace('BÂTIMENTS',f'Page {page+1}/20 : lignes={items!r}')
        seen = set()
        for item in items:
            if excluded_titles and any(same_building_title(item[0], title) for title in excluded_titles):
                continue
            if not can_start_upgrade(free, balances[0 if item[3]=='or' else 1], item[2]):
                app._trace('BÂTIMENTS',f'Ligne non payable : {item!r}')
                continue
            index = next((index for index, record in enumerate(observations)
                          if record[1] == item[2:] and same_building_title(record[0],item[0])), None)
            if index is None:
                observations.append([item[0],item[2:],0,item])
                index = len(observations)-1
            if index not in seen:
                observations[index][2] += 1
                observations[index][3] = item
                seen.add(index)
        # Text equality avoids treating animated scenery as further scrolling.
        signature = normal(m.read_text(m.crop_percent(menu,m.Roi(39,12,64,64)),scale=2))
        rows = menu_anchor_rows(menu)
        stationary = menu_rows_stationary(previous_rows, rows)
        if stationary:
            for title, y, cost, resource in items:
                for old_title, old_y, old_cost, old_resource in previous_items:
                    if (resource == old_resource and abs(y - old_y) < 1.5 and
                            min(cost, old_cost) > 0 and max(cost, old_cost) >= 3 * min(cost, old_cost)):
                        ambiguous_prices.extend(((y, cost, resource), (old_y, old_cost, old_resource)))
                        app._trace('BÂTIMENTS', f'Prix contradictoires sur la même ligne : {old_title!r} {old_cost}, {title!r} {cost} {resource}')
        unchanged = unchanged + 1 if ((signature and signature == previous) or
                                      stationary) else 0
        if _menu_image_is_stable(previous_image, menu) and page >= 2:
            unchanged = max(unchanged, 2)
        if unchanged >= 2:
            break
        previous = signature
        previous_image = menu
        previous_rows = rows
        previous_items = items
        if not m.builders_menu_open(menu):
            raise RuntimeError('Liste des ouvriers fermée pendant la recherche : aucun défilement envoyé.')
        with app.action_lock:
            app._check_stopped()
            app._trace('DÉFILEMENT', 'Améliorations : ligne suivante')
            if not m.WindowDriver.scroll_menu(window,delta=-1200):
                raise RuntimeError('Défilement de la liste des améliorations refusé.')
        app._wait(.35)
    confirmed = [record for record in observations if record[2] >= 2 and not any(
        abs(record[3][1] - y) < 1.5 and record[1] == (cost, resource)
        for y, cost, resource in ambiguous_prices)]
    app._trace('BÂTIMENTS',f'Lignes vues au moins deux fois : {[(record[0],record[1],record[2]) for record in confirmed]!r}')
    if not confirmed:
        app.events.put('Liste des ouvriers parcourue : aucune amélioration payable lue sur deux captures.')
        return None
    best = max(confirmed, key=lambda record: record[1][0])[3]
    app.events.put(f'Bâtiment le plus cher reconnu : {best[0]}, {best[2]:,} {best[3]}.')
    # The scan ends elsewhere in the list. Re-find the exact row before a click.
    pages_scanned = page + 1
    scroll_builders_to_top(app,window)
    for page in range(pages_scanned):
        for _ in range(4 if page == 0 else 1):
            menu = app._capture(window)
            for item in suggested_items(menu,include_others=True,include_town_hall=include_town_hall):
                if excluded_titles and any(same_building_title(item[0], title) for title in excluded_titles):
                    continue
                if same_building_title(item[0], best[0]) and item[2:] == best[2:]:
                    app._trace('BÂTIMENTS',f'Ligne retrouvée page {page+1} : {item!r}')
                    return item
            if page == 0:
                title = m.read_text(m.crop_percent(menu,m.Roi(39,best[1]-2,56,best[1]+2)),scale=2)
                if (same_building_title(title,best[0])
                        and builder_price_resource(menu,best[1]) == best[2:]):
                    app._trace('BÂTIMENTS',f'Ligne du haut retrouvée : {title!r}, y={best[1]:.2f}')
                    return best
        if not m.builders_menu_open(menu):
            raise RuntimeError('Liste des ouvriers fermée avant de retrouver la ligne : aucun défilement envoyé.')
        with app.action_lock:
            app._check_stopped()
            app._trace('DÉFILEMENT', 'Améliorations : retrouver la ligne sélectionnée')
            if not m.WindowDriver.scroll_menu(window,delta=-1200):
                raise RuntimeError('Défilement de la liste des améliorations refusé.')
        app._wait(.35)
    app.events.put('Bâtiment le plus cher perdu après défilement : aucun clic envoyé.')
    return None


def perform_direct_upgrade(app, window, title, cost, resource):
    """Reopen and recheck a special panel before its direct payment click."""
    m = engine()
    app._wall_click(window,(88.4,7.5),'fermer la confirmation directe')
    free = stable_builders(app,window)
    balances = app.stable_reserves(window)
    app._trace('BÂTIMENTS',f'Contrôle direct avant achat : {title!r}, coût={cost} {resource}, ouvriers={free}, réserves={balances}')
    if balances is None or not can_start_upgrade(free,balances[0 if resource=='or' else 1],cost):
        app.events.put(f'Contrôle avant dépense non validé : ouvriers={free}, réserves={balances}, coût={cost}.')
        return None
    menu = app._capture(window)
    visible = suggested_items(menu,include_others=True)
    if not visible and not m.builders_menu_open(menu):
        app._wall_click(window,m.BUILDERS_BUTTON,'rouvrir la liste des ouvriers')
        menu = app._capture(window)
        visible = suggested_items(menu,include_others=True)
    matches = [item for item in visible if same_building_title(item[0],title) and
               item[2:] == (cost,resource)]
    app._trace('BÂTIMENTS',f'Ligne directe retrouvée : {matches!r}')
    if len(matches) != 1:
        app.events.put('Ligne de l’amélioration directe introuvable après contrôle : aucune dépense envoyée.')
        return None
    app._wall_click(window,(44,matches[0][1]),'rouvrir l’amélioration directe')
    final = app._capture(window)
    button = direct_upgrade_button(final,title,cost,resource)
    for _ in range(4):
        if button is not None:
            break
        app._wait(.4)
        final = app._capture(window)
        button = direct_upgrade_button(final,title,cost,resource)
    app._trace('BÂTIMENTS',f'Bouton direct vérifié : {button!r}, coût={cost} {resource}')
    if button is None:
        raise RuntimeError('Confirmation directe modifiée : aucune dépense envoyée.')
    app._wall_click(window,button,'confirmer l’amélioration directe vérifiée')
    after_click = app._capture(window)
    if any(title_matches_heading(title,heading) for heading in confirmation_headings(after_click)):
        # Special building panels remain open after the purchase and hide the
        # worker and resource counters used to verify the actual spend.
        app._wall_click(window,(88.4,7.5),'fermer le panneau après confirmation')
    return free, balances


def verify_building_spend(app, window, title, cost, resource, free, balances):
    app._wait(1)
    after = stable_builders(app,window)
    reserves = app.stable_reserves(window)
    index = 0 if resource == 'or' else 1
    app._trace('BÂTIMENTS',f'Après achat {title!r} : ouvriers {free}->{after}, réserves {balances}->{reserves}, coût attendu={cost} {resource}')
    if after != free-1 or after < 1 or reserves is None or abs(reserves[index]-(balances[index]-cost))>20_000:
        raise RuntimeError('Amélioration envoyée mais non confirmée : arrêt des dépenses.')
    app.events.put(f'{title} : amélioration lancée pour {cost:,} {resource} ; {after} ouvrier(s) libre(s).')


def stable_upgrade_row(app, window, title, cost, resource, include_town_hall=False):
    """Relocate a moving builder row before any click is sent."""
    m = engine()
    previous_y = None
    for attempt in range(6):
        app._wait(.35)
        menu = app._capture(window)
        if not m.builders_menu_open(menu):
            return None
        matches = [item for item in suggested_items(menu, include_others=True,
                                                   include_town_hall=include_town_hall)
                   if same_building_title(item[0], title) and item[2:] == (cost, resource)]
        app._trace('BÂTIMENTS', f'Ligne avant clic {attempt + 1}/6 : {matches!r}')
        if len(matches) != 1:
            previous_y = None
            continue
        current_y = matches[0][1]
        if previous_y is not None and abs(current_y - previous_y) <= .8:
            return current_y
        previous_y = current_y
    return None


def upgrade_suggested(app, window, max_upgrades=5):
    m = engine()
    if app.settings.dry_run:
        return 0
    completed = 0
    skipped_titles = set()
    failed_choices = 0
    for _ in range(max_upgrades):
        free = stable_builders(app, window)
        app._trace('BÂTIMENTS',f'Début du tour {completed+1} : ouvriers libres={free}')
        if free is None or free <= 1:
            app.events.put('Ouvrier réservé : aucune autre amélioration longue lancée.' if free == 1 else
                           'Ouvriers indisponibles ou illisibles : aucune amélioration longue lancée.')
            return completed
        balances = app.stable_reserves(window)
        if balances is None and m.builders_menu_open(app._capture(window)):
            app._wall_click(window, m.BUILDERS_BUTTON, 'fermer la liste avant nouvelle lecture des réserves')
            balances = app.stable_reserves(window)
        app._trace('BÂTIMENTS',f'Réserves avant recherche : {balances}')
        if balances is None:
            return completed
        if not m.builders_menu_open(app._capture(window)):
            app._wall_click(window, m.BUILDERS_BUTTON, 'liste des ouvriers')
            if not m.builders_menu_open(app._capture(window)):
                app.events.put('Liste des ouvriers non confirmée : aucune amélioration lancée.')
                return completed
        choice = None
        allow_town_hall = False
        candidate = find_payable_upgrade(app,window,free,balances,excluded_titles=skipped_titles)
        if candidate is None:
            menu = app._capture(window)
            ratio = builder_count(menu, with_total=True)
            if ratio and ratio[0] == ratio[1] and town_hall_ready(menu):
                app.events.put('Toutes les autres améliorations sont terminées : recherche de l’Hôtel de ville autorisée.')
                candidate = find_payable_upgrade(app,window,free,balances,include_town_hall=True,excluded_titles=skipped_titles)
                allow_town_hall = bool(candidate and is_town_hall(candidate[0]))
        if candidate is not None:
            choice = candidate
            app._trace('UPGRADE', f'Row ready for selection: {choice!r}')
        if choice is None:
            app.events.put(f'Aucune amélioration payable et confirmée dans la liste ; ouvriers libres={free}, réserves={balances}. Hôtel de ville exclu.')
            if m.builders_menu_open(app._capture(window)):
                app._wall_click(window, m.BUILDERS_BUTTON, 'fermer la liste des ouvriers')
            return completed
        title, y, cost, resource = choice
        app._trace('BÂTIMENTS',f'Sélection : {title!r} à y={y:.2f} %, coût={cost} {resource}')
        if is_town_hall(title) and not allow_town_hall:
            raise RuntimeError('Hôtel de ville exclu des améliorations automatiques.')
        # The list can move after the row is found; confirm its current
        # position from title and price on two consecutive captures.
        settled_y = stable_upgrade_row(app, window, title, cost, resource,
                                      include_town_hall=allow_town_hall)
        if settled_y is None:
            app.events.put(f'Ligne {title} déplacée ou illisible avant le clic : aucune sélection envoyée.')
            skipped_titles.add(title)
            failed_choices += 1
            if failed_choices >= 2:
                app.events.put('Deux lignes de bâtiments instables : reprise des remparts et des attaques.')
                return completed
            continue
        if abs(settled_y - y) > .8:
            app._trace('BÂTIMENTS', f'Ligne {title} recalée de {y:.2f} % à {settled_y:.2f} %.')
        y = settled_y
        app._wall_click(window, (44,y), title)
        selected = app._capture(window)
        # The builder list remains as a translucent overlay. Close it before
        # reading the selected building title; otherwise OCR can read the list
        # row or the building behind it instead of the selected panel.
        if m.builders_menu_open(selected):
            app._wall_click(window, m.BUILDERS_BUTTON, 'fermer la liste après sélection')
            for _check in range(3):
                selected = app._capture(window)
                if not m.builders_menu_open(selected):
                    break
                app._wait(.5)
            if m.builders_menu_open(selected):
                app.events.put('Liste des ouvriers encore ouverte après sélection : aucune dépense envoyée.')
                return completed
        if direct_upgrade_button(selected,title,cost,resource) is not None:
            checked = perform_direct_upgrade(app,window,title,cost,resource)
            if checked is None:
                return completed
            verify_building_spend(app,window,title,cost,resource,*checked)
            completed += 1
            failed_choices = 0
            continue
        panel_verified = selected_panel_matches(selected,title,cost,resource)
        if not panel_verified and not selected_panel_title_matches(selected,title):
            app.events.put(f'Sélection vérifiée différente de {title} : aucune dépense envoyée.')
            skipped_titles.add(title)
            failed_choices += 1
            app._wall_click(window,(88.4,7.5),'fermer la sélection refusée')
            if not m.builders_menu_open(app._capture(window)):
                app._wall_click(window, m.BUILDERS_BUTTON, 'rouvrir la liste après sélection refusée')
                if not m.builders_menu_open(app._capture(window)):
                    app.events.put('Liste des ouvriers non confirmée après sélection refusée : arrêt des améliorations.')
                    return completed
            if failed_choices >= 2:
                app.events.put('Deux lignes de bâtiments instables : reprise des remparts et des attaques.')
                return completed
            continue
        if not panel_verified:
            app._trace('BÂTIMENTS', f'Titre {title!r} confirmé sur le panneau ; prix à confirmer dans la boîte de dialogue.')
        # The world-space building label is occluded by the open builder menu.
        # Verify its identity on the confirmation dialog before any spending.
        labels = m.crop_percent(selected,m.Roi(25,81,76,87))
        buttons = []
        for scale in (1,2):
            buttons = [(25+x*.51,81+y*.06) for text,x,y in m.read_word_centers(labels.resize((labels.width*scale,labels.height*scale)))
                       if SequenceMatcher(None, normal(text).strip('.,:').replace('0','o').replace('1','l'), 'ameliorer').ratio() >= .62]
            if buttons:
                break
        if len(buttons) != 1:
            app.events.put('Bâtiment sélectionné sans bouton Améliorer unique : sélection reportée.')
            skipped_titles.add(title)
            app._wall_click(window,(88.4,7.5),'close selection without upgrade button')
            failed_choices += 1
            if failed_choices >= 2:
                app.events.put('Deux lignes de bâtiments instables : reprise des remparts et des attaques.')
                return completed
            continue
        app._wall_click(window, buttons[0], 'ouvrir la confirmation')
        dialog = app._capture(window)
        headings = confirmation_headings(dialog)
        for _ in range(2):
            if any(title_matches_heading(title, heading) for heading in headings):
                break
            app._wait(.45)
            dialog = app._capture(window)
            headings = confirmation_headings(dialog)
        app._trace('BÂTIMENTS',f'Titres de confirmation : {headings!r}')
        if any(is_town_hall(heading) for heading in headings) and not allow_town_hall:
            app._wall_click(window,(88.4,7.5),'fermer la confirmation HDV interdite')
            raise RuntimeError('HDV exclu des améliorations automatiques : aucune dépense envoyée.')
        if not any(title_matches_heading(title,heading) for heading in headings):
            app._wall_click(window,(88.4,7.5),'fermer la confirmation inattendue')
            app.events.put('Confirmation de bâtiment différente de la ligne lue : aucune dépense envoyée.')
            return completed
        confirmed_cost = confirmation_cost(dialog)
        confirmed_resource = resource_icon(dialog,m.Roi(74.5,85.5,77.5,92))
        app._trace('BÂTIMENTS',f'Confirmation : {confirmed_cost} {confirmed_resource}; attendus={cost} {resource}')
        if confirmed_cost != cost or confirmed_resource!=resource:
            raise RuntimeError('Coût ou ressource non confirmé : aucune dépense envoyée.')
        # Re-open the same dialog after a fresh builder/reserve check; a user
        # or another client may have assigned a builder during inspection.
        app._wall_click(window,(88.4,7.5),'fermer la confirmation')
        free = stable_builders(app,window)
        balances = app.stable_reserves(window)
        app._trace('BÂTIMENTS',f'Contrôle final : ouvriers={free}, réserves={balances}, coût={cost} {resource}')
        if balances is None or not can_start_upgrade(free,balances[0 if resource=='or' else 1],cost):
            app.events.put(f'Contrôle avant dépense non validé : ouvriers={free}, réserves={balances}, coût={cost}.')
            return completed
        app._wall_click(window,buttons[0],'rouvrir la confirmation')
        final = app._capture(window)
        if not any(title_matches_heading(title,heading) for heading in confirmation_headings(final)):
            raise RuntimeError('La confirmation a changé : arrêt.')
        final_cost = confirmation_cost(final)
        app._trace('BÂTIMENTS',f'Prix final={final_cost}, ressource finale={resource_icon(final,m.Roi(74.5,85.5,77.5,92))}')
        if final_cost != confirmed_cost or resource_icon(final,m.Roi(74.5,85.5,77.5,92)) != resource:
            raise RuntimeError('Le prix ou la ressource a changé : aucune dépense envoyée.')
        app._wall_click(window,(70,87),'confirmer l’amélioration conseillée')
        verify_building_spend(app,window,title,cost,resource,free,balances)
        completed += 1
        failed_choices = 0
    return completed
