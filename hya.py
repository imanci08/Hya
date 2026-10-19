__version__ = "0.9.2"

import sqlite3
import sys, math, time
import argparse
from panel_boundary import PanelBoundary
from appearance import Appearance, PRESETS
from personality import Personality, ExpressionController
from ai_activity import AIActivity
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QPoint, QPointF, QRectF, QObject, Property, Signal, Slot, QMargins, QUrl
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient, QPolygonF, QRegion, QCursor, QActionGroup
from PySide6.QtQuick import QQuickPaintedItem
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QMessageBox, QColorDialog, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

def paint_expression_face(p, t, cx, cy, pose):
    """Local coordinates and white features remain independent of crystal color."""
    w = pose.weight
    openness = 1 + (pose.eyes - 1) * w
    blink = pose.blink and (t % 4.2) > 4.06
    for base in (-13, 13):
        x, y = cx + base + pose.look_x*w, cy - 4 + pose.look_y*w
        squeezed = pose.squeeze and openness < .5
        if openness < .12 or blink or squeezed:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(246,250,255),3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
            if squeezed:
                direction = 1 if base < 0 else -1
                p.drawLine(QPointF(x-3*direction,y-2), QPointF(x+2*direction,y))
                p.drawLine(QPointF(x+2*direction,y), QPointF(x-3*direction,y+2))
            elif pose.mouth == "sleep":
                p.drawArc(QRectF(x-3,y-1,6,4),190*16,160*16)
            else:
                p.drawLine(QPointF(x-3,y), QPointF(x+3,y))
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255,255,255))
            p.drawEllipse(QPointF(x,y),3,5*openness)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255,255,255),2.7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
    p.save()
    p.setOpacity(p.opacity() * (1-w))
    p.drawArc(QRectF(cx-7,cy+5,14,9),190*16,160*16)
    p.restore()
    p.save()
    p.setOpacity(p.opacity() * w)
    if pose.mouth == 'thought':
        p.drawLine(QPointF(cx-2,cy+10), QPointF(cx+3,cy+9))
    elif pose.mouth == 'yawn':
        p.drawEllipse(QPointF(cx,cy+10),4,max(.6,7*pose.mouth_amount))
    elif pose.mouth == 'sleep':
        p.drawArc(QRectF(cx-4,cy+7,8,5),190*16,160*16)
    elif pose.mouth == 'scrunch':
        p.drawLine(QPointF(cx-4,cy+10), QPointF(cx,cy+8))
        p.drawLine(QPointF(cx,cy+8), QPointF(cx+4,cy+10))
    elif pose.mouth == 'surprised':
        p.drawEllipse(QPointF(cx,cy+10),3,4)
    else:
        p.drawArc(QRectF(cx-7,cy+5,14,9),190*16,160*16)
    p.restore()


def paint_hyal(p, t, palette=None, pose=None):
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy = 71, 78 + math.sin(t * 1.8) * 2.5
    tone = palette.color if palette else QColor
    p.save()
    if pose and pose.weight > 0:
        # Procedural squash/rebound is inside the existing edge rotation.
        p.translate(cx, cy + pose.bob)
        p.scale(pose.scale_x, pose.scale_y)
        p.translate(-cx, -cy)
    halo = QRadialGradient(QPointF(cx, cy), 64)
    halo.setColorAt(0, tone(95,155,255,75))
    halo.setColorAt(.65, tone(120,90,255,40))
    halo.setColorAt(1, tone(80,130,255,0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(halo)
    p.drawEllipse(QPointF(cx,cy),64,64)
    p.save()
    p.translate(cx,cy)
    p.rotate(-22)
    p.setPen(QPen(tone(164,202,255,145),3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(-59,-19,118,38))
    p.restore()
    glass = QRadialGradient(QPointF(cx-21,cy-25),67)
    glass.setColorAt(0,tone(130,225,255,235))
    glass.setColorAt(.4,tone(40,115,235,225))
    glass.setColorAt(.78,tone(64,45,174,240))
    glass.setColorAt(1,tone(194,142,255,225))
    p.setBrush(glass)
    p.setPen(QPen(tone(195,228,255,195),1.5))
    p.drawEllipse(QPointF(cx,cy),44,44)
    p.setBrush(QColor(240,255,255,55))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(cx-15,cy-24),18,8)
    if pose and pose.weight > 0:
        paint_expression_face(p, t, cx, cy, pose)
    else:
        blink = (t % 4.2) > 4.06
        pen = QPen(QColor(246,250,255),3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        if blink:
            p.drawLine(QPointF(cx-16,cy-3),QPointF(cx-10,cy-3))
            p.drawLine(QPointF(cx+10,cy-3),QPointF(cx+16,cy-3))
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255,255,255))
            p.drawEllipse(QPointF(cx-13,cy-4),3,5)
            p.drawEllipse(QPointF(cx+13,cy-4),3,5)
        p.setPen(QPen(QColor(255,255,255),2.7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(cx-7,cy+5,14,9),190*16,160*16)
    p.save()
    p.translate(cx,cy)
    p.rotate(-22)
    p.setPen(QPen(tone(210,230,255,175),2))
    p.drawArc(QRectF(-59,-19,118,38),180*16,180*16)
    p.restore()
    dy = 17 + math.sin(t*2.2)*2
    p.setBrush(tone(165,230,255,220))
    p.setPen(QPen(QColor(255,255,255,220),1))
    p.drawPolygon(QPolygonF([QPointF(cx,dy-9),QPointF(cx+6,dy),QPointF(cx,dy+9),QPointF(cx-6,dy)]))
    p.restore()


# Logical pixels beyond the output. Hover exposes the original face.
EDGE_OFFSETS = {
    "bottom": (59.0, 30.0),  # Reference: upper crystal head, eyes and diamond.
    "left": (94.0, 55.0),
    "right": (94.0, 55.0),
}


def edge_offset(curiosity, conceal, side):
    rest, hover = EDGE_OFFSETS[side]
    return (rest + (hover - rest)
            * max(0.0, min(1.0, curiosity))) * conceal


def paint_edge(p, t, side, curiosity, conceal, palette=None, pose=None):
    """Transform the complete original character; only the physical edge clips it."""
    offset = edge_offset(curiosity, conceal, side)
    dx, dy, angle = {
        'bottom': (0, offset, 0),
        'right': (offset, 0, -90),
        'left': (-offset, 0, 90),
    }[side]
    p.save()
    # Rotate around the resting body center. The painter already animates in
    # local coordinates; tracking its bob here would turn it into screen-Y motion.
    cy = 78
    p.translate(71 + dx, cy + dy)
    p.rotate(angle * conceal)
    p.translate(-71, -cy)
    paint_hyal(p, t, palette, pose)
    p.restore()


class PeekBridge(QObject):
    changed = Signal()

    def __init__(self, owner, screen):
        super().__init__(owner)
        self.owner = owner
        self.output = screen

    @Property(QObject, constant=True)
    def outputScreen(self):
        return self.output

    @Property(QMargins, notify=changed)
    def edgeMargins(self):
        area = self.output.geometry()
        position = self.owner.saved_position or self.owner.pos()
        if self.owner.edge_side == 'bottom':
            return QMargins(0, 0, self.owner.effective_bottom_inset(self.output), 0)
        top = max(0, min(position.y() - area.y(), max(0, area.height() - 142)))
        return QMargins(0, top, 0, 0)

    @Property(int, notify=changed)
    def panelInset(self):
        return self.owner.panel_boundary.inset(self.output) if self.owner.edge_side == 'bottom' else 0

    @Property(str, constant=True)
    def edgeSide(self):
        return self.owner.edge_side

    @Slot()
    def contextMenu(self):
        self.owner.show_menu()

    @Slot()
    def chat(self):
        self.owner.open_chat()

    @Slot(bool)
    def hover(self, inside):
        self.owner.set_edge_hover(inside)

    @Slot(float, float, bool)
    def pointerMoved(self, x, y, inside):
        self.owner.edge_pointer_moved(x, y, inside)

    @Slot()
    def restore(self):
        self.owner.begin_restore()


class PeekArtwork(QQuickPaintedItem):
    def paint(self, painter):
        owner = self.window().property("owner")
        if owner:
            owner.paint_edge_surface(painter)


class ExpressionPreview(QWidget):
    """Passive, upright live view of the exact pose used by both companion surfaces."""
    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self.owner = owner
        self.setFixedSize(284, 284)

    def paintEvent(self, event):
        p = QPainter(self)
        p.scale(self.width() / 142, self.height() / 142)
        paint_hyal(p, time.monotonic() - self.owner.start,
                   self.owner.appearance.palette, self.owner.pose)
        p.end()


class Hyal(QWidget):
    frame_ready = Signal()
    SIZE = 142
    def __init__(self, bottom_panel_inset=None, appearance=None, personality=None, bottom_horizontal_inset=24):
        super().__init__()
        if not isinstance(bottom_horizontal_inset, int) or bottom_horizontal_inset < 0:
            raise ValueError('bottom_horizontal_inset must be a nonnegative integer')
        self.bottom_horizontal_inset = bottom_horizontal_inset
        self.setWindowTitle('Hya Companion')
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        QApplication.instance().screenRemoved.connect(self._screen_removed)
        self.start = time.monotonic()
        self.appearance = appearance or Appearance(parent=self)
        self.personality = personality or Personality(enabled=self.appearance.idle_enabled)
        self.pose = self.personality.advance()
        self.ai_activity = AIActivity(self.personality)
        self._chat_window = None
        self._docked = False
        self._dock_snapshot = None
        self._dock_restore_requested = False
        self._shutting_down = False
        self._menu_open = False
        self._color_dialog = None
        self._studio_dialog = None
        self._studio_canvas = None
        self._studio_status = None
        self.appearance.changed.connect(self._appearance_changed)
        self.drag_origin = None
        self.hidden_at_edge = False
        self.peek = 0.0
        self.peek_target = 0.0
        self._edge_hover_armed = False
        self._edge_pointer = None
        self.edge_engine = None
        self.edge_window = None
        self.saved_position = None
        self._normal_screen = None
        self._normal_parked = False
        self._using_layer_shell = False
        self.edge_bridge = None
        self.edge_side = "right"
        self.edge_phase = "normal"
        self.conceal = 0.0
        self.transition_start = time.monotonic()
        self.panel_boundary = PanelBoundary(self, bottom_panel_inset)
        self.panel_boundary.changed.connect(self._panel_changed)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)

    def tick(self):
        now = time.monotonic()
        if (self._menu_open or self._color_dialog is not None
                or QApplication.activeModalWidget() is not None
                or QApplication.mouseButtons() != Qt.MouseButton.NoButton
                or (not self._docked and self.edge_phase in ('hiding', 'restoring'))):
            self.personality.interact(now)
        self.personality.advance(now)
        self.ai_activity.tick()
        self.pose = self.personality.sample(now)
        if self.edge_phase == "hiding":
            self.peek_target = 0.0
        if not self._docked:
            self.peek += (self.peek_target - self.peek) * .19
        if self.hidden_at_edge and not self._docked:
            elapsed = (time.monotonic() - self.transition_start) / .65
            progress = max(0.0, min(1.0, elapsed))
            eased = progress * progress * (3 - 2 * progress)
            if self.edge_phase == 'hiding':
                self.conceal = eased
                if progress >= 1:
                    self.edge_phase = 'hidden'
                    self.peek = self.peek_target = 0.0
            elif self.edge_phase == 'restoring':
                self.conceal = self.restore_from * (1 - eased)
                if progress >= 1:
                    self.restore()
            if self.hidden_at_edge:
                region = self.edge_input_region()
                if self.edge_window:
                    self.edge_window.setMask(region)
                    self.edge_window.findChild(QObject, "artwork").update()
                else:
                    self.setMask(region)
        self.update()
        self._update_studio()
        self.frame_ready.emit()

    def paintEvent(self, event):
        t = time.monotonic() - self.start
        p = QPainter(self)
        if self._docked or (self.hidden_at_edge and self._using_layer_shell):
            # Keep the existing xdg surface mapped so KWin retains its position.
            # Explicitly clear the backing store, rather than drawing a clipped orb.
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.fillRect(self.rect(), QColor(0, 0, 0, 0))
            p.end()
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.hidden_at_edge:
            p.setClipRect(0, 0, 142, 142)
            self.paint_edge_surface(p)
        else:
            paint_hyal(p, t, self.appearance.palette, self.pose)
        p.end()

    def paint_edge_surface(self, painter):
        paint_edge(painter, time.monotonic() - self.start, self.edge_side,
                   self.peek, self.conceal, self.appearance.palette, self.pose)

    def edge_input_region(self):
        if self.edge_phase != 'hidden':
            return QRegion(0, 0, 142, 142)
        # Follow the exposed artwork, leaving the rest of the surface click-through.
        offset = int(edge_offset(self.peek, self.conceal, self.edge_side))
        if self.edge_side == 'bottom':
            return QRegion(7, 14 + offset, 128, max(1, 128 - offset))
        if self.edge_side == 'left':
            return QRegion(0, 7, max(1, 142 - offset), 128)
        return QRegion(offset, 7, max(1, 142 - offset), 128)

    def play_expression(self, name, force=True, *, source='manual', priority=None):
        """Public GUI-thread entry point for menus, AI and desktop integrations."""
        accepted = self.personality.play_expression(name, force, source=source, priority=priority)
        if not accepted:
            return False
        self.pose = self.personality.advance()
        if self.hidden_at_edge and not self._docked and source == 'manual' and self.personality.active_expression:
            self.show_expression_studio()
        self.update()
        if self.edge_window:
            self.edge_window.findChild(QObject, 'artwork').update()
        self._update_studio()
        self.frame_ready.emit()
        return True

    def add_expression_menu(self, menu):
        studio = menu.addMenu('Expression Studio')
        for label, name in (('Look Around','look_around'), ('Thinking','thinking'),
                            ('Sleeping','sleeping'), ('Sniffle','sniffle'),
                            ('Sneeze','sneeze'), ('Wake Up / Reset','reset')):
            studio.addAction(label, lambda checked=False, name=name: self.play_expression(name))
        studio.addSeparator()
        studio.addAction('Open Preview Window…', self.show_expression_studio)

    def show_expression_studio(self):
        if self._docked and self._chat_window is not None:
            self._chat_window.character.update()
            return  # Chat already supplies the full animated expression preview.
        if self._studio_dialog is None:
            dialog = QDialog(self, Qt.WindowType.Tool)
            dialog.setWindowTitle('Hya — Expression Studio')
            dialog.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            layout = QVBoxLayout(dialog)
            status = QLabel('Neutral', dialog)
            layout.addWidget(status)
            canvas = ExpressionPreview(self, dialog)
            layout.addWidget(canvas)
            layout.addWidget(QLabel('Live upright preview; edge position stays unchanged.', dialog))
            buttons = QHBoxLayout()
            reset = QPushButton('Wake Up / Reset', dialog)
            reset.clicked.connect(lambda: self.play_expression('reset'))
            close = QPushButton('Close Preview', dialog)
            close.clicked.connect(dialog.close)
            buttons.addWidget(reset)
            buttons.addWidget(close)
            layout.addLayout(buttons)
            self._studio_dialog, self._studio_canvas, self._studio_status = dialog, canvas, status
        self._studio_dialog.show()
        self._update_studio()

    def _update_studio(self):
        if self._studio_dialog is not None and self._studio_dialog.isVisible():
            expression = self.personality.active_expression or 'neutral'
            text = expression.replace('_', ' ').title() + ' · ' + self.personality.state.replace('_',' ').title()
            if self._studio_status.text() != text:
                self._studio_status.setText(text)
            self._studio_canvas.update()

    def interact(self):
        self.personality.interact()
        self.pose = self.personality.advance()

    def _appearance_changed(self):
        self.personality.set_enabled(self.appearance.idle_enabled)
        self.interact()
        self.update()
        if self.edge_window:
            self.edge_window.findChild(QObject, 'artwork').update()

    def choose_custom_color(self):
        self.interact()
        if self._color_dialog is not None:
            self._color_dialog.raise_()
            self._color_dialog.activateWindow()
            return
        old = self.appearance.preset, self.appearance.custom
        dialog = QColorDialog(QColor(self.appearance.color), self)
        dialog.setWindowTitle('Hya — Custom Orb Color')
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.currentColorChanged.connect(
            lambda color: self.appearance.select('Custom', color.name(), persist=False) if color.isValid() else None)
        def finish(result):
            if result == QDialog.DialogCode.Accepted:
                self.appearance.save()
            else:
                self.appearance.select(*old, persist=False)
            self._color_dialog = None
        dialog.finished.connect(finish)
        self._color_dialog = dialog
        dialog.open()

    def add_appearance_menu(self, menu):
        appearance = menu.addMenu('Appearance')
        colors = appearance.addMenu('Orb Color')
        colors.setEnabled(self._color_dialog is None)
        group = QActionGroup(colors)
        group.setExclusive(True)
        for name in PRESETS:
            action = colors.addAction(name)
            action.setCheckable(True)
            action.setChecked(self.appearance.preset == name)
            group.addAction(action)
            action.triggered.connect(lambda checked=False, name=name: self.appearance.select(name))
        colors.addSeparator()
        custom = colors.addAction('Custom Color…', self.choose_custom_color)
        custom.setCheckable(True)
        custom.setChecked(self.appearance.preset == 'Custom')
        group.addAction(custom)
        colors.addAction('Reset to Default', lambda: self.appearance.select('Sapphire'))
        idle = appearance.addAction('Idle Animations')
        idle.setEnabled(self._color_dialog is None)
        idle.setCheckable(True)
        idle.setChecked(self.appearance.idle_enabled)
        idle.toggled.connect(self.appearance.set_idle_enabled)

    def set_edge_hover(self, inside):
        if self._docked:
            return
        if not inside:
            self.peek_target = 0.0
        elif self.edge_phase == 'hidden' and self._edge_hover_armed:
            self.interact()
            self.peek_target = 1.0

    def edge_pointer_moved(self, x, y, inside):
        if self._docked:
            return
        point = (x, y)
        previous = self._edge_pointer
        self._edge_pointer = point
        if previous is not None and point != previous:
            self.interact()
        # Mapping/enter events can report a stationary cursor, and the shrinking
        # input mask can generate leave events. Neither should interrupt retreat.
        if self.edge_phase != 'hidden':
            return
        if previous is not None and point != previous:
            self._edge_hover_armed = True
            self.set_edge_hover(inside)

    def begin_restore(self):
        self.interact()
        if not self.hidden_at_edge or self.edge_phase == 'restoring':
            return
        self.restore_from = self.conceal
        self.edge_phase = 'restoring'
        self.transition_start = time.monotonic()

    def effective_bottom_inset(self, screen):
        return min(self.bottom_horizontal_inset, max(0, screen.geometry().width() - self.SIZE))

    def bottom_surface_left(self, screen):
        """Output-local X, shared by anchors, panel discovery and the X11 fallback."""
        return max(0, screen.geometry().width() - self.SIZE - self.effective_bottom_inset(screen))

    def start_hidden(self, normal_position=None, screen=None):
        """Map only the fully tucked peek surface; never flash the normal widget."""
        if self.hidden_at_edge:
            return True
        screen = screen or self.screen() or QApplication.primaryScreen()
        if not screen:
            return False
        position = QPoint(normal_position) if normal_position is not None else screen.geometry().topLeft() + QPoint(80, 100)
        self.move(position)  # Initial placement hint only on Wayland, never a mapped window.
        return self.hide_at_edge('bottom', animate=False, screen=screen)

    def _park_normal_window(self):
        if not self.isVisible():
            return  # Quiet startup has no normal surface to preserve yet.
        self._normal_parked = True
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # An empty QWindow mask means "accept all input". A nonempty region
        # outside the surface produces no effective pointer/touch input region.
        self.windowHandle().setMask(QRegion(-1, -1, 1, 1))
        self.repaint()

    def _dispose_edge_surface(self):
        if self.edge_window is None:
            return
        window, engine, bridge = self.edge_window, self.edge_engine, self.edge_bridge
        self.edge_window = self.edge_engine = self.edge_bridge = None
        window.hide()
        try:
            bridge.output.geometryChanged.disconnect(self._panel_changed)
        except (TypeError, RuntimeError):
            pass
        engine.deleteLater()
        bridge.deleteLater()

    def hide_at_edge(self, side='bottom', *, animate=True, screen=None):
        self.interact()
        if side not in ('bottom', 'left', 'right'):
            side = 'bottom'
        already_hidden = self.hidden_at_edge
        if already_hidden and side == self.edge_side:
            return True
        if screen is None:
            screen = self.edge_bridge.output if self.edge_window else self.screen()
        screen = screen or QApplication.primaryScreen()
        if not screen:
            return False
        if not already_hidden:
            # Snapshot ONLY the normal widget, never the anchored peek surface.
            self.saved_position = QPoint(self.pos())
            self._normal_screen = screen
        self._dispose_edge_surface()
        self._using_layer_shell = QApplication.platformName().startswith('wayland')
        self.edge_side = side
        if side == 'bottom':
            self.panel_boundary.prepare(screen)
        self.peek = self.peek_target = 0.0
        self.edge_phase = 'hiding' if animate else 'hidden'
        self._edge_hover_armed = False
        self._edge_pointer = None
        self.conceal = 0.0 if animate else 1.0
        self.transition_start = time.monotonic()
        if self._using_layer_shell:
            bridge = PeekBridge(self, screen)
            engine = QQmlApplicationEngine(self)
            engine.rootContext().setContextProperty('peekBridge', bridge)
            engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name('peek.qml'))))
            if not engine.rootObjects():
                engine.deleteLater()
                bridge.deleteLater()
                self.restore()
                QMessageBox.warning(self, 'Hya', 'Could not load the Layer Shell peek surface. '
                                    'Check that layer-shell-qt and its QML module are installed.')
                return False
            window = engine.rootObjects()[0]
            window.setProperty('owner', self)
            self.edge_engine, self.edge_window, self.edge_bridge = engine, window, bridge
            screen.geometryChanged.connect(bridge.changed)
            screen.geometryChanged.connect(self._panel_changed)
            window.closing.connect(lambda event, surface=window: self._edge_closed(event, surface))
            self.hidden_at_edge = True
            self._park_normal_window()
            window.setMask(self.edge_input_region())
            if self._docked:
                self._dock_snapshot['edge'] = window
                self._dock_snapshot['edge_visible'] = True
            else:
                window.show()
            QTimer.singleShot(1500, lambda: self._check_edge(window))
        else:
            self.hidden_at_edge = True
            area = screen.geometry()
            # Every side remains 142 high; only Bottom needs a panel-height strip.
            inset = self.panel_boundary.inset(screen) if side == 'bottom' else 0
            self.setFixedSize(self.SIZE, self.SIZE + inset)
            x = max(area.left(), min(self.x(), area.right() - self.width() + 1))
            y = max(area.top(), min(self.y(), area.bottom() - self.height() + 1))
            if side == 'bottom':
                x = area.left() + self.bottom_surface_left(screen)
                y = area.bottom() - self.height() + 1
            elif side == 'left':
                x = area.left()
                y = max(area.top(), min(self.saved_position.y(), area.bottom() - self.height() + 1))
            else:
                x = area.right() - self.width() + 1
                y = max(area.top(), min(self.saved_position.y(), area.bottom() - self.height() + 1))
            self.move(x, y)
            self.setMask(self.edge_input_region())
            self.show()
        self.panel_boundary.refresh()
        self._panel_changed()
        self.update()
        return True

    def _panel_changed(self):
        if self._docked and not self.edge_window:
            return
        if not self.hidden_at_edge:
            return
        if self.edge_window:
            self.edge_bridge.changed.emit()
        elif not self._using_layer_shell and self.edge_side == "bottom":
            screen = self.screen()
            inset = self.panel_boundary.inset(screen)
            self.setFixedSize(142, 142 + inset)
            area = screen.geometry()
            self.move(area.left() + self.bottom_surface_left(screen), area.bottom() - self.height() + 1)
            self.setMask(self.edge_input_region())

    def _screen_removed(self, screen):
        if self.edge_window and self.edge_bridge.output == screen:
            self.restore()

    def _check_edge(self, window):
        if self._docked or self._shutting_down:
            return
        if self.edge_window is window and not window.isExposed():
            self.restore()
            QMessageBox.warning(self, 'Hya', 'The compositor did not expose the edge surface. '
                                'Normal mode has been restored. Layer Shell support is required.')

    def _edge_closed(self, event, surface=None):
        surface = surface or self.edge_window
        QTimer.singleShot(0, lambda: self.restore() if self.edge_window is surface else None)

    def restore(self):
        if self._docked:
            self._dock_restore_requested = True
            return
        was_hidden = self.hidden_at_edge
        parked = self._normal_parked
        self.hidden_at_edge = False
        self.edge_phase = 'normal'
        self._edge_hover_armed = False
        self._edge_pointer = None
        self.clearMask()
        if self.windowHandle():
            self.windowHandle().setMask(QRegion())
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.peek = self.peek_target = self.conceal = 0.0
        self._dispose_edge_surface()
        self._normal_parked = False
        # An existing Wayland surface is already at the compositor's true last
        # position (which Qt may not know globally). Do not move or remap it.
        if was_hidden and not parked and self.saved_position is not None:
            self.move(self.saved_position)
        if not self.isVisible():
            self.show()
        self.update()

    def closeEvent(self, event):
        self._shutting_down = True
        self.timer.stop()
        if getattr(self, '_tray', None) is not None:
            self._tray.shutdown()
        if getattr(self, '_ai_setup', None) is not None:
            self._ai_setup.shutdown()
        if self._chat_window is not None:
            self._chat_window.shutdown()
        if self.edge_window:
            self.edge_window.hide()
        QApplication.quit()
        super().closeEvent(event)

    def enterEvent(self, event):
        if not self.hidden_at_edge:
            self.interact()
        if self.hidden_at_edge and not self.edge_window:
            self.set_edge_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.hidden_at_edge and not self.edge_window:
            self.set_edge_hover(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.interact()
        if event.button() == Qt.MouseButton.LeftButton:
            if self.hidden_at_edge:
                self.begin_restore()
                return
            window = self.windowHandle()
            if window and window.startSystemMove():
                self.drag_origin = None
            else:
                self.drag_origin = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        self.interact()
        if self.hidden_at_edge:
            if not self.edge_window:
                point = event.position()
                self.edge_pointer_moved(point.x(), point.y(), True)
            return
        if self.drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_origin)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_origin = None

    def mouseDoubleClickEvent(self, event):
        self.interact()
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_chat()

    def dock_to_chat(self):
        """Suspend desktop presentation only; preserve the shared live character."""
        if self._docked or self._shutting_down:
            return
        native = self.windowHandle()
        self._dock_snapshot = {
            'started': time.monotonic(),
            'native_mask': QRegion(native.mask()) if native else None,
            'widget_mask': QRegion(self.mask()),
            'transparent': self.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents),
            'edge': self.edge_window,
            'edge_visible': bool(self.edge_window and self.edge_window.isVisible()),
            'studio_visible': bool(self._studio_dialog and self._studio_dialog.isVisible()),
        }
        self._dock_restore_requested = False
        self._docked = True  # Clear the normal painter BEFORE exposing chat.
        self.drag_origin = None
        if self.edge_window:
            self.edge_window.hide()
        if self._studio_dialog:
            self._studio_dialog.hide()
        # Keep a mapped normal Wayland surface in place, as edge parking does.
        # Unmapping it would discard KWin's actual compositor-managed position.
        if self.isVisible():
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            native.setMask(QRegion(-1, -1, 1, 1))
            self.repaint()

    def undock_from_chat(self):
        if getattr(self, '_tray_hidden', False):
            return
        if not self._docked or self._shutting_down or self._dock_snapshot is None:
            return
        snapshot, self._dock_snapshot = self._dock_snapshot, None
        self.transition_start += time.monotonic() - snapshot['started']
        self._docked = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, snapshot['transparent'])
        if snapshot['widget_mask'].isEmpty():
            self.clearMask()
        else:
            self.setMask(snapshot['widget_mask'])
        if self.windowHandle() and snapshot['native_mask'] is not None:
            self.windowHandle().setMask(snapshot['native_mask'])
        if self._dock_restore_requested:
            self._dock_restore_requested = False
            self.restore()
        elif snapshot['edge_visible'] and self.edge_window is snapshot['edge']:
            self.edge_window.setMask(self.edge_input_region())
            self.edge_window.show()
            surface = self.edge_window
            QTimer.singleShot(1500, lambda: self._check_edge(surface))
        if snapshot['studio_visible'] and self._studio_dialog:
            self._studio_dialog.show()
        self._panel_changed()
        self.repaint()

    def open_chat(self):
        # Lazy creation keeps quiet startup independent of Ollama availability.
        try:
            if self._chat_window is None:
                from chat_window import ChatWindow
                self._chat_window = ChatWindow(self)
                QApplication.instance().aboutToQuit.connect(self._chat_window.shutdown)
            self._chat_window.show_quick()
        except (OSError, sqlite3.Error, RuntimeError) as error:
            if self._chat_window is not None:
                self._chat_window.hide()
            self.undock_from_chat()
            QMessageBox.warning(self, 'Hya local chat', 'Could not open chat: ' + str(error))

    def open_ai_setup(self, first_run=False):
        if self._chat_window is not None and self._chat_window.client.busy:
            self._chat_window.status.setText('Stop the current response before changing AI setup.')
            return
        from ai_settings import AISettings
        from ai_setup_window import AISetupWizard
        settings = self._chat_window.settings if self._chat_window is not None else AISettings()
        if first_run and settings.setup_complete:
            return
        wizard = getattr(self, '_ai_setup', None)
        if wizard is None or not wizard.isVisible():
            wizard = AISetupWizard(settings)
            self._ai_setup = wizard
            def finished(_):
                if self._chat_window is not None:
                    if self._chat_window.client.busy:
                        self._chat_window.client.cancel()
                    self._chat_window.settings = settings
                    self._chat_window.client.settings = settings
                    self._chat_window.desktop.policy.settings = settings
                    self._chat_window.refresh()
            wizard.finished.connect(finished)
        wizard.show()
        wizard.raise_()
        wizard.activateWindow()

    def contextMenuEvent(self, event):
        self.show_menu(event.globalPos())

    def show_menu(self, position=None):
        self.interact()
        menu = QMenu(self)
        menu.addAction('Chat with Hya', self.open_chat)
        menu.addAction('Set up local AI…', self.open_ai_setup)
        if self.hidden_at_edge:
            menu.addAction('Come out', self.begin_restore)
        edges = menu.addMenu('Hide at Screen Edge')
        edges.addAction('Bottom', lambda: self.hide_at_edge('bottom'))
        edges.addAction('Left', lambda: self.hide_at_edge('left'))
        edges.addAction('Right', lambda: self.hide_at_edge('right'))
        self.add_appearance_menu(menu)
        self.add_expression_menu(menu)
        menu.addSeparator()
        menu.addAction('Quit Hya',self.close)
        self._menu_open = True
        try:
            menu.exec(position if position is not None else QCursor.pos())
        finally:
            self._menu_open = False
            self.interact()

# Preferred name; retain Hyal for existing imports and launch scripts.
Hya = Hyal


def create_companion(*, bottom_panel_inset=None, bottom_horizontal_inset=24):
    """Application startup path, also usable by launchers without a normal flash."""
    window = Hya(bottom_panel_inset, bottom_horizontal_inset=bottom_horizontal_inset)
    window.start_hidden()
    return window


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Hya desktop companion')
    parser.add_argument('--bottom-panel-inset', type=int, metavar='PIXELS',
                        help='override panel boundary in logical pixels (0 disables panel clipping)')
    parser.add_argument('--bottom-horizontal-inset', type=int, default=24, metavar='PIXELS',
                        help='logical pixels between the bottom peek surface and the right screen edge (default: 24)')
    options, qt_args = parser.parse_known_args()
    if options.bottom_panel_inset is not None and options.bottom_panel_inset < 0:
        parser.error('--bottom-panel-inset must be nonnegative')
    if options.bottom_horizontal_inset < 0:
        parser.error('--bottom-horizontal-inset must be nonnegative')
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName('Hya')
    app.setApplicationVersion(__version__)
    app.setApplicationDisplayName('Hya')
    app.setQuitOnLastWindowClosed(False)
    qmlRegisterType(PeekArtwork, "Hyal", 1, 0, "PeekArtwork")
    from single_instance import SingleInstance
    instance = SingleInstance(app)
    try:
        if not instance.acquire(): sys.exit(0)
    except RuntimeError as error:
        QMessageBox.warning(None, 'Hya', str(error))
        sys.exit(1)
    app.aboutToQuit.connect(instance.shutdown)
    from PySide6.QtGui import QIcon
    from runtime_paths import asset
    app.setWindowIcon(QIcon(str(asset('assets/hya.svg'))))
    app.setDesktopFileName('io.hyalos.Hya')
    w = create_companion(bottom_panel_inset=options.bottom_panel_inset,
                         bottom_horizontal_inset=options.bottom_horizontal_inset)
    from application_tray import HyaTray
    w._tray = HyaTray(w)
    instance.activated.connect(w._tray.activate)
    app.aboutToQuit.connect(w._tray.shutdown)
    app.aboutToQuit.connect(lambda: getattr(w, '_ai_setup', None) and w._ai_setup.shutdown())
    QTimer.singleShot(0, lambda: w.open_ai_setup(first_run=True))
    sys.exit(app.exec())
