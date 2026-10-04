"""Update regressions with isolated files; never touch a running bot."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import auto_update as updater


def metadata(version="2.0.20", payload=b"MZ-test-executable"):
    tag = "v" + version
    return {
        "tag_name": tag, "draft": False, "prerelease": False,
        "assets": [{"name": updater.ASSET_NAME, "state": "uploaded", "size": len(payload),
                    "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
                    "browser_download_url": f"https://github.com/{updater.REPOSITORY}/releases/download/{tag}/{updater.ASSET_NAME}"}],
    }


class UpdateTests(unittest.TestCase):
    def latest(self, data, current="2.0.19"):
        with patch.object(updater, "urlopen", return_value=io.BytesIO(json.dumps(data).encode())):
            return updater.latest_release(current)

    def test_numeric_versions_do_not_compare_as_text(self):
        self.assertIsNotNone(self.latest(metadata("2.0.20"), "2.0.9"))
        self.assertIsNotNone(self.latest(metadata("2.1.0"), "2.0.99"))

    def test_same_or_older_version_is_not_downloaded(self):
        self.assertIsNone(self.latest(metadata(), "2.0.20"))
        self.assertIsNone(self.latest(metadata(), "2.0.21"))

    def test_drafts_and_prereleases_are_ignored(self):
        for field in ("draft", "prerelease"):
            data = metadata()
            data[field] = True
            self.assertIsNone(self.latest(data))

    def test_untrusted_or_incomplete_assets_are_rejected(self):
        for field, value in (("browser_download_url", "https://example.com/CoCFarmBot.exe"),
                             ("digest", None), ("digest", "sha256:123"),
                             ("size", -1), ("size", True), ("size", updater.MAX_ASSET_SIZE + 1),
                             ("state", "new")):
            with self.subTest(field=field, value=value):
                data = metadata()
                data["assets"][0][field] = value
                with self.assertRaises(ValueError):
                    self.latest(data)

    def test_missing_and_duplicate_asset_are_rejected(self):
        for assets in ([], metadata()["assets"] * 2):
            data = metadata()
            data["assets"] = assets
            with self.assertRaises(ValueError):
                self.latest(data)

    def test_invalid_tag_cannot_change_the_download_path(self):
        for tag in ("v2.0.21-beta", "v2.0.21/evil", "main", None):
            data = metadata()
            data["tag_name"] = tag
            with self.assertRaises(ValueError):
                self.latest(data)

    def test_valid_download_reports_progress(self):
        payload = b"MZ-valid-executable"
        release = self.latest(metadata(payload=payload))
        messages = []
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(updater, "urlopen", return_value=io.BytesIO(payload)):
            destination = Path(temporary) / "candidate.exe"
            updater.download_release(release, destination, threading.Event(), messages.append)
            self.assertEqual(destination.read_bytes(), payload)
        self.assertIn("100 %", messages[-1])

    def test_corrupt_truncated_and_non_executable_downloads_are_rejected(self):
        payload = b"MZ-valid-executable"
        for received in (payload[:-1], payload + b"extra", b"MZ-corrupt-execute!"):
            release = self.latest(metadata(payload=payload))
            with tempfile.TemporaryDirectory() as temporary, \
                 patch.object(updater, "urlopen", return_value=io.BytesIO(received)):
                with self.assertRaises(ValueError):
                    updater.download_release(release, Path(temporary) / "candidate.exe", threading.Event(), lambda _: None)
        release = self.latest(metadata(payload=b"<html>"))
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(updater, "urlopen", return_value=io.BytesIO(b"<html>")):
            with self.assertRaises(ValueError):
                updater.download_release(release, Path(temporary) / "candidate.exe", threading.Event(), lambda _: None)

    def test_cancelled_download_does_not_continue(self):
        cancelled = threading.Event()
        cancelled.set()
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(updater, "urlopen", return_value=io.BytesIO(b"MZ-valid-executable")):
            release = self.latest(metadata())
            with self.assertRaises(updater.UpdateCancelled):
                updater.download_release(release, Path(temporary) / "candidate.exe", cancelled, lambda _: None)

    def test_candidate_self_test_must_match_the_release_version(self):
        release = self.latest(metadata())
        for report in ({"ok": True, "frozen": True, "version": release.version},
                       {"ok": True, "frozen": True, "version": "2.0.19"},
                       {"ok": False, "frozen": True, "version": release.version}):
            with tempfile.TemporaryDirectory() as temporary:
                candidate = Path(temporary) / "candidate.exe"
                (candidate.parent / "candidate-check.json").write_text(json.dumps(report), encoding="utf-8")
                with patch.object(updater.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as launch:
                    if report["ok"] and report["version"] == release.version:
                        updater.verify_candidate(candidate, release, threading.Event())
                    else:
                        with self.assertRaises(ValueError):
                            updater.verify_candidate(candidate, release, threading.Event())
                    self.assertEqual(launch.call_args.kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")

    def test_failed_staging_leaves_installed_executable_and_settings_intact(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            target = directory / "CoCFarmBot.exe"
            settings = directory / "config-v2.json"
            target.write_bytes(b"previous")
            settings.write_bytes(b"personal settings")
            with patch.object(updater, "download_release", side_effect=TimeoutError("offline")):
                with self.assertRaises(TimeoutError):
                    updater.stage_release(self.latest(metadata()), target, threading.Event(), lambda _: None)
            self.assertEqual(target.read_bytes(), b"previous")
            self.assertEqual(settings.read_bytes(), b"personal settings")
            self.assertEqual(sorted(p.name for p in directory.iterdir()), ["CoCFarmBot.exe", "config-v2.json"])

    def test_developer_launch_does_not_check_or_install(self):
        with patch.object(sys, "frozen", False, create=True), patch.object(updater, "_startup_update") as update:
            self.assertFalse(updater.startup_update(Path("unused")))
        update.assert_not_called()

    def test_unavailable_updater_falls_back_to_existing_app(self):
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(sys, "frozen", True, create=True), \
             patch.object(updater, "_startup_update", side_effect=OSError("offline")):
            directory = Path(temporary)
            self.assertFalse(updater.startup_update(directory))
            self.assertIn("offline", (directory / "update.log").read_text(encoding="utf-8"))

    def test_real_startup_window_continues_when_offline(self):
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(sys, "frozen", True, create=True), \
             patch.object(updater, "latest_release", side_effect=TimeoutError("offline")):
            directory = Path(temporary)
            self.assertFalse(updater.startup_update(directory))
            self.assertIn("offline", (directory / "update.log").read_text(encoding="utf-8"))

    def test_real_startup_window_continues_when_already_current(self):
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(sys, "frozen", True, create=True), \
             patch.object(updater, "latest_release", return_value=None), \
             patch.object(updater, "launch_installer") as installer:
            self.assertFalse(updater.startup_update(Path(temporary)))
        installer.assert_not_called()

    def test_windows_helper_parses_before_shipping(self):
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        with tempfile.TemporaryDirectory(prefix="CoC updater ' ") as temporary:
            script = Path(temporary) / "install.ps1"
            script.write_text(updater.INSTALL_SCRIPT, encoding="utf-8-sig")
            # The script path is a positional argument, never interpolated in PS.
            checker = Path(temporary) / "check.ps1"
            checker.write_text("param([string]$Source)\n$tokens=$null; $errors=$null\n"
                               "[System.Management.Automation.Language.Parser]::ParseFile($Source,[ref]$tokens,[ref]$errors) | Out-Null\n"
                               "if ($errors.Count) { $errors | Out-String | Write-Output; exit 1 }\n", encoding="utf-8")
            result = subprocess.run([str(powershell), "-NoProfile", "-File", str(checker), str(script)],
                                    capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_windows_helper_waits_for_old_process_and_restores_failed_start(self):
        compiler = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        self.assertTrue(compiler.is_file())
        with tempfile.TemporaryDirectory(prefix="CoC rollback ' ") as temporary:
            directory = Path(temporary)
            old_source = directory / "old.cs"
            old_source.write_text('''using System; using System.IO; using System.Threading;
class Program { static void Main(string[] args) {
    if (args.Length == 2 && args[0] == "--hold") {
        File.WriteAllText(args[1] + ".alive", "alive");
        while (!File.Exists(args[1])) Thread.Sleep(20);
        return;
    }
    var folder = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location);
    File.WriteAllText(Path.Combine(folder, "old-started.txt"), "restored");
} }''', encoding="utf-8")
            new_source = directory / "new.cs"
            new_source.write_text('class Program { static void Main(string[] args) {} }', encoding="utf-8")
            target = directory / "CoCFarmBot.exe"
            staged = directory / ".CoCFarmBot-update-test"
            staged.mkdir()
            candidate = staged / updater.ASSET_NAME
            for source, output in ((old_source, target), (new_source, candidate)):
                result = subprocess.run([str(compiler), "/nologo", "/target:winexe", "/out:" + str(output), str(source)],
                                        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                self.assertEqual(result.returncode, 0, result.stdout)
            old_payload = target.read_bytes()
            release = updater.Release("2.0.20", "unused", candidate.stat().st_size,
                                      hashlib.sha256(candidate.read_bytes()).hexdigest())
            release_marker = directory / "release-old"
            previous = subprocess.Popen([str(target), "--hold", str(release_marker)],
                                        creationflags=subprocess.CREATE_NO_WINDOW)
            helper = None
            try:
                deadline = time.monotonic() + 10
                while not release_marker.with_suffix(".alive").exists():
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.02)
                with patch.object(updater.os, "getpid", return_value=previous.pid):
                    helper = updater.launch_installer(staged, target, release, directory / "update.log")
                self.assertEqual(target.read_bytes(), old_payload)
                self.assertIsNone(previous.poll())
                release_marker.touch()
                previous.wait(timeout=10)
                helper.wait(timeout=20)
                self.assertEqual(target.read_bytes(), old_payload)
                deadline = time.monotonic() + 10
                while not (directory / "old-started.txt").exists():
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.02)
                self.assertFalse(staged.exists())
                self.assertIn("avant son ouverture", (directory / "update.log").read_text(encoding="utf-8-sig"))
            finally:
                if previous.poll() is None:
                    previous.terminate()
                    previous.wait(timeout=5)
                if helper is not None and helper.poll() is None:
                    helper.terminate()
                    helper.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
