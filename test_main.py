"""Focused regressions for the farm decisions; no game window is needed."""

import queue
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main


class FarmLogicTests(unittest.TestCase):
    def test_wall_batch_keeps_both_reserves(self):
        self.assertEqual(main.wall_batch_size(9_499_000, 500_000, 184), 16)
        self.assertEqual(main.wall_batch_size(10_000_000, 500_000, 184), 18)
        self.assertEqual(main.wall_batch_size(1_499_000, 500_000, 184), 0)
        self.assertEqual(main.wall_batch_size(10_000_000, 500_000, 3), 3)

    def test_reserve_ocr_requires_complete_amount(self):
        self.assertEqual(main.parse_reserve_number("g 499 OOO-"), 9_499_000)
        self.assertEqual(main.parse_reserve_number("Io 000 000"), 10_000_000)
        self.assertIsNone(main.parse_reserve_number("94 9 000-"))

    def test_troop_is_counted_only_after_counter_drops(self):
        app = SimpleNamespace(
            settings=SimpleNamespace(electrodragon_count=2, dragon_count=0, delay_between_dragons_ms=0),
            stop_event=threading.Event(), events=queue.Queue(),
        )
        clicks = []
        with patch.object(main.WindowDriver, "capture", return_value=object()), \
             patch.object(main.WindowDriver, "click_percent", side_effect=lambda _, x, y: clicks.append((x, y)) or True), \
             patch.object(main, "read_troop_count", side_effect=[2, 2, 1, 0]):
            placed = main.BotApp.deploy_unit(app, object(), "Électro-dragon", (23, 92), [(20, 40), (30, 30)])
        self.assertEqual(placed, 2)
        self.assertEqual(clicks, [(23, 92), (20, 40), (30, 30), (30, 30)])
        self.assertEqual(sum("confirmé" in message for message in list(app.events.queue)), 2)


if __name__ == "__main__":
    unittest.main()
