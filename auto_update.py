"""Startup updates from the public GitHub release, without user credentials."""
from __future__ import annotations

from dataclasses import dataclass
import gc
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request, urlopen

from app_meta import APP_NAME, APP_VERSION

REPOSITORY = "MathisLo/coc-farm-bot"
RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
ASSET_NAME = "CoCFarmBot.exe"
NETWORK_TIMEOUT = 8
DOWNLOAD_TIMEOUT = 180
MAX_ASSET_SIZE = 250 * 1024 * 1024


class UpdateCancelled(Exception):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    size: int
    sha256: str


def version_numbers(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise ValueError("Version de publication invalide.")
    return tuple(int(part) for part in value.removeprefix("v").split("."))


def latest_release(current_version=APP_VERSION):
    request = Request(RELEASE_URL, headers={
        "User-Agent": f"CoCFarmBot/{APP_VERSION}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urlopen(request, timeout=NETWORK_TIMEOUT) as response:
        metadata = response.read(1024 * 1024 + 1)
    if len(metadata) > 1024 * 1024:
        raise ValueError("Réponse GitHub trop volumineuse.")
    data = json.loads(metadata)
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = data["tag_name"]
    if version_numbers(tag) <= version_numbers(current_version):
        return None
    assets = [asset for asset in data.get("assets", []) if asset.get("name") == ASSET_NAME]
    if len(assets) != 1:
        raise ValueError("Exécutable de publication absent ou ambigu.")
    asset = assets[0]
    expected_url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{ASSET_NAME}"
    digest = asset.get("digest", "")
    size = asset.get("size")
    if (asset.get("state") != "uploaded" or asset.get("browser_download_url") != expected_url
            or not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest)
            or type(size) is not int or not 0 < size <= MAX_ASSET_SIZE):
        raise ValueError("Informations de publication incomplètes ou invalides.")
    return Release(tag.removeprefix("v"), expected_url, size, digest[7:].lower())


def check_cancelled(cancelled):
    if cancelled.is_set():
        raise UpdateCancelled()


def download_release(release, destination, cancelled, progress):
    digest = hashlib.sha256()
    total = 0
    deadline = time.monotonic() + DOWNLOAD_TIMEOUT
    request = Request(release.url, headers={"User-Agent": f"CoCFarmBot/{APP_VERSION}"})
    with urlopen(request, timeout=NETWORK_TIMEOUT) as response, destination.open("wb") as output:
        while True:
            check_cancelled(cancelled)
            if time.monotonic() >= deadline:
                raise TimeoutError("Téléchargement de la mise à jour expiré.")
            block = response.read(256 * 1024)
            if not block:
                break
            total += len(block)
            if total > release.size:
                raise ValueError("Taille de la mise à jour incorrecte.")
            output.write(block)
            digest.update(block)
            progress(f"Téléchargement de la version {release.version} : {total * 100 // release.size} %")
    if total != release.size or digest.hexdigest() != release.sha256:
        raise ValueError("Empreinte SHA-256 de la mise à jour incorrecte.")
    with destination.open("rb") as executable:
        if executable.read(2) != b"MZ":
            raise ValueError("La mise à jour n'est pas un exécutable Windows.")


def verify_candidate(executable, release, cancelled):
    check_cancelled(cancelled)
    report_path = executable.parent / "candidate-check.json"
    result = subprocess.run(
        [str(executable), "--self-test-report", str(report_path)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW, timeout=60, check=False,
        cwd=str(executable.parent), env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
    )
    check_cancelled(cancelled)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if result.returncode != 0 or not report.get("ok") or not report.get("frozen") or report.get("version") != release.version:
        raise ValueError("L'autotest de la nouvelle version a échoué.")


def stage_release(release, target, cancelled, progress):
    # Stage on the same volume for an atomic replacement. A read-only install
    # directory fails here while the currently installed executable stays intact.
    directory = Path(tempfile.mkdtemp(prefix=".CoCFarmBot-update-", dir=target.parent))
    try:
        candidate = directory / ASSET_NAME
        download_release(release, candidate, cancelled, progress)
        progress("Vérification de la nouvelle version…")
        verify_candidate(candidate, release, cancelled)
        check_cancelled(cancelled)
        return directory
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise


# The running one-file EXE remains locked until both PyInstaller processes have
# stopped. A separate, hidden Windows helper waits and retries the atomic swap.
# Paths travel through JSON and LiteralPath, never through generated shell code.
INSTALL_SCRIPT = r'''
param([string]$PlanPath)
$ErrorActionPreference = 'Stop'
$plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
$installed = $false
$started = $false
try {
    'ready' | Set-Content -LiteralPath $plan.helper_ready -Encoding UTF8
    $previous = Get-Process -Id $plan.process_id -ErrorAction SilentlyContinue
    if ($previous -and -not $previous.WaitForExit(60000)) { throw 'Ancienne application encore ouverte.' }
    if ((Get-FileHash -LiteralPath $plan.candidate -Algorithm SHA256).Hash.ToLowerInvariant() -ne $plan.sha256) {
        throw 'Empreinte de la mise à jour incorrecte.'
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    do {
        try {
            [System.IO.File]::Replace($plan.candidate, $plan.target, $plan.backup)
            $installed = $true
        } catch {
            if ([DateTime]::UtcNow -ge $deadline) { throw }
            Start-Sleep -Milliseconds 250
        }
    } until ($installed)
    $env:PYINSTALLER_RESET_ENVIRONMENT = '1'
    $new = Start-Process -FilePath $plan.target -WorkingDirectory $plan.working_directory -ArgumentList @('--update-ready-file', ('"' + $plan.ready_file + '"')) -WindowStyle Hidden -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(75)
    do {
        if (Test-Path -LiteralPath $plan.ready_file) { $started = $true; break }
        $new.Refresh()
        if ($new.HasExited) { throw 'La nouvelle application a quitté avant son ouverture.' }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $started) {
        # Stop only the new process tree started by this helper. This also
        # releases the PyInstaller parent lock before restoring the old file.
        & "$env:SystemRoot\System32\taskkill.exe" /PID $new.Id /T /F | Out-Null
        $new.WaitForExit(10000) | Out-Null
        throw 'La nouvelle interface ne répond pas.'
    }
    'Mise à jour installée : ' + $plan.version | Set-Content -LiteralPath $plan.log_file -Encoding UTF8
} catch {
    $_.Exception.Message | Set-Content -LiteralPath $plan.log_file -Encoding UTF8
    if ($installed -and -not $started) {
        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        do {
            try {
                [System.IO.File]::Replace($plan.backup, $plan.target, $plan.rejected)
                $installed = $false
            } catch {
                if ([DateTime]::UtcNow -ge $deadline) { break }
                Start-Sleep -Milliseconds 250
            }
        } while ($installed)
    }
    if (-not $installed) {
        # Bypass the check once so a rejected release cannot cause an update loop.
        Start-Process -FilePath $plan.target -WorkingDirectory $plan.working_directory -ArgumentList @('--update-ready-file', ('"' + $plan.ready_file + '"')) -WindowStyle Hidden
    }
} finally {
    # Never discard the backup if restoration failed. All cleanup is constrained
    # to the uniquely named staging directory next to the exact target EXE.
    if ($started -or -not $installed) {
        $directory = [System.IO.Path]::GetFullPath($plan.directory)
        $parent = [System.IO.Path]::GetDirectoryName([System.IO.Path]::GetFullPath($plan.target))
        if ([System.IO.Path]::GetDirectoryName($directory) -eq $parent -and [System.IO.Path]::GetFileName($directory).StartsWith('.CoCFarmBot-update-')) {
            Remove-Item -LiteralPath $directory -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
'''


def launch_installer(directory, target, release, log_file):
    script = directory / "install.ps1"
    script.write_text(INSTALL_SCRIPT, encoding="utf-8-sig")
    plan_path = directory / "plan.json"
    plan = {
        "process_id": os.getpid(), "directory": str(directory),
        "candidate": str(directory / ASSET_NAME), "target": str(target),
        "backup": str(directory / "previous.exe"), "ready_file": str(directory / "started.txt"),
        "rejected": str(directory / "rejected.exe"),
        "helper_ready": str(directory / "helper-ready.txt"),
        "working_directory": str(target.parent), "sha256": release.sha256,
        "version": release.version, "log_file": str(log_file),
    }
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    process = subprocess.Popen(
        [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(script), "-PlanPath", str(plan_path)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW, cwd=str(target.parent), close_fds=True,
        env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
    )
    # Detect immediate launch/policy failures before asking the running app to exit.
    deadline = time.monotonic() + 10
    while not (directory / "helper-ready.txt").exists():
        if process.poll() is not None:
            raise RuntimeError("Le programme de mise à jour n'a pas pu démarrer.")
        if time.monotonic() >= deadline:
            process.terminate()
            process.wait(timeout=5)
            raise TimeoutError("Le programme de mise à jour ne répond pas.")
        time.sleep(.05)
    return process


def write_log(log_file, message):
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text(message + "\n", encoding="utf-8")
    except OSError:
        pass


def startup_update(app_directory):
    """Return True only after handing a validated update to the installer."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    result = [False]

    def window_thread():
        try:
            result[0] = _startup_update(app_directory)
        except Exception as error:
            write_log(app_directory / "update.log", f"Mise à jour indisponible : {error}")
        finally:
            # Tk and EdgeChromium must own separate native event loops. Dispose
            # every splash Tk object on its creating thread before WebView starts.
            gc.collect()

    thread = threading.Thread(target=window_thread, name="StartupUpdateWindow")
    thread.start()
    thread.join()
    return result[0]


def _startup_update(app_directory):
    from tkinter import StringVar, Tk, ttk

    target = Path(sys.executable).resolve()
    app_directory.mkdir(parents=True, exist_ok=True)
    log_file = app_directory / "update.log"
    root = Tk()
    root.title(f"{APP_NAME} — mise à jour")
    root.geometry("490x145")
    root.resizable(False, False)
    status = StringVar(root, "Vérification des mises à jour sur GitHub…")
    ttk.Label(root, text=APP_NAME, font=("Segoe UI", 12, "bold")).pack(pady=(14, 8))
    ttk.Label(root, textvariable=status).pack(pady=4)
    progress_bar = ttk.Progressbar(root, mode="indeterminate", length=420)
    progress_bar.pack(pady=8)
    progress_bar.start()
    cancelled = threading.Event()
    results = queue.Queue()
    state_lock = threading.Lock()
    staged = None
    handed_off = False

    def worker():
        nonlocal staged
        try:
            release = latest_release()
            check_cancelled(cancelled)
            if release is None:
                results.put(("done", None))
                return
            directory = stage_release(release, target, cancelled, lambda message: results.put(("progress", message)))
            with state_lock:
                if cancelled.is_set():
                    shutil.rmtree(directory, ignore_errors=True)
                else:
                    staged = directory
                    results.put(("ready", release))
        except UpdateCancelled:
            pass
        except Exception as error:
            results.put(("error", f"Mise à jour indisponible : {type(error).__name__}: {error}"))

    def skip():
        cancelled.set()
        root.quit()

    ttk.Button(root, text="Ouvrir sans attendre", command=skip).pack()
    root.protocol("WM_DELETE_WINDOW", skip)

    def poll():
        nonlocal handed_off
        try:
            while True:
                kind, value = results.get_nowait()
                if kind == "progress":
                    status.set(value)
                elif kind == "ready":
                    launch_installer(staged, target, value, log_file)
                    handed_off = True
                    root.quit()
                    return
                else:
                    if kind == "error":
                        write_log(log_file, value)
                    root.quit()
                    return
        except queue.Empty:
            root.after(50, poll)
        except Exception as error:
            write_log(log_file, f"Mise à jour non installée : {error}")
            root.quit()

    try:
        threading.Thread(target=worker, name="StartupUpdate", daemon=True).start()
        root.after(50, poll)
        root.mainloop()
    finally:
        cancelled.set()
        with state_lock:
            if staged is not None and not handed_off:
                shutil.rmtree(staged, ignore_errors=True)
        progress_bar.stop()
        root.destroy()
    return handed_off
