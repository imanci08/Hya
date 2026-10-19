"""AI reactions use the existing expression controller and animation timer."""
class AIActivity:
    def __init__(self, controller):
        self.controller = controller
        self.busy = False

    def begin(self):
        self.busy = True
        self.tick()

    def tick(self):
        actor = self.controller
        if self.busy and (actor.source != 'ai' or actor.active_expression is None):
            actor.play_expression('thinking', force=False, source='ai')

    def end(self, failed=False):
        self.busy = False
        actor = self.controller
        if actor.source == 'ai':
            actor.reset()
        if failed:
            # No confused expression exists: a short curious glance is the fallback.
            actor.play_expression('curious', force=False, source='ai')
