import random
import unittest
from personality import Personality, Pose


class Clock:
    now = 0.
    def __call__(self):
        return self.now


class PersonalityTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.actor = Personality(clock=self.clock, rng=random.Random(12))

    def test_randomized_idle_intervals_and_centered_return(self):
        deadline = self.actor.next_event
        self.assertTrue(20 <= deadline <= 50)
        self.clock.now = deadline - .001
        self.assertEqual(self.actor.advance(), Pose())
        self.clock.now = deadline
        self.actor.advance()
        self.assertIn(self.actor.state, ('curious', 'thinking'))
        self.clock.now += self.actor.DURATIONS[self.actor.state]
        self.assertEqual(self.actor.advance(), Pose())
        self.assertTrue(20 <= self.actor.next_event - self.clock.now <= 50)

    def test_curious_and_thinking_use_smooth_envelopes(self):
        for state in ('curious', 'thinking'):
            self.actor.start(state, 0)
            self.assertEqual(self.actor.sample(0).weight, 0)
            self.assertLess(self.actor.sample(.05).weight, self.actor.sample(.25).weight)
            middle = self.actor.sample(1.5)
            self.assertEqual(middle.weight, 1)
            self.assertTrue(middle.blink)
            if state == 'thinking':
                self.assertEqual((middle.look_y, middle.mouth), (-3, 'thought'))
            else:
                self.assertIn((middle.look_x, middle.look_y), ((-4,0), (4,0), (0,-3)))
            self.assertEqual(self.actor.sample(self.actor.DURATIONS[state]).weight, 0)

    def test_yawn_doze_sleep_and_interaction_wakes_without_restart(self):
        self.clock.now = 180
        self.actor.advance()
        self.assertEqual(self.actor.state, 'yawning')
        self.clock.now = 181
        yawn = self.actor.advance()
        self.assertEqual(yawn.mouth, 'yawn')
        self.assertFalse(yawn.blink)
        self.clock.now = 182
        self.assertAlmostEqual(self.actor.advance().eyes, .55)
        self.assertEqual(self.actor.state, 'dozing')
        self.clock.now = 183
        self.assertLess(self.actor.advance().eyes, .55)
        self.clock.now = 184.5
        asleep = self.actor.advance()
        self.assertEqual((self.actor.state, asleep.eyes, asleep.blink), ('sleeping', 0, False))
        self.actor.interact()
        self.assertEqual(self.actor.state, 'waking')
        self.clock.now += .25
        halfway = self.actor.advance()
        self.actor.interact()
        self.assertEqual(halfway.weight, .5)
        self.clock.now += .25
        self.assertEqual(self.actor.advance(), Pose())

    def test_rare_sneeze_sequence_and_cooldown(self):
        class RareRandom(random.Random):
            def random(self):
                return .999
        self.actor.rng = RareRandom()
        self.clock.now = 301
        self.actor.last_interaction = 300
        self.actor.next_event = 300
        self.actor.advance()
        self.assertEqual(self.actor.state, 'sniffle')
        preparation = self.actor.sample(301.9)
        self.assertLess(preparation.eyes, 1)
        self.clock.now = 301.901
        sneeze = self.actor.advance()
        self.assertEqual(self.actor.state, 'sneeze')
        self.assertAlmostEqual(sneeze.scale_y, preparation.scale_y, delta=.001)
        self.clock.now = 302.1
        squeeze = self.actor.advance()
        self.assertFalse(squeeze.blink)
        self.assertTrue(squeeze.squeeze)
        self.assertLess(squeeze.scale_y, .91)
        self.clock.now = 302.351
        rebound = self.actor.advance()
        self.assertEqual((self.actor.state, rebound.mouth), ('rebound', 'surprised'))
        self.assertGreater(rebound.scale_y, 1)
        self.clock.now = 303.5
        self.assertEqual(self.actor.advance(), Pose())
        self.actor.next_event = 304
        self.clock.now = 304
        self.actor.advance()
        self.assertEqual(self.actor.state, 'thinking')  # cooldown forbids another sneeze

    def test_disable_is_neutral_and_reenable_resets_inactivity(self):
        self.actor.start('sleeping')
        self.actor.set_enabled(False)
        self.clock.now = 1000
        self.assertEqual(self.actor.advance(), Pose())
        self.actor.set_enabled(True)
        self.assertEqual(self.actor.advance(), Pose())
        self.assertEqual(self.actor.last_interaction, 1000)

    def test_interaction_settles_expression_and_blocks_immediate_idle(self):
        self.actor.start('thinking', 0)
        self.clock.now = 1
        self.actor.interact()
        self.assertEqual(self.actor.state, 'settling')
        self.assertEqual(self.actor.sample().weight, 1)
        self.clock.now = 1.15
        self.assertAlmostEqual(self.actor.advance().weight, .5)
        self.clock.now = 1.31
        self.assertEqual(self.actor.advance(), Pose())
        self.assertGreater(self.actor.next_event, self.clock.now)

    def test_poses_remain_bounded_and_sleep_sneeze_override_blink(self):
        for state, duration in self.actor.DURATIONS.items():
            self.actor.start(state, 0)
            for fraction in (0, .1, .25, .5, .9, 1):
                pose = self.actor.sample(duration*fraction)
                self.assertTrue(0 <= pose.weight <= 1)
                self.assertTrue(0 <= pose.eyes <= 1.2)
                self.assertTrue(.85 < pose.scale_y < 1.08)
                if state in ('yawning','dozing','sniffle','sneeze','rebound'):
                    self.assertFalse(pose.blink)

    def test_curious_directions_do_not_repeat_back_to_back(self):
        previous = None
        for index in range(20):
            self.actor.start('curious', index*10)
            self.assertNotEqual(self.actor.direction, previous)
            previous = self.actor.direction
