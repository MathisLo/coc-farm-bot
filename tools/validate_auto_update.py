"""Exercise a real Windows EXE update in an isolated profile, without game input."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from PIL import ImageGrab

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import main


HARNESS = '''
import json
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
import auto_update as updater
plan = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
sys.frozen = True
sys.executable = plan["target"]
release = updater.Release(plan["version"], Path(plan["candidate"]).as_uri(), plan["size"], plan["sha256"])
updater.latest_release = lambda: release
result = updater.startup_update(Path(plan["profile"]) / "CoCFarmBot")
Path(plan["handoff"]).write_text(json.dumps({"handed_off": result}), encoding="utf-8")
sys.exit(0 if result else 1)
'''


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", default=str(BASE / "dist/CoCFarmBot.exe"))
    parser.add_argument("--previous", default=str(BASE / "build/update-validation/previous.exe"))
    args = parser.parse_args()
    candidate = Path(args.candidate).resolve()
    previous = Path(args.previous).resolve()
    directory = BASE / "build/update-validation" / ("run-" + str(time.time_ns()))
    directory.mkdir(parents=True)
    target_directory = directory / "installation avec espaces et ' apostrophe"
    target_directory.mkdir()
    target = target_directory / "CoCFarmBot.exe"
    shutil.copy2(previous, target)
    profile = directory / "profile"
    storage = profile / "CoCFarmBot"
    storage.mkdir(parents=True)
    settings = main.asdict(main.Settings(min_gold=765432, dragon_count=2))
    (storage / "config-v2.json").write_text(json.dumps(settings), encoding="utf-8")
    (storage / main.STORAGE_MARKER).write_text(main.STORAGE_GENERATION, encoding="utf-8")
    preserved = {"config-v2.json": (storage / "config-v2.json").read_bytes(),
                 "farm-stats.json": b'{"gold": 123456, "elixir": 654321, "dark_elixir": 1234, "battles": 7, "pending": null}',
                 "account_snapshot.json": b'{"account_name": "isolated updater validation"}'}
    for name, payload in preserved.items():
        (storage / name).write_bytes(payload)
    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    plan = {"target": str(target), "candidate": str(candidate), "profile": str(profile),
            "version": main.APP_VERSION, "size": candidate.stat().st_size, "sha256": digest,
            "handoff": str(directory / "handoff.json")}
    plan_path = directory / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    harness = directory / "launch.py"
    harness.write_text(HARNESS, encoding="utf-8")
    environment = {**os.environ, "USERPROFILE": str(profile), "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    cleanup = directory / "stop-validation.ps1"
    cleanup.write_text("param([string]$Executable)\n"
                       "Get-CimInstance Win32_Process -Filter \"Name = 'CoCFarmBot.exe'\" | "
                       "Where-Object { $_.ExecutablePath -eq $Executable } | "
                       "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }\n",
                       encoding="utf-8")
    report = {"ok": False, "directory": str(directory), "version": main.APP_VERSION}
    process = None
    normal_process = None
    try:
        process = subprocess.Popen([sys.executable, str(harness), str(BASE), str(plan_path)],
                                   env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 150
        log = storage / "update.log"
        while time.monotonic() < deadline:
            if log.exists() and "Mise à jour installée" in log.read_text(encoding="utf-8-sig"):
                break
            if process.poll() not in (None, 0):
                raise RuntimeError("L'application de départ n'a pas transmis la mise à jour.")
            time.sleep(.25)
        else:
            raise TimeoutError(log.read_text(encoding="utf-8-sig") if log.exists() else "Installation expirée")
        report["handed_off"] = json.loads(Path(plan["handoff"]).read_text(encoding="utf-8"))["handed_off"]
        report["installed_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        assert report["installed_sha256"] == digest
        report["preserved"] = {name: (storage / name).read_bytes() == payload for name, payload in preserved.items()}
        assert all(report["preserved"].values())
        report["staging_removed"] = not list(target_directory.glob(".CoCFarmBot-update-*"))
        assert report["staging_removed"]
        # Capture only the validation process, never a user's existing bot.
        find = main.USER32.FindWindowW
        find.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        find.restype = ctypes.c_void_p
        hwnd = find(None, main.APP_NAME)
        if hwnd:
            process_id = ctypes.c_ulong()
            main.USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            inspect = directory / "inspect.ps1"
            inspect.write_text("param([int]$ProcessIdToInspect)\n"
                               "(Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $ProcessIdToInspect)).ExecutablePath\n",
                               encoding="utf-8")
            path = subprocess.run([str(powershell), "-NoProfile", "-File", str(inspect), str(process_id.value)],
                                  capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()
            if Path(path) == target:
                screenshot = directory / "updated-interface.png"
                main.WindowDriver.capture(main.GameWindow(hwnd, main.APP_NAME, 1366, 768)).save(screenshot)
                report["screenshot"] = str(screenshot)
        # Exercise the packaged startup check too. The update harness above uses
        # the repository updater to simulate a newer release; this normal launch
        # must import the updater embedded in the EXE and reach the real WebView.
        subprocess.run([str(powershell), "-NoProfile", "-File", str(cleanup), str(target)],
                       creationflags=subprocess.CREATE_NO_WINDOW, check=False)
        log.unlink()
        normal_process = subprocess.Popen([str(target)], env=environment,
                                          creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            hwnd = find(None, main.APP_NAME)
            if hwnd:
                time.sleep(2)
                screenshot = directory / "normal-start-interface.png"
                # Hardware-accelerated Edge can return a flat PrintWindow image
                # even when its UI is visible. Read the actual window pixels.
                rectangle = main.wintypes.RECT()
                main.USER32.GetWindowRect(hwnd, ctypes.byref(rectangle))
                image = ImageGrab.grab(bbox=(rectangle.left, rectangle.top, rectangle.right, rectangle.bottom))
                image.save(screenshot)
                sidebar = main.read_text(image.crop((0, 70, 200, 195)))
                if main.APP_VERSION in sidebar.lower().replace("o", "0").replace(" ", ""):
                    report["normal_start"] = True
                    report["normal_start_screenshot"] = str(screenshot)
                    break
            if normal_process.poll() is not None:
                raise RuntimeError("Le lancement normal de l'EXE a échoué.")
            time.sleep(.2)
        else:
            raise TimeoutError("La vérification au lancement n'a pas ouvert l'interface.")
        assert not log.exists(), log.read_text(encoding="utf-8-sig")
        report["ok"] = report["handed_off"] and report["normal_start"]
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        subprocess.run([str(powershell), "-NoProfile", "-File", str(cleanup), str(target)],
                       creationflags=subprocess.CREATE_NO_WINDOW, check=False)
        (BASE / "build/auto-update-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(run())
