"""Validate the rendered WebView settings against an isolated bot directory."""
import json
import ctypes
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from modern_dashboard import Bridge
import webview

BASE = Path(__file__).resolve().parents[1]
CHOICES = ('upgrade_hero_eradicator', 'upgrade_explosive_catapult', 'upgrade_firespitter')


def run():
    report = {'ok': False, 'choices': list(CHOICES)}
    with tempfile.TemporaryDirectory(prefix='coc-ui-validation-') as temporary:
        directory = Path(temporary) / 'CoCFarmBot'
        with patch.multiple(main, APP_DIR=directory, CONFIG_PATH=directory / 'config-v2.json',
                            LOG_PATH=directory / 'bot.log', STATS_PATH=directory / 'farm-stats.json',
                            ACCOUNT_SNAPSHOT_PATH=directory / 'account_snapshot.json'), \
             patch.object(main.WindowDriver, 'list_windows', return_value=[]), \
             patch.object(main.WindowDriver, 'click_percent', side_effect=AssertionError('No game input in UI validation')):
            bridge = Bridge()
            title = 'CoC runtime UI validation'
            window = webview.create_window(title, (BASE / 'web_dashboard.html').as_uri(),
                                           js_api=bridge, width=1366, height=768)

            def wait_until(predicate, timeout=15):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if predicate():
                        return
                    time.sleep(.1)
                raise AssertionError('UI condition not reached before timeout')

            def validate():
                try:
                    wait_until(lambda: window.evaluate_js("document.getElementById('min_gold')?.value === '500000'"))
                    report['defaults'] = window.evaluate_js(
                        'Object.fromEntries(' + json.dumps(CHOICES) + '.map(key=>[key,document.getElementById(key).checked]))')
                    assert all(report['defaults'].values())
                    window.evaluate_js("document.querySelector('[data-tabs=\"settings\"] [data-tab=\"cycle\"]').click()")
                    for field in CHOICES:
                        window.evaluate_js(f"document.getElementById('{field}').click()")
                    window.evaluate_js("document.querySelector('[data-action=\"save\"]').click()")
                    wait_until(lambda: main.CONFIG_PATH.exists() and
                               all(getattr(main.load_settings(), key) is False for key in CHOICES))
                    report['saved'] = {key: getattr(main.load_settings(), key) for key in CHOICES}
                    window.evaluate_js('location.reload()')
                    wait_until(lambda: window.evaluate_js("document.getElementById('min_gold')?.value === '500000'"))
                    report['reloaded'] = window.evaluate_js(
                        'Object.fromEntries(' + json.dumps(CHOICES) + '.map(key=>[key,document.getElementById(key).checked]))')
                    assert all(value is False for value in report['reloaded'].values())
                    window.evaluate_js("document.querySelector('[data-tabs=\"settings\"] [data-tab=\"cycle\"]').click()")
                    for field in CHOICES:
                        window.evaluate_js(f"document.getElementById('{field}').click()")
                        window.evaluate_js("document.querySelector('[data-action=\"save\"]').click()")
                        wait_until(lambda: getattr(main.load_settings(), field) is True)
                    report['enabled_again'] = {key: getattr(main.load_settings(), key) for key in CHOICES}
                    report['layout'] = window.evaluate_js('''(() => {
                      const body=document.querySelector('.settings-body');
                      const first=document.getElementById('upgrade_hero_eradicator').closest('label');
                      body.scrollTop+=first.getBoundingClientRect().top-body.getBoundingClientRect().top;
                      const box=body.getBoundingClientRect();
                      return Object.fromEntries(''' + json.dumps(CHOICES) + '''.map(key=>{
                        const label=document.getElementById(key).closest('label').getBoundingClientRect();
                        return [key,{width:label.width,height:label.height,accessible:label.width>0&&label.height>0&&label.left>=box.left&&label.right<=box.right+1&&label.top>=box.top-1&&label.bottom<=box.bottom+1}];
                      }));
                    })()''')
                    assert all(item['accessible'] for item in report['layout'].values())
                    window.evaluate_js("document.querySelectorAll('.toast').forEach(item=>item.remove())")
                    find = main.USER32.FindWindowW
                    find.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
                    find.restype = ctypes.c_void_p
                    target = main.GameWindow(find(None, title), title, 1366, 768)
                    screenshot = BASE / 'build' / 'runtime-ui-cycle.png'
                    main.WindowDriver.capture(target).save(screenshot)
                    report['screenshot'] = str(screenshot)
                    report['ok'] = True
                except Exception as error:
                    report['error'] = f'{type(error).__name__}: {error}'
                finally:
                    bridge.call('close')
                    window.destroy()

            webview.start(validate, gui='edgechromium', private_mode=True)
    (BASE / 'build' / 'runtime-ui-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(run())
