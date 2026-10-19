"""Hya's modeless, plain-text local conversation window."""
from pathlib import Path
import sqlite3
import json
import re
from PySide6.QtCore import Qt, Signal, QTimer, QSize, QRect
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QScrollArea, QPlainTextEdit, QMessageBox, QFrame,
    QFormLayout, QLineEdit, QSpinBox, QDialogButtonBox, QSizeGrip, QApplication, QCheckBox)
from chat_widgets import (DragHandle, DockedCharacter, MessageBubble, quick_geometry, character_anchor)
from ai_settings import AISettings, local_endpoint
from conversation_store import ConversationStore
from ollama_client import OllamaClient
from desktop_service import DesktopService
from glass_wordmark import GlassWordmark
from action_presentation import action_summary, visible_text, stream_text


class MessageInput(QPlainTextEdit):
    send_requested = Signal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
            self.send_requested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class ChatWindow(QDialog):
    def __init__(self, owner, settings=None, store=None, client=None):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint)
        self.owner = owner
        self.settings = settings or AISettings()
        self.store = store or ConversationStore()
        self.client = client or OllamaClient(self.settings, self)
        self.desktop = None
        self._permission_dialog = None
        self._desktop_capable = None
        self._desktop_action_started = False
        if hasattr(self.client, 'attach_desktop'):
            self.desktop = DesktopService(self,settings=self.settings)
            self.client.attach_desktop(self.desktop)
            self.desktop.permission_needed.connect(self._request_permission)
            self.desktop.permission_cleared.connect(self._clear_permission)
            self.desktop.log_ready.connect(self._show_action_log)
            self.client.action_status.connect(self.status_action)
            self.client.action_result.connect(self._action_result)
            self.client.response_reset.connect(self._reset_response)
            self.client.tool_capability.connect(self._tool_capability)
        self.conversation = None
        self.pending = None
        self._last_action = None
        self.response = ''
        self.reply_label = None
        self._follow_tail = True
        self._changing_view = False
        self._view_serial = 0
        self._closed = False
        self.compact = True
        self._workspace_size = QSize(720, 800)
        self._quick_size = QSize(410, 470)
        self.setWindowTitle('Hya — Orb Quick Chat')
        self.setMinimumSize(300, 320)
        self.resize(self._quick_size)
        self.setAttribute(Qt.WA_TranslucentBackground)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        glass = QFrame()
        glass.setObjectName('glass')
        outer.addWidget(glass)
        layout = QVBoxLayout(glass)
        layout.setContentsMargins(20, 18, 20, 18)
        self.header = DragHandle()
        header = QHBoxLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        self.title = GlassWordmark(getattr(owner, 'appearance', None))
        header.addWidget(self.title)
        header.addStretch()
        self.expand_button = QPushButton('Expand')
        self.expand_button.setToolTip('Open full workspace without interrupting generation')
        self.close_button = QPushButton('×')
        self.close_button.setAccessibleName('Close chat')
        self.close_button.setFixedWidth(30)
        for button in (self.expand_button, self.close_button):
            header.addWidget(button)
        layout.addWidget(self.header)
        self.character = DockedCharacter(self)
        layout.addWidget(self.character, 0, Qt.AlignHCenter)
        self.workspace_controls = QWidget()
        workspace_layout = QVBoxLayout(self.workspace_controls)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.conversations = QComboBox()
        self.conversations.setAccessibleName('Conversation')
        row.addWidget(self.conversations, 1)
        self.new_button = QPushButton('New')
        self.clear_button = QPushButton('Clear')
        self.delete_button = QPushButton('Delete')
        self.action_log_button = QPushButton('Action Log')
        self.action_log_button.clicked.connect(lambda: self.desktop.read_log() if self.desktop else None)
        self.action_log_button.setEnabled(self.desktop is not None)
        for button in (self.new_button, self.clear_button, self.delete_button, self.action_log_button):
            row.addWidget(button)
        workspace_layout.addLayout(row)
        row = QHBoxLayout()
        self.models = QComboBox()
        self.models.setAccessibleName('Installed local model')
        row.addWidget(self.models, 1)
        self.refresh_button = QPushButton('Refresh models')
        self.settings_button = QPushButton('Settings')
        self.setup_button = QPushButton('AI Setup')
        self.setup_button.clicked.connect(self.owner.open_ai_setup if hasattr(self.owner,'open_ai_setup') else self._open_setup)
        row.addWidget(self.setup_button)
        row.addWidget(self.refresh_button)
        row.addWidget(self.settings_button)
        workspace_layout.addLayout(row)
        layout.addWidget(self.workspace_controls)
        self.workspace_controls.hide()
        self.status = QLabel('Checking local Ollama…')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.messages_widget = QWidget()
        self.messages_widget.setObjectName('messages')
        self.message_layout = QVBoxLayout(self.messages_widget)
        self.message_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.messages_widget)
        layout.addWidget(self.scroll, 1)
        self.input = MessageInput()
        self.input.setPlaceholderText('Talk to Hya…')
        self.input.setToolTip('Enter to send · Shift+Enter for a newline')
        self.input.setMaximumHeight(100)
        self.input.setAccessibleName('Message to Hya')
        layout.addWidget(self.input)
        row = QHBoxLayout()
        self.privacy_label = QLabel('Local · private history')
        self.privacy_label.setToolTip('History stays on this device. Model responses can be mistaken.')
        row.addWidget(self.privacy_label)
        row.addStretch()
        self.send_button = QPushButton('Send')
        self.stop_button = QPushButton('Stop')
        self.stop_button.setAccessibleName('Stop Generation')
        row.addWidget(self.send_button)
        row.addWidget(self.stop_button)
        self.size_grip = QSizeGrip(self)
        row.addWidget(self.size_grip)
        layout.addLayout(row)
        self.setStyleSheet('''
          QFrame#glass { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
            stop:0 rgba(29,55,98,180), stop:1 rgba(49,34,83,180));
            border:1px solid rgba(175,220,255,140); border-radius:18px; }
          QWidget { color:#eef5ff; font-size:13px; }
          QLabel#title { font-size:25px; font-weight:600; color:#d8edff; }
          QScrollArea { background:transparent; }
          QWidget#messages {
            background:rgba(20,30,55,242);
            border-radius:12px;
          }
          QFrame[bubble="true"] { background:rgba(160,195,255,26);
            border:1px solid rgba(180,215,255,55); border-radius:12px; }
          QFrame[speaker="user"] { background:rgba(100,135,255,55); }
          QPushButton, QComboBox, QPlainTextEdit, QLineEdit, QSpinBox {
            background:rgba(15,26,50,180); border:1px solid rgba(165,200,255,85);
            border-radius:7px; padding:7px; selection-background-color:#526faa; }
          QPushButton:hover { background:rgba(90,125,200,150); }
          QPushButton:disabled { color:#8e9ab5; }
          QComboBox QAbstractItemView { background:#253253; color:#eef5ff; }
          QScrollBar:vertical { background:rgba(12,22,44,90); width:9px; border-radius:4px; }
          QScrollBar::handle:vertical { background:rgba(160,190,240,140); border-radius:4px; min-height:24px; }
          QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
          QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
        ''')
        # QDialog's implicit default button must not turn Shift+Enter into Send.
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        self.expand_button.clicked.connect(self.toggle_workspace)
        self.close_button.clicked.connect(self.close)
        self.input.send_requested.connect(self.send)
        self.send_button.clicked.connect(self.send)
        self.stop_button.clicked.connect(self.client.cancel)
        self.refresh_button.clicked.connect(self.refresh)
        self.models.currentIndexChanged.connect(self._model_selected)
        self.conversations.currentIndexChanged.connect(self._conversation_selected)
        self.new_button.clicked.connect(self.new_conversation)
        self.clear_button.clicked.connect(self.clear_conversation)
        self.delete_button.clicked.connect(self.delete_conversation)
        self.settings_button.clicked.connect(self.edit_settings)
        self.client.models_ready.connect(self._models_ready)
        self.client.discovery_failed.connect(self._discovery_failed)
        self.client.chunk.connect(self._chunk)
        self.client.completed.connect(lambda: self._finished('complete'))
        self.client.cancelled.connect(lambda: self._finished('cancelled'))
        self.client.failed.connect(lambda error: self._finished('error', error))
        self.client.busy_changed.connect(self._busy_changed)
        bar = self.scroll.verticalScrollBar()
        bar.valueChanged.connect(self._scroll_changed)
        bar.rangeChanged.connect(self._scroll_range_changed)
        from glass_effects import request_blur
        request_blur = lambda widget: False
        self._blur_timer=QTimer(self)
        self._blur_timer.setSingleShot(True)
        self._blur_timer.timeout.connect(lambda:request_blur(self))
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render_response)
        rows = self.store.conversations()
        self.conversation = rows[0]['id'] if rows else self.store.new()
        self._load_conversations()
        self._load_messages()
        self._busy_changed(False)
        QTimer.singleShot(0, self.refresh)

    def status_action(self, text):
        if text == 'Running approved desktop action…':
            self._desktop_action_started = True
        self.status.setText(text)

    def _tool_capability(self, capable):
        self._desktop_capable = capable
        if not capable:
            self.status.setText('This model does not support AI desktop tools. Local shortcuts and ordinary chat remain available.')

    def _request_permission(self, token, details):
        self._clear_permission()
        dialog = QDialog(self)
        dialog.setWindowTitle('Hya — Desktop action permission')
        layout = QVBoxLayout(dialog)
        choices=details.get('choices',[])
        application=details.get('application')
        label = QLabel('Which application would you like to open?' if choices else
                       ('Open '+application['name']+'?' if application else
                        ('Authorize future filename searches in this directory?' if details['action']=='search_files' else 'Allow this exact action once?')))
        label.setTextFormat(Qt.PlainText)
        layout.addWidget(label)
        description = QPlainTextEdit()
        description.setReadOnly(True)
        display=details
        if choices:
            display={'request':details['requested_application'],'notice':details['notice']}
            if details.get('more_matches'): display['notice']+=' More matches exist; use a more specific name if needed.'
        elif application:
            display={'application':application['name'],'request':details.get('requested_application',application['name']),
                     'notice':'This application is not eligible for automatic launching, or automatic launching is disabled. Launch once? No additional arguments will be passed.',
                     'installed_entry':application['path'],'installed_launcher':application.get('exec',''),
                     'categories':application.get('categories',[])}
        description.setPlainText(json.dumps(display,ensure_ascii=True,indent=2))
        description.setMinimumSize(380,180)
        layout.addWidget(description)
        buttons = QHBoxLayout()
        selector=None
        if choices:
            selector=QComboBox()
            selector.setAccessibleName('Installed application choices')
            selector.addItem('Choose an application…',None)
            for row in choices:
                entry=row['application']
                name=entry['name']
                generic=entry.get('generic_names',[])
                if generic and generic[0].casefold()!=name.casefold(): name+=' — '+generic[0]
                selector.addItem(name,row['desktop_id'])
            layout.addWidget(selector)
        allow = QPushButton('Continue' if choices else
            ('Open '+application['name'] if application else
             ('Authorize directory searches' if details['action']=='search_files' else 'Allow once')))
        if choices:
            allow.setEnabled(False)
            selector.currentIndexChanged.connect(lambda:allow.setEnabled(selector.currentData() is not None))
        deny = QPushButton('Deny')
        stop = QPushButton('Stop generation')
        for button in (allow,deny,stop):
            button.setAutoDefault(False)
            buttons.addWidget(button)
        deny.setDefault(True)
        layout.addLayout(buttons)
        self._permission_dialog = dialog
        if choices:
            allow.clicked.connect(lambda:self.desktop.select_application(token,selector.currentData()))
        else:
            allow.clicked.connect(lambda: self.desktop.approve(token))
        deny.clicked.connect(lambda: self.desktop.deny(token))
        stop.clicked.connect(self.client.cancel)
        dialog.finished.connect(lambda _: self.desktop.deny(token) if self._permission_dialog is dialog else None)
        dialog.show()  # Modeless: Stop in chat and the character timer stay usable.

    def _clear_permission(self):
        dialog,self._permission_dialog = self._permission_dialog,None
        if dialog:
            dialog.close()
            dialog.deleteLater()

    def _reset_response(self):
        self.response = ''
        if self.reply_label is not None:
            self.reply_label.setText('Preparing desktop action…')

    def _action_result(self, record):
        self._last_action = record
        # One assistant bubble per turn. Results are internal; status is transient.
        self.status.setText(action_summary(record['tool'], record['result']).splitlines()[0][:240])

    def _show_action_log(self, text):
        dialog=QDialog(self)
        dialog.setWindowTitle('Hya — Desktop action log')
        layout=QVBoxLayout(dialog)
        path=QLabel(str(self.desktop.log.path))
        path.setTextFormat(Qt.PlainText)
        path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(path)
        content=QPlainTextEdit()
        content.setReadOnly(True)
        content.setPlainText(text)
        layout.addWidget(content)
        close=QPushButton('Close')
        close.clicked.connect(dialog.close)
        layout.addWidget(close)
        dialog.resize(620,420)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.show()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self, '_blur_timer'):self._blur_timer.start(0)

    def showEvent(self, event):
        # Qt delivers this before the first visible chat frame.
        if not self._closed and hasattr(self.owner, 'dock_to_chat'):
            self.owner.dock_to_chat()
        super().showEvent(event)
        self._blur_timer.start(0)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._blur_timer.stop()
        # Hide the embedded painter first; only then reveal the desktop.
        if not self._closed and hasattr(self.owner, 'undock_from_chat'):
            self.owner.undock_from_chat()

    def _target_screen(self):
        bridge = getattr(self.owner, 'edge_bridge', None)
        return bridge.output if bridge else self.owner.screen()

    def _activate_input(self):
        # Called only from explicit open/expand actions, never from stream/timers.
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus(Qt.OtherFocusReason)

    def show_quick(self):
        scroll = self._begin_view_change()
        self._set_compact(True)
        screen = self._target_screen()
        if screen:
            self.setScreen(screen)
            anchor, side = character_anchor(self.owner, screen)
            self.setGeometry(quick_geometry(screen.availableGeometry(), anchor, side, self._quick_size))
        self._activate_input()
        self._finish_view_change(scroll)

    def show_workspace(self):
        scroll = self._begin_view_change()
        self._set_compact(False)
        screen = self._target_screen()
        if screen:
            area = screen.availableGeometry()
            size = self._workspace_size.boundedTo(area.size())
            self.resize(size)
            # This is a compositor placement hint, not guaranteed on Wayland.
            self.move(max(area.left(), min(self.x(), area.right()+1-size.width())),
                      max(area.top(), min(self.y(), area.bottom()+1-size.height())))
        self._activate_input()
        self._finish_view_change(scroll)

    def show_workspace_options(self):
        self.show_workspace()
        self.models.setFocus(Qt.OtherFocusReason)

    def toggle_workspace(self):
        if self.compact:
            self.show_workspace()
        else:
            self.show_quick()

    def _set_compact(self, compact):
        if self.compact != compact:
            if self.compact:
                self._quick_size = self.size()
            else:
                self._workspace_size = self.size()
        self.compact = compact
        self.character.setFixedSize(92 if compact else 114, 92 if compact else 114)
        self.input.setMaximumHeight(72 if compact else 100)
        self.workspace_controls.setVisible(not compact)
        self.expand_button.setText('Expand' if compact else 'Compact')
        self.privacy_label.setText('Local · private history' if compact else 'Private history on this device. Responses can be mistaken.')
        self.setWindowTitle('Hya — Orb Quick Chat' if compact else 'Hya — Full Chat Workspace')
        self.layout().activate()

    def _begin_view_change(self):
        self._changing_view = True
        self._view_serial += 1
        return self.scroll.verticalScrollBar().value(), self._follow_tail, self._view_serial

    def _finish_view_change(self, saved):
        value, follow, serial = saved
        def restore_scroll():
            if serial != self._view_serial or self._closed:
                return
            bar = self.scroll.verticalScrollBar()
            bar.setValue(bar.maximum() if follow else min(value, bar.maximum()))
            self._follow_tail = follow
            self._changing_view = False
        QTimer.singleShot(0, restore_scroll)

    def _scroll_changed(self, value):
        if self._changing_view:
            return
        bar = self.scroll.verticalScrollBar()
        self._follow_tail = value >= bar.maximum() - 24

    def _scroll_range_changed(self, low, high):
        if self._follow_tail and not self._changing_view:
            self.scroll.verticalScrollBar().setValue(high)

    def _bubble(self, role, text, status='complete'):
        frame = MessageBubble(role, text, status)
        self.message_layout.addWidget(frame)
        return frame.label

    def _load_conversations(self):
        self.conversations.blockSignals(True)
        self.conversations.clear()
        for row in self.store.conversations():
            self.conversations.addItem(row['title'], row['id'])
        self.conversations.setCurrentIndex(self.conversations.findData(self.conversation))
        self.conversations.blockSignals(False)

    def _load_messages(self):
        while self.message_layout.count():
            widget = self.message_layout.takeAt(0).widget()
            widget.hide()
            widget.deleteLater()
        self.reply_label = None
        self._follow_tail = True
        for row in self.store.messages(self.conversation):
            self._bubble(row['role'], (visible_text(row['content']) if row['role']=='assistant' else row['content']) or '(No completed response)', row['status'])

    def _conversation_selected(self):
        if self.client.busy:
            return
        self.conversation = self.conversations.currentData()
        if self.conversation is not None:
            self._load_messages()

    def new_conversation(self):
        if self.client.busy:
            return
        try:
            self.conversation = self.store.new()
            self._load_conversations()
            self._load_messages()
        except sqlite3.Error as error:
            self.status.setText('Could not create conversation: ' + str(error))

    def _confirm(self, title, text):
        return QMessageBox.question(self, title, text, QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) == QMessageBox.Yes

    def clear_conversation(self):
        if self.client.busy or not self._confirm('Clear conversation?', 'Delete every message in this conversation from local history?'):
            return
        try:
            self.store.clear(self.conversation)
            self._load_messages()
            self._load_conversations()
        except sqlite3.Error as error:
            self.status.setText('Could not clear history: ' + str(error))

    def delete_conversation(self):
        if self.client.busy or not self._confirm('Delete conversation?', 'Permanently delete this local conversation?'):
            return
        try:
            self.store.delete(self.conversation)
            rows = self.store.conversations()
            self.conversation = rows[0]['id'] if rows else self.store.new()
            self._load_conversations()
            self._load_messages()
        except sqlite3.Error as error:
            self.status.setText('Could not delete history: ' + str(error))

    def _open_setup(self):
        from ai_setup_window import AISetupWizard
        self._setup_wizard = AISetupWizard(self.settings,self)
        self._setup_wizard.finished.connect(lambda _:self.refresh())
        self._setup_wizard.show()

    def refresh(self):
        if self._closed or self.client.busy:
            return
        self.models.clear()
        if not self.settings.ai_enabled:
            self.status.setText('Conversational AI is off. Choose AI Setup in the expanded workspace whenever you are ready.')
            self._busy_changed(False)
            return
        self.status.setText('Checking local Ollama…')
        self.send_button.setEnabled(False)
        self.client.refresh_models()

    def _models_ready(self, models):
        self.models.blockSignals(True)
        self.models.clear()
        self.models.addItem('Select an installed local model…', '')
        for model in models:
            self.models.addItem(model, model)
        index = self.models.findData(self.settings.model)
        self.models.setCurrentIndex(max(0, index))
        self.models.blockSignals(False)
        if not models:
            self.status.setText('Ollama is reachable, but no local models were found. Choose AI Setup in the expanded workspace to select an installed model or approve a guided download. You can also skip AI and keep using Hya. See AI_SETUP.md.')
        elif self.settings.model and index < 0:
            self.status.setText('Your saved model is unavailable. Select an installed local model.')
        else:
            self.status.setText('Choose your local model in the expanded workspace to begin.' if not self.models.currentData() else 'Ready · local inference only')
        self._busy_changed(False)

    def _discovery_failed(self, error):
        installed = 'Ollama executable found.' if self.client.installed else 'Ollama executable was not found on PATH.'
        self.status.setText(f'{error}\n{installed} Start the local Ollama server and Refresh models. Setup: LOCAL_AI.md. Hya remains usable offline.')
        self._busy_changed(False)

    def _model_selected(self):
        if self.client.busy or not self.models.currentData():
            self.send_button.setEnabled(False)
            return
        self.settings.model = self.models.currentData()
        try:
            self.settings.save()
            self.status.setText('Ready · local inference only')
        except OSError as error:
            self.status.setText(str(error))
        self.send_button.setEnabled(True)

    def _busy_changed(self, busy):
        for widget in (self.models, self.refresh_button, self.settings_button, self.conversations,
                       self.new_button, self.clear_button, self.delete_button, self.setup_button):
            widget.setEnabled(not busy)
        self.send_button.setEnabled(not busy and bool(self.models.currentData()))
        self.stop_button.setEnabled(busy)

    def send(self):
        if self.client.busy or self._closed:
            return
        if not self.settings.ai_enabled:
            self.status.setText('AI is off. Choose AI Setup to enable local conversation.')
            return
        model = self.models.currentData()
        text = self.input.toPlainText().strip()
        if not model or model not in self.client.models:
            self.status.setText('Select a local model in the expanded workspace first.')
            return
        if not text or len(text) > 16000:
            self.status.setText('Enter a message of 1–16000 characters.')
            return
        self.response = ''
        self._last_action = None
        self.reply_label = None
        try:
            prompt = Path(__file__).with_name('system_prompt.txt').read_text(encoding='utf-8').strip()
            if not prompt or len(prompt) > 16000:
                raise ValueError('system_prompt.txt must contain 1–16000 characters.')
            self.pending = self.store.begin(self.conversation, text, model)
            context = self.store.context(self.conversation, budget=max(1600, self.settings.context * 2))
        except (OSError, sqlite3.Error, ValueError) as error:
            self.status.setText('Could not prepare message: ' + str(error))
            if self.pending is not None:
                self._finished('error', str(error))
            return
        self.input.clear()
        self._follow_tail = True
        self._bubble('user', text)
        self.reply_label = self._bubble('assistant', 'Thinking…', 'generating')
        self.response = ''
        self._load_conversations()
        self._desktop_action_started = False
        self.status.setText('Thinking locally…')
        self.owner.ai_activity.begin()
        try:
            self.client.generate(model, [{'role': 'system', 'content': prompt}, *context])
        except (ValueError, OSError) as error:
            self._finished('error', str(error))

    def _chunk(self, text):
        if self.pending is None:
            return
        self.response += text
        self.status.setText('Hya is responding…')
        if not self._render_timer.isActive():
            self._render_timer.start(33)

    def _display_response(self, streaming=False):
        tool = self._last_action['tool'] if self._last_action else ''
        display = (stream_text if streaming else visible_text)(self.response, tool)
        if self._last_action and display != self.response and display != 'Preparing action summary…':
            return action_summary(tool, self._last_action['result'])
        return display

    def _render_response(self):
        if self.reply_label is not None:
            self.reply_label.setText(self._display_response(streaming=True) or 'Thinking…')

    def _finished(self, status, error=None):
        if self.pending is None:
            return
        self._render_timer.stop()
        self.response = self._display_response()
        if self._last_action and 'script' in self._last_action['result']:
            self.response = action_summary(self._last_action['tool'], self._last_action['result'])
        if self._last_action and (not self.response.strip() or self.response.strip() == 'Preparing action summary…'):
            self.response = action_summary(self._last_action['tool'], self._last_action['result'])
        if status == 'complete' and not self.response.strip():
            status, error = 'error', 'The model returned no visible text. Try another local chat model.'
        try:
            self.store.finish(self.pending, self.response, status)
        except sqlite3.Error as problem:
            error = 'Could not save reply: ' + str(problem)
        self.pending = None
        if status=='cancelled' and self._desktop_action_started:
            error = 'Stopped. An approved action may already have been dispatched and cannot be undone; see Action Log.'
        self.owner.ai_activity.end(failed=status == 'error')
        self.status.setText(error or ('Ready · local inference only' if status == 'complete' else 'Generation stopped. Partial reply is marked cancelled and excluded from context.'))
        if self.reply_label is not None:
            self.reply_label.setText(self.response or '(No completed response)')
            heading = self.reply_label.parentWidget().layout().itemAt(0).widget()
            heading.setText('Hya' if status == 'complete' else 'Hya · ' + status)
            self.reply_label.parentWidget().set_copy_actions(self.response)
        self._busy_changed(False)
        if status=='complete' and self._desktop_capable is False and not getattr(self.client, '_local_action', False):
            self.status.setText('Ready · ordinary chat and local shortcuts; this model does not support AI desktop tools.')

    def edit_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Local AI settings')
        form = QFormLayout(dialog)
        endpoint = QLineEdit(self.settings.endpoint)
        form.addRow('Local server', endpoint)
        auto_launch = QCheckBox('Automatically launch ordinary installed graphical applications')
        auto_launch.setObjectName('auto_launch_apps')
        auto_launch.setChecked(self.settings.auto_launch_apps)
        form.addRow(auto_launch)
        local_intents = QCheckBox('Resolve simple desktop requests locally (fast path)')
        local_intents.setObjectName('local_intents')
        local_intents.setChecked(self.settings.local_intents)
        form.addRow(local_intents)
        forget = QPushButton('Forget approved search directories')
        forget.setEnabled(self.desktop is not None)
        forget.clicked.connect(lambda:self.desktop.forget_directories())
        form.addRow(forget)
        controls = {}
        for name, title, low, high in (('context', 'Context tokens', 512, 32768),
                ('timeout', 'Request timeout (seconds)', 10, 3600), ('keep_alive', 'Keep model loaded (seconds; 0 unloads)', 0, 300)):
            control = QSpinBox()
            control.setRange(low, high)
            control.setValue(getattr(self.settings, name))
            controls[name] = control
            form.addRow(title, control)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        form.addRow(buttons)
        def save():
            try:
                address = local_endpoint(endpoint.text())
                self.settings.endpoint = address
                self.settings.auto_launch_apps = auto_launch.isChecked()
                self.settings.local_intents = local_intents.isChecked()
                for name, control in controls.items():
                    setattr(self.settings, name, control.value())
                self.settings.save()
            except (ValueError, OSError) as error:
                QMessageBox.warning(dialog, 'Settings', str(error))
                return
            dialog.accept()
        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def reject(self):
        self.client.cancel()
        super().reject()

    def closeEvent(self, event):
        # Closing chat cancels generation; hiding preserves the reusable window.
        self.client.cancel()
        super().closeEvent(event)

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        self._blur_timer.stop()
        self.hide()  # Terminal shutdown must not flash the desktop back into view.
        self.client.shutdown()
        self._clear_permission()
        if self.desktop:
            self.desktop.shutdown()
        self._render_timer.stop()
        self.store.close()
