"""One procedural expression at a time, driven by the existing animation timer."""
from dataclasses import dataclass, replace
import math
import random
import time


def ease(value):
    value = max(0., min(1., value))
    return value * value * (3 - 2 * value)


@dataclass(frozen=True, slots=True)
class Pose:
    weight: float = 0.
    look_x: float = 0.
    look_y: float = 0.
    eyes: float = 1.
    mouth: str = 'smile'
    blink: bool = True
    squeeze: bool = False
    scale_x: float = 1.
    scale_y: float = 1.
    bob: float = 0.
    mouth_amount: float = 1.


@dataclass(frozen=True, slots=True)
class StageSpec:
    duration: float | None
    interruptible: bool = True


@dataclass(frozen=True, slots=True)
class ExpressionSpec:
    stages: tuple[str, ...]
    priority: int = 100
    persistent: bool = False


class ExpressionController:
    STAGES = {
        'curious': StageSpec(3.8), 'look_around': StageSpec(5.2),
        'thinking': StageSpec(4.5), 'yawning': StageSpec(2.),
        'dozing': StageSpec(2.5), 'sleeping': StageSpec(None),
        'sniffle': StageSpec(.9), 'sniffle_out': StageSpec(.45),
        'sneeze': StageSpec(.45, interruptible=False), 'rebound': StageSpec(1.1),
        'waking': StageSpec(.5), 'settling': StageSpec(.3),
    }
    DURATIONS = {name: stage.duration for name, stage in STAGES.items() if stage.duration is not None}
    EXPRESSIONS = {
        'look_around': ExpressionSpec(('look_around',)),
        'curious': ExpressionSpec(('curious',)),  # original natural single glance
        'thinking': ExpressionSpec(('thinking',)),
        'sleeping': ExpressionSpec(('yawning', 'dozing', 'sleeping'), persistent=True),
        'sniffle': ExpressionSpec(('sniffle', 'sniffle_out')),
        'sneeze': ExpressionSpec(('sniffle', 'sneeze', 'rebound')),
    }
    SOURCE_PRIORITIES = {'idle': 10, 'interaction': 20, 'desktop': 30, 'ai': 50, 'manual': 100}
    SLEEP_AFTER = 180.
    SNEEZE_COOLDOWN = 300.
    def __init__(self, enabled=True, clock=None, rng=None):
        self.clock = clock or time.monotonic
        self.rng = rng or random.Random()
        now = self.clock()
        self.enabled = enabled
        self.state = 'neutral'
        self.active_expression = None
        self.source = None
        self.priority = 0
        self._stage_index = 0
        self.started = self.last_interaction = self.last_sneeze = now
        self.next_event = now + self.rng.uniform(20, 50)
        self.direction = (0, 0)
        self.last_idle = None
        self.resume_pose = Pose()

    def _clear_expression(self):
        self.active_expression = None
        self.source = None
        self.priority = 0
        self._stage_index = 0

    def reset(self, now=None):
        now = self.clock() if now is None else now
        self._clear_expression()
        self.last_interaction = now
        self._start_stage('neutral', now)
        return True

    def play_expression(self, name, force=True, *, source='manual', priority=None, now=None):
        """Start a named sequence. Return False if priority/interruptibility rejects it.

        Call on the GUI thread through Hya.play_expression() to update all views.
        Idle Animations controls natural scheduling, not explicit previews.
        """
        name = str(name).strip().lower().replace(' ', '_')
        name = {'wake_up_/_reset': 'reset', 'wake_up': 'reset', 'sleep': 'sleeping'}.get(name, name)
        if name not in self.EXPRESSIONS and name != 'reset':
            raise ValueError('Unknown expression: ' + name)
        if source not in self.SOURCE_PRIORITIES and priority is None:
            raise ValueError('Unknown trigger source: ' + source)
        default = self.EXPRESSIONS[name].priority if source == 'manual' and name != 'reset' else self.SOURCE_PRIORITIES.get(source, 0)
        requested = default if priority is None else priority
        if not isinstance(requested, int) or requested < 0:
            raise ValueError('Priority must be a nonnegative integer')
        now = self.clock() if now is None else now
        if source == 'idle' and not self.enabled:
            return False
        if not force and self.state != 'neutral':
            stage = self.STAGES[self.state]
            if not stage.interruptible or requested <= self.priority:
                return False
        if name == 'reset':
            return self.reset(now)
        self.active_expression = name
        self.source = source
        self.priority = requested
        self._stage_index = 0
        if source != 'idle':
            self.last_interaction = now
        self._start_stage(self.EXPRESSIONS[name].stages[0], now)
        return True

    def start(self, state, now=None):
        """Compatibility hook for old tools/tests that sample a single raw stage.

        New callers should use play_expression() so sequence ownership is tracked.
        """
        self._clear_expression()
        self._start_stage(state, now)

    def _start_stage(self, state, now=None):
        if state not in self.DURATIONS and state not in ('neutral', 'sleeping'):
            raise ValueError('Unknown expression')
        self.state = state
        self.started = self.clock() if now is None else now
        if state == 'curious':
            self.direction = self.rng.choice(tuple(direction for direction in ((-4, 0), (4, 0), (0, -3))
                                                   if direction != self.direction))
        if state == 'sneeze':
            self.last_sneeze = self.started
        if state == 'neutral':
            self.next_event = self.started + self.rng.uniform(20, 50)

    def set_enabled(self, enabled, now=None):
        if self.enabled == enabled:
            return
        now = self.clock() if now is None else now
        self.enabled = enabled
        self.last_interaction = now
        if self.active_expression is None or self.source == 'idle':
            self.reset(now)

    def interact(self, now=None):
        now = self.clock() if now is None else now
        self.last_interaction = now
        self.next_event = max(self.next_event, now + 8)
        # Cursor/menu cleanup must not cancel a manual preview or an AI reaction.
        if self.active_expression is not None and (
                self.priority >= self.SOURCE_PRIORITIES['interaction']
                or not self.STAGES[self.state].interruptible):
            return
        if self.state not in ('neutral', 'waking', 'settling'):
            self.resume_pose = self.sample(now)
            waking = self.state in ('sleeping', 'dozing', 'yawning')
            self._clear_expression()
            self._start_stage('waking' if waking else 'settling', now)

    def advance(self, now=None):
        now = self.clock() if now is None else now
        if not self.enabled and self.active_expression is None:
            return Pose()
        # At most a short finite sequence can finish in a single delayed frame.
        while self.state in self.DURATIONS and now >= self.started + self.DURATIONS[self.state]:
            end = self.started + self.DURATIONS[self.state]
            if self.active_expression is not None:
                sequence = self.EXPRESSIONS[self.active_expression].stages
                self._stage_index += 1
                if self._stage_index < len(sequence):
                    self._start_stage(sequence[self._stage_index], end)
                else:
                    self._clear_expression()
                    self._start_stage('neutral', end)
            else:
                # Legacy stage-only sampling retains its previous transitions.
                follow = {'yawning': 'dozing', 'dozing': 'sleeping',
                          'sniffle': 'sneeze', 'sneeze': 'rebound'}.get(self.state, 'neutral')
                self._start_stage(follow, end)
        if self.state == 'neutral' and self.enabled:
            if now - self.last_interaction >= self.SLEEP_AFTER:
                self.play_expression('sleeping', force=False, source='idle', now=now)
            elif now >= self.next_event:
                choice = self.rng.random()
                rare = now - self.last_sneeze >= self.SNEEZE_COOLDOWN
                state = 'sniffle' if rare and choice > .98 else 'thinking' if choice > .7 else 'curious'
                if state == self.last_idle == 'thinking':
                    state = 'curious'
                self.last_idle = state
                self.play_expression('sneeze' if state == 'sniffle' else state,
                                     force=False, source='idle', now=now)
        return self.sample(now)

    def sample(self, now=None):
        if (not self.enabled and self.active_expression is None) or self.state == 'neutral':
            return Pose()
        now = self.clock() if now is None else now
        elapsed = max(0, now - self.started)
        if self.state == 'sleeping':
            return Pose(1, eyes=0, mouth='sleep', blink=False)
        duration = self.DURATIONS[self.state]
        u = min(1, elapsed / duration)
        envelope = ease(elapsed / .55) * ease((duration - elapsed) / .65)
        if self.state in ('waking', 'settling'):
            old = self.resume_pose
            fade = 1 - ease(u)
            return replace(old, weight=old.weight * fade, scale_x=1 + (old.scale_x - 1) * fade,
                           scale_y=1 + (old.scale_y - 1) * fade, bob=old.bob * fade)
        if self.state == 'look_around':
            keys = ((0., 0, 0), (.65, -4, 0), (1.4, -4, 0),
                    (2.1, 4, 0), (2.85, 4, 0), (3.55, 0, -3),
                    (4.35, 0, -3), (5.2, 0, 0))
            for a, b in zip(keys, keys[1:]):
                if elapsed <= b[0]:
                    blend = ease((elapsed - a[0]) / (b[0] - a[0]))
                    return Pose(envelope, look_x=a[1] + (b[1]-a[1])*blend,
                                look_y=a[2] + (b[2]-a[2])*blend)
            return Pose()
        if self.state == 'sniffle_out':
            w = 1 - ease(u)
            return Pose(w, eyes=.35, mouth='scrunch', blink=False,
                        scale_x=1+.02*w, scale_y=1-.025*w, bob=-.8*w)
        if self.state == 'curious':
            return Pose(envelope, *self.direction)
        if self.state == 'thinking':
            return Pose(envelope, look_y=-3, eyes=.85, mouth='thought')
        if self.state == 'yawning':
            weight = ease(elapsed / .5)
            return Pose(weight, eyes=1 - .45 * ease(u), mouth='yawn', blink=False,
                        mouth_amount=math.sin(math.pi*u)**.8)
        if self.state == 'dozing':
            return Pose(1, eyes=.55 * (1 - ease(u)), mouth='sleep', blink=False)
        if self.state == 'sniffle':
            w = ease(elapsed / .35)
            return Pose(w, eyes=.35, mouth='scrunch', blink=False,
                        scale_x=1 + .02*w, scale_y=1 - .025*w, bob=-.8*w)
        if self.state == 'sneeze':
            squeeze = math.sin(math.pi*u)
            return Pose(1, eyes=.35*(1-ease(u/.25)), mouth='scrunch', blink=False, squeeze=True,
                        scale_x=1.02-.03*ease(u)+.035*squeeze,
                        scale_y=.975+.065*ease(u)-.12*squeeze, bob=-.8*(1-ease(u))+2*squeeze)
        if self.state == 'rebound':
            w = 1 - ease(max(0, (u - .4) / .6))
            return Pose(w, eyes=1.2*ease(u/.18), mouth='surprised', blink=False,
                        scale_x=1-.01*w, scale_y=1+.04*w)
        return Pose()


# Preserve imports and integrations created before the Hya rename.
Personality = ExpressionController
