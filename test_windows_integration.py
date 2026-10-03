"""Real Windows OCR and Tk checks; no capture or input in Clash of Clans."""
import tempfile
from tkinter import ttk
import threading
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw
import main
from tools.headless_validation import deployment_matches_configuration


class WindowsIntegrationTests(unittest.TestCase):
    def test_soak_accepts_all_visible_troops_above_configured_minimum(self):
        settings = main.replace(main.Settings(), electrodragon_count=8, dragon_count=1)
        self.assertTrue(deployment_matches_configuration(
            "Déploiement vérifié : 10 électro-dragons, 1 dragons, 4 héros, 5 Rage.", settings))
        self.assertFalse(deployment_matches_configuration(
            "Déploiement vérifié : 7 électro-dragons, 1 dragons, 4 héros, 5 Rage.", settings))
        self.assertFalse(deployment_matches_configuration(
            "Déploiement vérifié : 10 électro-dragons, 1 dragons, 3 héros, 5 Rage.", settings))

    def test_home_attack_button_is_not_multiplayer_menu(self):
        with Image.open(Path(__file__).parent / "testdata" / "suggested_menu.png") as village:
            self.assertTrue(main.has_screen_text(village, "attaquer"))
            self.assertFalse(main.multiplayer_menu_ready(village))
        multiplayer = Image.new("RGB", (1765, 993))
        with Image.open(Path(__file__).parent / "testdata" / "multiplayer_menu.png") as crop:
            multiplayer.paste(crop, (0, 0))
        self.assertTrue(main.multiplayer_menu_ready(multiplayer))
        self.assertFalse(main.army_selection_ready(multiplayer))

    def test_battle_log_is_not_the_multiplayer_attack_menu(self):
        image = Image.new('RGB', (1323, 744))
        with patch.object(main, 'normalized_screen_text', return_value=(
                'multijoueurattaquesjournaldecomatdefenseshistoriquedeligue')):
            self.assertFalse(main.multiplayer_menu_ready(image))

    def test_army_readiness_detects_ten_electrodragons_and_four_heroes(self):
        image = Image.new("RGB", (1765, 993))
        with Image.open(Path(__file__).parent / "testdata" / "army_ready_selection.png") as crop:
            image.paste(crop, (100, 210))
        settings = main.replace(main.Settings(), electrodragon_count=10)
        for frame in (image, image.resize((1920, 1080))):
            ready, _, counts = main.army_readiness(frame, settings)
            self.assertTrue(ready)
            self.assertEqual(counts["electrodragon"], 10)
            self.assertEqual(counts["rage"], 5)
        incomplete = image.copy()
        ImageDraw.Draw(incomplete).rectangle((135, 225, 225, 280), fill="black")
        ready, _, counts = main.army_readiness(incomplete, settings)
        self.assertTrue(ready)
        self.assertEqual(counts["heroes"], 4)
        unavailable = incomplete.copy()
        card_region = main.crop_percent(unavailable, main.Roi(16, 33, 42, 70))
        unavailable.paste(card_region.convert("L").convert("RGB"),
                          (round(unavailable.width * .16), round(unavailable.height * .33)))
        ready, reason, _ = main.army_readiness(unavailable, settings)
        self.assertFalse(ready)
        self.assertIn("héros", reason)

    def test_army_readiness_across_requested_16_9_resolutions(self):
        image = Image.new("RGB", (1765, 993))
        with Image.open(Path(__file__).parent / "testdata" / "army_ready_selection.png") as crop:
            image.paste(crop, (100, 210))
        settings = main.replace(main.Settings(), electrodragon_count=10)
        for size in ((1920, 1080), (2560, 1440), (1387, 780)):
            with self.subTest(size=size):
                frame = image.resize(size, Image.Resampling.LANCZOS)
                ready, reason, counts = main.army_readiness(frame, settings)
                self.assertTrue(ready, reason)
                self.assertEqual(counts["electrodragon"], 10)
                self.assertEqual(counts["rage"], 5)

    def test_enemy_loot_across_requested_16_9_resolutions(self):
        with Image.open(Path(__file__).parent / "testdata" / "enemy_clear.png") as source:
            for size in ((1920, 1080), (2560, 1440), (1387, 780)):
                with self.subTest(size=size):
                    frame = source.resize(size, Image.Resampling.LANCZOS)
                    loot = main.read_enemy_loot(frame)
                    self.assertEqual((loot.gold, loot.elixir, loot.dark_elixir),
                                     (855156, 941101, 9297))

    def test_wall_result_and_connection_across_requested_16_9_resolutions(self):
        fixtures = (
            ("wall_single_4m_1765.png", lambda frame: main.single_wall_confirmation_matches(frame, 4_000_000, "or")),
            ("result_defeat_unread_1765.png", lambda frame: main.read_battle_earnings(frame) == (648788, 326588, 2324)),
            ("connection_lost.png", lambda frame: main.connection_retry_point(frame) is not None),
        )
        for filename, check in fixtures:
            with Image.open(Path(__file__).parent / "testdata" / filename) as source:
                for size in ((1920, 1080), (2560, 1440), (1387, 780)):
                    with self.subTest(filename=filename, size=size):
                        frame = source.resize(size, Image.Resampling.LANCZOS)
                        self.assertTrue(check(frame))

    def test_wall_payment_controls_across_requested_16_9_resolutions(self):
        for filename, single in (("wall_panel_live_1765.png", False),
                                 ("wall_last_selected.png", True)):
            with Image.open(Path(__file__).parent / "testdata" / filename) as source:
                for size in ((1920, 1080), (2560, 1440), (1387, 780)):
                    with self.subTest(filename=filename, size=size):
                        frame = source.resize(size, Image.Resampling.LANCZOS)
                        controls = main.wall_group_controls(frame, single=single,
                                                            expected_price=500_000)
                        self.assertIsNotNone(controls)
                        self.assertEqual(controls["payments"]["or"][1], 500_000)
                        self.assertEqual(controls["payments"]["\u00e9lixir"][1], 500_000)

    def test_enemy_resource_crops_exclude_labels_and_icons(self):
        with Image.open(Path(__file__).parent/'testdata/enemy_clear.png') as im:
            loot=main.read_enemy_loot(im)
            self.assertEqual((loot.gold,loot.elixir,loot.dark_elixir),(855156,941101,9297))

    def test_grass_above_unplaced_queen_is_not_a_health_bar(self):
        before = self.fixture("hero_unplaced.png", (0, 880))
        self.assertEqual([main.hero_health_visible(before, i, -6.25) for i in range(3)], [False]*3)
        after = self.fixture("hero_deployed.png", (0, 880))
        self.assertTrue(main.hero_health_visible(after, 0, -6.25))
        self.assertTrue(main.hero_health_visible(after, 1, -6.25))
        self.assertFalse(main.hero_health_visible(after, 2, -6.25))

    def test_prince_first_card_uses_compact_hero_layout(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'hero_prince_compact_1765.png') as image:
            self.assertEqual(main.hero_layout_shift(image), -6.25)
            self.assertTrue(all(main.hero_card_present(image, index, -6.25) for index in range(4)))

    def test_empty_hero_slot_is_not_a_coloured_card(self):
        image = self.fixture("hero_empty_slot.png", (0, 880))
        self.assertGreater(main.hero_icon_saturation(image, 2, -6.25), 55)
        self.assertEqual([main.hero_placeholder_slot(image, i, -6.25) for i in range(3)],
                         [False, False, True])

    def test_fourth_hero_card_is_detected_without_treating_background_as_hero(self):
        for filename, expected in (("hero_unplaced.png", [True, True, True, False]),
                                   ("hero_empty_slot.png", [True, False, False, False])):
            image = self.fixture(filename, (0, 880))
            self.assertEqual([main.hero_card_present(image, i, -6.25) for i in range(4)], expected)

    def test_rage_card_location_is_independent_of_order_and_hero_row_shift(self):
        for shift, center, hero_count in ((-6.25, 53.6, 4), (0, 59.85, 4),
                                          (0, 30.45, None), (-6.25, 44.5, 2),
                                          (-6.25, 44.5, None), (None, 53.6, None),
                                          (None, 30.45, None)):
            image = Image.new("RGB", (1920, 1080))
            card = Image.new("RGB", (110, 150), (42, 60, 120))
            draw = ImageDraw.Draw(card)
            draw.rounded_rectangle((29, 40, 81, 137), radius=18, fill=(132, 20, 218))
            draw.rounded_rectangle((35, 20, 75, 47), radius=7, fill=(192, 139, 83))
            left = round(image.width * center / 100 - card.width / 2)
            image.paste(card, (left, 900))
            detected = main.rage_card_center(image, shift, hero_count)
            if center == 44.5:
                self.assertAlmostEqual(detected, center, delta=1.5)
            else:
                self.assertAlmostEqual(detected, center, places=2)

    def test_live_compact_rage_counter_uses_actual_card_center(self):
        for filename, expected in (("live_compact_battle_bar.png", 5),
                                   ("live_compact_battle_bar_rage_two.png", 2)):
            image = Image.new("RGB", (1765, 993))
            with Image.open(Path(__file__).parent / "testdata" / filename) as bar:
                image.paste(bar, (0, 830))
            center = main.rage_card_center(image, -6.25)
            self.assertGreater(center, 56)
            self.assertLess(center, 58)
            self.assertEqual(main.read_rage_count(image, center), expected)

    def test_rage_two_template_recovers_when_windows_ocr_is_blank(self):
        for filename, expected in (("live_compact_battle_bar_rage_two.png", True),
                                   ("live_compact_battle_bar.png", False)):
            with self.subTest(filename=filename):
                image = Image.new("RGB", (1765, 993))
                with Image.open(Path(__file__).parent / "testdata" / filename) as bar:
                    image.paste(bar, (0, 830))
                center = main.rage_card_center(image, -6.25)
                with patch.object(main, "read_text", return_value=""):
                    self.assertEqual(main.rage_counter_is_two(image, center), expected)
                    self.assertEqual(main.read_rage_count(image, center), 2 if expected else None)

    def test_event_prefers_gold_or_elixir_over_bonus_troops(self):
        for name, token in (("event_gold.png", "OR"), ("event_elixir.png", "lixi")):
            image = self.fixture(name, (400, 120))
            self.assertTrue(main.battle_reward_open(image))
            point, label = main.battle_reward_choice(image)
            self.assertEqual(point, (70, 53))
            self.assertIn(token.casefold(), label.casefold())
            # During the opening animation, missing card frames must block input.
            image.paste((0, 0, 0), (400, 320, 1530, 345))
            self.assertIsNone(main.battle_reward_choice(image))

    def fixture(self, name, offset):
        image = Image.new("RGB", (1920, 1080))
        with Image.open(Path(__file__).parent / "testdata" / name) as strip:
            image.paste(strip, offset)
        return image

    def test_reserve_digits_on_coloured_bar_and_leading_one(self):
        for name, expected in (("reserves_colour.png", (3926844, 3724487)),
                               ("reserves_leading_one.png", (1426844, 1224487))):
            with self.subTest(name=name):
                image = self.fixture(name, (1500, 0))
                self.assertEqual(tuple(main.read_safe_reserve(image, k) for k in ("gold", "elixir")), expected)
        self.assertIsNone(main.parse_reserve_number("1 4261 844"))

    def test_real_780p_village_reserves(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'village_live_1387x780.png') as image:
            self.assertTrue(main.village_home_ready(image))
            self.assertEqual(main.read_safe_reserve(image, 'gold'), 3_303_214)
            self.assertEqual(main.read_safe_reserve(image, 'elixir'), 4_446_704)
            self.assertTrue(main.wall_selection_open(image))
            icons = main.find_collectible_icons(image)
            self.assertEqual([kind for kind, *_ in icons].count('dark'), 2)
            self.assertTrue(main.collectible_icon_still_visible(image, 'dark', 1501, 341))

    def test_compact_scrolled_builder_menu_is_not_the_village(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'builders_scrolled_1323.png') as menu, \
             Image.open(Path(__file__).parent / 'testdata' / 'village_zoomed_1323.png') as village:
            self.assertTrue(main.builders_menu_open(menu))
            self.assertFalse(main.builders_menu_open(village))

    def test_selected_last_troop_is_one_not_unreadable(self):
        image = self.fixture("army_last_electro.png", (0, 880))
        self.assertEqual(main.read_troop_count(image, "Électro-dragon"), 1)
        self.assertEqual(main.read_troop_count(image, "Dragon"), 1)
        # Removing the numeral must not turn a standalone x into a count of 1.
        image.paste((0, 0, 0), (505, 910, 532, 956))
        self.assertFalse(main.counter_is_one(main.crop_percent(image, main.Roi(23, 84.5, 27.8, 90))))

    def test_troop_card_order_and_counts_are_detected_after_swap(self):
        image = self.fixture("hero_unplaced.png", (0, 880))
        self.assertEqual(main.troop_slot_offset(image, "Dragon"), 0)
        self.assertEqual(main.troop_slot_offset(image, main.ELECTRODRAGON_LABEL), 0)
        left, right = (280, 0, 399, 1080), (399, 0, 518, 1080)
        first, second = image.crop(left), image.crop(right)
        image.paste(second, (left[0], 0))
        image.paste(first, (right[0], 0))
        self.assertAlmostEqual(main.troop_slot_offset(image, main.ELECTRODRAGON_LABEL), -6.2)
        self.assertAlmostEqual(main.troop_slot_offset(image, "Dragon"), 6.2)
        self.assertEqual(main.read_troop_count(image, main.ELECTRODRAGON_LABEL), 8)
        self.assertEqual(main.read_troop_count(image, "Dragon"), 1)

    def test_troop_cards_are_located_across_the_bar_past_hero_colours(self):
        image = self.fixture("hero_unplaced.png", (0, 880))
        dragon = image.crop((280, 880, 399, 1080))
        electro = image.crop((399, 880, 518, 1080))
        image.paste((0, 0, 0), (280, 880, 518, 1080))
        image.paste(dragon, (280 + round(6 * 6.2 * 19.2), 880))
        image.paste(electro, (399 + round(7 * 6.2 * 19.2), 880))
        self.assertAlmostEqual(main.troop_slot_offset(image, "Dragon"), 37.2)
        self.assertAlmostEqual(main.troop_slot_offset(image, main.ELECTRODRAGON_LABEL), 43.4)
        self.assertEqual(main.read_troop_count(image, "Dragon"), 1)
        self.assertEqual(main.read_troop_count(image, main.ELECTRODRAGON_LABEL), 8)

    def test_selected_electro_count_does_not_clip_seven(self):
        image = self.fixture("edrag_selected_x7.png", (250, 900))
        self.assertEqual(main.read_troop_count(image, "Électro-dragon"), 7)

    def test_selected_electro_count_two_is_read_inside_card_border(self):
        image = self.fixture("edrag_selected_x2.png", (250, 900))
        self.assertEqual(main.read_troop_count(image, "Électro-dragon"), 2)

    def test_vm_electro_counter_survives_plain_and_masked_ocr(self):
        for filename, expected in (("electro_counter_x8_vm.png", 8),
                                   ("electro_counter_x2_vm.png", 2)):
            with self.subTest(filename=filename):
                image = Image.new("RGB", (1765, 993), "black")
                with Image.open(Path(__file__).parent / "testdata" / filename) as crop:
                    image.paste(crop, (360, 835))
                self.assertEqual(main.read_troop_count(image, "Électro-dragon"), expected)

    def test_vm_laboratory_counter_is_read_when_wide_ocr_is_empty(self):
        image = Image.new("RGB", (1765, 993), "black")
        with Image.open(Path(__file__).parent / "testdata" / "lab_counter_vm.png") as crop:
            image.paste(crop, (690, 25))
        self.assertEqual(main.read_laboratory_ratio(image, ""), "1/1")

    def test_defeat_result_return_button_is_read(self):
        image = self.fixture("battle_result_rentrer.png", (700, 780))
        self.assertTrue(main.battle_result_return_ready(image))
        self.assertFalse(main.battle_result_return_ready(Image.new("RGB", (1920, 1080))))

    def test_wall_ring_moves_more_button_and_price_regions(self):
        image = self.fixture("wall_ring_actions.png", (0, 720))
        point = main.find_wall_more_button(image)
        self.assertIsNotNone(point)
        self.assertTrue(44 < point[0] < 48)
        self.assertTrue(82 < point[1] < 87)
        shift = point[0] - main.WALL_MORE_BUTTON[0]
        self.assertEqual(main.read_wall_cost(image, "or", shift), 500000)
        self.assertEqual(main.read_wall_cost(image, "élixir", shift), 500000)

    def test_native_capture_excludes_test_window_title_and_borders(self):
        # Exercise the actual Win32/GDI coordinate path on our own window.
        # This never discovers, captures or clicks a Clash window.
        root = main.Tk()
        try:
            root.title("CoC - test de capture uniquement")
            root.geometry("640x360+30+30")
            root.configure(background="#345678")
            root.attributes('-topmost', True)
            root.update()
            window = main.GameWindow(int(root.wm_frame(), 0), "test", 1, 1)
            geometry = main.WindowDriver.client_geometry(window)
            for attempt in range(10):
                root.lift()
                root.update()
                try:
                    image = main.WindowDriver.capture(window)
                    break
                except RuntimeError as exc:
                    if 'Capture noire' not in str(exc) or attempt == 9:
                        raise
                    time.sleep(.1)  # Let Windows paint the new test window.
            self.assertEqual(image.size, (geometry.width, geometry.height))
            self.assertGreater(geometry.outer_height, geometry.height)
            self.assertEqual(image.getpixel((image.width // 2, image.height // 2)), (52, 86, 120))
        finally:
            root.destroy()

    def test_windows_ocr_on_synthetic_number(self):
        main.self_test()

    def test_counters_on_saved_game_capture(self):
        path = Path(__file__).parent / "diagnostics" / "v18_dragon_heroes_live.png"
        if not path.exists():
            self.skipTest("Capture de diagnostic locale absente")
        with Image.open(path) as image:
            self.assertEqual(main.read_troop_count(image, "Électro-dragon"), 8)
            self.assertEqual(main.read_troop_count(image, "Dragon"), 0)

    def test_tk_interface_and_calibration_save_without_game_input(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(main, "APP_DIR", Path(directory) / "CoCFarmBot"), \
             patch.object(main, "CONFIG_PATH", Path(directory) / "CoCFarmBot" / "config-v2.json"), \
             patch.object(main, "STATS_PATH", Path(directory) / "CoCFarmBot" / "farm-stats.json"), \
             patch.object(main, "LOG_PATH", Path(directory) / "CoCFarmBot" / "bot.log"), \
             patch.object(main.WindowDriver, "list_windows", return_value=[]), \
             patch.object(main.WindowDriver, "capture") as capture, \
             patch.object(main.WindowDriver, "click_percent") as click:
            app = main.BotApp()
            try:
                app.root.withdraw()
                app.root.update()
                self.assertEqual(str(app.inspect_button["text"]), "Lire l’écran")
                app._show_calibration(Image.new("RGB", (1920, 1080), "#345678"))
                dialog = app.calibration_dialog
                dialog.window.withdraw()
                label = main.layout_labels()["DRAGON_SLOT"]
                dialog.selection.set(label)
                dialog.press(SimpleNamespace(x=200, y=100))
                dialog.release(SimpleNamespace(x=250, y=150))
                expected = [250 * 100 / dialog.photo.width(), 150 * 100 / dialog.photo.height()]
                dialog.save()
                self.assertIsNone(app.calibration_dialog)
                self.assertEqual(main.load_settings().layout_overrides["DRAGON_SLOT"], expected)
                app._pump()
                app.events.put(main.StatsEvent(dict(gold=1773011, elixir=2057709, dark_elixir=16323, battles=1)))
                app._pump()
                self.assertEqual([value.get() for value in app.stats_vars.values()],
                                 ["1 773 011", "2 057 709", "16 323"])
                self.assertIn("1 combat", app.stats_count.get())
                self.assertFalse(app.start_button.instate(["disabled"]))
                self.assertTrue(app.reset_data_button.winfo_exists())
            finally:
                app.close()
            capture.assert_not_called()
            click.assert_not_called()

    def test_console_controls_fit_at_minimum_window_size(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(main, "APP_DIR", Path(directory) / "CoCFarmBot"), \
             patch.object(main, "CONFIG_PATH", Path(directory) / "CoCFarmBot" / "config-v2.json"), \
             patch.object(main, "STATS_PATH", Path(directory) / "CoCFarmBot" / "farm-stats.json"), \
             patch.object(main, "LOG_PATH", Path(directory) / "CoCFarmBot" / "bot.log"), \
             patch.object(main.WindowDriver, "list_windows", return_value=[]):
            app = main.BotApp()
            try:
                app.root.geometry("1080x760")
                app.root.update()
                loot = app.settings_tabs.nametowidget(app.settings_tabs.tabs()[0])
                and_rule = next(child for child in loot.winfo_children()
                                if isinstance(child, ttk.Checkbutton))
                for widget in (and_rule, app.save_button, app.start_button,
                               app.stop_button, app.inspect_button, app.calibrate_button):
                    self.assertTrue(widget.winfo_ismapped(), str(widget))
                    self.assertGreaterEqual(widget.winfo_height(), 28, str(widget))
                    self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                                         app.root.winfo_rooty() + app.root.winfo_height(), str(widget))
                app.activity_tabs.select(2)
                app.root.update()
                self.assertTrue(app.reset_data_button.winfo_ismapped())
                self.assertGreaterEqual(app.reset_data_button.winfo_height(), 28)
                self.assertLessEqual(app.reset_data_button.winfo_rooty() + app.reset_data_button.winfo_height(),
                                     app.root.winfo_rooty() + app.root.winfo_height())
            finally:
                app.close()

    def test_reset_button_erases_saved_data_and_closes_app(self):
        with tempfile.TemporaryDirectory() as parent, \
             patch.object(main, "APP_DIR", Path(parent) / "CoCFarmBot"), \
             patch.object(main, "CONFIG_PATH", Path(parent) / "CoCFarmBot" / "config-v2.json"), \
             patch.object(main, "STATS_PATH", Path(parent) / "CoCFarmBot" / "farm-stats.json"), \
             patch.object(main, "LOG_PATH", Path(parent) / "CoCFarmBot" / "bot.log"), \
             patch.object(main.WindowDriver, "list_windows", return_value=[]), \
             patch.object(main.WindowDriver, "click_percent") as click:
            app = main.BotApp()
            directory = Path(parent) / "CoCFarmBot"
            (directory / "runs").mkdir(exist_ok=True)
            (directory / "runs" / "old.txt").write_text("old", encoding="utf-8")
            try:
                with patch.object(main.messagebox, "askyesno", return_value=False):
                    app.reset_data_button.invoke()
                self.assertTrue(directory.exists())
                app.worker = SimpleNamespace(is_alive=lambda: True)
                with patch.object(main.messagebox, "askyesno") as confirmation:
                    app.reset_data_button.invoke()
                    confirmation.assert_not_called()
                self.assertTrue(directory.exists())
                app.worker = None
                with patch.object(main.messagebox, "askyesno", return_value=True):
                    app.reset_data_button.invoke()
                self.assertFalse(directory.exists())
                self.assertTrue(app._closed)
            finally:
                app.close()
            click.assert_not_called()

    def test_stop_button_remains_responsive_during_slow_inspection(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(main, "APP_DIR", Path(directory) / "CoCFarmBot"), \
             patch.object(main, "CONFIG_PATH", Path(directory) / "CoCFarmBot" / "config-v2.json"), \
             patch.object(main, "STATS_PATH", Path(directory) / "CoCFarmBot" / "farm-stats.json"), \
             patch.object(main, "LOG_PATH", Path(directory) / "CoCFarmBot" / "bot.log"), \
             patch.object(main.WindowDriver, "list_windows", return_value=[]), \
             patch.object(main.WindowDriver, "resolve", return_value=object()):
            app = main.BotApp()
            entered = threading.Event()
            def slow_read(window):
                entered.set()
                app.stop_event.wait(2)
            try:
                app.root.withdraw()
                app._start_inspection(slow_read)
                self.assertTrue(entered.wait(2))
                app._pump()
                self.assertFalse(app.stop_button.instate(["disabled"]))
                app.stop_button.invoke()
                self.assertTrue(app.stop_event.is_set())
                app.inspection_worker.join(2)
                self.assertFalse(app.inspection_worker.is_alive())
            finally:
                app.stop_event.set()
                app.close()

    def test_journal_button_exports_live_actions_and_errors_as_zip(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(main, "APP_DIR", Path(directory) / "CoCFarmBot"), \
             patch.object(main, "CONFIG_PATH", Path(directory) / "CoCFarmBot" / "config-v2.json"), \
             patch.object(main, "STATS_PATH", Path(directory) / "CoCFarmBot" / "farm-stats.json"), \
             patch.object(main, "LOG_PATH", Path(directory) / "CoCFarmBot" / "bot.log"), \
             patch.object(main.WindowDriver, "list_windows", return_value=[]), \
             patch.object(main.WindowDriver, "click_percent", return_value=True):
            app = main.BotApp()
            destination = Path(directory) / 'diagnostic.zip'
            try:
                app.root.geometry('1040x860')
                app.root.update()
                self.assertTrue(app.export_log_button.winfo_ismapped())
                self.assertLess(app.export_log_button.winfo_rooty() + app.export_log_button.winfo_height(),
                                app.root.winfo_rooty() + app.root.winfo_height())
                app.root.withdraw()
                app._begin_run('essai diagnostic')
                app.events.put('Étape de diagnostic')
                self.assertTrue(app._click(SimpleNamespace(title='Fenêtre test'), 30, 60))
                with patch.object(main.WindowDriver, 'capture', return_value=Image.new('RGB', (1920, 1080), 'white')):
                    app._capture(SimpleNamespace(title='Fenêtre test'))
                app._wait(.001)
                def fail():
                    raise RuntimeError('blocage exemple')
                app._run_operation(fail)
                app.worker = SimpleNamespace(is_alive=lambda: True)
                app._pump()
                self.assertFalse(app.export_log_button.instate(['disabled']))
                with patch.object(main.filedialog, 'asksaveasfilename', return_value=str(destination)):
                    app.export_log_button.invoke()
                with zipfile.ZipFile(destination) as archive:
                    self.assertIn('diagnostic.json', archive.namelist())
                    self.assertIn('bot.log', archive.namelist())
                    self.assertTrue(any(name.endswith('.png') for name in archive.namelist()))
                    exported = archive.read(next(name for name in archive.namelist() if name.endswith('.txt'))).decode('utf-8')
                self.assertIn('Étape de diagnostic', exported)
                self.assertIn('CLIC Envoi à 30.00 %, 60.00 %', exported)
                self.assertIn('CLIC Résultat à 30.00 %, 60.00 % : accepté', exported)
                self.assertIn('CAPTURE Image reçue : 1920x1080', exported)
                self.assertIn('ATTENTE 0.00 s', exported)
                self.assertIn('RuntimeError: blocage exemple', exported)
                self.assertIn('DÉBUT Action=essai diagnostic', exported)
                self.assertTrue(exported.splitlines()[0].startswith('20'))
            finally:
                app.close()

    def test_journal_export_is_a_complete_snapshot_during_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = main.DiagnosticJournal(Path(directory) / 'bot.log')
            destination = Path(directory) / 'export.txt'
            started = threading.Event()
            def write_lines():
                for index in range(300):
                    journal.record('ÉTAPE', f'ligne {index} é')
                    if index == 20:
                        started.set()
            writer = threading.Thread(target=write_lines)
            try:
                writer.start()
                self.assertTrue(started.wait(2))
                journal.export(destination)
                writer.join(2)
                exported = destination.read_text(encoding='utf-8')
                self.assertTrue(exported.endswith('\n'))
                self.assertIn('ligne 20 é', exported)
                self.assertTrue(all('ÉTAPE ligne ' in line for line in exported.splitlines()))
            finally:
                writer.join(2)
                journal.close()

    def test_journal_export_converts_old_windows_text_to_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'bot.log'
            source.write_bytes('Ancien journal : récolte terminée\n'.encode('cp1252'))
            journal = main.DiagnosticJournal(source)
            try:
                journal.record('ÉTAPE', 'Nouvelle récolte confirmée')
                destination = Path(directory) / 'export.txt'
                journal.export(destination)
                exported = destination.read_text(encoding='utf-8')
                self.assertIn('Ancien journal : récolte terminée', exported)
                self.assertIn('ÉTAPE Nouvelle récolte confirmée', exported)
            finally:
                journal.close()


if __name__ == "__main__":
    unittest.main()
