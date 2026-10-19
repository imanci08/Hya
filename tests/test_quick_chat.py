"""Quick/workspace are two presentations of one live chat session."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QRect, QSize, QPoint, Qt, QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QLineEdit
from appearance import Appearance
from chat_widgets import quick_geometry, character_anchor, fenced_blocks, MessageBubble
from chat_window import ChatWindow
from conversation_store import ConversationStore
from hya import Hya
from test_hyal import app
import test_local_ai as fixtures


class GeometryTests(unittest.TestCase):
    def test_each_edge_normal_negative_monitor_origins_and_small_displays(self):
        for area in (QRect(0, 0, 1920, 1040), QRect(-1920, -200, 1920, 1040), QRect(0, 0, 320, 400)):
            anchors = {'bottom': QRect(area.right()-165, area.bottom()-70, 142, 142),
                       'left': QRect(area.left(), area.top()+30, 142, 142),
                       'right': QRect(area.right()-141, area.bottom()-141, 142, 142),
                       'normal': QRect(area.left()+30, area.top()+30, 142, 142)}
            for side, anchor in anchors.items():
                rect = quick_geometry(area, anchor, side)
                self.assertTrue(area.contains(rect), (area, side, rect))
                if area.width() > 1000:
                    if side == 'left': self.assertGreater(rect.left(), anchor.right())
                    if side == 'right': self.assertLess(rect.right(), anchor.left())
                    if side == 'bottom': self.assertLess(rect.bottom(), anchor.top())
            tiny = quick_geometry(area, area, size=QSize(4000, 3000))
            self.assertEqual(tiny, area)

    def test_literal_fences_and_unclosed_blocks(self):
        text = 'Hello\n```python\nprint("<tag>")\n```\n~~~sh\necho hi\n~~~\n'
        self.assertEqual(fenced_blocks(text), [('python', 'print("<tag>")\n'), ('sh', 'echo hi\n')])
        self.assertEqual(fenced_blocks('```py\nunfinished'), [])
        self.assertEqual(fenced_blocks('````py\n```\n````\n'), [('py', '```\n')])


class QuickChatTests(unittest.TestCase):
    setUp = fixtures.LocalAI.setUp

    def chat(self):
        self.owner = fixtures.QWidgetOwner()
        self.window = ChatWindow(self.owner, self.settings,
                ConversationStore(Path(self.temp.name) / 'quick.sqlite3'), self.client)
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.shutdown)
        app.processEvents()
        self.manager.calls[-1][2].done(b'{"models":[{"name":"tiny:latest"}]}')
        self.window.models.setCurrentIndex(1)
        return self.window

    def begin(self, window):
        window.input.setPlainText('Hello Hya')
        QTest.keyClick(window.input, Qt.Key_Return)
        self.manager.calls[-1][2].done(b'{"model_info":{"architecture":"fake"}}')
        return self.manager.calls[-1][2]

    def test_compact_open_focus_and_options_separate_from_conversation(self):
        window = self.chat()
        window.show_quick()
        app.processEvents()
        self.assertTrue(window.isVisible())
        self.assertTrue(window.compact)
        self.assertFalse(window.workspace_controls.isVisible())
        self.assertFalse(window.windowFlags() & Qt.WindowStaysOnTopHint)
        self.assertIsNone(window.parentWidget())  # cannot inherit companion keep-above
        self.assertIs(app.focusWidget(), window.input)
        self.assertLessEqual(window.width(), 430)
        self.assertFalse(any(b.text()=='Options' for b in window.findChildren(QPushButton)))
        QTest.mouseClick(window.expand_button, Qt.LeftButton)
        app.processEvents()
        self.assertFalse(window.compact)
        self.assertTrue(window.models.isVisible())
        self.assertIs(app.focusWidget(), window.input)
        old = window.size()
        window.resize(old.width()+20, old.height()+10)
        self.assertGreater(window.width(), old.width())
        self.assertTrue(window.size_grip.isVisible())
        with patch.object(window.windowHandle(), 'startSystemMove', return_value=True) as move:
            QTest.mousePress(window.header, Qt.LeftButton, pos=QPoint(3, 3))
            move.assert_called_once()
            QTest.mouseRelease(window.header, Qt.LeftButton)

    def test_expand_compact_preserve_stream_draft_and_single_request(self):
        window = self.chat()
        window.show_quick()
        reply = self.begin(window)
        conversation, pending, count = window.conversation, window.pending, len(self.manager.calls)
        packet = lambda text, done=False: (json.dumps({'message': {'content': text}, 'done': done})+'\n').encode()
        reply.feed(packet('First '))
        window._render_response()
        label = window.reply_label
        window.input.setPlainText('My unsent draft')
        QTest.mouseClick(window.expand_button, Qt.LeftButton)
        reply.feed(packet('second '))
        QTest.mouseClick(window.expand_button, Qt.LeftButton)
        reply.done(packet('third', True))
        app.processEvents()
        self.assertEqual(len(self.manager.calls), count)
        self.assertEqual(window.conversation, conversation)
        self.assertEqual(window.response, 'First second third')
        self.assertIs(window.reply_label, label)
        self.assertEqual(label.text(), 'First second third')
        self.assertEqual(window.input.toPlainText(), 'My unsent draft')
        row = window.store.messages(conversation)[-1]
        self.assertEqual((row['id'], row['status'], row['content']), (pending, 'complete', 'First second third'))
        self.assertFalse(window.stop_button.isEnabled())

    def test_close_cancels_without_quit_and_reopen_retains_history(self):
        window = self.chat()
        window.show_quick()
        reply = self.begin(window)
        reply.feed(b'{"message":{"content":"partial"},"done":false}\n')
        with patch.object(QApplication, 'quit') as quit_app:
            QTest.mouseClick(window.close_button, Qt.LeftButton)
            app.processEvents()
            quit_app.assert_not_called()
        self.assertFalse(window.isVisible())
        self.assertTrue(reply.aborted)
        self.assertFalse(self.client.busy)
        self.assertFalse(self.owner.ai_activity.busy)
        self.assertEqual(window.store.messages(window.conversation)[-1]['status'], 'cancelled')
        window.show_quick()
        self.assertEqual(window.reply_label.text(), 'partial')
        window.show_workspace()
        self.begin(window)
        QTest.keyClick(window, Qt.Key_Escape)
        self.assertFalse(self.client.busy)
        self.assertFalse(window.isVisible())

    def test_stop_copy_response_code_and_reloaded_history(self):
        window = self.chat()
        window.show_quick()
        reply = self.begin(window)
        text = 'Try this:\n```python\nprint("<safe>")\n```\n'
        reply.done((json.dumps({'message': {'content': text}, 'done': True})+'\n').encode())
        frame = window.reply_label.parentWidget()
        buttons = frame.findChildren(QPushButton)
        copy = next(button for button in buttons if button.text() == 'Copy Response')
        QTest.mouseClick(copy, Qt.LeftButton)
        self.assertEqual(app.clipboard().text(), text)
        code = next(button for button in buttons if button.text().startswith('Copy code'))
        QTest.mouseClick(code, Qt.LeftButton)
        self.assertEqual(app.clipboard().text(), 'print("<safe>")\n')
        self.assertEqual(window.reply_label.textFormat(), Qt.PlainText)
        window._load_messages()
        frame = window.message_layout.itemAt(1).widget()
        self.assertTrue(any(button.text().startswith('Copy code') for button in frame.findChildren(QPushButton)))
        reply = self.begin(window)
        QTest.mouseClick(window.stop_button, Qt.LeftButton)
        self.assertTrue(reply.aborted)
        self.assertEqual(window.store.messages(window.conversation)[-1]['status'], 'cancelled')

    def test_stream_does_not_activate_window_or_force_reader_to_bottom(self):
        window = self.chat()
        window.show_quick()
        reply = self.begin(window)
        reply.feed((json.dumps({'message': {'content': 'A long response.\n'*100}, 'done': False})+'\n').encode())
        window._render_response()
        QTest.qWait(80)
        bar = window.scroll.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        bar.setValue(0)
        self.assertFalse(window._follow_tail)
        with patch.object(window, '_activate_input') as activate:
            reply.feed(b'{"message":{"content":"Still going"},"done":false}\n')
            window._render_response()
            app.processEvents()
            self.assertEqual(bar.value(), 0)
            activate.assert_not_called()
        self.client.cancel()

    def test_double_click_and_edge_opening_preserve_character_surfaces(self):
        window = self.chat()
        appearance = Appearance(QSettings(str(Path(self.temp.name)/'appearance.ini'), QSettings.IniFormat))
        owner = Hya(40, appearance=appearance)
        owner.timer.stop()
        owner._chat_window = window
        window.owner = owner
        self.addCleanup(owner.deleteLater)
        owner.show()
        owner.move(100, 100)
        app.processEvents()
        QTest.mouseDClick(owner, Qt.LeftButton)
        app.processEvents()
        self.assertTrue(window.isVisible())
        for side in ('bottom', 'left', 'right'):
            with patch.object(QApplication, 'platformName', return_value='wayland'):
                owner.hide_at_edge(side, animate=False)
            edge, saved = owner.edge_window, owner.saved_position
            anchor, inferred_side = character_anchor(owner, owner.edge_bridge.output)
            self.assertEqual(inferred_side, side)
            owner.edge_bridge.chat()
            app.processEvents()
            self.assertTrue(owner.hidden_at_edge)
            self.assertIs(owner.edge_window, edge)
            self.assertEqual(owner.saved_position, saved)
            self.assertEqual(owner.conceal, 1)
            self.assertTrue(owner.screen().availableGeometry().contains(window.geometry()))
            owner.play_expression('sleeping')
            self.begin(window)
            owner.tick()
            self.client.cancel()
            self.assertEqual(owner.personality.active_expression, 'sleeping')
            owner.play_expression('reset')
        owner.restore()
        owner.hide()
        if owner._studio_dialog:
            owner._studio_dialog.close()

    def test_peek_double_click_routes_to_chat_without_replacing_surface(self):
        window = self.chat()
        owner = Hya(40, appearance=Appearance(QSettings(str(Path(self.temp.name)/'peek.ini'), QSettings.IniFormat)))
        owner.timer.stop()
        self.addCleanup(owner.deleteLater)
        owner._chat_window = window
        window.owner = owner
        with patch.object(QApplication, 'platformName', return_value='wayland'):
            owner.start_hidden()
        app.processEvents()
        edge = owner.edge_window
        point = QPoint(71, 130)
        QTest.mouseClick(edge, Qt.LeftButton, Qt.NoModifier, point)
        QTest.mouseDClick(edge, Qt.LeftButton, Qt.NoModifier, point)
        QTest.mouseRelease(edge, Qt.LeftButton, Qt.NoModifier, point)
        app.processEvents()
        self.assertTrue(window.isVisible())
        self.assertIs(owner.edge_window, edge)
        self.assertEqual(owner.edge_phase, 'restoring')
        owner.restore()
        owner.hide()
