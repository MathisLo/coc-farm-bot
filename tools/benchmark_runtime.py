"""Compare the committed baseline and candidate using real OCR, without input."""
import json
from pathlib import Path
import queue
import statistics
import subprocess
import sys
import threading
import time
import types
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
import main
import upgrades

BASE = Path(__file__).resolve().parents[1]


def baseline_module(name, filename):
    module = types.ModuleType(name)
    module.__file__ = str(BASE / filename)
    sys.modules[name] = module
    source = subprocess.check_output(['git', 'show', 'HEAD:' + filename], cwd=BASE)
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


def measure(engine, upgrade_module, image, scan=False):
    calls = [0]
    frames = [0]
    original_text = engine._ocr_file
    original_words = engine._ocr_words_file

    async def text(path):
        calls[0] += 1
        return await original_text(path)

    async def words(path):
        calls[0] += 1
        return await original_words(path)

    def capture(_window):
        frames[0] += 1
        engine._operation.ocr_cache = {}
        return image

    app = types.SimpleNamespace(settings=engine.Settings(), _capture=capture,
                                _wait=lambda _: None, _trace=lambda *_: None,
                                _check_stopped=lambda: None, action_lock=threading.RLock(),
                                events=queue.Queue())
    started = time.perf_counter()
    with engine.operation_context(threading.Event(), app.settings), \
         patch.object(engine, '_ocr_file', text), patch.object(engine, '_ocr_words_file', words), \
         patch.object(engine.WindowDriver, 'scroll_menu', return_value=True), \
         patch.object(upgrade_module, 'engine', return_value=engine), \
         patch.object(upgrade_module, 'scroll_builders_to_top'):
        if scan:
            result = upgrade_module.find_payable_upgrade(app, 'fixture', 4, (20_000_000, 20_000_000))
        else:
            result = [engine.connection_retry_point(image), engine.builders_menu_open(image),
                      engine.village_home_ready(image), engine.builders_menu_open(image),
                      engine.connection_retry_point(image)]
    return {'seconds': round(time.perf_counter() - started, 4), 'ocr_calls': calls[0],
            'captures': frames[0], 'result': result}


def run():
    baseline = baseline_module('runtime_baseline', 'main.py')
    baseline_upgrades = baseline_module('runtime_baseline_upgrades', 'upgrades.py')
    reports = {}
    fixture = BASE / 'build' / 'runtime-builders-menu.png'
    if not fixture.exists():
        fixture = BASE / 'testdata' / 'suggested_menu.png'
    with Image.open(fixture) as image:
        for name, scan in (('screen_checks', False), ('building_list', True)):
            old, new = [], []
            # Alternate the order to limit OCR startup and background-load bias.
            for order in ((0, 1), (1, 0), (0, 1)):
                for version in order:
                    engine, upgrade_module = (baseline, baseline_upgrades) if version == 0 else (main, upgrades)
                    (old if version == 0 else new).append(measure(engine, upgrade_module, image, scan))
            before = statistics.median(item['seconds'] for item in old)
            after = statistics.median(item['seconds'] for item in new)
            reports[name] = {'baseline': old, 'candidate': new,
                             'median_before_seconds': before, 'median_after_seconds': after,
                             'reduction_percent': round(100 * (1 - after / before), 1),
                             'same_result': all(item['result'] == old[0]['result'] for item in old + new)}
    report = {'fixture': str(fixture), 'baseline_commit': subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=BASE, text=True).strip(),
        'candidate_version': main.APP_VERSION, 'measurements': reports}
    report['ok'] = all(item['same_result'] and item['median_after_seconds'] < item['median_before_seconds']
                       for item in reports.values())
    (BASE / 'build' / 'runtime-benchmark.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(run())
