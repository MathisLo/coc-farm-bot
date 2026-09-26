"""Focused regressions for the farm decisions; no game window is needed."""

import queue
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main
from PIL import Image, ImageDraw, ImageFont


class FarmLogicTests(unittest.TestCase):
    def test_package_report_rejects_missing_webview(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(main, "self_test"), \
             patch.object(main, "validate_layout"), \
             patch.dict(sys.modules, {"webview": None}):
            report_path = Path(directory) / "report.json"
            self.assertEqual(main.self_test_report(report_path), 1)
            report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertFalse(report["ok"])
        self.assertIn("webview", report["error"])

    def test_loot_does_not_prefer_truncated_mask_reading(self):
        with patch.object(main, "read_text", side_effect=["1 256 104", "256 104"]):
            self.assertEqual(main.read_resource_number(Image.new("RGB", (100, 40)))[0], 1256104)

    def test_enemy_loot_above_old_ceiling_is_read(self):
        with patch.object(main, "read_text", side_effect=["3 120 500", "3 120 500"]):
            self.assertEqual(main.read_resource_number(Image.new("RGB", (100,40)))[0],3120500)

    def test_enemy_loot_retries_other_scales_when_initial_ocr_is_empty(self):
        with patch.object(main, "read_text", side_effect=["", "", "941 101", "941 101"]):
            self.assertEqual(main.read_resource_number(Image.new("RGB", (100,40)))[0],941101)

    def test_wall_batch_keeps_both_reserves(self):
        self.assertEqual(main.wall_batch_size(9_499_000, 500_000, 184), 16)
        self.assertEqual(main.wall_batch_size(10_000_000, 500_000, 184), 18)
        self.assertEqual(main.wall_batch_size(1_499_000, 500_000, 184), 0)
        self.assertEqual(main.wall_batch_size(10_000_000, 500_000, 3), 3)

    def test_wall_payment_checks_only_the_resource_being_spent(self):
        balances = (718_360, 5_185_508)
        self.assertTrue(main.wall_spend_preserves_reserve(balances, "élixir", 4_000_000))
        self.assertFalse(main.wall_spend_preserves_reserve(balances, "or", 4_000_000))
        self.assertTrue(main.wall_spend_preserves_reserve((718_360, 1_185_508), "élixir", 0))

    def test_reserve_ocr_requires_complete_amount(self):
        self.assertEqual(main.parse_reserve_number("g 499 OOO-"), 9_499_000)
        self.assertEqual(main.parse_reserve_number("1 000-000"), 1_000_000)
        self.assertEqual(main.parse_reserve_number("Io 000 000"), 10_000_000)
        self.assertEqual(main.parse_reserve_number("-2-625*518"), 2_625_518)
        self.assertEqual(main.parse_reserve_number("1,800 575"), 1_800_575)
        self.assertEqual(main.parse_reserve_number("1-800S75"), 1_800_575)
        self.assertEqual(main.parse_reserve_number("43 380"), 43_380)
        self.assertEqual(main.parse_reserve_number("43380"), 43_380)
        self.assertEqual(main.parse_reserve_number("1307 362"), 1_307_362)
        self.assertIsNone(main.parse_reserve_number("94 9 000-"))

    def test_group_confirmation_checks_amount_and_resource(self):
        image = Image.new("RGB", (1920, 1080))
        with patch.object(main, "read_text", side_effect=["Améliorer les remparts pour 9000000 élixir ?", "OK"]):
            self.assertTrue(main.wall_batch_confirmation_matches(image, 9_000_000, "élixir"))
        with patch.object(main, "read_text", side_effect=["Améliorer les remparts pour 9000000 élixir ?", "OK"]):
            self.assertFalse(main.wall_batch_confirmation_matches(image, 9_000_000, "or"))

    def test_group_confirmation_accepts_visible_green_ok_when_ocr_is_empty(self):
        image = Image.new("RGB", (1920, 1080), (20, 20, 20))
        draw = ImageDraw.Draw(image)
        draw.rectangle((round(1920 * .50), round(1080 * .57), round(1920 * .66), round(1080 * .67)), fill=(150, 230, 60))
        with patch.object(main, "read_text", side_effect=["Ameliorer les remparts pour 9000000 élixir ?", ""]):
            self.assertTrue(main.wall_batch_confirmation_matches(image, 9_000_000, "élixir"))

    def test_troop_is_counted_only_after_counter_drops(self):
        app = object.__new__(main.BotApp)
        app.settings = SimpleNamespace(electrodragon_count=2, dragon_count=0, delay_between_dragons_ms=0)
        app.stop_event = threading.Event()
        app.action_lock = threading.RLock()
        app.events = queue.Queue()
        clicks = []
        with patch.object(main.WindowDriver, "capture", return_value=Image.new("RGB",(1920,1080),(30,60,110))), \
             patch.object(main.WindowDriver, "click_percent", side_effect=lambda _, x, y: clicks.append((x, y)) or True), \
             patch.object(main, "battle_reward_open", return_value=False), \
             patch.object(main, "read_troop_count", side_effect=[2, 2, 2, 2, 1, 1, 0, 0]):
            placed = main.BotApp.deploy_unit(app, object(), "Électro-dragon", (23, 92), [(20, 40), (30, 30)])
        self.assertEqual(placed, 2)
        self.assertEqual(clicks, [(23, 92), (20, 40), (30, 30), (30, 30)])
        self.assertEqual(sum("confirmé" in message for message in list(app.events.queue)), 2)

    def test_troop_counter_fallback_ignores_bar_shift_but_sees_new_digit(self):
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 34)
        def counter(text, shift=0):
            image = Image.new("RGB", (1920, 1080), (30, 60, 110))
            ImageDraw.Draw(image).text((465, 917 + shift), text, font=font, fill="white")
            return image
        self.assertFalse(main.troop_counter_visually_changed(counter("x1"), counter("x1", 6), "Électro-dragon"))
        self.assertTrue(main.troop_counter_visually_changed(counter("x2"), counter("x1"), "Électro-dragon"))


if __name__ == "__main__":
    unittest.main()
