"""Read-only Plasma panel discovery; no work-area or window-position guesses."""
import json
import sys

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage, QDBusPendingCallWatcher


def panel_script(connector):
    # screenForConnector uses Plasma's output IDs, not Qt's screen list order.
    return '''var output = screenForConnector(%s);
var result = [];
panels().forEach(function(p) {
    if (p.screen === output && p.location === "bottom") {
        result.push({height:p.height, length:p.length, lengthMode:p.lengthMode,
                     offset:p.offset, alignment:p.alignment, floating:p.floating});
    }
});
print(JSON.stringify(result));''' % json.dumps(connector)


def panel_inset(rows, screen_width, local_x):
    """Panel thickness at the character center, in logical output coordinates.

    Plasma exposes live thickness and length, but not floating-theme padding or
    the panel's live autohide position. An explicit inset handles those cases.
    """
    inset = 0
    for row in rows:
        height = max(0, int(row['height']))
        length = screen_width if row['lengthMode'] == 'fill' else int(row['length'])
        offset = int(row['offset'])
        if row['alignment'] == 'right':
            left = screen_width - length - offset
        elif row['alignment'] == 'center':
            left = (screen_width - length) / 2 + offset
        else:
            left = offset
        if left <= local_x < left + length:
            inset = max(inset, height)
    return inset


class PanelBoundary(QObject):
    changed = Signal()

    def __init__(self, owner, override=None):
        super().__init__(owner)
        self.owner = owner
        self.override = override
        self.rows = {}
        self.pending = None
        self.warned = False
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def inset(self, screen):
        if self.override is not None:
            return min(self.override, max(0, screen.geometry().height() - 142))
        area = screen.geometry()
        left = self.owner.bottom_surface_left(screen)
        value = panel_inset(self.rows.get(screen.name(), []), area.width(), left + 71)
        return min(value, max(0, area.height() - 142))

    def _message(self, name):
        message = QDBusMessage.createMethodCall('org.kde.plasmashell', '/PlasmaShell',
                                              'org.kde.PlasmaShell', 'evaluateScript')
        message.setArguments([panel_script(name)])
        return message

    def prepare(self, screen):
        # Resolve the initial inset BEFORE mapping, so the first frame cannot
        # draw over/capture input from a known panel. Subsequent refreshes are async.
        name = screen.name()
        if self.override is not None or name in self.rows:
            return
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            self._warn('session bus unavailable')
            self.rows[name] = []
            return
        self._read_reply(bus.call(self._message(name), QDBus.CallMode.Block, 500), name)

    def refresh(self):
        if self.override is not None or self.pending is not None:
            return
        if self.owner.edge_side != 'bottom' or not self.owner.hidden_at_edge:
            return
        screen = self.owner.edge_bridge.output if self.owner.edge_window else self.owner.screen()
        if not screen:
            return
        name = screen.name()
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            self._warn('session bus unavailable')
            return
        watcher = QDBusPendingCallWatcher(bus.asyncCall(self._message(name), 800), self)
        self.pending = watcher
        watcher.finished.connect(lambda: self._finished(watcher, name))

    def _finished(self, watcher, name):
        self.pending = None
        self._read_reply(watcher.reply(), name)
        watcher.deleteLater()

    def _read_reply(self, reply, name):
        try:
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                raise ValueError(reply.errorMessage())
            rows = json.loads(str(reply.arguments()[0]).strip())
            if not isinstance(rows, list):
                raise ValueError('invalid panel data')
            # Validate before replacing a previously valid snapshot.
            panel_inset(rows, 1920, 960)
            if self.rows.get(name) != rows:
                self.rows[name] = rows
                self.changed.emit()
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
            self._warn(str(error))

    def _warn(self, reason):
        if not self.warned:
            print('Hya: could not read Plasma panel boundary (%s). '
                  'Use --bottom-panel-inset PIXELS if needed.' % reason, file=sys.stderr)
            self.warned = True
