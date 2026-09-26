"""Saved-data lifecycle checks use temporary bot directories only."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from modern_dashboard import FIELDS


class StorageTests(unittest.TestCase):
    def test_hero_upgrade_choice_is_saved_and_old_configs_keep_previous_behavior(self):
        self.assertEqual(FIELDS['upgrade_heroes'], 'upgrade_heroes')
        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent)
            config = directory / 'config-v2.json'
            with patch.object(main, 'APP_DIR', directory), patch.object(main, 'CONFIG_PATH', config):
                config.write_text('{"version":8,"upgrade_recommended":true}', encoding='utf-8')
                self.assertTrue(main.load_settings().upgrade_heroes)
                main.save_settings(main.replace(main.load_settings(), upgrade_heroes=False))
                self.assertFalse(main.load_settings().upgrade_heroes)

    def test_new_version_erases_all_old_data_once(self):
        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent) / "CoCFarmBot"
            (directory / "runs").mkdir(parents=True)
            (directory / "unread-results").mkdir()
            for name in ("config-v2.json", "config.json", "farm-stats.json", "bot.log", "last_capture.png"):
                (directory / name).write_text("old", encoding="utf-8")
            (directory / "runs" / "old.txt").write_text("old", encoding="utf-8")
            (directory / "unread-results" / "old.png").write_text("old", encoding="utf-8")
            self.assertTrue(main.prepare_storage(directory))
            self.assertEqual([item.name for item in directory.iterdir()], [main.STORAGE_MARKER])
            (directory / "new-log.txt").write_text("new", encoding="utf-8")
            self.assertFalse(main.prepare_storage(directory))
            self.assertEqual((directory / "new-log.txt").read_text(encoding="utf-8"), "new")

    def test_old_settings_written_after_marker_trigger_fresh_start(self):
        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent) / "CoCFarmBot"
            self.assertFalse(main.prepare_storage(directory))
            (directory / "config-v2.json").write_text('{"version": 7}', encoding="utf-8")
            self.assertTrue(main.prepare_storage(directory))
            self.assertFalse((directory / "config-v2.json").exists())

    def test_only_named_bot_directory_can_be_erased(self):
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent)
            directory = root / "CoCFarmBot"
            directory.mkdir()
            (directory / "old.txt").write_text("old", encoding="utf-8")
            (root / "keep.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(ValueError):
                main.clear_saved_data(root)
            self.assertTrue(directory.exists())
            main.clear_saved_data(directory)
            self.assertFalse(directory.exists())
            self.assertEqual((root / "keep.txt").read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
