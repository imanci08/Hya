"""No running Ollama required: fake HTTP replies drive the real transport."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from ai_settings import AISettings, local_endpoint
from ollama_client import OllamaClient
from conversation_store import ConversationStore
from personality import ExpressionController
from ai_activity import AIActivity
from chat_window import ChatWindow

app = QApplication.instance() or QApplication([])


class Reply(QObject):
    readyRead = Signal()
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.data = b''
        self.status = 200
        self.code = QNetworkReply.NoError
        self.aborted = False

    def readAll(self):
        data, self.data = self.data, b''
        return data

    def attribute(self, _):
        return self.status

    def error(self):
        return self.code

    def errorString(self):
        return 'Connection refused' if self.code else 'HTTP failure'

    def abort(self):
        self.aborted = True
        self.finished.emit()

    def feed(self, data):
        self.data += data
        self.readyRead.emit()

    def done(self, data=b''):
        self.feed(data)
        self.finished.emit()


class Manager:
    def __init__(self):
        self.calls = []

    def setProxy(self, proxy):
        self.proxy = proxy

    def get(self, request):
        return self.post(request, None)

    def post(self, request, data):
        reply = Reply()
        self.calls.append((request, json.loads(data) if data else None, reply))
        return reply


class LocalAI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = AISettings(Path(self.temp.name) / 'ai.ini')
        self.manager = Manager()
        self.client = OllamaClient(self.settings, manager=self.manager)
        self.addCleanup(self.client.shutdown)
        self.errors = []
        self.client.failed.connect(self.errors.append)

    def discover(self, rows=None):
        self.client.refresh_models()
        rows = [{'name': 'tiny:latest'}] if rows is None else rows
        self.manager.calls[-1][2].done(json.dumps({'models': rows}).encode())

    def generate(self):
        self.discover()
        self.client.generate('tiny:latest', [{'role': 'user', 'content': 'Hi'}])
        self.manager.calls[-1][2].done(b'{"model_info":{"general.architecture":"test"},"capabilities":["completion"]}')
        return self.manager.calls[-1][2]

    def test_endpoint_and_persisted_selection(self):
        for bad in ('https://example.com', 'http://192.168.1.2:11434', 'http://127.0.0.1/x', 'http://user@localhost', 'http://localhost:99999'):
            with self.assertRaises(ValueError):
                local_endpoint(bad)
        self.assertEqual(local_endpoint('http://localhost:1234/'), 'http://127.0.0.1:1234')
        self.settings.model = 'tiny:latest'
        self.settings.context = 2048
        self.settings.save()
        again = AISettings(self.settings.store.fileName())
        self.assertEqual(again.model, 'tiny:latest')
        self.assertEqual(again.context, 2048)

    def test_detection_and_local_discovery(self):
        with patch('ollama_client.shutil.which', return_value=None):
            self.assertFalse(OllamaClient(self.settings, manager=Manager()).installed)
        found = []
        self.client.models_ready.connect(found.append)
        self.discover([{'name': 'tiny:latest'}, {'name': 'remote:cloud'}, {'name': 'alias', 'remote_host': 'https://ollama.com'}, {'name': 'other', 'remote_model': 'cloud'}])
        self.assertEqual(found, [['tiny:latest']])
        self.assertTrue(self.manager.calls[0][0].url().toString().endswith('/api/tags'))
        with self.assertRaises(ValueError):
            self.client.generate('missing', [{'role': 'user', 'content': 'hi'}])

    def test_fragmented_utf8_stream_and_request_settings(self):
        reply = self.generate()
        result, complete = [], []
        self.client.chunk.connect(result.append)
        self.client.completed.connect(lambda: complete.append(True))
        packet = json.dumps({'message': {'content': 'Hi ◇'}, 'done': False}, ensure_ascii=False).encode() + b'\n'
        for byte in packet:
            reply.feed(bytes([byte]))
        reply.done(b'{"message":{"content":"!"},"done":true}')
        self.assertEqual(''.join(result), 'Hi ◇!')
        self.assertEqual(complete, [True])
        self.assertFalse(self.client.busy)
        request, payload, _ = self.manager.calls[-1]
        self.assertEqual(payload['options']['num_ctx'], 4096)
        self.assertEqual(payload['keep_alive'], 0)
        self.assertTrue(payload['stream'])
        self.assertEqual(request.attribute(QNetworkRequest.RedirectPolicyAttribute), QNetworkRequest.ManualRedirectPolicy)

    def test_cancel_during_preflight_and_generation(self):
        self.discover()
        self.client.generate('tiny:latest', [{'role': 'user', 'content': 'hi'}])
        preflight = self.manager.calls[-1][2]
        cancelled = []
        self.client.cancelled.connect(lambda: cancelled.append(True))
        self.client.cancel()
        preflight.done(b'{"model_info":{"x":1}}')
        self.assertEqual(len(self.manager.calls), 2)
        self.assertTrue(preflight.aborted)
        reply = self.generate()
        reply.feed(b'{"message":{"content":"partial"},"done":false}\n')
        self.client.cancel()
        reply.done(b'{"done":true}\n')
        self.assertEqual(cancelled, [True, True])
        self.assertFalse(self.errors)

    def test_cloud_preflight_never_sends_conversation(self):
        self.discover()
        self.client.generate('tiny:latest', [{'role': 'user', 'content': 'private'}])
        self.manager.calls[-1][2].done(b'{"remote_host":"https://ollama.com","model_info":{"x":1}}')
        self.assertFalse(any('/api/chat' in call[0].url().toString() for call in self.manager.calls))
        self.assertIn('Cloud', self.errors[-1])

    def test_stream_error_truncation_invalid_and_timeout(self):
        for body in (b'{"error":"out of memory"}\n', b'not json\n', b'{"message":{"content":"unfinished"}}\n'):
            reply = self.generate()
            reply.done(body)
            self.assertFalse(self.client.busy)
        self.assertEqual(len(self.errors), 3)
        self.generate()
        self.client._generation['timer'].timeout.emit()
        self.assertIn('timed out', self.errors[-1])

    def test_http_failure_and_unavailable_server(self):
        failures = []
        self.client.discovery_failed.connect(failures.append)
        self.client.refresh_models()
        reply = self.manager.calls[-1][2]
        reply.status = None
        reply.code = QNetworkReply.ConnectionRefusedError
        reply.done()
        self.assertIn('Connection refused', failures[-1])
        reply = self.generate()
        reply.status = 404
        reply.done(b'{"error":"model disappeared"}')
        self.assertIn('404', self.errors[-1])
        self.assertIn('model disappeared', self.errors[-1])

    def test_history_crash_recovery_cancel_and_delete(self):
        path = Path(self.temp.name) / 'history.sqlite3'
        store = ConversationStore(path)
        conversation = store.new()
        reply = store.begin(conversation, 'hello', 'tiny')
        store.finish(reply, 'hello back', 'complete')
        reply = store.begin(conversation, 'second', 'tiny')
        store.finish(reply, 'partial', 'cancelled')
        store.begin(conversation, 'third', 'tiny')
        store.close()
        store = ConversationStore(path)
        self.addCleanup(store.close)
        rows = store.messages(conversation)
        self.assertEqual([r['status'] for r in rows], ['complete', 'complete', 'complete', 'cancelled', 'complete', 'interrupted'])
        self.assertNotIn('partial', str(store.context(conversation)))
        self.assertEqual(store.context(conversation)[1]['content'], 'hello back')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        other = store.new()
        store.delete(conversation)
        self.assertFalse(store.messages(conversation))
        self.assertEqual(len(store.conversations()), 1)
        store.begin(other, 'hi', 'tiny')
        store.clear(other)
        self.assertFalse(store.messages(other))
        with self.assertRaises(ValueError):
            store.begin(other, ' ', 'tiny')

    def test_expression_activity_respects_manual_sleep(self):
        now = [0.]
        actor = ExpressionController(clock=lambda: now[0])
        activity = AIActivity(actor)
        activity.begin()
        self.assertEqual(actor.source, 'ai')
        now[0] = 5
        actor.advance()
        activity.tick()
        self.assertEqual(actor.state, 'thinking')
        actor.play_expression('sleeping')
        now[0] = 10
        actor.advance()
        activity.tick()
        self.assertEqual(actor.state, 'sleeping')
        activity.end(failed=True)
        self.assertEqual(actor.state, 'sleeping')
        actor.reset()
        activity.begin()
        activity.end()
        self.assertEqual(actor.state, 'neutral')

    def test_chat_stream_cancel_reopen_and_plain_text(self):
        owner = QWidgetOwner()
        store = ConversationStore(Path(self.temp.name) / 'ui.sqlite3')
        window = ChatWindow(owner, self.settings, store, self.client)
        self.addCleanup(window.shutdown)
        app.processEvents()
        self.manager.calls[-1][2].done(b'{"models":[{"name":"tiny:latest"}]}')
        window.models.setCurrentIndex(1)
        window.input.setPlainText('Hello')
        window.send()
        self.assertTrue(window.stop_button.isEnabled())
        self.assertFalse(window.models.isEnabled())
        self.manager.calls[-1][2].done(b'{"model_info":{"x":1}}')
        self.manager.calls[-1][2].feed(b'{"message":{"content":"<script>text</script>"},"done":false}\n')
        window._render_response()
        self.assertEqual(window.reply_label.textFormat(), Qt.PlainText)
        self.client.cancel()
        self.assertEqual(store.messages(window.conversation)[-1]['status'], 'cancelled')
        self.assertFalse(window.stop_button.isEnabled())
        self.assertEqual(owner.personality.state, 'neutral')
        window.input.setPlainText('Again')
        window.send()
        self.manager.calls[-1][2].done(b'{"model_info":{"x":1}}')
        self.manager.calls[-1][2].done(b'{"message":{"content":"Hi!"},"done":true}\n')
        self.assertEqual(store.messages(window.conversation)[-1]['status'], 'complete')
        window.close()
        window.show()
        self.assertEqual(window.message_layout.count(), 4)
        with patch.object(window, '_confirm', return_value=True):
            window.clear_conversation()
        self.assertEqual(window.message_layout.count(), 0)
        window.hide()

    def test_chat_unavailable_and_input_keys(self):
        owner = QWidgetOwner()
        store = ConversationStore(Path(self.temp.name) / 'offline.sqlite3')
        window = ChatWindow(owner, self.settings, store, self.client)
        self.addCleanup(window.shutdown)
        app.processEvents()
        reply = self.manager.calls[-1][2]
        reply.status = None
        reply.code = QNetworkReply.ConnectionRefusedError
        reply.done()
        self.assertFalse(window.send_button.isEnabled())
        self.assertIn('offline', window.status.text())
        window.input.setPlainText('hello')
        QTest.keyClick(window.input, Qt.Key_Return, Qt.ShiftModifier)
        self.assertIn('\n', window.input.toPlainText())
        QTest.keyClick(window.input, Qt.Key_Return)
        self.assertIsNone(window.pending)
        self.assertFalse(store.messages(window.conversation))


from PySide6.QtWidgets import QWidget
class QWidgetOwner(QWidget):
    def __init__(self):
        super().__init__()
        self.personality = ExpressionController()
        self.ai_activity = AIActivity(self.personality)

class IntegrationTests(unittest.TestCase):
    setUp = LocalAI.setUp
    discover = LocalAI.discover
    generate = LocalAI.generate
    def test_model_switch_unloads_previous_before_loading_next(self):
        reply = self.generate()
        reply.done(b'{"message":{"content":"ok"},"done":true}\n')
        self.client.models.append('second:latest')
        self.client.generate('second:latest', [{'role': 'user', 'content': 'hi'}])
        request, payload, reply = self.manager.calls[-1]
        self.assertTrue(request.url().toString().endswith('/api/generate'))
        self.assertEqual(payload['keep_alive'], 0)
        self.assertNotIn('messages', payload)
        reply.done(b'{"done":true}')
        self.assertTrue(self.manager.calls[-1][0].url().toString().endswith('/api/show'))

    def test_real_companion_chat_and_ai_pose_share_all_edge_surfaces(self):
        from hyal import Hya
        from test_hyal import app
        from PySide6.QtCore import QSettings
        from appearance import Appearance
        owner = Hya(0, appearance=Appearance(QSettings(str(Path(self.temp.name)/'appearance.ini'), QSettings.IniFormat)))
        owner.timer.stop()
        self.addCleanup(owner.deleteLater)
        window = ChatWindow(owner, self.settings, ConversationStore(Path(self.temp.name)/'edge.sqlite3'), self.client)
        self.addCleanup(window.shutdown)
        app.processEvents()
        self.manager.calls[-1][2].done(b'{"models":[{"name":"tiny:latest"}]}')
        window.models.setCurrentIndex(1)
        owner._chat_window = window
        owner.show()
        app.processEvents()
        for side in ('bottom', 'left', 'right'):
            with patch.object(QApplication, 'platformName', return_value='wayland'):
                owner.hide_at_edge(side, animate=False)
            saved = owner.saved_position
            window.input.setPlainText('Hello')
            window.send()
            owner.tick()
            self.assertEqual(owner.personality.source, 'ai')
            self.assertEqual(owner.personality.state, 'thinking')
            self.assertEqual(owner.pose.mouth, 'thought')
            self.assertIsNotNone(owner.edge_window)
            owner.open_chat()
            app.processEvents()
            self.assertTrue(window.isVisible())
            self.assertEqual(owner.saved_position, saved)
            self.assertTrue(owner.hidden_at_edge)
            self.client.cancel()
            owner.restore()
            self.assertEqual(owner.personality.state, 'neutral')
        window.hide()
        owner.hide()
