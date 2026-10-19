from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, QTimer, QPoint
from PySide6.QtWidgets import QMenu
from appearance import Appearance
from personality import ExpressionController, Personality, Pose
from hyal import Hya, Hyal
from test_hyal import app


class Clock:
    def __init__(self, now=0.):
        self.now = now
    def __call__(self):
        return self.now


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.actor = ExpressionController(clock=self.clock, rng=random.Random(3))

    def test_look_around_visits_all_directions_then_returns_neutral(self):
        self.assertTrue(self.actor.play_expression('Look Around'))
        for when, point in ((1.,(-4,0)),(2.5,(4,0)),(4.,(0,-3))):
            self.clock.now = when
            pose = self.actor.advance()
            self.assertEqual((pose.look_x,pose.look_y),point)
            self.assertEqual(pose.weight,1)
        self.clock.now = 5.21
        self.assertEqual(self.actor.advance(),Pose())
        self.assertIsNone(self.actor.active_expression)

    def test_manual_sleep_yawns_and_remains_asleep_until_explicit_reset(self):
        self.actor.play_expression('Sleeping')
        self.clock.now = 1
        self.assertEqual(self.actor.advance().mouth,'yawn')
        self.clock.now = 2.1
        self.actor.advance()
        self.assertEqual(self.actor.state,'dozing')
        self.clock.now = 4.5
        self.assertEqual(self.actor.advance().eyes,0)
        self.clock.now = 3600
        self.actor.interact()
        self.assertEqual(self.actor.advance().mouth,'sleep')
        self.assertEqual(self.actor.active_expression,'sleeping')
        self.assertTrue(self.actor.play_expression('Wake Up / Reset'))
        self.assertEqual(self.actor.sample(),Pose())
        self.assertEqual(self.actor.advance(),Pose())
        self.assertIsNone(self.actor.active_expression)

    def test_sniffle_standalone_and_sneeze_full_sequence(self):
        self.actor.play_expression('sniffle')
        self.clock.now = .6
        self.assertEqual(self.actor.advance().mouth,'scrunch')
        self.clock.now = .95
        self.actor.advance()
        self.assertEqual(self.actor.state,'sniffle_out')
        self.clock.now = 1.36
        self.assertEqual(self.actor.advance(),Pose())
        self.assertEqual(self.actor.last_sneeze,0)
        self.actor.play_expression('sneeze')
        self.assertEqual(self.actor.state,'sniffle')
        self.clock.now += 1.1
        self.assertTrue(self.actor.advance().squeeze)
        self.assertLess(self.actor.sample().scale_y,.92)
        self.clock.now += .4
        self.assertEqual(self.actor.advance().mouth,'surprised')
        self.clock.now += 1.1
        self.assertEqual(self.actor.advance(),Pose())

    def test_priority_force_and_noninterruptible_sneeze_impact(self):
        self.assertTrue(self.actor.play_expression('curious',False,source='idle'))
        self.assertTrue(self.actor.play_expression('thinking',False,source='desktop'))
        self.assertFalse(self.actor.play_expression('sneeze',False,source='idle'))
        self.assertTrue(self.actor.play_expression('sleeping',False))
        self.assertFalse(self.actor.play_expression('thinking',False,source='ai'))
        self.assertFalse(self.actor.play_expression('thinking',False))
        self.assertTrue(self.actor.play_expression('sneeze',True))
        self.clock.now = 1.1
        self.actor.advance()
        self.assertFalse(self.actor.play_expression('thinking',False,priority=1000))
        self.assertTrue(self.actor.play_expression('thinking',True))
        self.assertEqual(self.actor.state,'thinking')

    def test_idle_events_and_incidental_interactions_cannot_cancel_preview(self):
        self.actor.play_expression('thinking')
        for when in (.1,1,2,3):
            self.clock.now = when
            self.actor.next_event = -100
            self.actor.last_interaction = -1000
            self.actor.interact()  # menu dismissal, hover, held mouse button
            pose = self.actor.advance()
            self.assertEqual(self.actor.active_expression,'thinking')
            self.assertGreater(pose.weight,0)
            self.assertFalse(self.actor.play_expression('curious',False,source='idle'))
        self.clock.now = 4.6
        self.actor.advance()
        self.assertEqual(self.actor.state,'neutral')

    def test_manual_previews_work_with_idle_disabled(self):
        self.actor.set_enabled(False)
        self.assertFalse(self.actor.play_expression('curious',False,source='idle'))
        self.actor.play_expression('thinking')
        self.clock.now = 1
        self.assertEqual(self.actor.advance().mouth,'thought')
        self.actor.set_enabled(True)
        self.actor.set_enabled(False)
        self.assertEqual(self.actor.active_expression,'thinking')
        self.actor.play_expression('reset')
        self.assertEqual(self.actor.advance(),Pose())
        self.assertFalse(self.actor.enabled)

    def test_natural_sleep_still_wakes_from_interaction(self):
        self.actor.play_expression('sleeping',False,source='idle')
        self.clock.now = 5
        self.actor.advance()
        self.actor.interact()
        self.assertEqual(self.actor.state,'waking')
        self.clock.now += .5
        self.assertEqual(self.actor.advance(),Pose())

    def test_idle_triggers_use_public_controller_api(self):
        self.actor.next_event = 0
        with patch.object(self.actor,'play_expression',wraps=self.actor.play_expression) as play:
            self.actor.advance()
        self.assertEqual(play.call_args.kwargs['source'],'idle')
        self.assertFalse(play.call_args.kwargs['force'])

    def test_registry_timing_and_invalid_requests(self):
        self.assertIs(Personality,ExpressionController)
        for name,spec in self.actor.EXPRESSIONS.items():
            self.assertTrue(spec.stages)
            self.assertGreater(spec.priority,0)
            for stage in spec.stages:
                self.assertIn(stage,self.actor.STAGES)
            final = self.actor.STAGES[spec.stages[-1]]
            self.assertEqual(final.duration is None,spec.persistent)
        self.actor.play_expression('thinking')
        for arguments in (dict(name='missing'),dict(name='sneeze',priority=-1),dict(name='sneeze',source='missing')):
            with self.assertRaises(ValueError):
                self.actor.play_expression(**arguments)
            self.assertEqual(self.actor.active_expression,'thinking')


class StudioViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.clock = Clock(1000)
        appearance = Appearance(QSettings(str(Path(self.temp.name)/'appearance.ini'),QSettings.Format.IniFormat))
        appearance.set_idle_enabled(False)
        actor = ExpressionController(enabled=False,clock=self.clock)
        self.window = Hya(0,appearance=appearance,personality=actor)
        self.window.start = 1000
        self.window.timer.stop()
        self.window.show()
        app.processEvents()

    def tearDown(self):
        if self.window._studio_dialog is not None:
            self.window._studio_dialog.close()
        self.window.restore()
        self.window.hide()
        self.window.timer.stop()
        self.window.deleteLater()
        app.processEvents()
        self.temp.cleanup()

    def displayed_difference(self, widget):
        pose = self.window.pose
        actual = widget.grab().toImage()
        self.window.pose = Pose()
        baseline = widget.grab().toImage()
        self.window.pose = pose
        self.assertNotEqual(actual,baseline)

    def test_every_menu_action_reaches_rendered_character_and_reset_is_immediate(self):
        self.assertIs(Hya,Hyal)
        self.assertEqual(self.window.windowTitle(),'Hya Companion')
        menu = QMenu(self.window)
        self.window.add_expression_menu(menu)
        actions = menu.actions()[0].menu().actions()
        self.assertEqual([a.text() for a in actions[:6]],
                         ['Look Around','Thinking','Sleeping','Sniffle','Sneeze','Wake Up / Reset'])
        for index,elapsed in enumerate((1.,1.3,5.,.6,1.1)):
            actions[index].trigger()
            self.clock.now += elapsed
            with patch('hyal.time.monotonic',return_value=self.clock.now):
                self.window.tick()
                self.assertGreater(self.window.pose.weight,0)
                self.displayed_difference(self.window)
        actions[5].trigger()
        self.assertEqual(self.window.pose,Pose())
        self.assertIsNone(self.window.personality.active_expression)

    def test_menu_exec_cleanup_does_not_cancel_selected_animation(self):
        errors = []
        def choose():
            root = app.activePopupWidget()
            try:
                studio = next(a.menu() for a in root.actions() if a.text() == 'Expression Studio')
                studio.actions()[1].trigger()
            except Exception as error:
                errors.append(error)
            finally:
                if root:
                    root.close()
        QTimer.singleShot(10,choose)
        self.window.show_menu(QPoint(10,10))
        self.assertEqual(errors,[])
        self.assertEqual(self.window.personality.active_expression,'thinking')
        self.clock.now += 1
        with patch('hyal.time.monotonic',return_value=self.clock.now):
            self.window.tick()
            self.assertEqual(self.window.pose.mouth,'thought')
            self.displayed_difference(self.window)

    def test_hidden_previews_leave_all_edges_anchored_and_show_upright_live_view(self):
        for side in ('bottom','left','right'):
            with patch.object(__import__('hyal').QApplication,'platformName',return_value='wayland'), \
                 patch('hyal.time.monotonic',side_effect=self.clock):
                self.window.hide_at_edge(side)
                self.window.edge_phase = 'hidden'
                self.window.conceal = 1
                self.window.tick()
                app.processEvents()
                edge = self.window.edge_window
                geometry, mask = edge.geometry(), edge.mask()
                for name,elapsed in (('look_around',1),('thinking',1),('sleeping',5),('sniffle',.6),('sneeze',1.1)):
                    self.window.play_expression(name)
                    self.clock.now += elapsed
                    self.window.tick()
                    app.processEvents()
                    self.assertTrue(self.window._normal_parked)
                    self.assertTrue(edge.isVisible())
                    self.assertEqual(edge.geometry(),geometry)
                    self.assertEqual(edge.mask(),mask)
                    self.assertTrue(self.window._studio_dialog.isVisible())
                    self.assertEqual(self.window._studio_dialog.windowTitle(),'Hya — Expression Studio')
                    self.displayed_difference(self.window._studio_canvas)
                    self.assertFalse(edge.grabWindow().isNull())
                self.window.play_expression('reset')
                self.assertEqual(self.window.pose,Pose())
                self.window.restore()
                app.processEvents()
