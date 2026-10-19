"""Render the actual chat UI offscreen with a fake local model; no inference."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QObject, Signal, QTimer, QSettings
from hya import Hya
from appearance import Appearance
from ai_settings import AISettings
from conversation_store import ConversationStore
from ai_activity import AIActivity
from personality import ExpressionController
from chat_window import ChatWindow

class PreviewClient(QObject):
    models_ready = Signal(list)
    discovery_failed = Signal(str)
    chunk = Signal(str)
    completed = Signal()
    failed = Signal(str)
    cancelled = Signal()
    busy_changed = Signal(bool)
    busy = False
    installed = True
    models = ['Preview model (no inference)']
    def refresh_models(self): self.models_ready.emit(self.models)
    def cancel(self): pass
    def shutdown(self): pass

app = QApplication.instance() or QApplication([])
with tempfile.TemporaryDirectory() as temp:
    owner = Hya(0, appearance=Appearance(QSettings(str(Path(temp)/'appearance.ini'), QSettings.IniFormat)))
    settings = AISettings(Path(temp) / 'ai.ini')
    settings.model = PreviewClient.models[0]
    store = ConversationStore(Path(temp) / 'history.sqlite3')
    conversation = store.new()
    reply = store.begin(conversation, 'Hi Hya! What can you help me with?', settings.model)
    store.finish(reply, 'Hi! I can help you think through an idea, explain something puzzling, or draft a little text. What are you curious about today?', 'complete')
    window = ChatWindow(owner, settings, store, PreviewClient())
    window.show_quick()
    def capture():
        destination = Path(__file__).resolve().parents[1] / 'previews' / 'local-chat.png'
        window.grab().save(str(destination))
        print(destination)
        window.show_workspace()
        QTimer.singleShot(150, capture_workspace)
    def capture_workspace():
        destination = Path(__file__).resolve().parents[1] / 'previews' / 'chat-workspace.png'
        window.grab().save(str(destination))
        print(destination)
        window.shutdown()
        app.quit()
    QTimer.singleShot(300, capture)
    app.exec()
