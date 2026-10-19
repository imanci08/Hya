"""One live character, distinct desktop and embedded presentation lifecycles."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QSettings, QPoint
from PySide6.QtGui import QImage, QPainter, QRegion
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication
from appearance import Appearance
from hya import Hya, paint_hyal
from personality import Pose
from chat_window import ChatWindow
from conversation_store import ConversationStore
from test_hyal import app
import test_local_ai as fixtures


class DockingTests(unittest.TestCase):
    setUp = fixtures.LocalAI.setUp

    def companion(self):
        self.owner = Hya(40, appearance=Appearance(QSettings(str(Path(self.temp.name)/'appearance.ini'), QSettings.IniFormat)))
        self.window = ChatWindow(self.owner, self.settings,
                ConversationStore(Path(self.temp.name)/'docking.sqlite3'), self.client)
        self.owner._chat_window = self.window
        self.addCleanup(self.cleanup_companion)
        app.processEvents()
        self.manager.calls[-1][2].done(b'{"models":[{"name":"tiny:latest"}]}')
        self.window.models.setCurrentIndex(1)
        return self.owner, self.window

    def cleanup_companion(self):
        if not self.window._closed:
            self.window.close()
            self.window.shutdown()
        self.owner.timer.stop()
        self.owner._dispose_edge_surface()
        if self.owner._studio_dialog:
            self.owner._studio_dialog.hide()
        self.owner.hide()
        self.window.deleteLater()
        self.owner.deleteLater()
        app.processEvents()

    def send(self):
        self.window.input.setPlainText('Hello')
        self.window.send()
        self.manager.calls[-1][2].done(b'{"model_info":{"architecture":"test"}}')
        return self.manager.calls[-1][2]

    def test_normal_surface_retains_native_position_and_becomes_blank_input_free(self):
        owner, window = self.companion()
        owner.move(270, 190)
        owner.show()
        app.processEvents()
        native, pos = owner.windowHandle(), owner.pos()
        for _ in range(3):
            window.show_quick()
            app.processEvents()
            self.assertTrue(owner._docked)
            self.assertTrue(native.isVisible())
            self.assertFalse(native.mask().intersects(QRegion(owner.rect())))
            image = owner.grab().toImage()
            self.assertTrue(all(image.pixelColor(x,y).alpha()==0 for x in range(142) for y in range(142)))
            self.assertTrue(window.character.isVisible())
            self.assertEqual(window.character.width(), 92)
            with patch.object(owner, 'move', wraps=owner.move) as move:
                window.close()
                app.processEvents()
                move.assert_not_called()
            self.assertFalse(owner._docked)
            self.assertIs(owner.windowHandle(), native)
            self.assertEqual(owner.pos(), pos)
            self.assertTrue(native.mask().isEmpty())
            self.assertFalse(owner.testAttribute(Qt.WA_TransparentForMouseEvents))
            self.assertGreater(owner.grab().toImage().pixelColor(71,78).alpha(),0)

    def test_all_edges_keep_same_surface_output_saved_position_and_idle_depth(self):
        owner, window = self.companion()
        owner.move(330, 170)
        owner.show()
        app.processEvents()
        for side in ('bottom', 'left', 'right'):
            with patch.object(QApplication, 'platformName', return_value='wayland'):
                owner.hide_at_edge(side, animate=False)
            edge, saved = owner.edge_window, QPoint(owner.saved_position)
            owner.peek = owner.peek_target = .3
            owner._edge_hover_armed = True
            for _ in range(2):
                window.show_quick()
                app.processEvents()
                owner._check_edge(edge)  # Intentionally hidden is not an exposure failure.
                owner.set_edge_hover(False)
                owner.edge_pointer_moved(40, 20, False)
                owner.tick()
                self.assertFalse(edge.isVisible())
                self.assertEqual(owner.peek, .3)
                self.assertEqual(owner.conceal, 1)
                self.assertEqual(owner.edge_phase, 'hidden')
                self.assertEqual(owner.saved_position, saved)
                window.show_workspace()
                window.show_quick()
                self.assertFalse(edge.isVisible())
                window.close()
                app.processEvents()
                self.assertIs(owner.edge_window, edge)
                self.assertTrue(edge.isVisible())
                self.assertEqual(owner.edge_side, side)
            owner.restore()

    def test_transition_clock_pauses_while_docked_and_resumes_after_close(self):
        owner, window = self.companion()
        owner.timer.stop()
        with patch.object(QApplication, 'platformName', return_value='wayland'):
            owner.start_hidden()
        owner.begin_restore()
        began = owner.transition_start
        with patch('hya.time.monotonic', return_value=began+.1):
            window.show_quick()
        with patch('hya.time.monotonic', return_value=began+10):
            owner.tick()
            self.assertEqual(owner.edge_phase, 'restoring')
            self.assertIsNotNone(owner.edge_window)
            window.close()
            self.assertAlmostEqual(owner.transition_start, began+9.9, places=4)
        with patch('hya.time.monotonic', return_value=began+10.7):
            owner.tick()
            self.assertFalse(owner.hidden_at_edge)

    def test_shared_render_pixels_expressions_colors_and_clock(self):
        owner, window = self.companion()
        owner.timer.stop()
        window.show_workspace()
        self.assertEqual(window.character.size().width(), 114)
        owner.appearance.select('Amethyst')
        for expression, elapsed in (('thinking', 1.), ('sleeping', 5.), ('sneeze', 1.05), ('look_around', 2.5), ('sniffle', .6)):
            owner.personality.play_expression(expression, now=owner.start)
            owner.pose = owner.personality.advance(owner.start+elapsed)
            frames=[]
            for original in (False,True):
                image=QImage(114,114,QImage.Format_ARGB32_Premultiplied)
                image.fill(0)
                p=QPainter(image)
                if original:
                    p.scale(114/142,114/142)
                    paint_hyal(p, elapsed, owner.appearance.palette, owner.pose)
                else:
                    with patch('chat_widgets.time.monotonic', return_value=owner.start+elapsed):
                        window.character.paint_character(p)
                p.end()
                frames.append(image)
            self.assertEqual(*frames, expression)
        self.assertEqual(owner.appearance.preset, 'Amethyst')

    def test_streaming_updates_animation_and_manual_sleep_survives(self):
        owner, window = self.companion()
        window.show_quick()
        spy=QSignalSpy(owner.frame_ready)
        reply=self.send()
        QTest.qWait(110)
        self.assertGreaterEqual(spy.count(), 2)
        self.assertEqual(owner.personality.state, 'thinking')
        reply.feed(b'{"message":{"content":"hello "},"done":false}\n')
        window.input.setPlainText('next draft')
        owner.play_expression('sleeping')
        manual_start=owner.personality.started
        owner.personality.advance(manual_start+5)
        owner.pose=owner.personality.sample(manual_start+5)
        window.show_workspace()
        window.show_quick()
        self.assertTrue(owner._docked)
        self.assertEqual(window.input.toPlainText(),'next draft')
        reply.done(b'{"message":{"content":"friend"},"done":true}\n')
        self.assertEqual(window.response,'hello friend')
        self.assertEqual(owner.personality.source,'manual')
        window.close()
        self.assertEqual(owner.personality.active_expression,'sleeping')

    def test_studio_uses_docked_preview_and_drag_does_not_move_desktop(self):
        owner, window = self.companion()
        owner.show()
        app.processEvents()
        owner.show_expression_studio()
        app.processEvents()
        self.assertTrue(owner._studio_dialog.isVisible())
        window.show_quick()
        self.assertFalse(owner._studio_dialog.isVisible())
        owner.show_expression_studio()
        self.assertFalse(owner._studio_dialog.isVisible())
        owner.play_expression('sneeze')
        point=owner.pos()
        QTest.mousePress(window.character,Qt.LeftButton)
        QTest.mouseMove(window.character,QPoint(20,20))
        QTest.mouseRelease(window.character,Qt.LeftButton)
        self.assertEqual(owner.pos(),point)
        window.close()
        self.assertTrue(owner._studio_dialog.isVisible())

    def test_show_failure_and_construction_failure_do_not_strand_character(self):
        owner, window = self.companion()
        owner.show()
        app.processEvents()
        with patch.object(window,'activateWindow',side_effect=RuntimeError('test failure')), patch('hya.QMessageBox.warning'):
            owner.open_chat()
        self.assertFalse(owner._docked)
        self.assertFalse(window.isVisible())
        self.assertTrue(owner.windowHandle().mask().isEmpty())
        owner._chat_window=None
        with patch('chat_window.ChatWindow',side_effect=OSError('history unavailable')), patch('hya.QMessageBox.warning'):
            owner.open_chat()
        self.assertFalse(owner._docked)
        owner._chat_window=window

    def test_unavailable_server_startup_docks_and_close_restores_quiet_edge(self):
        owner, window = self.companion()
        with patch.object(QApplication,'platformName',return_value='wayland'):
            owner.start_hidden()
        window.refresh()
        reply=self.manager.calls[-1][2]
        reply.status=None
        reply.code=fixtures.QNetworkReply.ConnectionRefusedError
        reply.done()
        window.show_quick()
        self.assertFalse(owner.edge_window.isVisible())
        self.assertFalse(window.send_button.isEnabled())
        self.assertIn('offline',window.status.text())
        window.close()
        self.assertTrue(owner.edge_window.isVisible())
        self.assertFalse(owner.isVisible())

    def test_window_manager_close_shutdown_and_screen_removal(self):
        owner, window = self.companion()
        with patch.object(QApplication,'platformName',return_value='wayland'):
            owner.start_hidden()
        window.show_workspace()
        window.windowHandle().close()  # Native WM close path, not just our button.
        app.processEvents()
        self.assertFalse(owner._docked)
        self.assertTrue(owner.edge_window.isVisible())
        window.show_quick()
        owner._screen_removed(owner.edge_bridge.output)
        self.assertTrue(owner._docked)
        self.assertFalse(owner.edge_window.isVisible())
        window.close()
        self.assertFalse(owner.hidden_at_edge)
        window.show_quick()
        reply=self.send()
        with patch.object(QApplication,'quit'):
            owner.close()
        self.assertTrue(window._closed)
        self.assertFalse(window.isVisible())
        self.assertTrue(reply.aborted)
        self.assertFalse(owner.timer.isActive())

    def test_width_bounds_and_character_centered_after_resize(self):
        owner, window = self.companion()
        window.show_workspace()
        QTest.qWait(30)
        area=owner.screen().availableGeometry()
        self.assertEqual(window.width(),min(720,area.width()))
        self.assertTrue(area.contains(window.geometry()))
        for size in ((720,700),(600,600),(410,470)):
            window.resize(*size)
            app.processEvents()
            self.assertAlmostEqual(window.character.geometry().center().x(), window.rect().center().x(), delta=2)
            self.assertTrue(window.rect().contains(window.character.geometry()))
        window.show_quick()
        self.assertEqual(window.character.width(),92)

    def test_reader_scroll_position_survives_expansion_and_contraction(self):
        owner, window = self.companion()
        window.show_quick()
        reply=self.send()
        text='A line of conversation.\n'*150
        reply.feed((json.dumps({'message':{'content':text},'done':False})+'\n').encode())
        window._render_response()
        QTest.qWait(70)
        bar=window.scroll.verticalScrollBar()
        bar.setValue(200)
        self.assertFalse(window._follow_tail)
        for display in (window.show_workspace, window.show_quick):
            display()
            QTest.qWait(40)
            self.assertEqual(bar.value(),200)
            self.assertFalse(window._follow_tail)
            self.assertTrue(owner._docked)
        self.client.cancel()

    def test_x11_fallback_restores_all_edge_masks_and_positions(self):
        owner, window = self.companion()
        owner.show()
        owner.move(200,140)
        app.processEvents()
        for side in ('bottom','left','right'):
            with patch.object(QApplication,'platformName',return_value='xcb'):
                owner.hide_at_edge(side,animate=False)
            native=owner.windowHandle()
            pos=owner.pos()
            mask=QRegion(owner.mask())
            window.show_quick()
            self.assertIsNone(owner.edge_window)
            self.assertFalse(native.mask().intersects(QRegion(owner.rect())))
            window.close()
            self.assertEqual(owner.pos(),pos)
            self.assertEqual(owner.mask(),mask)
            self.assertTrue(owner.hidden_at_edge)
            owner.restore()
