import sys, math, time
import argparse
from panel_boundary import PanelBoundary
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, QObject, Property, Signal, Slot, QMargins, QUrl
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient, QPolygonF, QRegion, QCursor
from PySide6.QtQuick import QQuickPaintedItem
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QMessageBox

def paint_hyal(p, t):
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy = 71, 78 + math.sin(t * 1.8) * 2.5
    halo = QRadialGradient(QPointF(cx, cy), 64)
    halo.setColorAt(0, QColor(95,155,255,75))
    halo.setColorAt(.65, QColor(120,90,255,40))
    halo.setColorAt(1, QColor(80,130,255,0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(halo)
    p.drawEllipse(QPointF(cx,cy),64,64)
    p.save()
    p.translate(cx,cy)
    p.rotate(-22)
    p.setPen(QPen(QColor(164,202,255,145),3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(-59,-19,118,38))
    p.restore()
    glass = QRadialGradient(QPointF(cx-21,cy-25),67)
    glass.setColorAt(0,QColor(130,225,255,235))
    glass.setColorAt(.4,QColor(40,115,235,225))
    glass.setColorAt(.78,QColor(64,45,174,240))
    glass.setColorAt(1,QColor(194,142,255,225))
    p.setBrush(glass)
    p.setPen(QPen(QColor(195,228,255,195),1.5))
    p.drawEllipse(QPointF(cx,cy),44,44)
    p.setBrush(QColor(240,255,255,55))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(cx-15,cy-24),18,8)
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
    p.setPen(QPen(QColor(210,230,255,175),2))
    p.drawArc(QRectF(-59,-19,118,38),180*16,180*16)
    p.restore()
    dy = 17 + math.sin(t*2.2)*2
    p.setBrush(QColor(165,230,255,220))
    p.setPen(QPen(QColor(255,255,255,220),1))
    p.drawPolygon(QPolygonF([QPointF(cx,dy-9),QPointF(cx+6,dy),QPointF(cx,dy+9),QPointF(cx-6,dy)]))


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


def paint_edge(p, t, side, curiosity, conceal):
    """Transform the complete original character; only the physical edge clips it."""
    offset = edge_offset(curiosity, conceal, side)
    dx, dy, angle = {
        'bottom': (0, offset, 0),
        'right': (offset, 0, -90),
        'left': (-offset, 0, 90),
    }[side]
    p.save()
    cy = 78 + math.sin(t * 1.8) * 2.5
    p.translate(71 + dx, cy + dy)
    p.rotate(angle * conceal)
    p.translate(-71, -cy)
    paint_hyal(p, t)
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
            left = max(0, min(position.x() - area.x(), max(0, area.width() - 142)))
            return QMargins(left, 0, 0, 0)
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

    @Slot(bool)
    def hover(self, inside):
        self.owner.peek_target = 1.0 if inside else 0.0

    @Slot()
    def restore(self):
        self.owner.begin_restore()


class PeekArtwork(QQuickPaintedItem):
    def paint(self, painter):
        owner = self.window().property("owner")
        if owner:
            owner.paint_edge_surface(painter)


class Hyal(QWidget):
    SIZE = 142
    def __init__(self, bottom_panel_inset=None):
        super().__init__()
        self.setWindowTitle('Hyal Companion')
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        QApplication.instance().screenRemoved.connect(self._screen_removed)
        self.start = time.monotonic()
        self.drag_origin = None
        self.hidden_at_edge = False
        self.peek = 0.0
        self.peek_target = 0.0
        self.edge_engine = None
        self.edge_window = None
        self.saved_position = None
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
        self.peek += (self.peek_target - self.peek) * .19
        if self.hidden_at_edge:
            elapsed = (time.monotonic() - self.transition_start) / .65
            progress = max(0.0, min(1.0, elapsed))
            eased = progress * progress * (3 - 2 * progress)
            if self.edge_phase == 'hiding':
                self.conceal = eased
                if progress >= 1:
                    self.edge_phase = 'hidden'
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

    def paintEvent(self, event):
        t = time.monotonic() - self.start
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.hidden_at_edge:
            p.setClipRect(0, 0, 142, 142)
            self.paint_edge_surface(p)
        else:
            paint_hyal(p, t)
        p.end()

    def paint_edge_surface(self, painter):
        paint_edge(painter, time.monotonic() - self.start, self.edge_side,
                   self.peek, self.conceal)

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

    def begin_restore(self):
        if not self.hidden_at_edge or self.edge_phase == 'restoring':
            return
        self.restore_from = self.conceal
        self.edge_phase = 'restoring'
        self.transition_start = time.monotonic()

    def hide_at_edge(self, side='bottom'):
        if side not in ('bottom', 'left', 'right'):
            side = 'bottom'

        if self.hidden_at_edge:
            return
        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return
        if side == "bottom":
            self.panel_boundary.prepare(screen)
        self.saved_position = self.pos()
        self.peek = 0.0
        self.peek_target = 0.0
        self.edge_side = side
        self.edge_phase = "hiding"
        self.conceal = 0.0
        self.transition_start = time.monotonic()
        if QApplication.platformName().startswith('wayland'):
            bridge = PeekBridge(self, screen)
            engine = QQmlApplicationEngine(self)
            engine.rootContext().setContextProperty("peekBridge", bridge)
            engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name('peek.qml'))))
            if not engine.rootObjects():
                engine.deleteLater()
                bridge.deleteLater()
                QMessageBox.warning(self, 'Hyal', 'Could not load the Layer Shell peek surface. '
                                    'Check that layer-shell-qt and its QML module are installed.')
                return
            window = engine.rootObjects()[0]
            window.setProperty("owner", self)
            self.edge_engine, self.edge_window = engine, window
            self.edge_bridge = bridge
            screen.geometryChanged.connect(bridge.changed)
            screen.geometryChanged.connect(self._panel_changed)
            window.closing.connect(self._edge_closed)
            self.hidden_at_edge = True
            window.setMask(self.edge_input_region())
            window.show()
            self.hide()
            QTimer.singleShot(1500, lambda: self._check_edge(window))
        else:
            self.hidden_at_edge = True
            area = screen.geometry()
            x = max(area.left(), min(self.x(), area.right() - self.width() + 1))
            y = max(area.top(), min(self.y(), area.bottom() - self.height() + 1))
            if side == 'bottom':
                y = area.bottom() - self.height() + 1
            elif side == 'left':
                x = area.left()
            else:
                x = area.right() - self.width() + 1
            self.move(x, y)
        self.panel_boundary.refresh()
        self._panel_changed()
        self.update()

    def _panel_changed(self):
        if not self.hidden_at_edge:
            return
        if self.edge_window:
            self.edge_bridge.changed.emit()
        elif self.edge_side == "bottom":
            screen = self.screen()
            inset = self.panel_boundary.inset(screen)
            self.setFixedSize(142, 142 + inset)
            self.move(self.x(), screen.geometry().bottom() - self.height() + 1)
            self.setMask(self.edge_input_region())

    def _screen_removed(self, screen):
        if self.edge_window and self.edge_bridge.output == screen:
            self.restore()

    def _check_edge(self, window):
        if self.edge_window is window and not window.isExposed():
            self.restore()
            QMessageBox.warning(self, 'Hyal', 'The compositor did not expose the edge surface. '
                                'Normal mode has been restored. Layer Shell support is required.')

    def _edge_closed(self, event):
        QTimer.singleShot(0, self.restore)

    def restore(self):
        self.hidden_at_edge = False
        self.edge_phase = "normal"
        self.clearMask()
        self.setFixedSize(self.SIZE, self.SIZE)
        self.peek = self.peek_target = 0.0
        if self.edge_window:
            window, engine = self.edge_window, self.edge_engine
            self.edge_window = self.edge_engine = None
            window.hide()
            engine.deleteLater()
            self.edge_bridge.deleteLater()
        if self.saved_position is not None:
            self.move(self.saved_position)
        self.show()
        self.update()

    def closeEvent(self, event):
        if self.edge_window:
            self.edge_window.hide()
        QApplication.quit()
        super().closeEvent(event)

    def enterEvent(self, event):
        if self.hidden_at_edge:
            self.peek_target = 1.0
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.hidden_at_edge:
            self.peek_target = 0.0
        super().leaveEvent(event)

    def mousePressEvent(self, event):
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
        if self.drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_origin)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_origin = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            QMessageBox.information(self,'Hyal','Hi! 💙 I’m Hyal. My local AI brain is coming soon!')

    def contextMenuEvent(self, event):
        self.show_menu(event.globalPos())

    def show_menu(self, position=None):
        menu = QMenu(self)
        menu.addAction('Say hello',lambda: QMessageBox.information(self,'Hyal','Hello! 💙'))
        if self.hidden_at_edge:
            menu.addAction('Come out', self.begin_restore)
        else:
            edges = menu.addMenu('Hide at Screen Edge')
            edges.addAction('Bottom', lambda: self.hide_at_edge('bottom'))
            edges.addAction('Left', lambda: self.hide_at_edge('left'))
            edges.addAction('Right', lambda: self.hide_at_edge('right'))
        menu.addSeparator()
        menu.addAction('Quit Hyal',self.close)
        menu.exec(position if position is not None else QCursor.pos())

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Hyal desktop companion')
    parser.add_argument('--bottom-panel-inset', type=int, metavar='PIXELS',
                        help='override panel boundary in logical pixels (0 disables panel clipping)')
    options, qt_args = parser.parse_known_args()
    if options.bottom_panel_inset is not None and options.bottom_panel_inset < 0:
        parser.error('--bottom-panel-inset must be nonnegative')
    app = QApplication([sys.argv[0], *qt_args])
    app.setQuitOnLastWindowClosed(False)
    qmlRegisterType(PeekArtwork, "Hyal", 1, 0, "PeekArtwork")
    w = Hyal(options.bottom_panel_inset)
    w.move(80,100)
    w.show()
    sys.exit(app.exec())
