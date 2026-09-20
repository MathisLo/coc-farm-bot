"""Real Windows OCR and Tk checks; no capture or input in Clash of Clans."""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
import main


class WindowsIntegrationTests(unittest.TestCase):
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

    def test_empty_hero_slot_is_not_a_coloured_card(self):
        image = self.fixture("hero_empty_slot.png", (0, 880))
        self.assertGreater(main.hero_icon_saturation(image, 2, -6.25), 55)
        self.assertEqual([main.hero_placeholder_slot(image, i, -6.25) for i in range(3)],
                         [False, False, True])

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

    def test_selected_last_troop_is_one_not_unreadable(self):
        image = self.fixture("army_last_electro.png", (0, 880))
        self.assertEqual(main.read_troop_count(image, "Électro-dragon"), 1)
        self.assertEqual(main.read_troop_count(image, "Dragon"), 1)
        # Removing the numeral must not turn a standalone x into a count of 1.
        image.paste((0, 0, 0), (505, 910, 532, 956))
        self.assertFalse(main.counter_is_one(main.crop_percent(image, main.Roi(23, 84.5, 27.8, 90))))

    def test_selected_electro_count_does_not_clip_seven(self):
        image = self.fixture("edrag_selected_x7.png", (250, 900))
        self.assertEqual(main.read_troop_count(image, "Électro-dragon"), 7)

    def test_selected_electro_count_two_is_read_inside_card_border(self):
        image = self.fixture("edrag_selected_x2.png", (250, 900))
        self.assertEqual(main.read_troop_count(image, "Électro-dragon"), 2)

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
            root.update()
            window = main.GameWindow(int(root.wm_frame(), 0), "test", 1, 1)
            geometry = main.WindowDriver.client_geometry(window)
            image = main.WindowDriver.capture(window)
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
             patch.object(main, "APP_DIR", Path(directory)), \
             patch.object(main, "CONFIG_PATH", Path(directory) / "config.json"), \
             patch.object(main, "STATS_PATH", Path(directory) / "stats.json"), \
             patch.object(main, "LOG_PATH", Path(directory) / "bot.log"), \
             patch.object(main.logging, "basicConfig"), \
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
            finally:
                app.root.destroy()
            capture.assert_not_called()
            click.assert_not_called()

    def test_stop_button_remains_responsive_during_slow_inspection(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(main, "APP_DIR", Path(directory)), \
             patch.object(main, "CONFIG_PATH", Path(directory) / "config.json"), \
             patch.object(main, "STATS_PATH", Path(directory) / "stats.json"), \
             patch.object(main.logging, "basicConfig"), \
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
                app.root.destroy()


if __name__ == "__main__":
    unittest.main()
