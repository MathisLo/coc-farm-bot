import unittest
from pathlib import Path
from PIL import Image
from unittest.mock import Mock, patch
from test_regressions import app_without_gui
import main
import upgrades


class UpgradeTests(unittest.TestCase):
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

    def test_buildings_reserve_resources_before_automatic_walls(self):
        for free in (None,0,2,3,5):
            app=app_without_gui()
            app.stable_reserves=Mock()
            app._wall_click=Mock()
            with patch.object(upgrades,'stable_builders',return_value=free):
                self.assertEqual(app.upgrade_walls_to_reserve(object()),0)
            app.stable_reserves.assert_not_called()
            app._wall_click.assert_not_called()

    def test_last_free_builder_can_work_on_walls(self):
        app=app_without_gui()
        app.stable_reserves=Mock(return_value=(1000000,1000000))
        with patch.object(upgrades,'stable_builders',return_value=1):
            app.upgrade_walls_to_reserve(object())
        app.stable_reserves.assert_called_once()

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
