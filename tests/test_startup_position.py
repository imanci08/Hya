from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject, QEvent, QPoint, QRect, QSettings, Qt
from PySide6.QtGui import QRegion
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest
from appearance import Appearance
from hyal import Hya, QApplication, PeekBridge, create_companion
from test_hyal import app


class VisibilityEvents(QObject):
    def __init__(self):
        super().__init__()
        self.events = []
    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Show,QEvent.Type.Hide):
            self.events.append(event.type())
        return False


class PositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.temp.name)/'appearance.ini'),QSettings.Format.IniFormat)
        appearance = Appearance(settings)
        appearance.set_idle_enabled(False)
        self.window = Hya(40,appearance=appearance)
        self.window.timer.stop()

    def tearDown(self):
        self.window.restore()
        self.window.hide()
        self.window.timer.stop()
        if self.window._studio_dialog:
            self.window._studio_dialog.close()
        self.window.deleteLater()
        app.processEvents()
        self.temp.cleanup()

    def test_startup_maps_only_tucked_bottom_right_surface_and_click_restores(self):
        spy = VisibilityEvents()
        self.window.installEventFilter(spy)
        with patch.object(QApplication,'platformName',return_value='wayland'):
            self.assertTrue(self.window.start_hidden(QPoint(80,100)))
        app.processEvents()
        edge = self.window.edge_window
        self.assertEqual(self.window.saved_position,QPoint(80,100))
        self.assertEqual(self.window.edge_side,'bottom')
        self.assertEqual(self.window.edge_phase,'hidden')
        self.assertEqual(self.window.conceal,1)
        self.assertEqual(self.window.peek,0)
        self.assertFalse(self.window.isVisible())
        self.assertEqual(spy.events,[])  # no normal Show, even briefly
        self.assertEqual(edge.height(),182)
        expression = QQmlExpression(QQmlEngine.contextForObject(edge),edge,'Number(LayerShell.Window.anchors)')
        value = expression.evaluate()
        self.assertFalse(expression.hasError())
        self.assertEqual(value[0] if isinstance(value,tuple) else value,10)  # Bottom | Right
        self.assertEqual(self.window.edge_bridge.edgeMargins.right(),24)
        self.assertEqual(self.window.edge_bridge.edgeMargins.left(),0)
        frame = edge.grabWindow()
        self.assertFalse(frame.isNull())
        self.assertTrue(all(frame.pixelColor(x,y).alpha()==0 for y in range(142,182) for x in range(142)))
        self.assertFalse(edge.mask().intersects(QRegion(0,142,142,40)))
        self.window.edge_bridge.hover(True)  # synthetic map enter must stay tucked
        self.window.tick()
        self.assertEqual(self.window.peek,0)
        QTest.mouseClick(edge,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(71,130))
        self.assertEqual(self.window.edge_phase,'restoring')
        self.window.transition_start -= 1
        self.window.tick()
        self.assertEqual(self.window.edge_phase,'normal')
        self.assertEqual(self.window.conceal,0)
        self.assertTrue(self.window.isVisible())
        self.assertEqual(self.window.pos(),QPoint(80,100))

    def test_existing_wayland_surface_stays_mapped_blank_and_input_free(self):
        self.window.move(300,200)
        self.window.show()
        app.processEvents()
        native = self.window.windowHandle()
        native_position = native.position()
        spy = VisibilityEvents()
        self.window.installEventFilter(spy)
        with patch.object(QApplication,'platformName',return_value='wayland'):
            self.window.hide_at_edge('right')
        app.processEvents()
        self.assertTrue(self.window._normal_parked)
        self.assertTrue(native.isVisible())
        self.assertIs(native,self.window.windowHandle())
        self.assertFalse(native.mask().intersects(QRegion(self.window.rect())))
        frame = self.window.grab().toImage()
        self.assertTrue(all(frame.pixelColor(x,y).alpha()==0 for y in range(frame.height()) for x in range(frame.width())))
        with patch.object(self.window,'move',wraps=self.window.move) as move:
            self.window.restore()
            move.assert_not_called()
        app.processEvents()
        self.assertEqual(spy.events,[])  # no hide/show round trip of the xdg toplevel
        self.assertIs(native,self.window.windowHandle())
        self.assertEqual(native.position(),native_position)
        self.assertTrue(native.mask().isEmpty())  # default/full input restored
        self.assertFalse(self.window.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))

    def test_wayland_return_does_not_depend_on_reported_global_coordinates(self):
        self.window.move(400,280)
        self.window.show()
        app.processEvents()
        native = self.window.windowHandle()
        position = native.position()
        with patch.object(self.window,'pos',return_value=QPoint(0,0)), \
             patch.object(QApplication,'platformName',return_value='wayland'):
            self.window.hide_at_edge('bottom')
        self.assertEqual(self.window.saved_position,QPoint(0,0))  # Qt can lack global Wayland coordinates
        self.window.restore()
        self.assertEqual(native.position(),position)  # actual mapped surface never moved

    def test_edge_changes_never_replace_normal_snapshot_and_drag_updates_it(self):
        self.window.move(300,210)
        self.window.show()
        app.processEvents()
        with patch.object(QApplication,'platformName',return_value='wayland'):
            self.window.hide_at_edge('bottom')
            old = self.window.edge_window
            old.setPosition(7,9)  # deliberately unrelated hidden-surface coordinates
            for side in ('left','right','bottom'):
                self.window.hide_at_edge(side)
                self.assertEqual(self.window.saved_position,QPoint(300,210))
            self.window._edge_closed(None,old)
            app.processEvents()
            self.assertTrue(self.window.hidden_at_edge)  # stale surface callbacks cannot restore the new one
        self.window.restore()
        self.assertEqual(self.window.pos(),QPoint(300,210))
        self.window.move(450,330)  # same position update produced by a completed normal drag
        with patch.object(QApplication,'platformName',return_value='wayland'):
            self.window.hide_at_edge('left')
        self.assertEqual(self.window.saved_position,QPoint(450,330))
        self.window.restore()
        self.assertEqual(self.window.pos(),QPoint(450,330))

    def test_x11_switching_and_restoration_with_panel_height(self):
        self.window.move(260,170)
        self.window.show()
        with patch.object(QApplication,'platformName',return_value='xcb'):
            for side in ('bottom','left','right','bottom'):
                self.window.hide_at_edge(side)
                self.assertEqual(self.window.saved_position,QPoint(260,170))
                if side == 'bottom':
                    self.assertEqual(self.window.height(),182)
                    self.assertEqual(self.window.x(),self.window.screen().geometry().right()+1-142-24)
                else:
                    self.assertEqual(self.window.height(),142)
            self.window.restore()
        self.assertEqual(self.window.pos(),QPoint(260,170))
        self.assertEqual(self.window.height(),142)

    def test_studio_buttons_stay_clickable_with_parked_normal_parent(self):
        from PySide6.QtWidgets import QPushButton
        self.window.show()
        app.processEvents()
        with patch.object(QApplication,'platformName',return_value='wayland'):
            self.window.hide_at_edge('bottom',animate=False)
        self.window.play_expression('sleeping')
        app.processEvents()
        dialog = self.window._studio_dialog
        reset = next(b for b in dialog.findChildren(QPushButton) if b.text()=='Wake Up / Reset')
        point = reset.mapTo(dialog,reset.rect().center())
        QTest.mouseClick(dialog.windowHandle(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
        self.assertIsNone(self.window.personality.active_expression)
        self.assertTrue(self.window._normal_parked)
        self.window.play_expression('thinking')
        close = next(b for b in dialog.findChildren(QPushButton) if b.text()=='Close Preview')
        point = close.mapTo(dialog,close.rect().center())
        QTest.mouseClick(dialog.windowHandle(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
        self.assertFalse(dialog.isVisible())
        self.assertEqual(self.window.personality.active_expression,'thinking')

    def test_bottom_inset_is_resolution_independent_and_does_not_change_sides(self):
        class Output:
            def geometry(self):
                return QRect(-1920,-200,1920,1080)
        screen = Output()
        self.window.saved_position = QPoint(-1700,100)
        bridge = PeekBridge(self.window,screen)
        self.window.edge_side = 'bottom'
        self.assertEqual(bridge.edgeMargins.right(),24)
        self.assertEqual(self.window.bottom_surface_left(screen),1754)
        self.window.bottom_horizontal_inset = 300
        self.assertEqual(bridge.edgeMargins.right(),300)
        self.assertEqual(self.window.bottom_surface_left(screen),1478)
        for side in ('left','right'):
            self.window.edge_side = side
            self.assertEqual(bridge.edgeMargins.top(),300)
            self.assertEqual(bridge.edgeMargins.right(),0)
            self.assertEqual(bridge.edgeMargins.left(),0)
        self.window.bottom_horizontal_inset = 99999
        self.assertEqual(self.window.effective_bottom_inset(screen),1778)
        self.assertEqual(self.window.bottom_surface_left(screen),0)

    def test_panel_detection_queries_new_bottom_right_location(self):
        screen = self.window.screen()
        width = screen.geometry().width()
        self.window.panel_boundary.override = None
        self.window.panel_boundary.rows[screen.name()] = [dict(height=40,length=200,lengthMode='custom',
                                                             offset=0,alignment='right',floating=False)]
        self.window.saved_position = QPoint(screen.geometry().left()+10,100)
        self.assertEqual(self.window.panel_boundary.inset(screen),40)
        self.window.bottom_horizontal_inset = width-142
        self.assertEqual(self.window.panel_boundary.inset(screen),0)

    def test_actual_startup_factory_never_maps_normal_window(self):
        with patch.object(QApplication,'platformName',return_value='wayland'):
            window = create_companion(bottom_panel_inset=40,bottom_horizontal_inset=64)
        try:
            app.processEvents()
            self.assertFalse(window.isVisible())
            self.assertTrue(window.edge_window.isVisible())
            self.assertEqual(window.conceal,1)
            self.assertEqual(window.edge_phase,'hidden')
            self.assertEqual(window.edge_bridge.edgeMargins.right(),64)
        finally:
            window.restore()
            window.hide()
            window.timer.stop()
            window.deleteLater()
            app.processEvents()
