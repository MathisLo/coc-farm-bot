"""Run one real, bounded bot action without opening its dashboard."""

import argparse
import threading
from dataclasses import replace

import main
from farm_stats import FarmStats


def main_cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("attack", "walls"))
    args = parser.parse_args()

    app = object.__new__(main.BotApp)
    app.settings = main.load_settings()
    if args.action == "attack":
        app.settings = replace(app.settings, chain_attacks=False,
                               upgrade_recommended=False,
                               upgrade_wall_between_attacks=False)
    app.stop_event = threading.Event()
    app.action_lock = threading.RLock()
    app.journal = main.DiagnosticJournal(main.LOG_PATH)
    app.events = main.DiagnosticEvents(app.journal)
    app.farm_stats = FarmStats(main.STATS_PATH)
    app._reconnect_pending = False
    app._last_capture = None
    result = {}

    if args.action == "attack":
        operation = app.farm_loop
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
        if args.action == "walls" and result.get("walls", 0) == 0:
            raise SystemExit("Aucun rempart amélioré dans cette validation.")
    finally:
        app.journal.close()


if __name__ == "__main__":
    main_cli()
