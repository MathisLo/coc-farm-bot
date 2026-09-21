import unittest
from pathlib import Path
from PIL import Image
from unittest.mock import Mock, patch
from test_regressions import app_without_gui
import main
import upgrades


class UpgradeTests(unittest.TestCase):
    def test_many_running_builders_do_not_hide_suggested_section(self):
        with Image.open(Path(__file__).parent/'testdata/new_account_builder_menu.png') as im:
            app = app_without_gui()
            app._capture = Mock(return_value=im)
            app._wait = Mock(return_value=False)
            with patch.object(main.WindowDriver, 'scroll_menu', return_value=True) as scroll:
                upgrades.scroll_builders_to_top(app, 'window')
            scroll.assert_not_called()

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
            with self.assertRaisesRegex(RuntimeError, 'Améliorer plus introuvable'):
                app.upgrade_walls_to_reserve('window', independent=True)
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
            with self.assertRaisesRegex(RuntimeError, 'Améliorer plus introuvable'):
                app.upgrade_walls_to_reserve('window', independent=True)
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
            self.assertIsNotNone(main.find_wall_menu_item(im))
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

    def test_unresponsive_more_button_is_retried_before_reading_group(self):
        app=app_without_gui()
        app._capture=Mock(return_value=object())
        app._wall_click=Mock()
        app._wait=Mock()
        app.stable_reserves=Mock(return_value=(1100000,1100000))
        controls={'add':(45.9,80),'remove':None,'payments':{'or':((50,80),600000),'élixir':((58.3,80),600000)}}
        app.stable_wall_group=Mock(return_value=controls)
        with patch.object(upgrades,'scroll_builders_to_top'),patch.object(main,'builders_menu_open',return_value=True),patch.object(main,'find_wall_menu_item',return_value=(44,54)),patch.object(main,'find_wall_menu_items',return_value=[]),patch.object(main,'read_wall_available',return_value=265),patch.object(main,'wall_selected',return_value=True),patch.object(main,'find_wall_more_button',return_value=(46,85)),patch.object(main,'wall_multi_mode',side_effect=[False,True]),patch.object(main.WindowDriver,'scroll_menu',return_value=True):
            self.assertEqual(app.upgrade_walls_to_reserve('window',independent=True),0)
        labels=[c.args[2] for c in app._wall_click.call_args_list]
        self.assertEqual(labels.count('Améliorer plus'),2)

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
        with patch.object(app, 'deploy_unit', return_value=1) as deploy, patch.object(main, 'hero_layout_shift', return_value=0), patch.object(main, 'hero_icon_saturation', return_value=100), patch.object(main, 'hero_placeholder_slot', return_value=False), patch.object(main, 'hero_health_visible', side_effect=[False,False,True]*3):
            app.deploy_attack_composition('window')
        line = deploy.call_args_list[0].args[3]
        self.assertEqual(line, deploy.call_args_list[1].args[3])
        x0,y0=line[0]; x1,y1=line[-1]
        self.assertGreater(abs(x1-x0), 15)
        for x,y in line:
            self.assertLess(x, 50)
            self.assertAlmostEqual((x-x0)*(y1-y0), (y-y0)*(x1-x0))
        drops=[c.args[1:] for c in app._click.call_args_list][1::2]
        self.assertEqual(len(drops), 3)
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
            return [item for item in pages[position[0]]
                    if include_town_hall or not upgrades.is_town_hall(item[0])]

        with patch.object(main.WindowDriver, 'scroll_menu', side_effect=scroll), \
                patch.object(upgrades, 'scroll_builders_to_top', side_effect=lambda app,window: position.__setitem__(0,0)), \
                patch.object(main, 'read_text', side_effect=lambda *args, **kwargs: str(position[0])), \
                patch.object(upgrades, 'suggested_items', side_effect=visible_items):
            choice = upgrades.find_payable_upgrade(app, 'window', 3, (10_000_000, 2_100_000))
        self.assertEqual(choice, pages[1][0])
        self.assertEqual(position[0], 1)

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
