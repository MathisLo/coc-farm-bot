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
from PIL import Image, ImageDraw


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
    def test_rage_counter_accepts_matching_readings_across_blank_frames(self):
        app = app_without_gui()
        app._battle_capture = Mock(return_value=Image.new('RGB', (1323, 744)))
        app._wait = Mock()
        app._trace = Mock()
        with patch.object(main, 'read_rage_count', side_effect=[1, None, 1, None]):
            self.assertEqual(app.stable_rage_count(object(), 22), 1)

    def test_compact_rage_x1_badge_is_read_left_of_detected_card_center(self):
        image = Image.new('RGB', (1323, 744))
        with Image.open(Path(__file__).parent / 'testdata' / 'vps_rage_x1_badge_1323.png') as badge:
            image.paste(badge, (705, 625))
        self.assertEqual(main.read_rage_count(image, 57.6), 1)

    def test_waiting_army_screen_is_exported_with_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = main.DiagnosticJournal(Path(directory) / 'bot.log')
            journal.start_run('army probe')
            app = app_without_gui()
            app.journal = journal
            app._capture = Mock(return_value=Image.new('RGB', (1920, 1080)))
            app._wait = Mock(side_effect=lambda _: app.stop_event.set())
            with patch.object(main, 'army_readiness', return_value=(False, 'Rage 0 / 5', {})):
                self.assertFalse(app.wait_for_army_ready(object()))
            screenshot = journal.run_path.with_name(f'{journal.run_path.stem}-army.png')
            self.assertTrue(screenshot.exists())
            journal.end_run('arrêtée')
            bundle = Path(directory) / 'diagnostic.zip'
            journal.export_bundle(bundle)
            with zipfile.ZipFile(bundle) as archive:
                self.assertIn(screenshot.name, archive.namelist())
            journal.close()

    def test_full_260_space_army_uses_capacity_limited_electrodragon_target(self):
        image = Image.new('RGB', (1920, 1080))
        settings = main.replace(main.Settings(), electrodragon_count=10, dragon_count=1)
        for spell_count, expected_ready in ((10, True), (0, False)):
            with self.subTest(spell_count=spell_count), \
                 patch.object(main, 'army_fraction', side_effect=[(260, 260), (4, 4), (spell_count, 11)]), \
                 patch.object(main, 'troop_card_kind', side_effect=['electrodragon', 'dragon'] + [None] * 5), \
                 patch.object(main, 'army_card_count', side_effect=[8, 1, 5]), \
                 patch.object(main, 'rage_card_score', return_value=.5):
                ready, detail, observed = main.army_readiness(image, settings)
            self.assertEqual(ready, expected_ready, detail)
            self.assertEqual(observed['electrodragon'], 8)
            if not ready:
                self.assertIn('Rage', detail)

    def test_army_fraction_recovers_zero_rendered_as_t_or_c(self):
        image = Image.new('RGB', (1920, 1080))
        with patch.object(main, 'read_text', side_effect=['260/26t', '260/26c']):
            self.assertEqual(main.army_fraction(image, main.Roi(44, 22, 51, 28)), (260, 260))
            self.assertEqual(main.army_fraction(image, main.Roi(44, 22, 51, 28)), (260, 260))

    def test_temporary_x40_card_is_detected_only_while_visible(self):
        captures = Path(__file__).parent / 'testdata'
        with Image.open(captures / 'event_extra_troop_x40_1323.png') as event:
            self.assertEqual(main.event_extra_troop_card(event), (17.0, 40))
            self.assertEqual(main.read_event_extra_troop_count(event, 17.0), 40)
        with Image.open(captures / 'event_extra_troop_x37_1323.png') as partial:
            self.assertEqual(main.read_event_extra_troop_count(partial, 17.0), 37)
        with Image.open(captures / 'event_extra_troop_x25_1323.png') as partial:
            self.assertEqual(main.read_event_extra_troop_count(partial, 17.0), 25)
            self.assertEqual(main.read_event_extra_troop_count(partial, 17.0, 25, 28), 25)
        with Image.open(captures / 'event_extra_troop_x35_shifted_1323.png') as shifted:
            self.assertEqual(main.event_extra_troop_card(shifted), (29.4, 35))
            self.assertEqual(main.read_event_extra_troop_count(shifted, 29.4, 35, 40), 35)
            for size in ((1387, 780), (1920, 1080), (2560, 1440)):
                self.assertEqual(main.event_extra_troop_card(shifted.resize(size)), (29.4, 35))
        with Image.open(captures / 'live_compact_battle_bar.png') as regular:
            self.assertIsNone(main.event_extra_troop_card(regular))

    def test_event_x40_can_be_found_without_red_icon_on_pc_sized_bar(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'event_extra_troop_x40_1323.png') as source:
            image = source.resize((1920, 1080))
        ImageDraw.Draw(image).rectangle((int(image.width * .148), int(image.height * .90),
                                         int(image.width * .192), int(image.height * .96)),
                                        fill=(25, 70, 175))
        self.assertLess(main.event_extra_troop_red_score(image, 17.0), .15)
        self.assertEqual(main.event_extra_troop_card(image), (17.0, 40))
        app = app_without_gui()
        gray = image.convert('L').convert('RGB')
        app._click = Mock(return_value=True)
        app._wait = Mock()
        app.stable_event_extra_count = Mock(side_effect=list(range(35, 0, -5)) + [0, 0])
        app._battle_capture = Mock(side_effect=lambda _: gray if app.stable_event_extra_count.call_count >= 9 else image)
        self.assertEqual(app.deploy_event_extra_troops(object(), (28.7, 25.6)), 40)
        self.assertEqual(app._click.call_count, 80)

    def test_missing_event_card_saves_battle_bar_in_diagnostic_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = main.DiagnosticJournal(Path(directory) / 'bot.log')
            app = app_without_gui()
            app.journal = journal
            with Image.open(Path(__file__).parent / 'testdata' / 'live_compact_battle_bar.png') as image:
                app._battle_capture = Mock(return_value=image)
                journal.start_run('event probe')
                screenshot = journal.run_path.with_suffix('.png')
                self.assertEqual(app.deploy_event_extra_troops(object(), (28.7, 25.6)), 0)
                self.assertTrue(screenshot.exists())
                with Image.open(screenshot) as saved:
                    self.assertLess(saved.height, image.height / 3)
            journal.end_run('terminée')
            destination = Path(directory) / 'diagnostic.zip'
            journal.export_bundle(destination)
            with zipfile.ZipFile(destination) as archive:
                self.assertIn(screenshot.name, archive.namelist())
            journal.close()

    def test_all_forty_temporary_troops_are_deployed_and_verified(self):
        app = app_without_gui()
        with Image.open(Path(__file__).parent / 'testdata' / 'event_extra_troop_x40_1323.png') as image:
            gray = image.convert('L').convert('RGB')
            app._click = Mock(return_value=True)
            app._wait = Mock()
            app.stable_event_extra_count = Mock(side_effect=list(range(35, 0, -5)) + [0, 0])
            app._battle_capture = Mock(side_effect=lambda _: gray if app.stable_event_extra_count.call_count >= 9 else image)
            self.assertEqual(app.deploy_event_extra_troops(object(), (28.7, 25.6)), 40)
        self.assertEqual(app._click.call_count, 80)
        self.assertTrue(any("Renfort d'événement vérifié : 40" in event for event in app.events.queue))

    def test_temporary_troops_continue_when_last_single_digit_counts_are_unreadable(self):
        app = app_without_gui()
        with Image.open(Path(__file__).parent / 'testdata' / 'event_extra_troop_x40_1323.png') as image:
            gray = image.convert('L').convert('RGB')
            app._click = Mock(return_value=True)
            app._wait = Mock()
            app.stable_event_extra_count = Mock(side_effect=list(range(35, 9, -5)) + [None, None, 0])
            app._battle_capture = Mock(side_effect=lambda _: gray if app.stable_event_extra_count.call_count >= 9 else image)
            self.assertEqual(app.deploy_event_extra_troops(object(), (28.7, 25.6)), 40)
        self.assertEqual(app._click.call_count, 80)
        self.assertTrue(any('estimé(s)' in event for event in app.events.queue))

    def test_victory_is_not_mistaken_for_empty_temporary_card(self):
        app = app_without_gui()
        with Image.open(Path(__file__).parent / 'testdata' / 'event_extra_troop_x40_1323.png') as image:
            app._battle_capture = Mock(return_value=image)
            app._click = Mock(return_value=True)
            app._wait = Mock()
            app.stable_event_extra_count = Mock(side_effect=list(range(35, 0, -5)) + [0, 0])
            with patch.object(main, 'battle_result_return_ready', return_value=True):
                with self.assertRaises(main.BattleEndedEarly):
                    app.deploy_event_extra_troops(object(), (28.7, 25.6))
        self.assertFalse(any('vérifié : 40' in event for event in app.events.queue))

    def test_battle_x10_misread_as_x1_uses_prebattle_army_count(self):
        app = app_without_gui()
        app.settings = main.replace(app.settings, electrodragon_count=10)
        app._army_preview_counts = {"electrodragon": 10}
        app._wait = Mock()
        app._battle_capture = Mock(return_value=object())
        app._click = Mock(return_value=True)
        app.stable_troop_count = Mock(side_effect=[1, 7, 4, 1, 0])
        points = main.layout_points("ELECTRODRAGON_PERIMETER_POINTS")
        self.assertEqual(app.deploy_unit(object(), main.ELECTRODRAGON_LABEL,
                                         main.ELECTRODRAGON_SLOT, points, burst=True), 10)
        self.assertEqual(len(app._troop_drop_points), 10)

    def test_delayed_first_electro_counter_accepts_two_confirmed_drops(self):
        app = app_without_gui()
        app._troop_drop_points = []
        app._battle_capture = Mock(return_value=Image.new('RGB', (1323, 744)))
        app._click = Mock(return_value=True)
        app._wait = Mock()
        app.stable_troop_count = Mock(side_effect=[10, 8, 8, 7, 6, 5, 4, 3, 2, 1, 0])
        points = main.layout_points('ELECTRODRAGON_PERIMETER_POINTS')
        with patch.object(main, 'battle_hud_visible', return_value=True):
            self.assertEqual(app._deploy_compact_electro(object(), main.ELECTRODRAGON_SLOT,
                                                          points, 10, 0), 10)
        self.assertEqual(app._click.call_count, 20)
        self.assertTrue(any('2 poses cumulées confirmées' in event for event in app.events.queue))

    def test_full_hd_live_client_continues_when_mid_burst_counter_is_unreadable(self):
        image = Image.new('RGB', (1920, 1080), (80, 80, 80))
        draw = ImageDraw.Draw(image)
        for y in range(0, image.height, 20):
            draw.rectangle((0, y, image.width, y + 9), fill=(180, 180, 180))
        app = app_without_gui()
        app.settings = main.replace(app.settings, electrodragon_count=10)
        app._wait = Mock()
        app._battle_capture = Mock(return_value=image)
        app._click = Mock(return_value=True)
        app.stable_troop_count = Mock(side_effect=[10, None, None, None, None])
        points = main.layout_points('ELECTRODRAGON_PERIMETER_POINTS')
        with patch.object(main, 'troop_slot_offset', return_value=0), \
                patch.object(main, 'battle_hud_visible', return_value=True):
            self.assertEqual(app.deploy_unit(SimpleNamespace(width=1920), main.ELECTRODRAGON_LABEL,
                                             main.ELECTRODRAGON_SLOT, points, burst=True), 10)
        self.assertEqual(app._click.call_count, 21)
        self.assertTrue(any('compteur OCR incohérent' in event for event in app.events.queue))

    def test_blue_expanded_hero_card_does_not_require_skin_tones(self):
        image = Image.new('RGB', (1323, 744))
        with patch.object(main, 'hero_card_present', return_value=True), \
                patch.object(main, 'hero_icon_saturation', side_effect=[75, 140]), \
                patch.object(main, 'rage_card_score', return_value=0):
            self.assertEqual(main.hero_layout_shift(image), 0.0)

    def test_impossible_battle_count_uses_army_preview_not_old_setting(self):
        app = app_without_gui()
        app._army_preview_counts = {"electrodragon": 10}
        app._wait = Mock()
        app._battle_capture = Mock(return_value=object())
        app._click = Mock(return_value=True)
        app.stable_troop_count = Mock(side_effect=[80, 7, 4, 1, 0])
        points = main.layout_points("ELECTRODRAGON_PERIMETER_POINTS")
        self.assertEqual(app.deploy_unit(object(), main.ELECTRODRAGON_LABEL,
                                         main.ELECTRODRAGON_SLOT, points, burst=True), 10)

    def test_dragon_neighbor_badge_cannot_exceed_prepared_army(self):
        app = app_without_gui()
        app._army_preview_counts = {'dragon': 1}
        app._battle_capture = Mock(return_value=object())
        app._click = Mock(return_value=True)
        app._wait = Mock()
        app.stable_troop_count = Mock(side_effect=[8, 0])
        self.assertEqual(app.deploy_unit(object(), 'Dragon', main.DRAGON_SLOT,
                                         [(28.7, 25.6)], burst=True), 1)
        self.assertTrue(any('supérieur à l\'armée préparée x1' in event for event in app.events.queue))

    def test_dragon_neighbor_badge_uses_setting_when_preview_is_unreadable(self):
        app = app_without_gui()
        app._army_preview_counts = {'dragon': None}
        app._battle_capture = Mock(return_value=object())
        app._click = Mock(return_value=True)
        app._wait = Mock()
        app.stable_troop_count = Mock(side_effect=[8, 0])
        self.assertEqual(app.deploy_unit(object(), 'Dragon', main.DRAGON_SLOT,
                                         [(28.7, 25.6)], burst=True), 1)
        self.assertTrue(any('issue de configuration' in event for event in app.events.queue))

    def test_live_card_x1_after_ten_clicks_requires_another_drop(self):
        image = Image.new("RGB", (1765, 993))
        with Image.open(Path(__file__).parent / "testdata" / "residual_electro_x1.png") as crop:
            image.paste(crop, (240, 820))
        self.assertEqual(main.read_troop_count(image, main.ELECTRODRAGON_LABEL, -6.2), 1)
        app = app_without_gui()
        app.settings = main.replace(app.settings, electrodragon_count=10)
        app._army_preview_counts = {"electrodragon": 10}
        app._wait = Mock()
        empty = image.copy()
        empty.paste(image.crop((240, 820, 610, 993)).convert("L").convert("RGB"), (240, 820))
        app._click = Mock(return_value=True)
        app._battle_capture = Mock(side_effect=lambda _: empty if app._click.call_count >= 23 else image)
        app.stable_troop_count = Mock(side_effect=[80, 7, 4, 1, 0])
        window = SimpleNamespace(width=1765)
        points = main.layout_points("ELECTRODRAGON_PERIMETER_POINTS")
        with patch.object(main, "battle_hud_visible", return_value=True):
            self.assertEqual(app.deploy_unit(window, main.ELECTRODRAGON_LABEL,
                                             main.ELECTRODRAGON_SLOT, points, burst=True), 10)
        self.assertEqual(app._click.call_count, 23)
        self.assertTrue(any("pose résiduelle" in event for event in app.events.queue))

    def test_live_x2_misread_as_21_requires_two_residual_drops(self):
        image = Image.new("RGB", (1765, 993))
        with Image.open(Path(__file__).parent / "testdata" / "residual_electro_x2.png") as crop:
            image.paste(crop, (240, 820))
        self.assertEqual(main.read_troop_count(image, main.ELECTRODRAGON_LABEL, -6.2), 21)
        empty = image.convert("L").convert("RGB")
        app = app_without_gui()
        app.settings = main.replace(app.settings, electrodragon_count=10)
        app._army_preview_counts = {"electrodragon": 10}
        app._wait = Mock()
        app._click = Mock(return_value=True)
        app._battle_capture = Mock(side_effect=lambda _: empty if app._click.call_count >= 25 else image)
        app.stable_troop_count = Mock(side_effect=[80, 7, 4, 1, 0])
        with patch.object(main, "battle_hud_visible", return_value=True):
            self.assertEqual(app.deploy_unit(SimpleNamespace(width=1765), main.ELECTRODRAGON_LABEL,
                                             main.ELECTRODRAGON_SLOT,
                                             main.layout_points("ELECTRODRAGON_PERIMETER_POINTS"), burst=True), 10)
        self.assertEqual(app._click.call_count, 25)

    def test_live_card_that_never_empties_stops_residual_clicks(self):
        image = Image.new("RGB", (1765, 993))
        with Image.open(Path(__file__).parent / "testdata" / "residual_electro_x1.png") as crop:
            image.paste(crop, (240, 820))
        app = app_without_gui()
        app.settings = main.replace(app.settings, electrodragon_count=10)
        app._army_preview_counts = {"electrodragon": 10}
        app._wait = Mock()
        app._battle_capture = Mock(return_value=image)
        app._click = Mock(return_value=True)
        app.stable_troop_count = Mock(side_effect=[80, 7, 4, 1, 0])
        with patch.object(main, "battle_hud_visible", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "toujours active"):
                app.deploy_unit(SimpleNamespace(width=1765), main.ELECTRODRAGON_LABEL,
                                main.ELECTRODRAGON_SLOT,
                                main.layout_points("ELECTRODRAGON_PERIMETER_POINTS"), burst=True)
        self.assertEqual(app._click.call_count, 45)

    def test_rejected_perimeter_retries_on_outer_line(self):
        app = app_without_gui()
        app.settings = main.replace(app.settings, electrodragon_count=1)
        app._wait = Mock()
        app._battle_capture = Mock(return_value=object())
        app._click = Mock(return_value=True)
        app.stable_troop_count = Mock(side_effect=[1, 1, 1, 0])
        points = [(18.0, 40.0), (26.0, 30.0)]
        self.assertEqual(app.deploy_unit(object(), main.ELECTRODRAGON_LABEL,
                                         main.ELECTRODRAGON_SLOT, points, burst=True), 1)
        drops = [call.args[1:] for call in app._click.call_args_list][2::2]
        self.assertEqual(drops, points + [(13.0, 40.0)])
        self.assertTrue(any("ligne de pose extérieure" in event for event in app.events.queue))

    def test_battle_x1_to_x9_recovers_ten_without_army_preview(self):
        app = app_without_gui()
        app.settings = main.replace(app.settings, electrodragon_count=10)
        app._wait = Mock()
        app._battle_capture = Mock(return_value=object())
        app._click = Mock(return_value=True)
        app.stable_troop_count = Mock(side_effect=[1, 9, 6, 3, 0])
        points = main.layout_points("ELECTRODRAGON_PERIMETER_POINTS")
        self.assertEqual(app.deploy_unit(object(), main.ELECTRODRAGON_LABEL,
                                         main.ELECTRODRAGON_SLOT, points, burst=True), 10)
        self.assertTrue(any("initial lu x1" in event for event in app.events.queue))

    def test_late_x1_ocr_does_not_rewrite_verified_initial_ten(self):
        app = app_without_gui()
        app.settings = main.replace(app.settings, electrodragon_count=10)
        app._army_preview_counts = {"electrodragon": 10}
        app._wait = Mock()
        app._battle_capture = Mock(return_value=object())
        app._click = Mock(return_value=True)
        app.stable_troop_count = Mock(side_effect=[80, 7, 4, 1, 5])
        self.assertEqual(app.deploy_unit(object(), main.ELECTRODRAGON_LABEL,
                                         main.ELECTRODRAGON_SLOT,
                                         main.layout_points("ELECTRODRAGON_PERIMETER_POINTS"), burst=True), 10)
        self.assertFalse(any("initial lu x1" in event for event in app.events.queue))

    def test_dragon_artwork_with_partial_magenta_is_recognized(self):
        image = Image.new("RGB", (100, 100), (35, 35, 35))
        image.paste((120, 25, 115), (0, 0, 31, 100))
        self.assertEqual(main.troop_card_kind(image, main.Roi(0, 0, 100, 100)), "dragon")

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
        self.assertEqual(app._troop_drop_points, drops)
        self.assertTrue(all(p in points for p in drops))
        self.assertLess(sum(c.args[0] for c in app._wait.call_args_list), .6)

    def test_reversed_troop_order_selects_detected_electro_card(self):
        app = app_without_gui()
        app._wait = Mock()
        image = Image.new("RGB", (1920, 1080))
        with Image.open(Path(__file__).parent / "testdata" / "hero_unplaced.png") as strip:
            image.paste(strip, (0, 880))
        left, right = (280, 0, 399, 1080), (399, 0, 518, 1080)
        first, second = image.crop(left), image.crop(right)
        image.paste(second, (left[0], 0))
        image.paste(first, (right[0], 0))
        app._battle_capture = Mock(return_value=image)
        app._click = Mock(return_value=True)
        app.stable_troop_count = Mock(side_effect=[8, 5, 2, 0])
        points = main.layout_points("ELECTRODRAGON_PERIMETER_POINTS")
        self.assertEqual(app.deploy_unit(object(), main.ELECTRODRAGON_LABEL, main.layout_values("ELECTRODRAGON_SLOT"), points, burst=True), 8)
        self.assertEqual(app._click.call_args_list[0].args[1:], (17.0, 92.5))
        for call in app.stable_troop_count.call_args_list:
            self.assertAlmostEqual(call.args[2], -6.2)

    def test_all_visible_rage_spells_are_placed_and_counted_one_by_one(self):
        app = app_without_gui()
        app._wait = Mock()
        app._battle_capture = Mock(return_value=Image.new("RGB", (1920, 1080)))
        app._click = Mock(return_value=True)
        app.stable_rage_count = Mock(side_effect=[5, 4, 3, 2, 1, 0])
        with patch.object(main, "rage_card_center", return_value=53.6):
            self.assertEqual(app.deploy_rage_spells(object(), -6.25), 5)
        clicks = [call.args[1:] for call in app._click.call_args_list]
        self.assertEqual(len(clicks), 10)
        self.assertEqual(clicks[::2], [(53.6, 92.5)] * 5)
        self.assertEqual(clicks[1::2], main.layout_points("RAGE_DROP_POINTS"))

    def test_rage_five_counter_read_as_xs_in_live_battle(self):
        image = Image.new("RGB", (1765, 993))
        with Image.open(Path(__file__).parent / "testdata" / "rage_five_xs.png") as crop:
            image.paste(crop, (900, 800))
        self.assertEqual(main.read_rage_count(image, 57.1), 5)

    def test_rage_targets_follow_confirmed_troop_drops(self):
        app = app_without_gui()
        app._wait = Mock()
        app._battle_capture = Mock(return_value=Image.new("RGB", (1920, 1080)))
        app._click = Mock(return_value=True)
        app._troop_drop_points = [(18, 40), (24, 32), (31, 23), (38, 13)]
        app.stable_rage_count = Mock(side_effect=[3, 2, 1, 0])
        with patch.object(main, "rage_card_center", return_value=59.85):
            self.assertEqual(app.deploy_rage_spells(object(), 0), 3)
        actual = [call.args[1:] for call in app._click.call_args_list][1::2]
        self.assertEqual(actual, main.rage_targets(app._troop_drop_points, 3))
        self.assertNotEqual(actual, main.layout_points("RAGE_DROP_POINTS")[:3])

    def test_rage_waits_for_count_animation_without_clicking_again(self):
        app = app_without_gui()
        app._wait = Mock()
        app._battle_capture = Mock(return_value=Image.new('RGB',(1323,744)))
        app._click = Mock(return_value=True)
        app._troop_drop_points = [(28,26)]
        app.stable_rage_count = Mock(side_effect=[2,None,1,0])
        with patch.object(main,'rage_card_center',return_value=59.85):
            self.assertEqual(app.deploy_rage_spells(object(),0),2)
        self.assertEqual(app._click.call_count,4)

    def test_rage_is_cast_after_troops_before_heroes(self):
        app = app_without_gui()
        order = []
        app.deploy_unit = Mock(side_effect=lambda *args, **kwargs: order.append('troop') or 1)
        app.deploy_rage_spells = Mock(side_effect=lambda *args: order.append('rage') or 1)
        app._battle_capture = Mock(return_value=object())
        with patch.object(main, 'hero_layout_shift', return_value=0), \
             patch.object(main, 'hero_health_visible', side_effect=lambda *args: order.append('hero') or True):
            app.deploy_attack_composition(object())
        self.assertEqual(order[:4], ['troop', 'troop', 'rage', 'hero'])

    def test_temporary_troops_follow_regular_army_and_heroes(self):
        app = app_without_gui()
        order = []
        def deploy_regular(*args, **kwargs):
            order.append('troop')
            app._confirmed_drop_point = (28.7, 25.6)
            return 1
        app.deploy_unit = Mock(side_effect=deploy_regular)
        app.deploy_rage_spells = Mock(side_effect=lambda *args: order.append('rage') or 5)
        app.deploy_event_extra_troops = Mock(side_effect=lambda *args: order.append('event') or 40)
        app._battle_capture = Mock(return_value=Image.new('RGB', (1323, 744)))
        with patch.object(main, 'hero_layout_shift', return_value=0), \
             patch.object(main, 'hero_card_present', return_value=True), \
             patch.object(main, 'hero_health_visible', side_effect=lambda *args: order.append('hero') or True):
            app.deploy_attack_composition(object())
        self.assertEqual(order, ['troop', 'troop', 'rage'] + ['hero'] * 4 + ['event'])

    def test_victory_before_hero_does_not_click_result_screen(self):
        app = app_without_gui()
        app.deploy_unit = Mock(return_value=0)
        app.deploy_rage_spells = Mock(return_value=0)
        app._battle_capture = Mock(return_value=Image.new('RGB', (1323, 744)))
        app._click = Mock()
        with patch.object(main, 'hero_layout_shift', return_value=0), \
             patch.object(main, 'hero_card_present', return_value=False), \
             patch.object(main, 'battle_result_return_ready', return_value=True):
            with self.assertRaises(main.BattleEndedEarly):
                app.deploy_attack_composition(object())
        app._click.assert_not_called()

    def test_absent_rage_card_never_receives_a_spell_click(self):
        app = app_without_gui()
        app._battle_capture = Mock(return_value=Image.new("RGB", (1920, 1080)))
        app._click = Mock()
        app.stable_rage_count = Mock()
        with patch.object(main, "rage_card_center", return_value=None):
            self.assertEqual(app.deploy_rage_spells(object(), 0), 0)
        app._click.assert_not_called()
        app.stable_rage_count.assert_not_called()

    def test_rage_card_retries_both_layouts_after_transient_miss(self):
        app = app_without_gui()
        app._army_preview_counts = {'rage': 1}
        app._wait = Mock()
        app._battle_capture = Mock(return_value=Image.new('RGB', (1323, 744)))
        app._click = Mock(return_value=True)
        app.stable_rage_count = Mock(side_effect=[1, 0])
        with patch.object(main, 'rage_card_center', side_effect=[None, None, None, None, 63.35]):
            self.assertEqual(app.deploy_rage_spells(object(), 0), 1)
        self.assertEqual(app._click.call_count, 2)
        self.assertEqual(sum(call.args == (.25,) for call in app._wait.call_args_list), 2)

    def test_expected_rage_card_missing_is_an_error_not_success(self):
        app = app_without_gui()
        app._army_preview_counts = {'rage': 5}
        app._wait = Mock()
        app._battle_capture = Mock(return_value=Image.new('RGB', (1323, 744)))
        app._click = Mock()
        with patch.object(main, 'rage_card_center', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'Rage présent avant combat'):
                app.deploy_rage_spells(object(), 0)
        app._click.assert_not_called()

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
        self.assertTrue(any("issue de configuration" in str(event) for event in app.events.queue))

    def test_wide_live_client_uses_configured_count_when_counter_is_empty(self):
        app = app_without_gui()
        app._wait = Mock()
        app._battle_capture = Mock(return_value=object())
        app._click = Mock(return_value=True)
        app.stable_troop_count = Mock(side_effect=[None, 0])
        window = type("WideWindow", (), {"width": 1765})()
        self.assertEqual(app.deploy_unit(window, "Dragon", (23, 92), [(18, 40)], burst=True), 1)
        self.assertTrue(any("fenêtre live" in str(event) for event in app.events.queue))

    def test_dimmed_hero_is_not_confirmed_and_retry_reselects(self):
        app = app_without_gui()
        app._wait = Mock()
        app._battle_capture = Mock(return_value=object())
        app._click = Mock(return_value=True)
        with patch.object(app, "deploy_unit", return_value=0), \
             patch.object(main, "hero_layout_shift", return_value=0), \
             patch.object(main, "hero_health_visible", return_value=False), \
             patch.object(main, "hero_placeholder_slot", return_value=False), \
             patch.object(main, "hero_card_present", return_value=True), \
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
             patch.object(main, "hero_health_visible", side_effect=[True, True, False, False]):
            app.deploy_attack_composition(object())
        app._click.assert_not_called()
        self.assertTrue(any("case vide ignorée" in event for event in app.events.queue))

    def test_fourth_available_hero_is_selected_and_verified(self):
        app = app_without_gui()
        app._wait = Mock()
        app._battle_capture = Mock(return_value=Image.new("RGB", (1920, 1080)))
        app._click = Mock(return_value=True)
        with patch.object(app, "deploy_unit", return_value=0), \
             patch.object(main, "hero_layout_shift", return_value=0), \
             patch.object(main, "hero_health_visible", side_effect=[False, False, True] * 4), \
             patch.object(main, "hero_placeholder_slot", return_value=False), \
             patch.object(main, "hero_card_present", return_value=True), \
             patch.object(main, "hero_icon_saturation", return_value=100), \
             patch.object(main, "rage_card_center", return_value=None):
            app.deploy_attack_composition(object())
        self.assertEqual(len(main.layout_points("HERO_SLOTS")), 4)
        self.assertEqual(app._click.call_count, 8)
        self.assertEqual(app._click.call_args_list[6].args[1:], main.layout_points("HERO_SLOTS")[3])
        self.assertTrue(any("4 héros" in str(event) for event in app.events.queue))

    def test_rage_locator_resolves_compact_bar_without_hero_deployment(self):
        app = app_without_gui()
        app.settings = main.replace(app.settings, deploy_heroes=False)
        app.deploy_unit = Mock(return_value=0)
        app.deploy_rage_spells = Mock(return_value=0)
        window = object()
        with patch.object(main, "hero_layout_shift", return_value=-6.25) as resolve_shift:
            app.deploy_attack_composition(window)
        resolve_shift.assert_not_called()
        app.deploy_rage_spells.assert_called_once_with(window, None)

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
             patch.object(main, "hero_card_present", return_value=True), \
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

    def test_partial_red_printwindow_frame_is_retried(self):
        incomplete = Image.new('RGB', (1765,993), (80,90,70))
        incomplete.paste((255,0,0), (0,510,1765,993))
        complete = Image.new('RGB', (1765,993), (80,90,70))
        self.assertTrue(main.capture_render_incomplete(incomplete))
        self.assertFalse(main.capture_render_incomplete(complete))
        app = app_without_gui()
        app._wait = Mock()
        with patch.object(main.WindowDriver, 'capture', side_effect=[incomplete,complete]) as capture, \
             patch.object(main, 'connection_retry_point', return_value=None):
            self.assertIs(app._capture(self.window), complete)
        self.assertEqual(capture.call_count, 2)
        app._wait.assert_called_once_with(.3)

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

    def test_custom_1280_by_780_calibration_maps_click_to_client(self):
        geometry = main.ClientGeometry(1280, 780, 0, 0, 1280, 780)
        settings = main.replace(main.Settings(), layout_aspect_ratio=1280 / 780)
        with main.operation_context(self.event, settings), \
             patch.object(main.WindowDriver, "client_geometry", return_value=geometry), \
             patch.object(main.USER32, "PostMessageW", return_value=True) as post:
            main._operation.last_capture = (self.window.hwnd, geometry)
            self.assertTrue(main.WindowDriver.click_percent(self.window, 50, 50))
        self.assertEqual(post.call_args_list[0].args[-1], (390 << 16) | 640)

    def test_closed_selected_window_does_not_switch_account(self):
        other = main.GameWindow(456, "Clash of Clans - autre compte", 1920, 1080)
        with patch.object(main.WindowDriver, "list_windows", return_value=[other]):
            self.assertIsNone(main.WindowDriver.resolve("Clash of Clans - choisi"))


class DeploymentRegressions(unittest.TestCase):
    def test_compact_battle_counter_tracks_one_real_drop(self):
        before = Image.open(Path(__file__).parent/'testdata/manual_battle_point_1323.png')
        after = Image.open(Path(__file__).parent/'testdata/manual_drop_result_1323.png')
        with before, after:
            self.assertEqual(main.read_troop_count(before, main.ELECTRODRAGON_LABEL, -6.2), 10)
            self.assertEqual(main.read_troop_count(after, main.ELECTRODRAGON_LABEL, -6.2), 9)

    def test_compact_battle_counter_rejects_neighbor_badge(self):
        with Image.open(Path(__file__).parent/'testdata/attack_adaptive_after_two_1323.png') as image:
            self.assertEqual(main.read_troop_count(image, main.ELECTRODRAGON_LABEL, -6.2), 8)

    def test_compact_battle_counter_reads_all_live_glyphs(self):
        fixtures = {10:'manual_battle_point_1323.png', 9:'manual_drop_result_1323.png',
                    8:'attack_adaptive_after_two_1323.png', 7:'attack_adaptive_after_three_1323.png'}
        fixtures.update({count:f'battle_badge_x{count}.png' for count in range(7)})
        for count, filename in fixtures.items():
            with self.subTest(count=count), Image.open(Path(__file__).parent/'testdata'/filename) as image:
                self.assertEqual(main.read_troop_count(image, main.ELECTRODRAGON_LABEL, -6.2), count)
                if 1 <= count <= 6:
                    scaled = image.resize((1387,780),Image.Resampling.BICUBIC)
                    self.assertEqual(main.read_troop_count(scaled, main.ELECTRODRAGON_LABEL, -6.2), count)

    def test_deployment_line_has_points_for_upper_left_probe(self):
        points = main.layout_points('ELECTRODRAGON_PERIMETER_POINTS')
        self.assertEqual(len(points), 16)
        self.assertTrue(all(15 <= x <= 40 and 10 <= y <= 45 for x,y in points))

    def test_compact_electro_probes_until_card_count_falls(self):
        app = app_without_gui()
        app._battle_capture = Mock(return_value=Image.new('RGB',(1323,744),'white'))
        app._click = Mock(return_value=True)
        app._wait = Mock()
        app.stable_troop_count = Mock(side_effect=[10,9] + list(range(8,-1,-1)))
        app._troop_drop_points = []
        with patch.object(main, 'battle_hud_visible', return_value=True):
            self.assertEqual(app._deploy_compact_electro(object(),(17,92.5),[(28,25.6)],10,-6.2),10)
        self.assertEqual(app._confirmed_drop_point,(28,20.6))
        self.assertEqual(len(app._troop_drop_points),10)

    def test_compact_electro_finishes_after_transient_counter_dropout(self):
        app = app_without_gui()
        app._battle_capture = Mock(return_value=Image.new('RGB', (1323, 744), 'white'))
        app._click = Mock(return_value=True)
        app._wait = Mock()
        app.stable_troop_count = Mock(side_effect=[9, None, 7, 6, 5, 4, 3, 2, 1, 0])
        app._troop_drop_points = []
        with patch.object(main, 'battle_hud_visible', return_value=True):
            self.assertEqual(app._deploy_compact_electro(object(), (17, 92.5), [(28, 25.6)], 10, 0), 10)
        self.assertEqual(len(app._troop_drop_points), 10)
        self.assertTrue(any('suivie provisoirement' in event for event in app.events.queue))

    def test_compact_electro_uses_bounded_residual_drop_until_card_empties(self):
        app = app_without_gui()
        active = Image.new('RGB', (1323, 744), (150, 35, 70))
        empty = Image.new('RGB', (1323, 744), (90, 90, 90))
        app._click = Mock(return_value=True)
        app._battle_capture = Mock(side_effect=lambda _window: empty if app._click.call_count >= 22 else active)
        app._wait = Mock()
        app.stable_troop_count = Mock(side_effect=[9] + [None] * 9)
        app._troop_drop_points = []
        with patch.object(main, 'battle_hud_visible', return_value=True):
            self.assertEqual(app._deploy_compact_electro(object(), (17, 92.5), [(28, 25.6)], 10, 0), 10)
        self.assertEqual(app._click.call_count, 22)
        self.assertTrue(any('pose résiduelle' in event for event in app.events.queue))

    def test_compact_army_badge_x10_is_read_before_attack(self):
        with Image.open(Path(__file__).parent/'testdata/army_wait_current_1323.png') as image:
            settings = main.replace(main.load_settings(), electrodragon_count=10)
            ready, detail, observed = main.army_readiness(image, settings)
        self.assertTrue(ready, detail)
        self.assertEqual(observed['electrodragon'], 10)
        self.assertEqual(observed['rage'], 5)

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
            self.assertEqual(len(icons), 14)
            self.assertEqual({kind for kind, *_ in icons}, {"gold", "elixir", "dark"})
            self.assertEqual(main.find_collectible_icons(after), [])
            self.assertFalse(main.collectible_icon_still_visible(after, "gold", 612, 322))
            self.assertFalse(main.collectible_icon_still_visible(after, "dark", 400, 399))

    def test_dark_drill_collection_is_counted_after_its_bubble_disappears(self):
        app = app_without_gui()
        app._capture = Mock(return_value=Image.new("RGB", (1920, 1080)))
        app._click = Mock(return_value=True)
        app._wait = Mock()
        app.stable_reserves = Mock(return_value=(3_000_000, 4_000_000))
        with patch.object(main, "village_home_ready", return_value=True), \
             patch.object(main, "builders_menu_open", return_value=False), \
             patch.object(main, "daily_reward_open", return_value=False), \
             patch.object(main, "wall_selection_open", return_value=False), \
             patch.object(main, "find_collectible_icons", return_value=[("dark", 400, 399, 0)]), \
             patch.object(main, "collectible_icon_still_visible", side_effect=[True, False]):
            self.assertEqual(app.collect_village_resources(object()), 1)
        app._click.assert_called_once_with(unittest.mock.ANY, 400 * 100 / 1920, 399 * 100 / 1080)
        self.assertTrue(any("1 foreuse" in str(event) for event in app.events.queue))

    def test_collection_does_not_click_through_builder_menu(self):
        app = app_without_gui()
        with Image.open(Path(__file__).parent / "testdata" / "suggested_menu.png") as image:
            app._capture = Mock(return_value=image)
            app._click = Mock()
            self.assertEqual(app.collect_village_resources(object()), 0)
            app._click.assert_not_called()

    def test_false_collectible_wall_selection_is_cleared_before_walls(self):
        app = app_without_gui()
        app._capture = Mock(return_value=Image.new("RGB", (1765, 993)))
        app._click = Mock(return_value=True)
        app._wait = Mock()
        app.stable_reserves = Mock(return_value=(6_000_000, 6_000_000))
        with patch.object(main, "village_home_ready", return_value=True), \
             patch.object(main, "builders_menu_open", return_value=False), \
             patch.object(main, "daily_reward_open", return_value=False), \
             patch.object(main, "wall_selection_open", side_effect=[False, False, False, True, False]), \
             patch.object(main, "find_collectible_icons", return_value=[("gold", 1176, 296, 1)]), \
             patch.object(main, "collectible_icon_still_visible", return_value=True):
            self.assertEqual(app.collect_village_resources(object()), 0)
        self.assertEqual(app._click.call_count, 2)
        self.assertEqual(app._click.call_args_list[0], app._click.call_args_list[1])

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
    def test_village_takes_priority_over_a_spurious_battle_ocr_token(self):
        image = Image.new("RGB", (1765, 993))
        with patch.object(main, "village_home_ready", return_value=True), \
             patch.object(main, "normalized_screen_text", return_value="degatsgeneraux"):
            self.assertFalse(main.battle_hud_visible(image))

    def test_real_connection_dialog_returns_only_retry_button(self):
        with Image.open(Path(__file__).parent/'testdata/connection_lost.png') as image:
            point=main.connection_retry_point(image)
            self.assertAlmostEqual(point[0],32.7,delta=.2)
            self.assertAlmostEqual(point[1],56.1,delta=.2)
        self.assertIsNone(main.connection_retry_point(Image.new('RGB',(1920,1080),'white')))

    def test_retry_button_survives_different_dialog_message(self):
        with Image.open(Path(__file__).parent/'testdata/connection_lost.png') as source:
            image=source.copy()
        image.paste((30,30,30),(557,443,1363,572))
        point=main.connection_retry_point(image)
        self.assertIsNotNone(point)
        self.assertAlmostEqual(point[0],32.7,delta=.2)

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

    def test_reconnect_accepts_a_restored_battle_without_extra_clicks(self):
        app=app_without_gui()
        app._wait=Mock()
        app._click=Mock(return_value=True)
        image=Image.new('RGB',(1920,1080))
        window=SimpleNamespace(title='Clash test')
        with patch.object(main.WindowDriver,'resolve',return_value=window), \
             patch.object(main.WindowDriver,'capture',return_value=image), \
             patch.object(main,'connection_retry_point',side_effect=[(35,56),None,None]), \
             patch.object(main,'battle_hud_visible',return_value=True), \
             patch.object(main,'village_home_ready',return_value=False):
            app.reconnect_game()
        app._click.assert_called_once_with(window,35,56)


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
