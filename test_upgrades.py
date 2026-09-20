import unittest
from pathlib import Path
from PIL import Image
from unittest.mock import Mock, patch
from test_regressions import app_without_gui
import main
import upgrades


class UpgradeTests(unittest.TestCase):
    def test_translucent_menu_does_not_select_background_wall_label(self):
        with Image.open(Path(__file__).parent/'testdata/wall_menu_background_false_row.png') as im:
            self.assertTrue(main.builders_menu_open(im))
            self.assertFalse(main.wall_menu_row_matches(im,61))
            self.assertIsNone(main.find_wall_menu_item(im))

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

    def test_wrong_screen_after_one_add_prevents_further_wall_clicks(self):
        app=app_without_gui();app._capture=Mock(return_value=object())
        app._wall_click=Mock();app._wait=Mock()
        app.stable_reserves=Mock(return_value=(6000000,8000000))
        controls={'add':(41.8,80),'remove':(33.6,80),'payments':{'or':((50,80),500000),'élixir':((58.3,80),500000)}}
        app.stable_wall_group=Mock(side_effect=[controls,None])
        with patch.object(main,'builders_menu_open',return_value=True),patch.object(main,'find_wall_menu_item',return_value=(44,54)),patch.object(main,'read_wall_available',return_value=7),patch.object(main,'wall_selected',return_value=True),patch.object(main,'find_wall_more_button',return_value=(46,85)):
            self.assertEqual(app.upgrade_walls_to_reserve('window',independent=True),0)
        self.assertEqual([c.args[1] for c in app._wall_click.call_args_list],[(44,54),(46,85),(41.8,80)])

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
        with patch.object(app, 'deploy_unit', return_value=1) as deploy, patch.object(main, 'hero_layout_shift', return_value=0), patch.object(main, 'hero_icon_saturation', return_value=100), patch.object(main, 'hero_health_visible', side_effect=[False,False,True]*3):
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
        for extra in ([('Rempart',20,55)],[('illisible',20,55)]):
            with patch.object(upgrades,'builder_count',return_value=(5,5)),patch.object(main,'read_word_centers',return_value=words+extra):
                self.assertFalse(upgrades.town_hall_ready(image))
        with patch.object(upgrades,'builder_count',return_value=(4,5)),patch.object(main,'read_word_centers',return_value=words):
            self.assertFalse(upgrades.town_hall_ready(image))

    def test_other_section_is_now_available_after_recommendations(self):
        with Image.open(Path(__file__).parent/'testdata/builders_selected_menu.png') as im:
            items=upgrades.suggested_items(im,include_others=True)
            self.assertTrue(items)
            self.assertTrue(all(not upgrades.is_town_hall(item[0]) for item in items))
            self.assertTrue(any('ressort' in upgrades.normal(item[0]) for item in items))

    def test_automatic_walls_require_a_confirmed_free_builder(self):
        for free in (None,0):
            app=app_without_gui()
            app.stable_reserves=Mock()
            app._wall_click=Mock()
            with patch.object(upgrades,'stable_builders',return_value=free):
                self.assertEqual(app.upgrade_walls_to_reserve(object()),0)
            app.stable_reserves.assert_not_called()
            app._wall_click.assert_not_called()

    def test_automatic_walls_are_considered_with_any_free_builder(self):
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
        with patch.object(main,'builders_menu_open',return_value=True),patch.object(main,'find_wall_menu_item',return_value=(44,54)),patch.object(main,'read_wall_available',return_value=6),patch.object(main,'wall_selected',return_value=True),patch.object(main,'find_wall_more_button',return_value=(46,85)),patch.object(main,'wall_batch_confirmation_matches',return_value=True):
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

    def test_last_builder_and_reserve_are_never_spent(self):
        for free in (None,0,1):
            self.assertFalse(upgrades.can_start_upgrade(free,10_000_000,500_000))
        self.assertFalse(upgrades.can_start_upgrade(2,1_499_999,500_000))
        self.assertTrue(upgrades.can_start_upgrade(2,1_500_000,500_000))

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
