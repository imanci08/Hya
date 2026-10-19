"""Small presentation helpers; no requests, history, or animation ownership."""
import re
import time
from PySide6.QtCore import Qt, QPoint, QRect, QSize, QEvent
from PySide6.QtGui import QPainter, QCursor
from PySide6.QtWidgets import QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QApplication


def quick_geometry(available, anchor, side='normal', size=QSize(410, 470), gap=12):
    """A placement hint in logical desktop coordinates, including negative origins."""
    width = min(size.width(), available.width())
    height = min(size.height(), available.height())
    if side == 'left':
        x, y = anchor.right() + 1 + gap, anchor.center().y() - height // 2
    elif side == 'right':
        x, y = anchor.left() - gap - width, anchor.center().y() - height // 2
    else:
        x, y = anchor.center().x() - width // 2, anchor.top() - gap - height
        if side == 'normal' and y < available.top():
            y = anchor.bottom() + 1 + gap
    x = max(available.left(), min(x, available.right() + 1 - width))
    y = max(available.top(), min(y, available.bottom() + 1 - height))
    return QRect(x, y, width, height)


def visible_peek_anchor(owner, surface):
    if getattr(owner, 'edge_phase', None) == 'hidden':
        # The existing input region follows the exposed artwork. Use it only as
        # a placement reference; never change the peek window or its region.
        local = owner.edge_input_region().boundingRect().intersected(QRect(0, 0, 142, 142))
        return local.translated(surface.topLeft())
    return surface


def character_anchor(owner, screen):
    """Infer peek coordinates from the unchanged anchors, not Wayland move()."""
    physical = screen.geometry()
    if getattr(owner, 'hidden_at_edge', False):
        side = owner.edge_side
        bridge = getattr(owner, 'edge_bridge', None)
        if side == 'bottom':
            inset = owner.effective_bottom_inset(screen)
            panel = owner.panel_boundary.inset(screen)
            surface = QRect(physical.right() + 1 - inset - 142,
                            physical.bottom() + 1 - panel - 142, 142, 142)
            return visible_peek_anchor(owner, surface), side
        top = bridge.edgeMargins.top() if bridge else max(0, min(owner.y() - physical.y(), physical.height() - 142))
        x = physical.left() if side == 'left' else physical.right() + 1 - 142
        return visible_peek_anchor(owner, QRect(x, physical.y() + top, 142, 142)), side
    anchor = owner.frameGeometry()
    # Wayland can report a fictitious toplevel origin. An intentional opening
    # from the character/menu gives a useful cursor-based fallback.
    if QApplication.platformName() == 'wayland' and not anchor.contains(QCursor.pos()):
        point = QCursor.pos()
        if screen.geometry().contains(point):
            anchor = QRect(point - QPoint(30, 30), QSize(60, 60))
    return anchor, 'normal'


def fenced_blocks(text):
    """Closed Markdown fences only; preserve code literally, never render HTML."""
    blocks, marker, language, lines = [], None, '', []
    for line in text.splitlines(keepends=True):
        match = re.match(r'^ {0,3}(`{3,}|~{3,})([^\r\n]*)[\r\n]*$', line)
        if marker is None:
            if match and not (match[1][0] == '`' and '`' in match[2]):
                marker, language, lines = match[1], match[2].strip(), []
        elif (match and match[1][0] == marker[0] and len(match[1]) >= len(marker)
              and not match[2].strip()):
            blocks.append((language, ''.join(lines)))
            marker = None
        else:
            lines.append(line)
    return blocks


class DragHandle(QWidget):
    """Native compositor move, with QWidget movement only as an X11 fallback."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.origin = None
        self.setCursor(Qt.OpenHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            native = self.window().windowHandle()
            if native and native.startSystemMove():
                return
            if QApplication.platformName() != 'wayland':
                self.origin = event.globalPosition().toPoint() - self.window().pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.origin is not None and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self.origin)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.origin = None
        super().mouseReleaseEvent(event)


class _CharacterCanvas(QWidget):
    def __init__(self,slot):
        super().__init__()
        self.slot=slot
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self,event):
        painter=QPainter(self)
        self.slot.paint_character(painter,self.size())
        painter.end()

    def contextMenuEvent(self,event):
        self.slot.contextMenuEvent(event)


class DockedCharacter(QWidget):
    """The original painter, shared pose and original clock; no second animator."""
    VISUAL_SCALE=1.25
    def __init__(self, chat, parent=None):
        super().__init__(parent)
        self.chat = chat
        self._canvas = _CharacterCanvas(self)
        self.setFixedSize(114, 114)  # 80% of the original 142 logical pixels.
        self.setAccessibleName('Animated Hya')
        owner = chat.owner
        if hasattr(owner, 'frame_ready'):
            owner.frame_ready.connect(self.update)
        if hasattr(owner, 'appearance'):
            owner.appearance.changed.connect(self.update)

    def event(self,event):
        result=super().event(event)
        if event.type() in (QEvent.ParentChange,QEvent.Move,QEvent.Resize,QEvent.Show,QEvent.Hide):
            if hasattr(self,'_canvas'):self._sync_canvas()
        return result

    def _sync_canvas(self):
        parent=self.parentWidget()
        if parent is None:return
        if self._canvas.parentWidget() is not parent:self._canvas.setParent(parent)
        size=round(self.width()*self.VISUAL_SCALE)
        self._canvas.setFixedSize(size,size)
        center=self.geometry().center()
        self._canvas.move(round(center.x()-(size-1)/2),round(center.y()-(size-1)/2))
        self._canvas.setVisible(self.isVisible())
        self._canvas.raise_()

    def update(self,*args):
        super().update(*args)
        if hasattr(self,'_canvas'):self._canvas.update()

    def paintEvent(self,event):
        pass  # Layout slot only; a sibling canvas permits the small safe overflow.

    def paint_character(self, painter, viewport=None):
        from hya import paint_hyal
        from personality import Pose
        owner = self.chat.owner
        viewport=viewport or self.size()
        scale = min(viewport.width(), viewport.height()) / 142
        painter.translate((viewport.width()-142*scale)/2, (viewport.height()-142*scale)/2)
        painter.scale(scale, scale)
        appearance = getattr(owner, 'appearance', None)
        paint_hyal(painter, time.monotonic() - getattr(owner, 'start', time.monotonic()),
                   appearance.palette if appearance else None, getattr(owner, 'pose', Pose()))

    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import QMenu
        owner = self.chat.owner
        if not hasattr(owner, 'add_expression_menu'):
            return
        owner.interact()
        menu = QMenu(self)
        owner.add_expression_menu(menu)
        owner.add_appearance_menu(menu)
        menu.addSeparator()
        menu.addAction('Quit Hya', owner.close)
        was_open = owner._menu_open
        owner._menu_open = True
        try:
            menu.exec(event.globalPos())
        finally:
            owner._menu_open = was_open
            owner.interact()

    # Deliberately no desktop dragging or click-to-restore handlers.


class MessageBubble(QFrame):
    def __init__(self, role, text, status='complete', parent=None):
        super().__init__(parent)
        self.setProperty('bubble', 'true')
        self.setProperty('speaker', role)
        self.role = role
        layout = QVBoxLayout(self)
        self.heading = QLabel(('You' if role == 'user' else 'Hya') +
                              ('' if status == 'complete' else ' · ' + status))
        self.heading.setTextFormat(Qt.PlainText)
        layout.addWidget(self.heading)
        self.label = QLabel()
        self.label.setTextFormat(Qt.PlainText)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.label.setWordWrap(True)
        self.label.setMinimumWidth(1)
        layout.addWidget(self.label)
        self.copy_area = QWidget()
        self.copy_layout = QVBoxLayout(self.copy_area)
        self.copy_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.copy_area)
        self.label.setText(text)
        self.set_copy_actions(text, ready=status != 'generating')

    def set_copy_actions(self, text, ready=True):
        while self.copy_layout.count():
            widget = self.copy_layout.takeAt(0).widget()
            widget.hide()
            widget.deleteLater()
        self.copy_area.setVisible(self.role == 'assistant' and ready and bool(text))
        if self.role != 'assistant' or not ready or not text:
            return
        copy = QPushButton('Copy Response')
        copy.setAutoDefault(False)
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.label.text()))
        self.copy_layout.addWidget(copy, 0, Qt.AlignLeft)
        for index, (language, code) in enumerate(fenced_blocks(text), 1):
            button = QPushButton(f'Copy code {index}' + (f' · {language[:24]}' if language else ''))
            button.setAutoDefault(False)
            button.setAccessibleName(f'Copy code block {index}')
            button.clicked.connect(lambda checked=False, value=code: QApplication.clipboard().setText(value))
            self.copy_layout.addWidget(button, 0, Qt.AlignLeft)
