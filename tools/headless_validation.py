"""Run one real, bounded bot action without opening its dashboard."""

import argparse
import re
import sys
import threading
import time
from dataclasses import replace

import main
from farm_stats import FarmStats


def deployment_matches_configuration(event, settings):
    match = re.fullmatch(
        r"Déploiement vérifié : (\d+) électro-dragons, (\d+) dragons, 4 héros, 5 Rage\.",
        event,
    )
    return bool(match and int(match.group(1)) >= settings.electrodragon_count
                and int(match.group(2)) >= settings.dragon_count)


def main_cli():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("attack", "walls", "buildings", "collect", "soak"))
    parser.add_argument("--minutes", type=float, default=30)
    parser.add_argument("--electrodragons", type=int)
    parser.add_argument("--walls", action="store_true")
    parser.add_argument("--buildings", action="store_true")
    args = parser.parse_args()
    if args.action == "soak" and args.minutes <= 0:
        parser.error("--minutes must be positive")

    app = object.__new__(main.BotApp)
    app.settings = main.load_settings()
    if args.action in ("attack", "soak"):
        app.settings = replace(app.settings, chain_attacks=args.action == "soak",
                               upgrade_recommended=args.action == "soak" and args.buildings,
                               upgrade_wall_between_attacks=args.action == "soak" and args.walls,
                               deploy_heroes=True,
                               electrodragon_count=args.electrodragons or app.settings.electrodragon_count)
    elif args.action == "buildings":
        app.settings = replace(app.settings, dry_run=False, upgrade_recommended=True)
    started = time.monotonic()
    if args.action == "soak":
        app._soak_deadline = started + args.minutes * 60
    app.stop_event = threading.Event()
    app.action_lock = threading.RLock()
    app.journal = main.DiagnosticJournal(main.LOG_PATH)
    app.events = main.DiagnosticEvents(app.journal)
    app.farm_stats = FarmStats(main.STATS_PATH)
    app._reconnect_pending = False
    app._last_capture = None
    result = {}

    if args.action in ("attack", "soak"):
        operation = app.farm_loop
    elif args.action == "buildings":
        def operation():
            from upgrades import upgrade_suggested
            window = main.WindowDriver.resolve(app.settings.window_title)
            if window is None:
                raise RuntimeError("Fenêtre Clash introuvable.")
            image = app._capture(window)
            if not main.village_home_ready(image) or main.wall_selection_open(image):
                raise RuntimeError("Revenir au village avant les améliorations de bâtiments.")
            result["buildings"] = upgrade_suggested(app, window, max_upgrades=1)
    elif args.action == "collect":
        def operation():
            window = main.WindowDriver.resolve(app.settings.window_title)
            if window is None:
                raise RuntimeError("Fenêtre Clash introuvable.")
            result["collected"] = app.collect_village_resources(window)
    else:
        def operation():
            window = main.WindowDriver.resolve(app.settings.window_title)
            if window is None:
                raise RuntimeError("Fenêtre Clash introuvable.")
            result["walls"] = app.upgrade_walls_to_reserve(window, independent=True, max_batches=1)

    try:
        app._begin_run(f"validation console {args.action}")
        run_path = app.journal.run_path
        app._run_operation(operation)
        events = list(app.events.queue)
        for event in events:
            if isinstance(event, str):
                print(event)
        print(f"Journal : {run_path}")
        status = next((event.status for event in reversed(events)
                       if isinstance(event, main.RunStateEvent)), None)
        if status != "terminée":
            raise SystemExit(f"Validation {args.action} interrompue : {status}")
        if args.action == "attack" and not any(
                isinstance(event, str) and event.startswith("Déploiement vérifié :")
                for event in events):
            raise SystemExit("Aucun déploiement complet confirmé dans cette validation.")
        if args.action == "soak":
            elapsed = time.monotonic() - started
            deployments = [event for event in events if isinstance(event, str)
                           and event.startswith("Déploiement vérifié :")]
            print(f"Durée : {elapsed / 60:.1f} min ; attaques complètes : {len(deployments)}")
            if any(not deployment_matches_configuration(event, app.settings)
                   for event in deployments):
                raise SystemExit("Composition différente de l'armée attendue pendant la validation continue.")
            if elapsed < args.minutes * 60 or len(deployments) < 2:
                raise SystemExit("Validation continue insuffisante : 30 minutes et deux attaques complètes requises.")
        if args.action == "walls" and result.get("walls", 0) == 0:
            raise SystemExit("Aucun rempart amélioré dans cette validation.")
        if args.action == "buildings" and result.get("buildings", 0) != 1:
            raise SystemExit("Aucune amélioration de bâtiment confirmée dans cette validation.")
        if args.action == "collect" and not any(
                isinstance(event, str) and "foreuse(s) d'élixir noir" in event and "0 foreuse(s)" not in event
                for event in events):
            raise SystemExit("Aucune foreuse d'élixir noir collectée dans cette validation.")
    finally:
        app.journal.close()


if __name__ == "__main__":
    main_cli()
