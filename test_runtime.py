"""Input timing, fresh-frame OCR, and destination readiness regressions."""
import threading
import ctypes
from ctypes import wintypes
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
import main
from test_regressions import app_without_gui


class RuntimeTests(unittest.TestCase):
    def test_diagnostic_gold_keeps_its_leading_millions(self):
        with Image.open(Path(__file__).parent / 'testdata/builder_overlay_after_wall_refusal.png') as image:
            self.assertEqual(main.read_safe_reserve(image, 'gold'), 2_719_974)

    def test_diagnostic_giant_bomb_title_allows_only_the_matching_panel(self):
        import upgrades
        with Image.open(Path(__file__).parent / 'testdata/giant_bomb_panel_clipped_title.png') as image:
            self.assertTrue(upgrades.selected_panel_title_matches(image, 'hmbe géante'))
            self.assertFalse(upgrades.selected_panel_title_matches(image, 'Mine chercheuse'))

    def test_search_closes_builder_overlay_before_attack_and_refreshes_state(self):
        app = app_without_gui()
        state = {'screen': 'builders'}
        def click(window, x, y):
            if state['screen'] == 'builders':
                self.assertEqual((x, y), main.BUILDERS_BUTTON)
                state['screen'] = 'village'
            elif state['screen'] == 'village':
                self.assertEqual((x, y), main.ATTACK_HOME_BUTTON)
                state['screen'] = 'multiplayer'
            elif state['screen'] == 'multiplayer':
                state['screen'] = 'army'
            else:
                state['screen'] = 'enemy'
            return True
        app._capture = Mock(side_effect=lambda _: state['screen'])
        app._click = Mock(side_effect=click)
        app._wait = Mock()
        app.wait_for_army_ready = Mock(return_value=True)
        with patch.object(main, 'battle_hud_visible', return_value=False), \
             patch.object(main, 'daily_reward_open', return_value=False), \
             patch.object(main, 'builders_menu_open', side_effect=lambda im: im == 'builders'), \
             patch.object(main, 'village_home_ready', side_effect=lambda im: im == 'village'), \
             patch.object(main, 'army_selection_ready', side_effect=lambda im: im == 'army'), \
             patch.object(main, 'multiplayer_menu_ready', side_effect=lambda im: im == 'multiplayer'), \
             patch.object(main, 'enemy_loot_screen_ready', side_effect=lambda im: im == 'enemy'):
            self.assertTrue(app.open_search('window'))
        self.assertEqual(app._click.call_count, 4)

    def test_search_never_attacks_through_a_builder_overlay_that_stays_open(self):
        app = app_without_gui()
        app._capture = Mock(return_value='builders')
        app._click = Mock(return_value=True)
        app._wait_for_screen = Mock(return_value=False)
        with patch.object(main, 'battle_hud_visible', return_value=False), \
             patch.object(main, 'daily_reward_open', return_value=False), \
             patch.object(main, 'builders_menu_open', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'ouvriers'):
                app.open_search('window')
        app._click.assert_called_once_with('window', *main.BUILDERS_BUTTON)

    def test_real_windows_input_is_seen_by_a_game_polling_at_30_fps(self):
        """Use an owned hidden Win32 target, never a game/account window."""
        user = ctypes.WinDLL('user32', use_last_error=True)
        proc_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                     wintypes.WPARAM, wintypes.LPARAM)

        class WindowClass(ctypes.Structure):
            _fields_ = [('style', wintypes.UINT), ('proc', proc_type),
                        ('class_extra', ctypes.c_int), ('window_extra', ctypes.c_int),
                        ('instance', wintypes.HINSTANCE), ('icon', wintypes.HICON),
                        ('cursor', wintypes.HANDLE), ('background', wintypes.HBRUSH),
                        ('menu', wintypes.LPCWSTR), ('name', wintypes.LPCWSTR)]

        user.RegisterClassW.argtypes = [ctypes.POINTER(WindowClass)]
        user.RegisterClassW.restype = wintypes.ATOM
        user.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                       wintypes.HINSTANCE, ctypes.c_void_p]
        user.CreateWindowExW.restype = wintypes.HWND
        user.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user.DefWindowProcW.restype = ctypes.c_ssize_t
        user.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
        user.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
        user.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user.DispatchMessageW.restype = ctypes.c_ssize_t
        user.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        state = {'pressed': False, 'sampled': False}
        ready = threading.Event()

        def receive():
            @proc_type
            def procedure(hwnd, message, flags, point):
                if message == main.WM_LBUTTONDOWN:
                    state['pressed'] = True
                    user.SetTimer(hwnd, 1, 33, None)
                elif message == main.WM_LBUTTONUP:
                    state['pressed'] = False
                elif message == 0x0113:  # A game sampling input once per frame.
                    state['sampled'] = state['sampled'] or state['pressed']
                    user.KillTimer(hwnd, 1)
                elif message == 0x0002:
                    user.PostQuitMessage(0)
                    return 0
                return user.DefWindowProcW(hwnd, message, flags, point)

            name = 'CoCBotOwnedTimingTarget' + str(threading.get_ident())
            definition = WindowClass(name=name, proc=procedure)
            if not user.RegisterClassW(ctypes.byref(definition)):
                state['error'] = ctypes.get_last_error()
                ready.set()
                return
            state['hwnd'] = user.CreateWindowExW(0, name, name, 0, 0, 0, 640, 360, None, None, None, None)
            ready.set()
            message = wintypes.MSG()
            while user.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user.DispatchMessageW(ctypes.byref(message))
            user.UnregisterClassW(name, None)

        worker = threading.Thread(target=receive, daemon=True)
        worker.start()
        self.assertTrue(ready.wait(5))
        self.assertTrue(state.get('hwnd'), state.get('error'))
        window = main.GameWindow(state['hwnd'], 'Owned input timing target', 640, 360)
        try:
            geometry = main.WindowDriver.client_geometry(window)
            point = (180 << 16) | 320
            # Reproduce the previous implementation: no frame sees the press.
            main.USER32.PostMessageW(window.hwnd, main.WM_LBUTTONDOWN, main.MK_LBUTTON, point)
            main.USER32.PostMessageW(window.hwnd, main.WM_LBUTTONUP, 0, point)
            time.sleep(.12)
            self.assertFalse(state['sampled'])
            settings = main.replace(main.Settings(), layout_aspect_ratio=geometry.width / geometry.height)
            with main.operation_context(threading.Event(), settings):
                main._operation.last_capture = (window.hwnd, geometry)
                self.assertTrue(main.WindowDriver.click_percent(window, 50, 50))
            time.sleep(.06)
            self.assertTrue(state['sampled'])
        finally:
            main.USER32.PostMessageW(window.hwnd, 0x0010, 0, 0)
            worker.join(5)
            self.assertFalse(worker.is_alive())

    def test_ocr_reuses_identical_crops_but_not_another_scale_or_changed_pixels(self):
        calls = []

        async def recognize(path):
            calls.append(path)
            return '12345'

        image = Image.new('RGB', (40, 20), 'white')
        with main.operation_context(threading.Event(), main.Settings()), \
             patch.object(main, '_ocr_file', recognize):
            self.assertEqual(main.read_text(image, 2), '12345')
            self.assertEqual(main.read_text(image.copy(), 2), '12345')
            main.read_text(image, 3)
            image.putpixel((0, 0), (0, 0, 0))
            main.read_text(image, 2)
        self.assertEqual(len(calls), 3)

    def test_two_fresh_identical_frames_still_make_two_independent_ocr_readings(self):
        app = app_without_gui()
        image = Image.new('RGB', (40, 20), 'white')
        calls = []

        async def recognize(path):
            calls.append(path)
            return str(len(calls))

        with main.operation_context(app.stop_event, app.settings), \
             patch.object(main.WindowDriver, 'capture', return_value=image), \
             patch.object(main, 'connection_retry_point', return_value=None), \
             patch.object(main, '_ocr_file', recognize):
            self.assertEqual(main.read_text(app._capture('window'), 2), '1')
            self.assertEqual(main.read_text(app._capture('window'), 2), '2')

    def test_stop_is_honored_even_when_the_ocr_result_is_cached(self):
        event = threading.Event()
        image = Image.new('RGB', (40, 20), 'white')

        async def recognize(path):
            return 'value'

        with main.operation_context(event, main.Settings()), patch.object(main, '_ocr_file', recognize):
            main.read_text(image)
            event.set()
            with self.assertRaises(main.OperationCancelled):
                main.read_text(image)

    def test_destination_wait_requires_two_consecutive_fresh_frames(self):
        app = app_without_gui()
        frames = [False, True, False, True, True]
        with patch.object(app, '_capture', side_effect=frames) as capture, \
             patch.object(app, '_wait') as wait:
            self.assertTrue(app._wait_for_screen('window', bool))
        self.assertEqual(capture.call_count, 5)
        self.assertEqual(wait.call_count, 5)

    def test_search_waits_for_each_menu_before_clicking_its_next_button(self):
        app = app_without_gui()
        state = {'screen': 'village', 'confirmed_frames': 0}

        def ready(image, expected):
            if image != expected:
                return False
            state['confirmed_frames'] += 1
            return True

        def click(window, x, y):
            if state['screen'] == 'village':
                state['screen'] = 'multiplayer'
            elif state['screen'] == 'multiplayer':
                self.assertGreaterEqual(state['confirmed_frames'], 2)
                state['screen'] = 'army'
            else:
                self.assertGreaterEqual(state['confirmed_frames'], 2)
                state['screen'] = 'enemy'
            state['confirmed_frames'] = 0
            return True

        app._capture = Mock(side_effect=lambda _: state['screen'])
        app._click = Mock(side_effect=click)
        app._wait = Mock()
        app.wait_for_army_ready = Mock(return_value=True)
        with patch.object(main, 'battle_hud_visible', return_value=False), \
             patch.object(main, 'daily_reward_open', return_value=False), \
             patch.object(main, 'builders_menu_open', return_value=False), \
             patch.object(main, 'army_selection_ready', side_effect=lambda image: ready(image, 'army')), \
             patch.object(main, 'multiplayer_menu_ready', side_effect=lambda image: ready(image, 'multiplayer')), \
             patch.object(main, 'enemy_loot_screen_ready', side_effect=lambda image: image == 'enemy'):
            self.assertTrue(app.open_search('window'))
        self.assertEqual(app._click.call_count, 3)

    def test_destination_wait_times_out_and_stop_interrupts_it(self):
        app = app_without_gui()
        with patch.object(app, '_capture') as capture:
            self.assertFalse(app._wait_for_screen('window', bool, timeout=0))
            capture.assert_not_called()
            app.stop_event.set()
            with self.assertRaises(main.OperationCancelled):
                app._wait_for_screen('window', bool)

    def test_mouse_press_is_held_and_stop_always_releases_it(self):
        geometry = main.ClientGeometry(1280, 720, 0, 0, 1280, 720)
        window = main.GameWindow(123, 'test', 1280, 720)
        for stop in (False, True):
            with self.subTest(stop=stop):
                event = threading.Event()
                messages = []

                def send(hwnd, message, flags, coordinates):
                    messages.append(message)
                    if message == main.WM_LBUTTONDOWN and stop:
                        event.set()
                    return True

                with main.operation_context(event, main.Settings()), \
                     patch.object(main.WindowDriver, 'client_geometry', return_value=geometry), \
                     patch.object(main.USER32, 'PostMessageW', side_effect=send), \
                     patch.object(event, 'wait', wraps=event.wait) as wait:
                    main._operation.last_capture = (window.hwnd, geometry)
                    if stop:
                        with self.assertRaises(main.OperationCancelled):
                            main.WindowDriver.click_percent(window, 50, 50)
                    else:
                        self.assertTrue(main.WindowDriver.click_percent(window, 50, 50))
                    wait.assert_called_once_with(.08)
                self.assertEqual(messages, [main.WM_LBUTTONDOWN, main.WM_LBUTTONUP])


if __name__ == '__main__':
    unittest.main()
