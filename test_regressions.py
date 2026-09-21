"""Regression checks using fake windows: never send input to a real game."""
import asyncio
import queue
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main
from PIL import Image


def app_without_gui():
    app = object.__new__(main.BotApp)
    app.settings = main.Settings()
    app.stop_event = threading.Event()
    app.action_lock = threading.RLock()
    app.events = queue.Queue()
    app.worker = None
    app.inspection_worker = None
    app.calibration_dialog = None
    app.write = Mock()
    return app


class CancellationRegressions(unittest.TestCase):
    def test_fast_line_counts_all_units_in_three_verified_bursts(self):
        app=app_without_gui()
        app._wait=Mock()
        app._battle_capture=Mock(return_value=object())
        app._click=Mock(return_value=True)
        app.stable_troop_count=Mock(side_effect=[8,5,2,0])
        points=main.layout_points("ELECTRODRAGON_PERIMETER_POINTS")
        self.assertEqual(app.deploy_unit('window', 'Électro-dragon', (23,92), points, burst=True), 8)
        self.assertEqual(app.stable_troop_count.call_count, 4)
        # Initial selection, then a fresh selection and drop for each troop.
        self.assertEqual(app._click.call_count, 17)
        drops=[c.args[1:] for c in app._click.call_args_list][2::2]
        self.assertEqual(len(set(drops)),8)
        self.assertTrue(all(p in points for p in drops))
        self.assertLess(sum(c.args[0] for c in app._wait.call_args_list), .6)

    def test_fast_line_stops_when_burst_outcome_is_unknown(self):
        app=app_without_gui()
        app._wait=Mock()
        app._battle_capture=Mock(return_value=object())
        app._click=Mock(return_value=True)
        app.stable_troop_count=Mock(side_effect=[8,None])
        with self.assertRaisesRegex(RuntimeError, 'non confirmé'):
            app.deploy_unit('window','Électro-dragon',(23,92),[(18,40),(28,26),(38,13)],burst=True)
        self.assertEqual(app._click.call_count,7)

    def test_scaled_client_uses_known_burst_delta_when_ocr_reads_neighbor_card(self):
        app = app_without_gui()
        app._wait = Mock()
        app._battle_capture = Mock(return_value=object())
        app._click = Mock(return_value=True)
        app.stable_troop_count = Mock(side_effect=[8, 0, 5, 2, 0])
        window = type("ScaledWindow", (), {"width": 1412})()
        points = main.layout_points("ELECTRODRAGON_PERIMETER_POINTS")
        self.assertEqual(app.deploy_unit(window, "Ã‰lectro-dragon", (23, 92), points, burst=True), 8)
        self.assertTrue(any("OCR incohérent" in str(event) for event in app.events.queue))

    def test_wide_client_normalizes_impossible_neighbor_troop_count(self):
        app = app_without_gui()
        app._wait = Mock()
        app._battle_capture = Mock(return_value=object())
        app._click = Mock(return_value=True)
        app.stable_troop_count = Mock(side_effect=[80, 0])
        window = type("WideWindow", (), {"width": 1765})()
        self.assertEqual(app.deploy_unit(window, "Dragon", (23, 92), [(18, 40)], burst=True), 1)
        self.assertTrue(any("quantité configurée" in str(event) for event in app.events.queue))

    def test_dimmed_hero_is_not_confirmed_and_retry_reselects(self):
        app = app_without_gui()
        app._wait = Mock()
        app._battle_capture = Mock(return_value=object())
        app._click = Mock(return_value=True)
        with patch.object(app, "deploy_unit", return_value=0), \
             patch.object(main, "hero_layout_shift", return_value=0), \
             patch.object(main, "hero_health_visible", return_value=False), \
             patch.object(main, "hero_placeholder_slot", return_value=False), \
             patch.object(main, "hero_icon_saturation", side_effect=[100, 0, 0]):
            with self.assertRaisesRegex(RuntimeError, "non confirmée"):
                app.deploy_attack_composition(object())
        clicks = app._click.call_args_list
        perimeter = main.layout_points("ELECTRODRAGON_PERIMETER_POINTS")
        slot = main.layout_points("HERO_SLOTS")[0]
        self.assertEqual(len(clicks), len(perimeter) * 2)
        for i in range(len(perimeter)):
            self.assertEqual(clicks[i * 2].args[1:], slot)
        self.assertFalse(any("confirmé à" in str(e) for e in app.events.queue))

    def test_empty_hero_slot_is_skipped_after_available_heroes(self):
        app = app_without_gui()
        image = Image.new("RGB", (1920, 1080))
        with Image.open(Path(__file__).parent / "testdata" / "hero_empty_slot.png") as strip:
            image.paste(strip, (0, 880))
        app._battle_capture = Mock(return_value=image)
        app._click = Mock(return_value=True)
        with patch.object(app, "deploy_unit", return_value=0), \
             patch.object(main, "hero_layout_shift", return_value=-6.25), \
             patch.object(main, "hero_health_visible", side_effect=[True, True, False]):
            app.deploy_attack_composition(object())
        app._click.assert_not_called()
        self.assertTrue(any("case vide ignorée" in event for event in app.events.queue))

    def test_rejected_deployment_point_is_not_retried_for_next_troop(self):
        app = app_without_gui()
        app._wait = Mock()
        app._battle_capture = Mock(return_value=object())
        app._click = Mock(return_value=True)
        app.stable_troop_count = Mock(side_effect=[2, 2, 1, 0])
        window = object()
        self.assertEqual(app.deploy_unit(window, "Électro-dragon", (23, 92), [(10, 30), (20, 40)]), 2)
        self.assertEqual([call.args[1:] for call in app._click.call_args_list],
                         [(23, 92), (10, 30), (20, 40), (20, 40)])

    def test_transient_battle_reward_waits_without_input(self):
        app = app_without_gui()
        first, final = object(), object()
        app._capture = Mock(side_effect=[first, final])
        app._wait = Mock()
        app._click = Mock()
        with patch.object(main, "battle_reward_open", side_effect=[True, False]), \
             patch.object(main, "battle_result_return_ready", return_value=False), \
             patch.object(main, "battle_reward_choice", return_value=None):
            self.assertIs(app._battle_capture(object()), final)
        app._wait.assert_called_once_with(.15)
        app._click.assert_not_called()

    def test_stop_during_reward_wait_interrupts_before_any_click(self):
        app = app_without_gui()
        app._capture = Mock(return_value=object())
        app._wait = Mock(side_effect=main.OperationCancelled)
        with patch.object(main, "battle_reward_open", return_value=True), \
             patch.object(main, "battle_result_return_ready", return_value=False), \
             patch.object(main, "battle_reward_choice", return_value=None):
            with self.assertRaises(main.OperationCancelled):
                app._battle_capture(object())

    def test_stopped_composition_never_selects_or_places_a_hero(self):
        app = app_without_gui()
        app.stop_event.set()
        with patch.object(app, "deploy_unit", return_value=0), \
             patch.object(main.WindowDriver, "capture", return_value=Image.new("RGB",(1920,1080),(30,60,110))), \
             patch.object(main.WindowDriver, "click_percent", return_value=True) as click, \
             patch.object(main, "hero_layout_shift", return_value=0), \
             patch.object(main, "hero_health_visible", return_value=True):
            try:
                app.deploy_attack_composition(object())
            except RuntimeError:
                pass
        click.assert_not_called()
        self.assertFalse(any("Déploiement vérifié" in str(event) for event in app.events.queue))

    def test_stop_before_wall_confirmation_prevents_click(self):
        app = app_without_gui()
        app.stop_event.set()
        with patch.object(main.WindowDriver, "click_percent", return_value=True) as click:
            with self.assertRaises(main.OperationCancelled):
                app._wall_click(object(), main.WALL_MULTI_CONFIRM_BUTTON, "confirmation")
        click.assert_not_called()

    def test_stop_during_counter_read_prevents_selection(self):
        app = app_without_gui()
        def counter(*args):
            app.stop_event.set()
            return 2
        with patch.object(main.WindowDriver, "capture", return_value=Image.new("RGB",(1920,1080),(30,60,110))), \
             patch.object(main.WindowDriver, "click_percent", return_value=True) as click, \
             patch.object(main, "battle_reward_open", return_value=False), \
             patch.object(main, "read_troop_count", side_effect=counter):
            with self.assertRaises(main.OperationCancelled):
                app.deploy_unit(object(), "Électro-dragon", (23, 92), [(20, 40)])
        click.assert_not_called()

    def test_stop_after_hero_selection_prevents_drop_and_success(self):
        app = app_without_gui()
        clicks = []
        def send(*args):
            clicks.append(args)
            app.stop()
            return True
        with patch.object(app, "deploy_unit", return_value=0), \
             patch.object(main.WindowDriver, "capture", return_value=Image.new("RGB",(1920,1080),(30,60,110))), \
             patch.object(main.WindowDriver, "click_percent", side_effect=send), \
             patch.object(main, "battle_reward_open", return_value=False), \
             patch.object(main, "hero_layout_shift", return_value=0), \
             patch.object(main, "hero_health_visible", return_value=False), \
             patch.object(main, "hero_placeholder_slot", return_value=False), \
             patch.object(main, "hero_icon_saturation", return_value=100):
            with self.assertRaises(main.OperationCancelled):
                app.deploy_attack_composition(object())
        self.assertEqual(len(clicks), 1)
        self.assertFalse(any("Déploiement vérifié" in str(event) for event in app.events.queue))

    def test_stop_serializes_with_inflight_click(self):
        app = app_without_gui()
        entered, release = threading.Event(), threading.Event()
        def send(*args):
            entered.set()
            self.assertTrue(release.wait(2))
            return True
        with patch.object(main.WindowDriver, "click_percent", side_effect=send) as click:
            sender = threading.Thread(target=app._click, args=(object(), 20, 40))
            sender.start()
            self.assertTrue(entered.wait(2))
            stopper = threading.Thread(target=app.stop)
            stopper.start()
            release.set()
            sender.join(2); stopper.join(2)
            self.assertFalse(sender.is_alive() or stopper.is_alive())
            with self.assertRaises(main.OperationCancelled):
                app._click(object(), 20, 40)
        self.assertEqual(click.call_count, 1)


class GeometryRegressions(unittest.TestCase):
    def setUp(self):
        self.window = main.GameWindow(123, "Clash of Clans", 1920, 1080)
        self.geometry = main.ClientGeometry(1280, 720, 8, 31, 1296, 759)
        self.event = threading.Event()

    def test_zoom_uses_screen_coordinates_and_negative_wheel_delta(self):
        def translate(hwnd, point):
            self.assertEqual((point._obj.x, point._obj.y), (640, 360))
            point._obj.x = -100
            point._obj.y = 560
            return True
        with main.operation_context(self.event, main.Settings()), \
             patch.object(main.WindowDriver, "client_geometry", return_value=self.geometry), \
             patch.object(main.USER32, "ClientToScreen", side_effect=translate), \
             patch.object(main.USER32, "PostMessageW", return_value=True) as post:
            main._operation.last_capture = (self.window.hwnd, self.geometry)
            self.assertTrue(main.WindowDriver.zoom_out_step(self.window))
        post.assert_called_once_with(123, 0x020A, (0xFF88 << 16), (560 << 16) | (0xFFFF & -100))

    def test_zoom_rejects_geometry_changed_since_capture(self):
        with main.operation_context(self.event, main.Settings()), \
             patch.object(main.WindowDriver, "client_geometry", return_value=self.geometry), \
             patch.object(main.USER32, "PostMessageW") as post:
            with self.assertRaises(RuntimeError):
                main.WindowDriver.zoom_out_step(self.window)
        post.assert_not_called()

    def test_click_uses_current_client_size_not_old_window_size(self):
        with main.operation_context(self.event, main.Settings()), \
             patch.object(main.WindowDriver, "client_geometry", return_value=self.geometry), \
             patch.object(main.USER32, "PostMessageW", return_value=True) as post:
            main._operation.last_capture = (self.window.hwnd, self.geometry)
            self.assertTrue(main.WindowDriver.click_percent(self.window, 50, 50))
        self.assertEqual(post.call_args_list[0].args[-1], (360 << 16) | 640)
        self.assertEqual([call.args[1] for call in post.call_args_list], [main.WM_LBUTTONDOWN, main.WM_LBUTTONUP])

    def test_resize_since_capture_rejects_click(self):
        with main.operation_context(self.event, main.Settings()), \
             patch.object(main.WindowDriver, "client_geometry", return_value=self.geometry), \
             patch.object(main.USER32, "PostMessageW") as post:
            main._operation.last_capture = (self.window.hwnd, main.ClientGeometry(1920, 1080, 0, 0, 1920, 1080))
            with self.assertRaisesRegex(RuntimeError, "modifiée"):
                main.WindowDriver.click_percent(self.window, 50, 50)
        post.assert_not_called()

    def test_other_window_capture_cannot_authorize_click(self):
        with main.operation_context(self.event, main.Settings()), \
             patch.object(main.WindowDriver, "client_geometry", return_value=self.geometry), \
             patch.object(main.USER32, "PostMessageW") as post:
            main._operation.last_capture = (999, self.geometry)
            with self.assertRaises(RuntimeError):
                main.WindowDriver.click_percent(self.window, 50, 50)
        post.assert_not_called()

    def test_uncalibrated_aspect_ratio_rejects_click(self):
        geometry = main.ClientGeometry(1024, 768, 0, 0, 1024, 768)
        with main.operation_context(self.event, main.Settings()), \
             patch.object(main.WindowDriver, "client_geometry", return_value=geometry), \
             patch.object(main.USER32, "PostMessageW") as post:
            main._operation.last_capture = (self.window.hwnd, geometry)
            with self.assertRaisesRegex(RuntimeError, "Calibrer"):
                main.WindowDriver.click_percent(self.window, 50, 50)
        post.assert_not_called()

    def test_closed_selected_window_does_not_switch_account(self):
        other = main.GameWindow(456, "Clash of Clans - autre compte", 1920, 1080)
        with patch.object(main.WindowDriver, "list_windows", return_value=[other]):
            self.assertIsNone(main.WindowDriver.resolve("Clash of Clans - choisi"))


class DeploymentRegressions(unittest.TestCase):
    def test_zoom_precedes_deployment_on_every_chained_attack(self):
        app = app_without_gui()
        app.settings = main.replace(app.settings, upgrade_recommended=False)
        order = []
        app.collect_village_resources = Mock()
        app.upgrade_walls_to_reserve = Mock()
        app.open_search = Mock(return_value=True)
        app.find_suitable_base = Mock(return_value=True)
        app.prepare_attack = lambda w: order.append("zoom")
        app.deploy_attack_composition = lambda w: order.append("deploy")
        app.wait_for_battle_return = Mock(side_effect=[True, False])
        with patch.object(main.WindowDriver, "resolve", return_value=object()):
            app.farm_loop()
        self.assertEqual(order, ["zoom", "deploy", "zoom", "deploy"])

    def test_collection_icons_disappear_after_real_village_collection(self):
        captures = Path(__file__).parent / "testdata"
        with Image.open(captures / "suggested_menu.png") as before, \
             Image.open(captures / "wall_group_two_no_ten.png") as after:
            icons = main.find_collectible_icons(before)
            self.assertEqual(len(icons), 12)
            self.assertEqual({kind for kind, *_ in icons}, {"gold", "elixir"})
            self.assertEqual(main.find_collectible_icons(after), [])
            self.assertFalse(main.collectible_icon_still_visible(after, "gold", 612, 322))

    def test_collection_does_not_click_through_builder_menu(self):
        app = app_without_gui()
        with Image.open(Path(__file__).parent / "testdata" / "suggested_menu.png") as image:
            app._capture = Mock(return_value=image)
            app._click = Mock()
            self.assertEqual(app.collect_village_resources(object()), 0)
            app._click.assert_not_called()

    def test_stop_interrupts_zoom_before_another_wheel_message(self):
        app = app_without_gui()
        app._capture = Mock()
        def wheel(w):
            app.stop_event.set()
            return True
        with patch.object(main.WindowDriver, "zoom_out_step", side_effect=wheel) as send:
            with self.assertRaises(main.OperationCancelled):
                app.prepare_attack(object())
        self.assertEqual(send.call_count, 1)

    def test_reward_clicked_once_and_confirmed_only_after_overlay_closes(self):
        app = app_without_gui()
        app._capture = Mock(return_value=object())
        app._wait = Mock()
        app._click = Mock(return_value=True)
        with patch.object(main, "battle_reward_open", side_effect=[True, True, False]), \
             patch.object(main, "battle_result_return_ready", return_value=False), \
             patch.object(main, "battle_reward_choice", return_value=((70, 53), "Or")) as choose:
            app._battle_capture(object())
        self.assertEqual(app._click.call_count, 1)
        self.assertEqual(choose.call_count, 1)
        self.assertTrue(any("fermeture du choix confirmée" in m for m in app.events.queue))

    def test_result_screen_ends_reward_wait_without_another_click(self):
        app = app_without_gui()
        image = Image.new("RGB", (1920, 1080))
        with Image.open(Path(__file__).parent / "testdata" / "battle_result_rentrer.png") as strip:
            image.paste(strip, (700, 780))
        app._capture = Mock(return_value=image)
        app._click = Mock()
        with patch.object(main, "battle_reward_open", return_value=True), \
             patch.object(main, "battle_reward_choice") as choice:
            self.assertIs(app._battle_capture(object()), image)
        choice.assert_not_called()
        app._click.assert_not_called()

    def test_unselectable_reward_can_wait_for_result_after_deployment(self):
        app = app_without_gui()
        frame = object()
        app._capture = Mock(return_value=frame)
        app._click = Mock()
        app._wait = Mock()
        with patch.object(main, "battle_reward_open", return_value=True), \
             patch.object(main, "battle_result_return_ready", return_value=False), \
             patch.object(main, "battle_reward_choice", return_value=None):
            self.assertIs(app._battle_capture(object(), allow_unselected_reward=True), frame)
        app._click.assert_not_called()
        app._wait.assert_not_called()

    def test_result_wait_survives_unselectable_reward(self):
        app = app_without_gui()
        app._battle_capture = Mock(side_effect=[object(), object(), object()])
        app._click = Mock(return_value=True)
        app._wait = Mock()
        app.record_battle_earnings = Mock()
        with patch.object(main, "battle_reward_open", return_value=False), \
             patch.object(main, "village_home_ready", side_effect=[False, False, True]), \
             patch.object(main, "battle_result_return_ready", side_effect=[False, True]), \
             patch.object(main, "has_screen_text", return_value=False):
            self.assertTrue(app.wait_for_battle_return(object()))
        self.assertEqual(app._battle_capture.call_count, 3)
        self.assertTrue(all(call.kwargs == {"allow_unselected_reward": True}
                            for call in app._battle_capture.call_args_list))
        app.record_battle_earnings.assert_called_once()
        app._click.assert_called_once()

    def test_victory_behind_reward_does_not_trigger_result_or_return_click(self):
        app = app_without_gui()
        frame = Image.new('RGB', (1920, 1080))
        app._battle_capture = Mock(side_effect=[frame, frame, frame])
        app._click = Mock(return_value=True)
        app._wait = Mock()
        app.record_battle_earnings = Mock()
        with patch.object(main, 'battle_reward_open', side_effect=[True, False, False]), \
                patch.object(main, 'village_home_ready', side_effect=[False, True]), \
                patch.object(main, 'battle_result_return_ready', return_value=True):
            self.assertTrue(app.wait_for_battle_return(object()))
        app.record_battle_earnings.assert_called_once()
        app._click.assert_called_once()
        self.assertEqual(app._battle_capture.call_count, 3)

    def test_reward_checked_while_waiting_after_deployment(self):
        app = app_without_gui()
        app._battle_capture = Mock(return_value=object())
        with patch.object(main, "village_home_ready", return_value=True):
            self.assertTrue(app.wait_for_battle_return(object()))
        app._battle_capture.assert_called_once()

    def test_unreadable_counter_never_becomes_a_guessed_decrement(self):
        app = app_without_gui()
        app._wait = Mock()
        with patch.object(app, "stable_troop_count", side_effect=[2, None]), \
             patch.object(main.WindowDriver, "capture", return_value=Image.new("RGB",(1920,1080),(30,60,110))), \
             patch.object(main.WindowDriver, "click_percent", return_value=True) as click, \
             patch.object(main, "battle_reward_open", return_value=False), \
             patch.object(main, "troop_counter_visually_changed", return_value=True) as visual:
            with self.assertRaisesRegex(RuntimeError, "non confirmé"):
                app.deploy_unit(object(), "Électro-dragon", (23, 92), [(20, 40), (30, 30)])
        self.assertEqual(click.call_count, 2)  # select + one attempted drop, never a retry
        visual.assert_not_called()
        self.assertFalse(any("confirmé à" in str(event) for event in app.events.queue))

    def test_one_click_cannot_confirm_several_troops(self):
        app = app_without_gui()
        app._wait = Mock()
        with patch.object(app, "stable_troop_count", side_effect=[8, 2]), \
             patch.object(main.WindowDriver, "capture", return_value=Image.new("RGB",(1920,1080),(30,60,110))), \
             patch.object(main.WindowDriver, "click_percent", return_value=True), \
             patch.object(main, "battle_reward_open", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "un seul clic"):
                app.deploy_unit(object(), "Électro-dragon", (23, 92), [(20, 40)])
        self.assertFalse(any("confirmé à" in str(event) for event in app.events.queue))

    def test_counter_requires_two_consecutive_agreeing_frames(self):
        app = app_without_gui()
        app._wait = Mock()
        with patch.object(main.WindowDriver, "capture", return_value=Image.new("RGB",(1920,1080),(30,60,110))), \
             patch.object(main, "battle_reward_open", return_value=False), \
             patch.object(main, "read_troop_count", side_effect=[1, None, 2, 2]) as read:
            self.assertEqual(app.stable_troop_count(object(), "Dragon"), 2)
        self.assertEqual(read.call_count, 4)

    def test_blank_card_is_unknown_not_zero_troops(self):
        self.assertIsNone(main.read_troop_count(Image.new("RGB", (1920, 1080)), "Dragon"))


class DeadlineRegressions(unittest.TestCase):
    def test_one_readable_resource_can_satisfy_or_rule(self):
        for gold,elixir in ((900000,None),(None,900000)):
            app=app_without_gui(); app.settings.use_and_rule=False
            app._capture=Mock(return_value=Image.new("RGB",(1920,1080)))
            app._click=Mock()
            with patch.object(main,'enemy_loot_screen_ready',return_value=True), patch.object(main,'read_enemy_loot',return_value=main.EnemyLoot(gold,elixir,None,{})):
                self.assertTrue(app.find_suitable_base('window'))
            app._click.assert_not_called()

    def test_unreadable_base_with_next_button_is_skipped_then_attack_resumes(self):
        app=app_without_gui(); app.settings.use_and_rule=True
        clock=[0.]
        app._wait=lambda seconds:clock.__setitem__(0,clock[0]+seconds)
        frame=Image.new("RGB",(1920,1080))
        app._capture=Mock(return_value=frame);app._click=Mock(return_value=True)
        readings=[main.EnemyLoot(None,900000,None,{})]*35+[main.EnemyLoot(900000,900000,0,{})]
        with tempfile.TemporaryDirectory() as directory, patch.object(main,'APP_DIR',Path(directory)), patch.object(main.time,'monotonic',side_effect=lambda:clock[0]), patch.object(main,'enemy_loot_screen_ready',return_value=True), patch.object(main,'has_screen_text',return_value=True), patch.object(main,'read_enemy_loot',side_effect=readings):
            self.assertTrue(app.find_suitable_base('window'))
            self.assertEqual(len(list((Path(directory)/'unread-enemies').glob('*.png'))),1)
        app._click.assert_called_once_with('window',*main.NEXT_BASE_BUTTON)

    def test_visible_but_unreadable_loot_expires_without_clicks(self):
        app = app_without_gui()
        clock = [0.0]
        app._wait = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
        with patch.object(main.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(main.WindowDriver, "capture", return_value=Image.new("RGB",(1920,1080),(30,60,110))), \
             patch.object(main.WindowDriver, "click_percent") as click, \
             patch.object(main, "enemy_loot_screen_ready", return_value=True), \
             patch.object(main, "read_enemy_loot", return_value=main.EnemyLoot(None, None, None, {})):
            with self.assertRaises(TimeoutError):
                app.find_suitable_base(object())
        self.assertEqual(clock[0], main.BASE_READ_TIMEOUT)
        click.assert_not_called()

    def test_new_base_gets_its_own_read_budget(self):
        app = app_without_gui()
        clock = [0.0]
        app._wait = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
        readings = [main.EnemyLoot(None, None, None, {})] * 34 + [main.EnemyLoot(1, 1, 1, {}), main.EnemyLoot(900000, 900000, 0, {})]
        with patch.object(main.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(main.WindowDriver, "capture", return_value=Image.new("RGB",(1920,1080),(30,60,110))), \
             patch.object(main.WindowDriver, "click_percent", return_value=True) as click, \
             patch.object(main, "enemy_loot_screen_ready", return_value=True), \
             patch.object(main, "read_enemy_loot", side_effect=readings):
            self.assertTrue(app.find_suitable_base(object()))
        self.assertGreater(clock[0], main.BASE_READ_TIMEOUT)
        self.assertEqual(click.call_count, 1)

    def test_ocr_timeout_cancels_pending_work(self):
        finished = []
        async def hang():
            try:
                await asyncio.sleep(10)
            finally:
                finished.append(True)
        with patch.object(main, "OCR_TIMEOUT", .02):
            with self.assertRaises(TimeoutError):
                asyncio.run(main.bounded_ocr(hang()))
        self.assertEqual(finished, [True])

    def test_stop_cancels_ocr_before_its_timeout(self):
        event = threading.Event()
        async def hang():
            event.set()
            await asyncio.sleep(10)
        with main.operation_context(event, main.Settings()):
            with self.assertRaises(main.OperationCancelled):
                asyncio.run(main.bounded_ocr(hang()))


class InspectionRegressions(unittest.TestCase):
    def test_ocr_does_not_block_ui_thread_and_can_be_stopped(self):
        app = app_without_gui()
        app.window_title = SimpleNamespace(get=lambda: "Clash of Clans")
        app.run_state = SimpleNamespace(set=Mock())
        entered = threading.Event()
        ui_thread = threading.get_ident()
        worker_threads = []
        def reader(window):
            worker_threads.append(threading.get_ident())
            entered.set()
            if not app.stop_event.wait(2):
                raise AssertionError("Inspection non interrompue")
        with patch.object(main.WindowDriver, "resolve", return_value=object()):
            app._start_inspection(reader)
            self.assertTrue(entered.wait(2))
            self.assertTrue(app.inspection_worker.is_alive())
            app.stop()
            app.inspection_worker.join(2)
        self.assertFalse(app.inspection_worker.is_alive())
        self.assertNotEqual(worker_threads, [ui_thread])

    def test_inspection_is_not_started_during_farming(self):
        app = app_without_gui()
        app.worker = SimpleNamespace(is_alive=lambda: True)
        with patch.object(threading, "Thread") as spawn:
            app._start_inspection(Mock())
        spawn.assert_not_called()


class CalibrationRegressions(unittest.TestCase):
    def test_custom_points_regions_and_perimeter_are_used(self):
        settings = main.Settings(layout_overrides={
            "ELECTRODRAGON_SLOT": [40, 90], "TROOP_COUNT_ROIS.Dragon": [50, 80, 55, 85],
            "ELECTRODRAGON_PERIMETER_POINTS.0": [12, 45],
        })
        main.validate_layout(settings)
        with main.operation_context(threading.Event(), settings):
            self.assertEqual(main.layout_values("ELECTRODRAGON_SLOT"), (40, 90))
            self.assertEqual(main.layout_roi("TROOP_COUNT_ROIS", "Dragon"), main.Roi(50, 80, 55, 85))
            self.assertEqual(main.layout_points("ELECTRODRAGON_PERIMETER_POINTS")[0], (12, 45))
        self.assertEqual(main.layout_values("ELECTRODRAGON_SLOT"), main.ELECTRODRAGON_SLOT)

    def test_invalid_calibration_is_rejected(self):
        for overrides in ({"unknown": [1, 2]}, {"DRAGON_SLOT": [float("nan"), 10]},
                          {"TROOP_COUNT_ROIS.Dragon": [20, 90, 10, 85]}, {"DRAGON_SLOT": [-1, 20]}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                main.validate_layout(main.Settings(layout_overrides=overrides))

    def test_calibration_survives_save_load_without_erasing_farm_settings(self):
        settings = main.Settings(min_gold=750000, dry_run=True, layout_overrides={"DRAGON_SLOT": [30, 92]}, layout_aspect_ratio=4/3)
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(main, "APP_DIR", Path(directory)), \
             patch.object(main, "CONFIG_PATH", Path(directory) / "config.json"):
            main.save_settings(settings)
            loaded = main.load_settings()
        self.assertEqual(loaded, settings)

    def test_enemy_loot_reads_calibrated_crops(self):
        settings = main.Settings(layout_overrides={"ENEMY_LOOT_ROIS.gold": [0, 0, 10, 10]})
        image = Image.new("RGB", (1000, 500))
        with main.operation_context(threading.Event(), settings), \
             patch.object(main, "read_resource_number", return_value=(123, "123")) as read:
            main.read_enemy_loot(image)
        self.assertEqual(read.call_args_list[0].args[0].size, (100, 50))

    def test_labels_are_unique_and_cover_every_target(self):
        labels = main.layout_labels()
        self.assertEqual(set(labels), set(main.LAYOUT_DEFAULTS))
        self.assertEqual(len(set(labels.values())), len(labels))


if __name__ == "__main__":
    unittest.main()


class ConnectionRegressions(unittest.TestCase):
    def test_real_connection_dialog_returns_only_retry_button(self):
        with Image.open(Path(__file__).parent/'testdata/connection_lost.png') as image:
            point=main.connection_retry_point(image)
            self.assertAlmostEqual(point[0],32.7,delta=.2)
            self.assertAlmostEqual(point[1],56.1,delta=.2)
        self.assertIsNone(main.connection_retry_point(Image.new('RGB',(1920,1080),'white')))

    def test_inactivity_dialog_blocks_village_and_offers_reload(self):
        with Image.open(Path(__file__).parent/'testdata/inactive_dialog.png') as image:
            self.assertEqual(main.connection_retry_point(image),(35,56.2))
            self.assertFalse(main.village_home_ready(image))

    def test_connection_unwinds_action_before_restart(self):
        app=app_without_gui()
        app.reconnect_game=Mock()
        completed=[]
        def action():
            app._capture(object())
            completed.append('fresh action')
        with patch.object(main.WindowDriver,'capture',return_value=Image.new('RGB',(1920,1080))),patch.object(main,'connection_retry_point',side_effect=[(32,56),None]):
            app._run_operation(action)
        app.reconnect_game.assert_called_once()
        self.assertEqual(completed,['fresh action'])

    def test_stop_prevents_reconnect_click(self):
        app=app_without_gui()
        app.stop_event.set()
        app._click=Mock()
        app.reconnect_game()
        app._click.assert_not_called()


class DiagnosticLogRegressions(unittest.TestCase):
    def test_unreadable_final_reward_screen_is_in_diagnostic_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = main.DiagnosticJournal(root / 'bot.log')
            run = journal.start_run('combat', main.Settings())
            screenshot = journal.save_reward_screen(Image.new('RGB', (20, 20), 'blue'))
            bundle = root / 'diagnostic.zip'
            journal.export_bundle(bundle)
            journal.close()
            with zipfile.ZipFile(bundle) as archive:
                self.assertEqual(set(archive.namelist()), {run.name, screenshot.name})
                self.assertIn('Capture du choix final non reconnu', archive.read(run.name).decode('utf-8'))

    def test_each_action_has_an_exportable_log_and_error_screen(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = main.DiagnosticJournal(root/'bot.log')
            first = journal.start_run('remparts', main.Settings())
            journal.record('OCR', 'ligne Rempart x203, coût 600000 élixir')
            journal.record('ERREUR', 'confirmation illisible')
            Image.new('RGB',(10,10),'red').save(first.with_suffix('.png'))
            journal.end_run('terminée')
            bundle = root/'diagnostic.zip'
            journal.export_bundle(bundle)
            second = journal.start_run('bâtiments', main.Settings())
            journal.record('ÉTAPE', 'ouvrier réservé')
            journal.end_run('terminée')
            journal.close()
            self.assertNotEqual(first,second)
            with zipfile.ZipFile(bundle) as archive:
                self.assertEqual(set(archive.namelist()),{first.name,first.with_suffix('.png').name})
                text = archive.read(first.name).decode('utf-8')
            self.assertIn('Rempart x203',text)
            self.assertIn('Statut=erreur',text)
            self.assertNotIn('ouvrier réservé',text)
            self.assertIn('ouvrier réservé',(root/'bot.log').read_text(encoding='utf-8'))
