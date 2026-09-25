import unittest
from pathlib import Path
from PIL import Image
from unittest.mock import Mock, patch
from test_regressions import app_without_gui
import main
import upgrades


class UpgradeTests(unittest.TestCase):
    def test_rejected_selected_panel_is_closed_before_builder_menu_reopens(self):
        app = app_without_gui()
        app._capture = Mock(return_value=Image.new('RGB', (1323, 744)))
        app._wall_click = Mock()
        app._trace = Mock()
        app.stable_reserves = Mock(return_value=(6_000_000, 6_000_000))
        with patch.object(upgrades, 'stable_builders', return_value=2), \
             patch.object(main, 'builders_menu_open', side_effect=[True, False, True]), \
             patch.object(upgrades, 'find_payable_upgrade', return_value=('Catapulte explosive', 54.2, 5_000_000, 'élixir')), \
             patch.object(upgrades, 'stable_upgrade_row', return_value=54.2), \
             patch.object(upgrades, 'direct_upgrade_button', return_value=None), \
             patch.object(upgrades, 'selected_panel_matches', return_value=False), \
             patch.object(upgrades, 'selected_panel_title_matches', return_value=False):
            self.assertEqual(upgrades.upgrade_suggested(app, object(), max_upgrades=1), 0)
        self.assertEqual(app._wall_click.call_args_list[-1].args[1:],
                         ((6, 55), 'désélectionner le bâtiment refusé'))
        self.assertFalse(any('confirmer l’amélioration conseillée' in str(call)
                             for call in app._wall_click.call_args_list))

    def test_shifted_panel_never_spends_when_dialog_price_differs(self):
        app = app_without_gui()
        app._capture = Mock(return_value=Image.new('RGB', (1920, 1080)))
        app._wall_click = Mock()
        app._trace = Mock()
        app._wait = Mock()
        app.stable_reserves = Mock(return_value=(10_000_000, 10_000_000))
        with patch.object(upgrades, 'stable_builders', return_value=3), \
             patch.object(main, 'builders_menu_open', side_effect=[True, False]), \
             patch.object(upgrades, 'find_payable_upgrade', return_value=('Caserne', 41.2, 2_800_000, 'élixir')), \
             patch.object(upgrades, 'stable_upgrade_row', return_value=41.2), \
             patch.object(upgrades, 'direct_upgrade_button', return_value=None), \
             patch.object(upgrades, 'selected_panel_matches', return_value=False), \
             patch.object(upgrades, 'selected_panel_title_matches', return_value=True), \
             patch.object(main, 'read_word_centers', return_value=[('Améliorer', 50, 50)]), \
             patch.object(upgrades, 'confirmation_headings', return_value=['Caserne (niveau 13)']), \
             patch.object(upgrades, 'confirmation_cost', return_value=2_900_000), \
             patch.object(upgrades, 'resource_icon', return_value='élixir'):
            self.assertEqual(upgrades.upgrade_suggested(app, object(), max_upgrades=1), 0)
        self.assertFalse(any('confirmer l’amélioration conseillée' in str(call)
                             for call in app._wall_click.call_args_list))
        self.assertEqual(app._wall_click.call_args_list[-1].args[1], (6, 55))

    def test_two_upgrade_buttons_probe_dialogs_and_pay_only_matching_price(self):
        app = app_without_gui()
        app._capture = Mock(return_value=Image.new('RGB', (1920, 1080)))
        app._wall_click = Mock()
        app._trace = Mock()
        app._wait = Mock()
        app.stable_reserves = Mock(return_value=(10_000_000, 10_000_000))
        app.journal = Mock()
        with patch.object(upgrades, 'stable_builders', return_value=3), \
             patch.object(main, 'builders_menu_open', side_effect=[True, False]), \
             patch.object(upgrades, 'find_payable_upgrade', return_value=('Caserne noire', 48.3, 2_880_000, 'élixir')), \
             patch.object(upgrades, 'stable_upgrade_row', return_value=48.3), \
             patch.object(upgrades, 'direct_upgrade_button', return_value=None), \
             patch.object(upgrades, 'selected_panel_matches', return_value=True), \
             patch.object(main, 'read_word_centers', return_value=[('Améliorer', 41, 45), ('Améliorer', 57, 45)]), \
             patch.object(upgrades, 'confirmation_headings', return_value=['Caserne noire (niveau 38)']), \
             patch.object(upgrades, 'confirmation_cost', side_effect=[2_900_000, 2_880_000, 2_880_000]), \
             patch.object(upgrades, 'resource_icon', return_value='élixir'), \
             patch.object(upgrades, 'verify_building_spend') as verify:
            self.assertEqual(upgrades.upgrade_suggested(app, object(), max_upgrades=1), 1)
        app.journal.save_upgrade_screen.assert_called_once()
        self.assertTrue(any('fermer la confirmation au prix différent' in str(call)
                            for call in app._wall_click.call_args_list))
        self.assertEqual(sum('confirmer l’amélioration conseillée' in str(call)
                             for call in app._wall_click.call_args_list), 1)
        verify.assert_called_once()

    def test_shifted_caserne_panel_title_allows_dialog_verification(self):
        image = Image.new('RGB', (1920, 1080))
        with patch.object(main, 'read_text', return_value='tCaSetRNe5(Niveau 13) INFOS AMéIi0ReR'):
            self.assertTrue(upgrades.selected_panel_title_matches(image, 'Caserne'))
            self.assertFalse(upgrades.selected_panel_title_matches(image, 'Caserne noire'))

    def test_moving_building_row_is_relocated_before_click(self):
        app = app_without_gui()
        app._wait = Mock()
        app._capture = Mock(return_value=Image.new('RGB', (1920, 1080)))
        rows = [[('Caserne noire', y, 2_880_000, 'élixir')] for y in (59.6, 55.2, 55.2)]
        with patch.object(main, 'builders_menu_open', return_value=True), \
             patch.object(upgrades, 'suggested_items', side_effect=rows):
            self.assertEqual(upgrades.stable_upgrade_row(
                app, object(), 'Caserne noire', 2_880_000, 'élixir'), 55.2)
        self.assertEqual(app._capture.call_count, 3)

    def test_matching_wall_payment_cards_remove_tiny_ocr_suffix(self):
        prices = {'or': ((58, 80), 4_000_004), 'élixir': ((66, 80), 4_000_000)}
        self.assertEqual(main.reconcile_wall_payment_prices(prices),
                         {'or': ((58, 80), 4_000_000), 'élixir': ((66, 80), 4_000_000)})
        missing_zero = {'or': ((58, 80), 400_000), 'élixir': ((66, 80), 4_000_000)}
        self.assertEqual(main.reconcile_wall_payment_prices(missing_zero),
                         {'or': ((58, 80), 4_000_000), 'élixir': ((66, 80), 4_000_000)})
        conflicting = {'or': ((58, 80), 5_000_000), 'élixir': ((66, 80), 4_000_000)}
        self.assertEqual(main.reconcile_wall_payment_prices(conflicting), conflicting)

    def test_two_unstable_building_rows_return_to_farming(self):
        app = app_without_gui()
        app._capture = Mock(return_value=Image.new('RGB',(1323,744)))
        app._wait = Mock()
        app._wall_click = Mock()
        app.stable_reserves = Mock(return_value=(5_000_000,5_000_000))
        choices = [('Tour A',30,4_000_000,'or'),('Tour B',35,3_000_000,'or')]
        with patch.object(upgrades,'stable_builders',return_value=3), \
             patch.object(main,'builders_menu_open',return_value=True), \
             patch.object(upgrades,'find_payable_upgrade',side_effect=choices) as find, \
             patch.object(upgrades,'builder_price_resource',return_value=None):
            self.assertEqual(upgrades.upgrade_suggested(app,object()),0)
        self.assertEqual(find.call_count,2)
        app._wall_click.assert_not_called()

    def test_wall_ocr_fragments_never_become_building_candidates(self):
        for title in ('Rempart x218', 'mpart', 'lempart', '\\empart 218', 'x 182'):
            self.assertTrue(upgrades.is_wall_row(title), title)
        self.assertFalse(upgrades.is_wall_row('Catapulte explosive'))

    def test_many_running_builders_do_not_hide_suggested_section(self):
        with Image.open(Path(__file__).parent/'testdata/new_account_builder_menu.png') as im:
            app = app_without_gui()
            app._capture = Mock(return_value=im)
            app._wait = Mock(return_value=False)
            with patch.object(main.WindowDriver, 'scroll_menu', return_value=True) as scroll:
                upgrades.scroll_builders_to_top(app, 'window')
            scroll.assert_not_called()

    def test_live_builder_header_enpours_is_already_at_top(self):
        with Image.open(Path(__file__).parent/'testdata/builders_after_upgrade_1765.png') as image:
            app = app_without_gui()
            app._capture = Mock(return_value=image)
            with patch.object(main.WindowDriver, 'scroll_menu', return_value=True) as scroll:
                upgrades.scroll_builders_to_top(app, 'window')
            scroll.assert_not_called()

    def test_compact_builder_header_encours_is_already_at_top(self):
        with Image.open(Path(__file__).parent/'testdata/builders_goblin_counter_1323.png') as image:
            app = app_without_gui()
            app._capture = Mock(return_value=image)
            with patch.object(main.WindowDriver, 'scroll_menu', return_value=True) as scroll:
                upgrades.scroll_builders_to_top(app, 'window')
            scroll.assert_not_called()

    def test_goblin_counter_is_not_village_builder_count(self):
        with Image.open(Path(__file__).parent/'testdata/builders_goblin_counter_1323.png') as image:
            self.assertEqual(upgrades.builder_count(image, with_total=True), (3, 6))

    def test_live_menu_accepts_stable_top_without_suggested_heading(self):
        with Image.open(Path(__file__).parent/'testdata/new_account_builder_menu.png') as im:
            app = app_without_gui()
            app._capture = Mock(side_effect=[im, im])
            app._wait = Mock(return_value=False)
            with patch.object(main, 'read_text', return_value='Ameliorations en cours : Disponible'), \
                 patch.object(main.WindowDriver, 'scroll_menu', return_value=True) as scroll:
                upgrades.scroll_builders_to_top(app, 'window')
            scroll.assert_called_once()

    def test_live_large_wall_panel_accepts_vm_heading_and_payments(self):
        with Image.open(Path(__file__).parent / "testdata" / "wall_panel_live_1765.png") as im:
            controls = main.wall_group_controls(im, single=True)
        self.assertEqual(controls["payments"]["or"][1], 4_000_000)
        self.assertEqual(controls["payments"][next(k for k in controls["payments"] if k != "or")][1], 4_000_000)

    def test_translucent_menu_does_not_select_background_wall_label(self):
        with Image.open(Path(__file__).parent/'testdata/wall_menu_background_false_row.png') as im:
            self.assertTrue(main.builders_menu_open(im))
            self.assertFalse(main.wall_menu_row_matches(im,61))
            self.assertIsNone(main.find_wall_menu_item(im))

    def test_wall_rows_at_different_positions_keep_separate_quantities(self):
        with Image.open(Path(__file__).parent/'testdata/builders_selected_menu.png') as base, \
                Image.open(Path(__file__).parent/'testdata/wall_last_menu.png') as last:
            for position in (32, 44, 53):
                with self.subTest(position=position):
                    image = base.copy()
                    box = (round(image.width*.38), round(image.height*.585),
                           round(image.width*.54), round(image.height*.627))
                    image.paste(last.crop(box), (box[0], round(image.height*(position-2.3)/100)))
                    rows = main.find_wall_menu_items(image)
                    self.assertEqual(len(rows), 2)
                    self.assertAlmostEqual(rows[0][1], position, delta=1)
                    self.assertEqual([main.read_wall_available(image, row) for row in rows], [1, 74])

    def test_wall_search_keeps_scrolling_when_menu_border_is_unreadable(self):
        app = app_without_gui()
        app._capture = Mock(return_value=object())
        app._wall_click = Mock()
        app._wait = Mock(return_value=False)
        app.stable_reserves = Mock(return_value=(2_000_000, 2_000_000))
        with patch.object(main, 'builders_menu_open', return_value=False), \
                patch.object(main, 'find_wall_menu_item', return_value=None), \
                patch.object(upgrades, 'scroll_builders_to_top'), \
                patch.object(main.WindowDriver, 'scroll_menu', return_value=True) as scroll:
            self.assertEqual(app.upgrade_walls_to_reserve('window', independent=True), 0)
        self.assertEqual(scroll.call_count, 20)
        app._wall_click.assert_called_once()

    def test_wall_search_does_not_scroll_when_builder_menu_never_opens(self):
        app = app_without_gui()
        app._capture = Mock(return_value=Image.new("RGB", (1765, 993)))
        app._wall_click = Mock()
        app._wait = Mock(return_value=False)
        app.stable_reserves = Mock(return_value=(6_000_000, 6_000_000))
        with patch.object(main, "builders_menu_open", return_value=False), \
             patch.object(main, "find_wall_menu_item", return_value=None), \
             patch.object(upgrades, "scroll_builders_to_top") as scroll:
            self.assertEqual(app.upgrade_walls_to_reserve("window", independent=True), 0)
        app._wall_click.assert_called_once()
        scroll.assert_not_called()

    def test_unconfirmed_builder_list_top_defers_walls_without_stopping_attacks(self):
        app = app_without_gui()
        app._capture = Mock(return_value=Image.new('RGB', (1323, 744)))
        app._wall_click = Mock()
        app.stable_reserves = Mock(return_value=(5_000_000, 5_000_000))
        with patch.object(main, 'builders_menu_open', return_value=True), \
             patch.object(upgrades, 'scroll_builders_to_top', side_effect=RuntimeError(
                 'Début de la liste des ouvriers non confirmé après défilement.')):
            self.assertEqual(app.upgrade_walls_to_reserve(object(), independent=True), 0)
        app._wall_click.assert_not_called()
        self.assertTrue(any('remparts reportés et attaque conservée' in event for event in app.events.queue))

    def test_wall_row_is_selected_after_menu_slides_to_a_new_position(self):
        app = app_without_gui()
        app._capture = Mock(return_value=object())
        app._wall_click = Mock()
        app._wait = Mock(return_value=False)
        app.stable_reserves = Mock(return_value=(2_000_000, 2_000_000))
        original_row = (42.2, 49.5)
        settled_row = (42.2, 43.6)
        with patch.object(upgrades, 'scroll_builders_to_top'), \
                patch.object(main, 'builders_menu_open', return_value=True), \
                patch.object(main, 'find_wall_menu_item', side_effect=[original_row, settled_row]), \
                patch.object(main, 'find_wall_menu_items', return_value=[settled_row]), \
                patch.object(main, 'read_wall_available', return_value=203), \
                patch.object(main, 'wall_selected', return_value=True), \
                patch.object(main, 'find_wall_more_button', return_value=None):
            self.assertEqual(app.upgrade_walls_to_reserve('window', independent=True),0)
        app._wall_click.assert_called_once_with('window', settled_row, 'rempart')

    def test_shifted_wall_row_uses_fresh_stable_quantity_after_ocr_error(self):
        app = app_without_gui()
        app._capture = Mock(return_value=object())
        app._wall_click = Mock()
        app._wait = Mock(return_value=False)
        app.stable_reserves = Mock(return_value=(2_283_051, 1_119_875))
        previous_row = (42.2, 50.85)
        settled_row = (42.2, 47.51)
        with patch.object(upgrades, 'scroll_builders_to_top'), \
                patch.object(main, 'builders_menu_open', return_value=True), \
                patch.object(main, 'find_wall_menu_item', side_effect=[previous_row, settled_row]), \
                patch.object(main, 'find_wall_menu_items', return_value=[settled_row]), \
                patch.object(main, 'read_wall_available', side_effect=[159, 169, 169]), \
                patch.object(main, 'wall_selected', return_value=True), \
                patch.object(main, 'find_wall_more_button', return_value=None):
            self.assertEqual(app.upgrade_walls_to_reserve('window', independent=True),0)
        app._wall_click.assert_called_once_with('window', settled_row, 'rempart')

    def test_unaffordable_wall_row_falls_through_to_second_row(self):
        with Image.open(Path(__file__).parent/'testdata/builders_selected_menu.png') as base, \
                Image.open(Path(__file__).parent/'testdata/wall_last_menu.png') as last:
            image = base.copy()
            box = (round(image.width*.38), round(image.height*.585),
                   round(image.width*.54), round(image.height*.627))
            image.paste(last.crop(box), (box[0], round(image.height*.297)))
        app = app_without_gui()
        app._capture = Mock(return_value=image)
        app._wall_click = Mock()
        app._wait = Mock(return_value=False)
        app.stable_reserves = Mock(side_effect=[(1_500_000, 1_500_000)]*3 +
                                    [(1_000_000, 1_500_000), (1_000_000, 1_000_000)])
        expensive = {'add': None, 'payments': {'or': ((50, 80), 600_000),
                                               'élixir': ((58, 80), 600_000)}}
        affordable = {'add': (42, 80), 'payments': {'or': ((50, 80), 500_000),
                                                  'élixir': ((58, 80), 500_000)}}
        app.stable_wall_group = Mock(side_effect=[expensive, affordable, affordable])
        with patch.object(main, 'wall_selected', return_value=True), \
                patch.object(upgrades, 'scroll_builders_to_top'), \
                patch.object(main, 'find_wall_more_button', return_value=(46, 85)), \
                patch.object(main, 'wall_multi_mode', return_value=True), \
                patch.object(main, 'wall_batch_confirmation_matches', return_value=True):
            self.assertEqual(app.upgrade_walls_to_reserve('window', independent=True), 1)
        wall_clicks = [call.args[1] for call in app._wall_click.call_args_list
                       if call.args[2] == 'rempart']
        self.assertEqual(len(wall_clicks), 2)
        self.assertAlmostEqual(wall_clicks[0][1], 32, delta=1)
        self.assertAlmostEqual(wall_clicks[1][1], 61, delta=1)

    def test_unaffordable_wall_row_shift_stops_search_and_starts_attack(self):
        app = app_without_gui()
        app.settings = main.replace(app.settings, upgrade_recommended=False)
        app.collect_village_resources = Mock()
        app._capture = Mock(return_value=object())
        app._wall_click = Mock()
        app._wait = Mock(return_value=False)
        app.stable_reserves = Mock(return_value=(1_500_278, 1_459_335))
        app.stable_wall_group = Mock(return_value={
            'add': None, 'payments': {'or': ((50, 80), 600_000), 'élixir': ((58, 80), 600_000)}})
        app.open_search = Mock(return_value=False)
        with patch.object(main.WindowDriver, 'resolve', return_value=object()), \
                patch.object(main, 'builders_menu_open', return_value=True), \
                patch.object(main, 'find_wall_menu_item', return_value=(42.2, 53.35)), \
                patch.object(main, 'find_wall_menu_items', return_value=[(42.2, 53.9)]), \
                patch.object(main, 'read_wall_available', return_value=190), \
                patch.object(main, 'read_wall_menu_price', return_value=600_000), \
                patch.object(main, 'wall_selected', return_value=True), \
                patch.object(main, 'find_wall_more_button', return_value=(46, 85)), \
                patch.object(main, 'wall_multi_mode', return_value=True), \
                patch.object(main.WindowDriver, 'scroll_menu', return_value=True), \
                patch.object(upgrades, 'scroll_builders_to_top'):
            app.farm_loop()
        app.stable_wall_group.assert_called_once()
        app.open_search.assert_called_once()
        self.assertTrue(any('Aucun autre rempart payable' in message for message in app.events.queue))

    def test_last_wall_has_an_individual_payment_path(self):
        with Image.open(Path(__file__).parent/'testdata/wall_last_menu.png') as im:
            row = main.find_wall_menu_item(im)
            self.assertIsNotNone(row)
            self.assertEqual(main.read_wall_menu_price(im, row), 500_000)
        with Image.open(Path(__file__).parent/'testdata/wall_last_selected.png') as im:
            controls=main.wall_group_controls(im,single=True)
            self.assertIsNotNone(controls)
            self.assertIsNone(controls['add'])
            self.assertEqual(controls['payments']['or'][1],500000)
        with Image.open(Path(__file__).parent/'testdata/wall_single_confirmation.png') as im:
            self.assertTrue(main.single_wall_confirmation_matches(im,500000,'or'))
            self.assertFalse(main.single_wall_confirmation_matches(im,750000,'or'))
            self.assertFalse(main.single_wall_confirmation_matches(im,500000,'élixir'))
        self.assertEqual(main.layout_values('WALL_CONFIRM_BUTTON'),(70,87))

    def test_live_vm_single_wall_confirmation_reads_four_million_gold(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'wall_single_4m_1765.png') as image:
            self.assertTrue(main.single_wall_confirmation_matches(image, 4_000_000, 'or'))
            self.assertFalse(main.single_wall_confirmation_matches(image, 5_000_000, 'or'))
            self.assertFalse(main.single_wall_confirmation_matches(image, 4_000_000, 'élixir'))
            self.assertFalse(main.village_home_ready(image))
            with patch.object(main, 'has_all_screen_text', return_value=False):
                self.assertTrue(main.village_home_ready(image))

    def test_group_of_one_uses_individual_confirmation_shown_by_game(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'wall_group_single_confirmation_1323.png') as image:
            self.assertEqual(main.wall_confirmation_button(image, 4_000_000, 'or', False, 1),
                             'WALL_CONFIRM_BUTTON')
            self.assertIsNone(main.wall_confirmation_button(image, 5_000_000, 'or', False, 1))
            self.assertIsNone(main.wall_confirmation_button(image, 4_000_000, 'élixir', False, 1))
            self.assertIsNone(main.wall_confirmation_button(image, 4_000_000, 'or', False, 2))

    def test_last_wall_without_x1_is_bought_with_individual_confirmation(self):
        app = app_without_gui()
        app.settings = main.replace(app.settings, upgrade_recommended=False)
        app._capture = Mock(return_value=Image.new('RGB', (1920, 1080)))
        app._wait = Mock(return_value=False)
        app._wall_click = Mock()
        app.stable_reserves = Mock(side_effect=[(2_000_000, 2_000_000),
                                                (2_000_000, 2_000_000),
                                                (1_500_000, 2_000_000)])
        payment = {'or': ((55, 80), 500_000)}
        app.stable_wall_group = Mock(return_value={'payments': payment, 'add': None})
        row = (52, 53)
        with patch.object(main, 'find_wall_menu_item', return_value=row), \
             patch.object(main, 'read_wall_available', return_value=None), \
             patch.object(main, 'wall_selected', side_effect=[False, False, True]), \
             patch.object(main, 'single_wall_confirmation_matches', return_value=True) as confirm, \
             patch.object(main, 'wall_batch_confirmation_matches') as batch_confirm, \
             patch.object(upgrades, 'scroll_builders_to_top'):
            self.assertEqual(app.upgrade_walls_to_reserve(object(), independent=True, max_batches=1), 1)
        confirm.assert_called_once()
        batch_confirm.assert_not_called()
        self.assertEqual([call.args[2] for call in app._wall_click.call_args_list],
                         ['rempart', 'amélioration groupée or identifiée', 'confirmation remparts'])
        self.assertEqual(app._wall_click.call_args_list[-1].args[1],
                         main.layout_values('WALL_CONFIRM_BUTTON'))

    def test_unreadable_reserves_before_wall_payment_keep_attack_available(self):
        app = app_without_gui()
        app.settings = main.replace(app.settings, upgrade_recommended=False)
        app._capture = Mock(return_value=Image.new('RGB', (1920, 1080)))
        app._wait = Mock(return_value=False)
        app._wall_click = Mock()
        app.stable_reserves = Mock(side_effect=[(3_000_000, 5_809_040), None])
        app.stable_wall_group = Mock(return_value={
            'payments': {'élixir': ((66, 80), 4_000_000)}, 'add': None})
        with patch.object(main, 'find_wall_menu_item', return_value=(52, 53)), \
             patch.object(main, 'read_wall_available', return_value=1), \
             patch.object(main, 'wall_selected', side_effect=[False, False, True]), \
             patch.object(upgrades, 'scroll_builders_to_top'):
            self.assertEqual(app.upgrade_walls_to_reserve(object(), independent=True), 0)
        self.assertEqual([call.args[2] for call in app._wall_click.call_args_list], ['rempart'])
        self.assertTrue(any('attaque conservée' in message for message in app.events.queue))

    def test_unverified_balance_after_wall_payment_defers_more_walls(self):
        app = app_without_gui()
        app._capture = Mock(return_value=Image.new('RGB', (1920, 1080)))
        app._wait = Mock(return_value=False)
        app._wall_click = Mock()
        app.stable_reserves = Mock(side_effect=[(2_000_000, 2_000_000),
                                                (2_000_000, 2_000_000),
                                                (500_000, 2_000_000)])
        app.stable_wall_group = Mock(return_value={
            'payments': {'or': ((55, 80), 500_000)}, 'add': None})
        with patch.object(main, 'find_wall_menu_item', return_value=(52, 53)), \
             patch.object(main, 'read_wall_available', return_value=1), \
             patch.object(main, 'wall_selected', side_effect=[False, False, True]), \
             patch.object(main, 'single_wall_confirmation_matches', return_value=True), \
             patch.object(upgrades, 'scroll_builders_to_top'):
            self.assertEqual(app.upgrade_walls_to_reserve(object(), independent=True), 0)
        self.assertEqual(len(app._wall_click.call_args_list), 3)
        self.assertTrue(any('autres remparts reportés, attaque conservée' in message
                            for message in app.events.queue))

    def test_group_buttons_follow_five_and_six_button_rows(self):
        cases = [('wall_group_no_ten.png',41.8,50.1,58.3,500000),
                 ('wall_group_background.png',41.8,50.1,58.3,500000),
                 ('wall_group_two_no_ten.png',41.8,50.1,58.3,1000000),
                 ('builders_one_wall_group.png',45.9,54.2,62.4,1000000)]
        for filename,add,gold,elixir,price in cases:
            with self.subTest(filename=filename), Image.open(Path(__file__).parent/'testdata'/filename) as image:
                controls=main.wall_group_controls(image)
                self.assertIsNotNone(controls)
                self.assertAlmostEqual(controls['add'][0],add,delta=.3)
                self.assertEqual(set(controls['payments']),{'or','élixir'})
                for resource,x in [('or',gold),('élixir',elixir)]:
                    point,cost=controls['payments'][resource]
                    self.assertAlmostEqual(point[0],x,delta=.3)
                    self.assertTrue(78 < point[1] < 84)
                    self.assertEqual(cost,price)

    def test_compact_wall_group_detects_small_active_add_one(self):
        with Image.open(Path(__file__).parent/'testdata/wall_group_compact_1323.png') as image:
            for size in ((1323,744),(1387,780),(1920,1080),(2560,1440)):
                with self.subTest(size=size):
                    controls=main.wall_group_controls(image.resize(size))
                    self.assertIsNotNone(controls)
                    self.assertTrue(48 < controls['add'][0] < 51)
                    self.assertEqual(controls['payments']['élixir'][1],4_000_000)
                    if 'or' in controls['payments']:
                        self.assertEqual(controls['payments']['or'][1],4_000_000)

    def test_army_camp_is_never_a_wall_group(self):
        with Image.open(Path(__file__).parent/'testdata/wall_wrong_army_camp.png') as image:
            self.assertIsNone(main.wall_group_controls(image))

    def test_seven_digit_wall_price_keeps_its_leading_digit(self):
        with Image.open(Path(__file__).parent/'testdata/wall_price_1200000.png') as strip:
            image=Image.new('RGB',(1920,1080))
            image.paste(strip,(400,720))
            controls=main.wall_group_controls(image)
            self.assertIsNotNone(controls)
            self.assertEqual(controls['payments']['or'][1],1200000)
            self.assertEqual(controls['payments']['élixir'][1],1200000)

    def test_group_controls_survive_unreadable_remove_label(self):
        with Image.open(Path(__file__).parent/'testdata/wall_remove_ocr_missed.png') as strip:
            image=Image.new('RGB',(1920,1080))
            image.paste(strip,(400,720))
            controls=main.wall_group_controls(image)
            self.assertIsNotNone(controls)
            self.assertIsNone(controls['remove'])
            self.assertEqual(controls['payments']['or'][1],600000)
            self.assertEqual(controls['payments']['élixir'][1],600000)

    def test_add_one_is_selected_when_ocr_only_reads_disabled_add_ten(self):
        with Image.open(Path(__file__).parent/'testdata/wall_add_ten_disabled.png') as strip:
            image=Image.new('RGB',(1920,1080))
            image.paste(strip,(400,720))
            controls=main.wall_group_controls(image)
            self.assertIsNotNone(controls)
            self.assertAlmostEqual(controls['add'][0],45.95,delta=.3)
            self.assertEqual(controls['payments']['or'][1],6600000)

    def test_expected_price_keeps_panel_when_more_label_is_temporarily_unreadable(self):
        with Image.open(Path(__file__).parent/'testdata/wall_add_ten_disabled.png') as strip:
            image=Image.new('RGB',(1920,1080))
            image.paste(strip,(400,720))
            with patch.object(main, 'wall_multi_mode', return_value=False), \
                    patch.object(main, 'find_wall_more_button', return_value=None):
                self.assertIsNone(main.wall_group_controls(image))
                controls=main.wall_group_controls(image,expected_price=6600000,expected_resource='or')
            self.assertIsNotNone(controls)
            self.assertEqual(controls['payments']['or'][1],6600000)

    def test_elixir_payment_survives_one_spurious_large_reading(self):
        with Image.open(Path(__file__).parent/'testdata/wall_elixir_price_vote.png') as strip:
            image=Image.new('RGB',(1920,1080))
            image.paste(strip,(400,720))
            controls=main.wall_group_controls(image)
            self.assertIsNotNone(controls)
            self.assertEqual(controls['payments']['or'][1],600000)
            self.assertEqual(controls['payments']['élixir'][1],600000)

    def test_expected_price_recovers_ocr_six_at_ten_walls(self):
        with Image.open(Path(__file__).parent/'testdata/wall_elixir_six_million.png') as strip:
            image=Image.new('RGB',(1920,1080))
            image.paste(strip,(400,720))
            self.assertIsNone(main.wall_group_controls(image))
            controls=main.wall_group_controls(image,expected_price=6000000,expected_resource='élixir')
            self.assertIsNotNone(controls)
            self.assertEqual(controls['payments']['élixir'][1],6000000)

    def test_expected_price_removes_ocr_digit_after_elixir_amount(self):
        with Image.open(Path(__file__).parent/'testdata/wall_elixir_trailing_one.png') as strip:
            image=Image.new('RGB',(1920,1080))
            image.paste(strip,(400,720))
            self.assertEqual(main.wall_group_controls(image)['payments']['élixir'][1],18000001)
            controls=main.wall_group_controls(image,expected_price=1800000,expected_resource='élixir')
            self.assertEqual(controls['payments']['élixir'][1],1800000)

    def test_wrong_screen_after_one_add_prevents_further_wall_clicks(self):
        app=app_without_gui();app._capture=Mock(return_value=object())
        app._wall_click=Mock();app._wait=Mock()
        app.stable_reserves=Mock(return_value=(6000000,8000000))
        controls={'add':(41.8,80),'remove':(33.6,80),'payments':{'or':((50,80),500000),'élixir':((58.3,80),500000)}}
        app.stable_wall_group=Mock(side_effect=[controls,None,None])
        with patch.object(upgrades,'scroll_builders_to_top'),patch.object(main,'builders_menu_open',return_value=True),patch.object(main,'find_wall_menu_item',return_value=(44,54)),patch.object(main,'read_wall_available',return_value=7),patch.object(main,'wall_selected',return_value=True),patch.object(main,'find_wall_more_button',return_value=(46,85)),patch.object(main,'wall_multi_mode',return_value=True):
            self.assertEqual(app.upgrade_walls_to_reserve('window',independent=True), 0)
        self.assertEqual([c.args[1] for c in app._wall_click.call_args_list],[(44,54),(46,85),(41.8,80)])

    def test_stable_group_waits_for_new_price_after_add(self):
        app=app_without_gui()
        app._capture=Mock(return_value=object())
        app._wait=Mock()
        old={'add':(45.9,80),'remove':(33.6,80),'payments':{'or':((50,80),600000)}}
        new={'add':(45.9,80),'remove':(33.6,80),'payments':{'or':((50,80),1200000)}}
        with patch.object(main,'wall_group_controls',side_effect=[old,old,new,new]):
            self.assertEqual(app.stable_wall_group('window','or',price_above=600000),new)
        self.assertEqual(app._capture.call_count,4)

    def test_stable_group_accepts_matching_nonconsecutive_price_reads(self):
        app=app_without_gui()
        app._capture=Mock(return_value=object())
        app._wait=Mock()
        truncated={'add':(50,80),'payments':{'élixir':((66,80),400000)}}
        full={'add':(50,80),'payments':{'élixir':((66,80),4_000_000)}}
        with patch.object(main,'wall_group_controls',side_effect=[truncated,full,None,full]):
            self.assertEqual(app.stable_wall_group('window'),full)
        self.assertEqual(app._capture.call_count,4)

    def test_unchanged_add_price_retries_before_spending(self):
        app=app_without_gui()
        app._capture=Mock(return_value=object())
        app._wall_click=Mock()
        app._wait=Mock()
        app.stable_reserves=Mock(side_effect=[(6000000,6000000),(6000000,6000000),(5000000,6000000),(1000000,1000000)])
        old={'add':(45.9,80),'remove':(33.6,80),'payments':{'or':((50,80),500000),'élixir':((58.3,80),500000)}}
        new={'add':(45.9,80),'remove':(33.6,80),'payments':{'or':((50,80),1000000),'élixir':((58.3,80),1000000)}}
        app.stable_wall_group=Mock(side_effect=[old,None,old,new,new])
        with patch.object(upgrades,'scroll_builders_to_top'),patch.object(main,'builders_menu_open',return_value=True),patch.object(main,'find_wall_menu_item',return_value=(44,54)),patch.object(main,'read_wall_available',return_value=2),patch.object(main,'wall_selected',return_value=True),patch.object(main,'find_wall_more_button',return_value=(46,85)),patch.object(main,'wall_multi_mode',return_value=True),patch.object(main,'wall_batch_confirmation_matches',return_value=True):
            self.assertEqual(app.upgrade_walls_to_reserve('window',independent=True),2)
        labels=[c.args[2] for c in app._wall_click.call_args_list]
        self.assertEqual(labels.count('ajouter un rempart identifié'),2)
        self.assertEqual(labels.count('confirmation remparts'),1)

    def test_delayed_wall_group_is_waited_for_before_reading_controls(self):
        app=app_without_gui()
        app._capture=Mock(return_value=object())
        app._wall_click=Mock()
        app._wait=Mock()
        app.stable_reserves=Mock(return_value=(1100000,1100000))
        controls={'add':(45.9,80),'remove':None,'payments':{'or':((50,80),600000),'élixir':((58.3,80),600000)}}
        app.stable_wall_group=Mock(return_value=controls)
        with patch.object(upgrades,'scroll_builders_to_top'),patch.object(main,'builders_menu_open',return_value=True),patch.object(main,'find_wall_menu_item',return_value=(44,54)),patch.object(main,'find_wall_menu_items',return_value=[]),patch.object(main,'read_wall_available',return_value=265),patch.object(main,'wall_selected',return_value=True),patch.object(main,'find_wall_more_button',return_value=(46,85)),patch.object(main,'wall_multi_mode',side_effect=[False,False,True]),patch.object(main.WindowDriver,'scroll_menu',return_value=True):
            self.assertEqual(app.upgrade_walls_to_reserve('window',independent=True),0)
        labels=[c.args[2] for c in app._wall_click.call_args_list]
        self.assertEqual(labels.count('Améliorer plus'),1)
        app._wait.assert_any_call(.3)

    def test_unaffordable_wall_is_not_reselected_when_quantity_ocr_changes(self):
        app=app_without_gui()
        app._capture=Mock(return_value=object())
        app._wall_click=Mock()
        app._wait=Mock()
        app.stable_reserves=Mock(return_value=(3_466_604,1_320_672))
        app.stable_wall_group=Mock(return_value={
            'add':None,'remove':None,
            'payments':{'or':((58,80),4_000_000),'élixir':((66,80),4_000_000)}})
        quantities=iter((1,1,216))
        with patch.object(upgrades,'scroll_builders_to_top'), \
                patch.object(main,'builders_menu_open',return_value=True), \
                patch.object(main,'find_wall_menu_item',return_value=(41,56)), \
                patch.object(main,'find_wall_menu_items',return_value=[(41,56)]), \
                patch.object(main,'read_wall_available',side_effect=lambda *_: next(quantities,216)), \
                patch.object(main,'read_wall_menu_price',return_value=4_000_000), \
                patch.object(main,'wall_selected',return_value=True), \
                patch.object(main,'find_wall_more_button') as more, \
                patch.object(main.WindowDriver,'scroll_menu',return_value=True):
            self.assertEqual(app.upgrade_walls_to_reserve('window',independent=True),0)
        more.assert_not_called()
        self.assertEqual(app._wall_click.call_count,1)

    def test_full_cycle_does_not_attack_after_unconfirmed_walls(self):
        app=app_without_gui()
        app.settings=main.replace(app.settings,upgrade_recommended=False)
        app.collect_village_resources=Mock()
        app.upgrade_walls_to_reserve=Mock(side_effect=RuntimeError('remparts non confirmés'))
        app.open_search=Mock()
        with patch.object(main.WindowDriver,'resolve',return_value=object()):
            app.farm_loop()
        app.open_search.assert_not_called()

    def test_wall_more_label_on_observed_background(self):
        with Image.open(Path(__file__).parent/'testdata/wall_more_background.png') as image:
            self.assertTrue(main.builders_menu_open(image))
            point = main.find_wall_more_button(image)
            self.assertIsNotNone(point)
            self.assertTrue(43 < point[0] < 49 and 81 < point[1] < 87)

    def test_army_and_heroes_share_one_straight_attack_edge(self):
        app = app_without_gui()
        app._wait = Mock()
        app._battle_capture = Mock(return_value=object())
        app._click = Mock(return_value=True)
        with patch.object(app, 'deploy_unit', return_value=1) as deploy, patch.object(main, 'hero_layout_shift', return_value=0), patch.object(main, 'hero_card_present', return_value=True), patch.object(main, 'hero_icon_saturation', return_value=100), patch.object(main, 'hero_placeholder_slot', return_value=False), patch.object(main, 'hero_health_visible', side_effect=[False,False,True]*4):
            app.deploy_attack_composition('window')
        line = deploy.call_args_list[0].args[3]
        self.assertEqual(line, deploy.call_args_list[1].args[3])
        x0,y0=line[0]; x1,y1=line[-1]
        self.assertGreater(abs(x1-x0), 15)
        for x,y in line:
            self.assertLess(x, 50)
            self.assertAlmostEqual((x-x0)*(y1-y0), (y-y0)*(x1-x0))
        drops=[c.args[1:] for c in app._click.call_args_list][1::2]
        self.assertEqual(len(drops), 4)
        self.assertTrue(all(p in line for p in drops))
        self.assertTrue(all(c.args[0] <= .12 for c in app._wait.call_args_list))

    def test_hdv_waits_for_other_rows_and_running_builders(self):
        image=Image.new('RGB',(1920,1080))
        words=[('Améliorations',10,10),('suggérées',40,10),('Hôtel',15,25),('de',30,25),('ville',40,25),('3000000',85,25),('Autres',15,40),('améliorations',45,40)]
        with patch.object(upgrades,'builder_count',return_value=(5,5)),patch.object(main,'read_word_centers',return_value=words):
            self.assertTrue(upgrades.town_hall_ready(image))
        with patch.object(upgrades,'builder_count',return_value=(5,5)),patch.object(main,'read_word_centers',return_value=words+[('illisible',20,55)]):
            self.assertFalse(upgrades.town_hall_ready(image))
        with patch.object(upgrades,'builder_count',return_value=(4,5)),patch.object(main,'read_word_centers',return_value=words):
            self.assertFalse(upgrades.town_hall_ready(image))

    def test_other_section_is_now_available_after_recommendations(self):
        with Image.open(Path(__file__).parent/'testdata/builders_selected_menu.png') as im:
            items=upgrades.suggested_items(im,include_others=True)
            self.assertTrue(items)
            self.assertTrue(all(not upgrades.is_town_hall(item[0]) for item in items))
            self.assertTrue(any('ressort' in upgrades.normal(item[0]) for item in items))

    def test_costliest_payable_building_is_chosen_across_menu_pages(self):
        app = app_without_gui()
        app._capture = Mock(return_value=Image.new('RGB', (1920, 1080)))
        app._wait = Mock()
        app._trace = Mock()
        position = [0]
        pages = {
            0: [('Petit piège', 25, 500_000, 'or'),
                ('Prix OCR erroné', 29, 6_800_002, 'or'),
                ('Hôtel de ville', 35, 4_000_000, 'or')],
            1: [('Grand bâtiment', 45, 2_000_000, 'élixir')],
            2: [('Grand bâtiment', 15, 2_000_000, 'élixir'),
                ('Bâtiment moyen', 55, 1_000_000, 'or')],
        }

        def scroll(window, delta=-120):
            position[0] = 0 if delta > 0 else min(2, position[0] + 1)
            return True

        def visible_items(image, include_others=False, include_town_hall=False):
            if not include_others:
                return []
            return [item for item in pages[position[0]]
                    if include_town_hall or not upgrades.is_town_hall(item[0])]

        with patch.object(main.WindowDriver, 'scroll_menu', side_effect=scroll), \
                patch.object(main, 'builders_menu_open', return_value=True), \
                patch.object(upgrades, 'scroll_builders_to_top', side_effect=lambda app,window: position.__setitem__(0,0)), \
                patch.object(main, 'read_text', side_effect=lambda *args, **kwargs: str(position[0])), \
                patch.object(upgrades, 'suggested_items', side_effect=visible_items):
            choice = upgrades.find_payable_upgrade(app, 'window', 3, (10_000_000, 2_100_000))
        self.assertEqual(choice, pages[1][0])
        self.assertEqual(position[0], 1)

    def test_menu_stall_uses_row_positions_despite_ocr_variation(self):
        previous = [(18, 'teslacamouflee'), (26, 'bombeaerienne'),
                    (34, 'piegearessort'), (42, 'catapulteexplosive')]
        same_page = [(18.2, 'teslacamouplée'), (26.1, 'bombeaerienne'),
                     (33.9, 'piegearessor'), (42.1, 'catapulteexplosive')]
        moving_page = [(23, label) for _, label in previous]
        self.assertTrue(upgrades.menu_rows_stationary(previous, same_page))
        self.assertFalse(upgrades.menu_rows_stationary(previous, moving_page))

    def test_conflicting_price_on_stationary_row_is_not_a_payable_upgrade(self):
        app = app_without_gui()
        app._capture = Mock(return_value=Image.new('RGB', (1323, 744)))
        app._wait = Mock()
        app._trace = Mock()
        prices = iter((300_000, 3_000_000, 300_000))
        rows = [(20, 'bombeaerienne'), (30, 'piegearessort'), (40, 'teslacamouflee')]

        def items(_image, include_others=False, include_town_hall=False):
            return [('Bombe aérienne x7', 33.9, next(prices), 'or')] if include_others else []

        with patch.object(upgrades, 'scroll_builders_to_top'), \
                patch.object(upgrades, 'suggested_items', side_effect=items), \
                patch.object(upgrades, 'menu_anchor_rows', return_value=rows), \
                patch.object(main, 'builders_menu_open', return_value=True), \
                patch.object(main, 'read_text', return_value='same'), \
                patch.object(main.WindowDriver, 'scroll_menu', return_value=True):
            self.assertIsNone(upgrades.find_payable_upgrade(app, 'window', 2, (1_000_000, 1_000_000)))
        self.assertTrue(any('Prix contradictoires' in call.args[1]
                            for call in app._trace.call_args_list))

    def test_closed_builder_menu_never_scrolls_the_village(self):
        app = app_without_gui()
        app._capture = Mock(return_value=Image.new('RGB', (1323, 744)))
        app._trace = Mock()
        with patch.object(main, 'builders_menu_open', return_value=False), \
             patch.object(main.WindowDriver, 'scroll_menu') as scroll:
            with self.assertRaisesRegex(RuntimeError, 'Liste des ouvriers absente'):
                upgrades.scroll_builders_to_top(app, 'window')
        scroll.assert_not_called()

    def test_automatic_walls_require_a_confirmed_free_builder(self):
        for free in (None,0):
            app=app_without_gui()
            app.stable_reserves=Mock()
            app._wall_click=Mock()
            with patch.object(upgrades,'stable_builders',return_value=free):
                self.assertEqual(app.upgrade_walls_to_reserve(object()),0)
            app.stable_reserves.assert_not_called()
            app._wall_click.assert_not_called()

    def test_automatic_walls_use_any_confirmed_builder_and_preserve_reserves(self):
        for free in (1,2,3,5):
            app=app_without_gui()
            app.stable_reserves=Mock(return_value=(1000000,1000000))
            with patch.object(upgrades,'stable_builders',return_value=free):
                app.upgrade_walls_to_reserve(object())
            app.stable_reserves.assert_called_once()

    def test_grouped_wall_quantity_jump_uses_verified_price(self):
        app=app_without_gui()
        app._capture=Mock(return_value=object())
        app._wall_click=Mock()
        app._wait=Mock()
        app.stable_reserves=Mock(side_effect=[(6000000,6000000),(6000000,6000000),(3000000,6000000),(1000000,1000000)])
        initial={'add':(45.9,80),'remove':(33.6,80),'payments':{'or':((50,80),500000),'élixir':((58.3,80),500000)}}
        after_add={'add':(41.8,80),'remove':(33.6,80),'payments':{'or':((50,80),3000000)}}
        app.stable_wall_group=Mock(side_effect=[initial,after_add,after_add])
        with patch.object(upgrades,'scroll_builders_to_top'),patch.object(main,'builders_menu_open',return_value=True),patch.object(main,'find_wall_menu_item',return_value=(44,54)),patch.object(main,'read_wall_available',return_value=6),patch.object(main,'wall_selected',return_value=True),patch.object(main,'find_wall_more_button',return_value=(46,85)),patch.object(main,'wall_multi_mode',return_value=True),patch.object(main,'wall_batch_confirmation_matches',return_value=True):
            self.assertEqual(app.upgrade_walls_to_reserve('window',independent=True),6)
        self.assertEqual([c.args[1] for c in app._wall_click.call_args_list],[(44,54),(46,85),(45.9,80),(50,80),main.layout_values('WALL_MULTI_CONFIRM_BUTTON')])

    def test_independent_attack_does_not_run_other_actions_or_change_settings(self):
        app=app_without_gui()
        original=app.settings
        def attack():
            self.assertFalse(app.settings.chain_attacks)
            self.assertFalse(app.settings.upgrade_recommended)
            self.assertFalse(app.settings.upgrade_wall_between_attacks)
        app.farm_loop=Mock(side_effect=attack)
        with patch.object(main.WindowDriver,'resolve',return_value=object()):
            app.independent_loop('attack')
        app.farm_loop.assert_called_once()
        self.assertIs(app.settings,original)

    def test_event_never_falls_back_to_a_troop(self):
        image=Image.new('RGB',(1920,1080),(150,170,200))
        with patch.object(main,'read_text',return_value='Dragon événement'):
            self.assertIsNone(main.battle_reward_choice(image))
        with patch.object(main,'read_text',return_value=''):
            self.assertIsNone(main.battle_reward_choice(image))

    def test_event_tickets_are_allowed_but_resources_win(self):
        image=Image.new('RGB',(1920,1080),(150,170,200))
        with patch.object(main,'read_text',side_effect=['100 tickets']*2+['Dragon']*4):
            self.assertEqual(main.battle_reward_choice(image)[0],(30,53))
        with patch.object(main,'read_text',side_effect=['100 tickets']*2+['Dragon']*2+['500 000 OR']*2):
            self.assertEqual(main.battle_reward_choice(image)[0],(70,53))

    def test_last_builder_blocks_entire_upgrade_path(self):
        app=app_without_gui()
        app._wall_click=Mock()
        app.stable_reserves=Mock()
        with patch.object(upgrades,'stable_builders',return_value=1):
            self.assertEqual(upgrades.upgrade_suggested(app,object()),0)
        app._wall_click.assert_not_called()
        app.stable_reserves.assert_not_called()

    def test_unreadable_builder_counter_blocks_spending(self):
        app=app_without_gui()
        app._wall_click=Mock()
        with patch.object(upgrades,'stable_builders',return_value=None):
            self.assertEqual(upgrades.upgrade_suggested(app,object()),0)
        app._wall_click.assert_not_called()

    def test_queen_health_with_yellow_gradient_is_detected(self):
        with Image.open(Path(__file__).parent/'testdata/queen_bar_missed.png') as im:
            self.assertTrue(main.hero_health_visible(im,1,-6.25))
            self.assertFalse(main.hero_health_visible(im,2,-6.25))

    def test_last_builder_is_reserved_and_buildings_use_available_resources(self):
        for free in (None,0,1):
            self.assertFalse(upgrades.can_start_upgrade(free,10_000_000,500_000))
        self.assertFalse(upgrades.can_start_upgrade(2,499_999,500_000))
        self.assertTrue(upgrades.can_start_upgrade(2,500_000,500_000))
        self.assertTrue(upgrades.can_start_upgrade(2,1_499_999,500_000))

    def test_workers_on_real_home_screens(self):
        for filename, count in [('builders_one_wall_group.png',1),('builders_two.png',2),('builders_four.png',4),('builders_five.png',5),('builders_selected_menu.png',4)]:
            with Image.open(Path(__file__).parent/'testdata'/filename) as im:
                self.assertEqual(upgrades.builder_count(im),count)

    def test_only_suggested_section_is_selected(self):
        with Image.open(Path(__file__).parent/'testdata/suggested_menu.png') as im:
            items=upgrades.suggested_items(im)
        self.assertEqual(len(items),1)
        self.assertEqual((items[0][0],items[0][2],items[0][3]),('Piège à ressort',500000,'or'))

    def test_expensive_vm_builder_rows_keep_separate_price_and_icon_crops(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'builders_expensive_1765.png') as image:
            items = upgrades.suggested_items(image, include_others=True)
            suggested = upgrades.suggested_items(image)
        self.assertTrue(any('sorciers' in title and cost == 5_500_000 and resource == 'or'
                            for title, _, cost, resource in items))
        self.assertTrue(any('Catapulte' in title and cost == 4_000_000 and resource == '\u00e9lixir'
                            for title, _, cost, resource in items))
        self.assertTrue(any('sorciers' in title and cost == 5_500_000 for title, _, cost, _ in suggested))

    def test_compact_builder_price_excludes_elixir_icon(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'builders_current_1323.png') as image:
            items = upgrades.suggested_items(image, include_others=True)
        self.assertTrue(any('Catapulte explosive' in title and cost == 4_000_000
                            and resource == 'élixir' for title, _, cost, resource in items))
        self.assertFalse(any(cost == 4_400_000 for _, _, cost, _ in items))
        self.assertFalse(any('mpart' in title.lower() for title, _, _, _ in items))

    def test_compact_catapult_direct_upgrade_requires_matching_price_resource_and_green_button(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'catapult_selected_1323.png') as image:
            self.assertEqual(upgrades.direct_upgrade_button(image, 'Catapulte explosive', 4_000_000, 'élixir'),
                             (83.0, 58.0))
            self.assertIsNone(upgrades.direct_upgrade_button(image, 'Catapulte explosive', 3_000_000, 'élixir'))
            self.assertIsNone(upgrades.direct_upgrade_button(image, 'Catapulte explosive', 4_000_000, 'or'))
            self.assertIsNone(upgrades.direct_upgrade_button(image, 'Tour de sorciers', 4_000_000, 'élixir'))

    def test_compact_hero_eradicator_direct_upgrade_requires_exact_cost_and_resource(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'hero_eradicator_selected_1323.png') as image:
            self.assertEqual(upgrades.direct_upgrade_button(image, 'Éradicateur de héros', 6_000_000, 'élixir'),
                             (83.0, 43.0))
            self.assertIsNone(upgrades.direct_upgrade_button(image, 'Éradicateur de héros', 5_000_000, 'élixir'))
            self.assertIsNone(upgrades.direct_upgrade_button(image, 'Éradicateur de héros', 6_000_000, 'or'))
            self.assertIsNone(upgrades.direct_upgrade_button(image, 'Catapulte explosive', 6_000_000, 'élixir'))
            for size in ((1387,780),(1920,1080),(2560,1440)):
                with self.subTest(size=size):
                    scaled=image.resize(size)
                    point=upgrades.direct_upgrade_button(scaled,'Éradicateur de héros',6_000_000,'élixir')
                    self.assertIsNotNone(point)
                    self.assertTrue(82 <= point[0] <= 84 and 39 <= point[1] <= 45)

    def test_direct_upgrade_waits_for_delayed_confirmation_panel(self):
        app=app_without_gui()
        app._capture=Mock(return_value=object())
        app._wall_click=Mock()
        app._wait=Mock()
        app.stable_reserves=Mock(return_value=(3_466_604,7_320_672))
        with patch.object(upgrades,'stable_builders',return_value=2), \
                patch.object(upgrades,'suggested_items',return_value=[('Éradicateur de héros',54,6_000_000,'élixir')]), \
                patch.object(upgrades,'direct_upgrade_button',side_effect=[None,(83,43)]), \
                patch.object(upgrades,'confirmation_headings',return_value=[]), \
                patch.object(main,'builders_menu_open',return_value=True):
            self.assertEqual(upgrades.perform_direct_upgrade(app,'window','Éradicateur de héros',
                                                              6_000_000,'élixir'),
                             (2,(3_466_604,7_320_672)))
        app._wait.assert_called_once_with(.4)
        self.assertEqual(app._wall_click.call_args_list[-1].args[1],(83,43))

    def test_compact_canon_panel_and_confirmation_require_exact_price(self):
        with Image.open(Path(__file__).parent/'testdata/canon_selected_1323.png') as image:
            self.assertTrue(upgrades.selected_panel_matches(image,'anon',3_000_000,'or'))
            self.assertFalse(upgrades.selected_panel_matches(image,'anon',3_200_000,'or'))
            self.assertFalse(upgrades.selected_panel_matches(image,'anon',3_000_000,'élixir'))
        with Image.open(Path(__file__).parent/'testdata/canon_confirmation_1323.png') as image:
            self.assertTrue(any(upgrades.title_matches_heading('anon', heading)
                                for heading in upgrades.confirmation_headings(image)))
            self.assertEqual(upgrades.confirmation_cost(image),3_000_000)

    def test_compact_two_button_panel_has_a_different_price_position(self):
        with Image.open(Path(__file__).parent/'testdata/bomb_aerial_overlay_1323.png') as image:
            self.assertTrue(upgrades.selected_panel_matches(image,'ombe aérienne',3_000_000,'or'))
            self.assertFalse(upgrades.selected_panel_matches(image,'ombe aérienne',3_200_000,'or'))

    def test_selected_wizard_tower_requires_title_price_and_resource(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'wizard_selected_1765.png') as image:
            self.assertTrue(upgrades.selected_panel_matches(image, 'our de sorciers', 5_500_000, 'or'))
            self.assertFalse(upgrades.selected_panel_matches(image, "our d'archères", 5_500_000, 'or'))
            self.assertFalse(upgrades.selected_panel_matches(image, 'our de sorciers', 4_000_000, 'or'))

    def test_wizard_confirmation_cost_recovers_stylized_five(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'wizard_confirmation_1765.png') as image:
            self.assertEqual(upgrades.confirmation_cost(image), 5_500_000)

    def test_six_digit_gold_balance_after_building_upgrade(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'wizard_upgraded_1765.png') as image:
            self.assertEqual(main.read_safe_reserve(image, 'gold'), 654_905)
            self.assertEqual(upgrades.builder_count(image), 2)

    def test_gold_balance_keeps_leading_one_after_single_wall_purchase(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'reserve_gold_after_wall_1323.png') as image:
            self.assertEqual(main.read_safe_reserve(image, 'gold'), 1_830_265)
            self.assertEqual(main.read_safe_reserve(image, 'elixir'), 3_614_231)

    def test_gold_balance_keeps_leading_one_after_group_wall_purchase(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'reserve_gold_after_group_wall_1323.png') as image:
            self.assertEqual(main.read_safe_reserve(image, 'gold'), 1_307_362)
            self.assertEqual(main.read_safe_reserve(image, 'elixir'), 3_067_265)

    def test_gold_balance_on_selected_wall_uses_two_thresholds(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'reserve_gold_3003444_1323.png') as image:
            self.assertEqual(main.read_safe_reserve(image, 'gold'), 3_003_444)
            self.assertEqual(main.read_safe_reserve(image, 'elixir'), 5_809_040)

    def test_gold_balance_after_wall_keeps_leading_one_at_new_price(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'reserve_gold_1587926_1323.png') as image:
            self.assertEqual(main.read_safe_reserve(image, 'gold'), 1_587_926)
            self.assertEqual(main.read_safe_reserve(image, 'elixir'), 4_775_582)

    def test_elixir_balance_survives_animated_village_background(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'reserve_elixir_stylized_1323.png') as image:
            self.assertEqual(main.read_safe_reserve(image, 'gold'), 3_828_394)
            self.assertEqual(main.read_safe_reserve(image, 'elixir'), 5_306_572)

    def test_elixir_balance_keeps_leading_one_after_wall_purchase(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'reserve_elixir_after_wall_1323.png') as image:
            self.assertEqual(main.read_safe_reserve(image, 'elixir'), 1_306_572)

    def test_reserves_survive_partial_and_conflicting_ocr(self):
        with Image.open(Path(__file__).parent/'testdata/reserves_one_million.png') as im:
            self.assertEqual(main.read_safe_reserve(im,'gold'),1020684)
            self.assertEqual(main.read_safe_reserve(im,'elixir'),1015690)

    def test_wall_row_at_bottom_of_builder_menu(self):
        with Image.open(Path(__file__).parent/'testdata/builders_selected_menu.png') as im:
            item=main.find_wall_menu_item(im)
            self.assertIsNotNone(item)
            self.assertEqual(main.read_wall_available(im,item),74)

    def test_town_hall_is_excluded_from_real_recommendations(self):
        with Image.open(Path(__file__).parent/'testdata/builders_selected_menu.png') as im:
            self.assertEqual(upgrades.suggested_items(im),[])
        for title in ('Hôtel de ville','Hotel de ville','HDV','Hôbel deuille'):
            self.assertTrue(upgrades.is_town_hall(title))
        self.assertFalse(upgrades.is_town_hall('Piège à ressort'))

    def test_town_hall_unlocks_only_when_other_section_contains_walls(self):
        words = [('Ameliorations', 10, 5), ('suggerees', 30, 5),
                 ('Hotel', 10, 20), ('de', 20, 20), ('ville', 30, 20),
                 ('Autres', 10, 40), ('rempart', 10, 50), ('x74', 30, 50),
                 ('500000', 50, 50)]
        with patch.object(upgrades, 'builder_count', return_value=(5,5)), \
             patch.object(main, 'read_word_centers', return_value=words):
            self.assertTrue(upgrades.town_hall_ready(Image.new('RGB',(100,100))))

    def test_town_hall_stays_locked_when_another_building_remains(self):
        words = [('Ameliorations', 10, 5), ('suggerees', 30, 5),
                 ('Hotel', 10, 20), ('de', 20, 20), ('ville', 30, 20),
                 ('Autres', 10, 40), ('Caserne', 10, 50), ('2800000', 50, 50)]
        with patch.object(upgrades, 'builder_count', return_value=(5,5)), \
             patch.object(main, 'read_word_centers', return_value=words):
            self.assertFalse(upgrades.town_hall_ready(Image.new('RGB',(100,100))))

    def test_observed_spring_label_ocr_variant(self):
        self.assertEqual(upgrades.normal('Piège à ressorc'),upgrades.normal('Piège à ressort'))
        self.assertNotEqual(upgrades.normal('Piège à ressort'),upgrades.normal('Bombe géante'))

    def test_gold_digits_survive_background_interference(self):
        with Image.open(Path(__file__).parent/'testdata/reserve_gold_background.png') as im:
            self.assertEqual(main.read_safe_reserve(im,'gold'),3496839)

    def test_elixir_digits_survive_background_interference(self):
        with Image.open(Path(__file__).parent/'testdata/reserve_elixir_background.png') as im:
            self.assertEqual(main.read_safe_reserve(im,'elixir'),2685294)

    def test_remove_wall_button_is_read_from_actual_group(self):
        with Image.open(Path(__file__).parent/'testdata/builders_one_wall_group.png') as im:
            point=main.find_wall_remove_button(im,-4.1)
            self.assertIsNotNone(point)
            self.assertAlmostEqual(point[0],29.5,delta=.5)
