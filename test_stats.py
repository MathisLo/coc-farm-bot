import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw
import main
from farm_stats import FarmStats
from test_regressions import app_without_gui


class StatisticsTests(unittest.TestCase):
    def test_result_uses_matching_readings_across_blank_or_wrong_frames(self):
        correct = (592_937, 733_074, 3_769)
        wrong = (592_937, 733_074, 2_769)
        for readings in ((correct, None, correct),
                         (correct, wrong, correct, wrong, correct)):
            with self.subTest(readings=readings), tempfile.TemporaryDirectory() as directory:
                app = app_without_gui()
                app.farm_stats = FarmStats(Path(directory) / 'stats.json')
                app.farm_stats.begin('account')
                app._battle_capture = Mock(return_value=Image.new('RGB', (1323, 744)))
                app._trace = Mock()
                app._wait = Mock()
                with patch.object(main, 'read_battle_earnings', side_effect=readings):
                    app.record_battle_earnings(object())
                self.assertEqual(app.farm_stats.data['battles'], 1)
                self.assertEqual(tuple(app.farm_stats.data[key] for key in
                                       ('gold', 'elixir', 'dark_elixir')), correct)

    def test_stylized_bonus_is_counted_on_real_vm_result(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'result_bonus_stylized_1765.png') as image:
            self.assertEqual(main.read_battle_earnings(image), (461_924, 657_042, 5_256))

    def test_mini_venom_small_result_with_outlined_digits_is_counted(self):
        with Image.open(Path(__file__).parent / 'testdata' / 'mini_venom_result_1920.png') as image:
            self.assertEqual(main.read_battle_earnings(image), (36_482, 34_902, 512))

    def test_final_reward_without_readable_top_border_is_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            app = app_without_gui()
            app.farm_stats = FarmStats(Path(directory)/'stats.json')
            app.farm_stats.begin('account')
            app._wait = Mock()
            app._click = Mock(return_value=True)
            with Image.open(Path(__file__).parent/'testdata/event_final_raised_cards.png') as source, \
                    Image.open(Path(__file__).parent/'testdata/result_bonus.png') as result:
                choice = source.copy()
                drawing = ImageDraw.Draw(choice)
                for y in (32.7, 33.4):
                    top = round(choice.height * y / 100)
                    drawing.rectangle((0, top, choice.width, top + 6), fill=(25, 25, 25))
                self.assertTrue(main.battle_reward_open(choice))
                self.assertEqual(main.battle_reward_choice(choice)[0], (30., 60.))
                home = Image.new('RGB', (1920, 1080))
                app._capture = Mock(side_effect=[choice, result, result, result, home, home])
                with patch.object(main, 'village_home_ready', side_effect=[False, True, True]):
                    self.assertTrue(app.wait_for_battle_return('window'))
            self.assertEqual([call.args[1:] for call in app._click.call_args_list],
                             [(30., 60.), main.layout_values('RETURN_HOME_BUTTON')])
            self.assertEqual(app.farm_stats.data['battles'], 1)

    def test_raised_final_reward_cards_are_selected_and_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            app = app_without_gui()
            app.farm_stats = FarmStats(Path(directory)/'stats.json')
            app.farm_stats.begin('account')
            app._wait = Mock()
            app._click = Mock(return_value=True)
            with Image.open(Path(__file__).parent/'testdata/event_final_raised_cards.png') as choice, Image.open(Path(__file__).parent/'testdata/result_bonus.png') as result:
                self.assertTrue(main.battle_reward_open(choice))
                self.assertEqual(main.battle_reward_choice(choice)[0], (30., 60.))
                app._capture = Mock(side_effect=[choice, result, result])
                app.record_battle_earnings('window')
            app._click.assert_called_once_with('window', 30., 60.)
            self.assertEqual(app.farm_stats.data['battles'], 1)
            self.assertEqual(app.farm_stats.data['gold'], 393408)

    def test_final_reward_is_selected_before_counting_result(self):
        with tempfile.TemporaryDirectory() as directory:
            app = app_without_gui()
            app.farm_stats = FarmStats(Path(directory)/'stats.json')
            app.farm_stats.begin('account')
            app._wait = Mock()
            app._click = Mock(return_value=True)
            with Image.open(Path(__file__).parent/'testdata/event_final.png') as choice, Image.open(Path(__file__).parent/'testdata/result_bonus.png') as result:
                self.assertTrue(main.battle_reward_open(choice))
                self.assertEqual(main.battle_reward_choice(choice)[0], (30., 60.))
                self.assertFalse(main.battle_reward_open(result))
                app._capture = Mock(side_effect=[choice, result, result])
                app.record_battle_earnings('window')
            app._click.assert_called_once_with('window', 30., 60.)
            self.assertEqual(app.farm_stats.data['battles'], 1)
            self.assertEqual(app.farm_stats.data['gold'], 393408)
            self.assertFalse((Path(directory)/'unread-results').exists())

    def test_unreadable_result_still_returns_home(self):
        with tempfile.TemporaryDirectory() as directory:
            app=app_without_gui()
            app.farm_stats=FarmStats(Path(directory)/'stats.json')
            app.farm_stats.begin('account')
            frame=Image.new('RGB',(30,30))
            app._capture=Mock(return_value=frame)
            app._battle_capture=Mock(return_value=frame)
            app._wait=Mock()
            app._click=Mock(return_value=True)
            with patch.object(main,'read_battle_earnings',return_value=None),patch.object(main,'village_home_ready',side_effect=[False,True,True]),patch.object(main,'has_screen_text',return_value=True):
                self.assertTrue(app.wait_for_battle_return(object()))
            app._click.assert_called_once()
            self.assertIsNone(app.farm_stats.data['pending'])

    def test_unreadable_result_is_archived_and_next_battle_can_start(self):
        with tempfile.TemporaryDirectory() as directory:
            app = app_without_gui()
            app.farm_stats = FarmStats(Path(directory)/'stats.json')
            app.farm_stats.begin('account')
            app._wait = Mock()
            app._capture = Mock(return_value=Image.new('RGB',(30,30),'red'))
            with patch.object(main,'read_battle_earnings',return_value=None):
                app.record_battle_earnings(object())
            self.assertEqual(app.farm_stats.data['gold'],0)
            self.assertEqual(app.farm_stats.data['battles'],0)
            self.assertIsNone(app.farm_stats.data['pending'])
            self.assertEqual(len(list((Path(directory)/'unread-results').glob('*.png'))),1)
            self.assertEqual(len(list((Path(directory)/'unread-results').glob('*.json'))),1)
            app.farm_stats.begin('account')
            self.assertTrue(app.farm_stats.data['pending'])

    def test_short_dark_amount_keeps_its_leading_digits(self):
        for filename in ('result_short_dark.png','result_short_dark_background.png'):
            with Image.open(Path(__file__).parent/'testdata'/filename) as im:
                self.assertEqual(main.read_battle_earnings(im),(316672,730999,16130))

    def test_bonus_plus_sign_does_not_become_four_hundred_thousand(self):
        image = Image.new('RGB', (1920, 1080))
        with Image.open(Path(__file__).parent/'testdata/result_bonus_plus_as_four.png') as strip:
            image.paste(strip, (700, 230))
        self.assertEqual(main.read_battle_earnings(image), (2276548, 2588920, 27849))

    def test_persistence_and_duplicate_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stats.json'
            stats = FarmStats(path)
            stats.begin('account')
            stats = FarmStats(path)
            self.assertTrue(stats.finish((100, 200, 3)))
            self.assertFalse(stats.finish((100, 200, 3)))
            stats = FarmStats(path)
            stats.begin('account')
            stats.finish((40, 50, 2))
            self.assertEqual(FarmStats(path).data,
                             dict(gold=140, elixir=250, dark_elixir=5, battles=2, pending=None))

    def test_real_result_reaches_persistent_totals_and_ui_event(self):
        with tempfile.TemporaryDirectory() as directory:
            app = app_without_gui()
            app.farm_stats = FarmStats(Path(directory) / 'stats.json')
            app.farm_stats.begin('account')
            app._wait = Mock()
            with Image.open(Path(__file__).parent / 'testdata/result_bonus.png') as screenshot:
                app._capture = Mock(return_value=screenshot)
                app.record_battle_earnings(object())
            event = app.events.get_nowait()
            self.assertIsInstance(event, main.StatsEvent)
            self.assertEqual([event.totals[k] for k in ('gold', 'elixir', 'dark_elixir')],
                             [393408, 55180, 1400])
            self.assertEqual(FarmStats(app.farm_stats.path).data, event.totals)

    def test_large_result_includes_league_bonus(self):
        with Image.open(Path(__file__).parent / 'testdata/result_large.png') as screenshot:
            self.assertEqual(main.read_battle_earnings(screenshot), (1773011, 2057709, 16323))

    def test_vm_defeat_heading_read_at_second_ocr_scale(self):
        with Image.open(Path(__file__).parent / 'testdata/result_defeat_unread_1765.png') as screenshot:
            self.assertEqual(main.read_battle_earnings(screenshot), (648788, 326588, 2324))

    def test_unknown_screen_does_not_count_as_zero(self):
        self.assertIsNone(main.read_battle_earnings(Image.new('RGB', (1920,1080))))

    def test_zero_loot_defeat_has_no_dark_elixir_row(self):
        with Image.open(Path(__file__).parent / 'testdata/result_zero.png') as screenshot:
            self.assertEqual(main.read_battle_earnings(screenshot), (0, 0, 0))
