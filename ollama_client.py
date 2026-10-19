"""Event-driven local Ollama HTTP transport. No blocking inference or polling."""
import json
import shutil
import time
from diagnostics import timing
from local_intents import resolve_intent, parse_intent
from desktop_tools import application_catalog
from action_presentation import action_summary
from PySide6.QtCore import QObject, Signal, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply, QNetworkProxy
from ai_settings import local_endpoint


def local_model(row):
    name = row.get('name', row.get('model', ''))
    return (isinstance(name, str) and bool(name.strip()) and len(name) <= 256
            and not row.get('remote_host') and not row.get('remote_model')
            and ':cloud' not in name.lower())


class OllamaClient(QObject):
    models_ready = Signal(list)
    discovery_failed = Signal(str)
    chunk = Signal(str)
    completed = Signal()
    failed = Signal(str)
    cancelled = Signal()
    busy_changed = Signal(bool)
    tool_capability = Signal(bool)
    action_status = Signal(str)
    action_result = Signal(object)
    response_reset = Signal()

    def __init__(self, settings, parent=None, manager=None):
        super().__init__(parent)
        self.settings = settings
        self.manager = manager or QNetworkAccessManager(self)
        self.manager.setProxy(QNetworkProxy(QNetworkProxy.NoProxy))
        self.installed = shutil.which('ollama') is not None
        self.models = []
        self.busy = False
        self._generation = None
        self._discovery = None
        self._last_model = None
        self.desktop = None
        self._tool_token = None
        self._tool_queue = []
        self._rounds = 0
        self._tools_enabled = False
        self._local_action = False
        self._inference_started = None

    def _request(self, path, payload, streaming, success, failure, generation=False, progress=None):
        request = QNetworkRequest(QUrl(local_endpoint(self.settings.endpoint) + path))
        request.setHeader(QNetworkRequest.ContentTypeHeader, 'application/json')
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.ManualRedirectPolicy)
        request.setTransferTimeout(self.settings.timeout * 1000 if generation else 8000)
        reply = (self.manager.get(request) if payload is None else
                 self.manager.post(request, json.dumps(payload, ensure_ascii=True).encode('utf-8')))
        state = {'reply': reply, 'buffer': b'', 'active': True, 'size': 0, 'done': False, 'content': [], 'thinking': [], 'calls': []}
        timer = QTimer(self)
        timer.setSingleShot(True)
        state['timer'] = timer

        def retire():
            if not state['active']:
                return False
            state['active'] = False
            timer.stop()
            timer.deleteLater()
            reply.deleteLater()
            return True

        def fail(message):
            if retire():
                reply.abort()
                failure(message)

        state['fail'] = fail
        state['retire'] = retire
        timer.timeout.connect(lambda: fail('Ollama request timed out. Try a smaller model or increase the timeout.'))
        timer.start((self.settings.timeout if generation else 8) * 1000)

        def parse_line(line):
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError('Expected an Ollama response object')
            if row.get('error'):
                raise ValueError(str(row['error'])[:1000])
            if row.get('remote_host') or row.get('remote_model'):
                raise ValueError('Cloud-backed responses are disabled. Select a local model.')
            if state['done']:
                raise ValueError('Unexpected data after the final response')
            if progress is not None:
                if not isinstance(row.get('status'),str):
                    raise ValueError('Invalid download progress status')
                for key in ('total','completed'):
                    if key in row and (type(row[key]) is not int or row[key] < 0):
                        raise ValueError('Invalid download byte count')
                if 'digest' in row and not isinstance(row['digest'],str):
                    raise ValueError('Invalid download layer')
                progress(row)
                state['done'] = row['status']=='success'
                state['size'] = 0  # Progress streams are long-lived, not chat text.
                timer.start(self.settings.timeout * 1000)  # Inactivity timeout.
                return
            message = row.get('message', {})
            if not isinstance(message, dict) or not isinstance(message.get('content', ''), str):
                raise ValueError('Invalid assistant message')
            thinking = message.get('thinking', '')
            if not isinstance(thinking,str):
                raise ValueError('Invalid thinking field')
            state['thinking'].append(thinking)
            content = message.get('content', '')
            if content:
                state['content'].append(content)
                self.chunk.emit(content)
            calls = message.get('tool_calls', [])
            if not isinstance(calls, list) or len(state['calls'])+len(calls)>4:
                raise ValueError('Invalid or excessive tool calls')
            for call in calls:
                if not isinstance(call,dict) or not isinstance(call.get('function'),dict):
                    raise ValueError('Malformed structured tool call')
                function=call['function']
                if (not isinstance(function.get('name'),str) or not 1 <= len(function['name']) <= 64
                        or not isinstance(function.get('arguments'),dict)):
                    raise ValueError('Tool name and arguments must be structured')
                state['calls'].append({'function':{'name':function['name'],'arguments':function['arguments']}})
            state['done'] = row.get('done') is True

        def read():
            if not state['active']:
                return
            state['buffer'] += bytes(reply.readAll())
            # Stream bytes are consumed a line at a time, capped cumulatively below.
            if streaming:
                status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
                if status is None or not 200 <= int(status) < 300:
                    if len(state['buffer']) > 2_000_000:
                        fail('Ollama response is too large.')
                    return
                try:
                    while b'\n' in state['buffer']:
                        line, state['buffer'] = state['buffer'].split(b'\n', 1)
                        state['size'] += len(line) + 1
                        if state['size'] + len(state['buffer']) > 2_000_000:
                            raise ValueError('Ollama response is too large.')
                        if line.strip():
                            parse_line(line)
                    if len(state['buffer']) > 2_000_000:
                        raise ValueError('Ollama response is too large.')
                except (ValueError, TypeError, UnicodeError, RecursionError) as error:
                    fail('Invalid Ollama stream: ' + str(error))
            elif len(state['buffer']) > 2_000_000:
                fail('Ollama response is too large.')

        def finished():
            read()
            if not state['active']:
                return
            status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            if reply.error() != QNetworkReply.NoError or status is None or not 200 <= int(status) < 300:
                detail = reply.errorString()
                try:
                    detail = json.loads(state['buffer']).get('error', detail)
                except (ValueError, AttributeError):
                    pass
                fail(f'Ollama unavailable or request failed (HTTP {status or "—"}): {str(detail)[:1000]}')
                return
            try:
                if streaming:
                    if state['buffer'].strip():
                        parse_line(state['buffer'])
                    if not state['done']:
                        raise ValueError('Connection ended before Ollama completed its response.')
                    result = ({'status':'success'} if progress is not None else
                        {'role':'assistant','content':''.join(state['content']), 'tool_calls':state['calls'], 'thinking':''.join(state['thinking'])})
                else:
                    result = json.loads(state['buffer'])
                    if not isinstance(result, dict):
                        raise ValueError('Expected an Ollama response object')
                    if result.get('error'):
                        raise ValueError(str(result['error']))
            except (ValueError, TypeError, UnicodeError, RecursionError) as error:
                fail(str(error))
                return
            if retire():
                success(result)

        reply.readyRead.connect(read)
        reply.finished.connect(finished)
        return state

    def refresh_models(self):
        if self.busy:
            return
        self._abort_discovery()
        self.models = []
        def success(data):
            self._discovery = None
            rows = data.get('models')
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                self.discovery_failed.emit('Ollama returned an invalid model list.')
                return
            self.models = sorted(set(row.get('name', row.get('model')) for row in rows if local_model(row)))
            self.models_ready.emit(self.models)
        def failure(message):
            self._discovery = None
            self.discovery_failed.emit(message)
        self._discovery = self._request('/api/tags', None, False, success, failure)

    def generate(self, model, messages):
        if not getattr(self.settings, 'ai_enabled', True):
            raise ValueError('Conversational AI is off. Complete AI Setup to enable it.')
        if self.busy:
            raise ValueError('A response is already in progress.')
        if model not in self.models:
            raise ValueError('Select an installed local model, then refresh if necessary.')
        if not messages or any(not isinstance(m,dict) or m.get('role') not in ('system', 'user', 'assistant') or not isinstance(m.get('content'), str) for m in messages):
            raise ValueError('Invalid conversation messages.')
        self._local_action = False
        self._abort_discovery()
        self._tool_token = None
        self._tool_queue = []
        self._rounds = 0
        if self.desktop is not None:
            self.desktop.begin_turn()
        self.busy = True
        self.busy_changed.emit(True)
        # Verify again immediately before sending ANY conversation text: a local
        # tag can be changed to point to a cloud model after discovery.
        payload = {'model': model, 'messages': messages, 'stream': True,
                   'keep_alive': self.settings.keep_alive,
                   'options': {'num_ctx': self.settings.context}}
        def checked(data):
            if data.get('remote_host') or data.get('remote_model') or not data.get('model_info'):
                self._end('failed', 'This model is not a verified local model. Cloud models are disabled.')
                return
            capabilities = data.get('capabilities', [])
            if not isinstance(capabilities,list) or not all(isinstance(value,str) for value in capabilities):
                capabilities = []
            if capabilities and 'completion' not in capabilities:
                self._end('failed', 'This model does not support text conversation.')
                return
            self._tools_enabled = self.desktop is not None and 'tools' in capabilities
            self.tool_capability.emit(self._tools_enabled)
            self._payload = payload
            # Copy history before appending ephemeral structured tool turns.
            self._payload['messages'] = [dict(m) for m in messages]
            if self._tools_enabled:
                self._payload['tools'] = self.desktop.schemas()
            else:
                self._payload['messages'] = [{'role':'system','content':
                    'Direct desktop actions are unavailable with this model. Continue ordinary chat and explain this limitation when an action is requested.'}, *self._payload['messages']]
            self._last_model = model
            self._request_turn()
        def preflight(_=None):
            self._generation = self._request('/api/show', {'model': model}, False, checked,
                                             lambda error: self._end('failed', error), True)
        def start_inference():
            if self._last_model and self._last_model != model:
                # Respect a custom keep-alive without keeping two Hya models loaded.
                self._generation = self._request('/api/generate',
                    {'model': self._last_model, 'keep_alive': 0, 'stream': False}, False,
                    preflight, lambda error: self._end('failed', error), True)
            else:
                preflight()
        def recognized(call, error):
            if not self.busy: return
            if call is not None and error is None:
                self._local_action = True
                self._current_tool = call['name']
                self.action_status.emit('Preparing local desktop action…')
                self._tool_token = self.desktop.submit(call)
            else:
                start_inference()
        text = next((m['content'] for m in reversed(messages) if m['role']=='user'), '')
        recognition_started = time.monotonic()
        candidate = parse_intent(text) if getattr(self.settings, 'local_intents', True) else None
        timing('intent_recognition', recognition_started)
        if self.desktop is not None and candidate is not None:
            serial = object()
            self._intent_serial = serial
            def recognize():
                started = time.monotonic()
                try:
                    # Parse grammar before scanning installed entries.
                    call = resolve_intent(text, {})
                    if call is not None: return call
                    lookup = time.monotonic()
                    catalog = application_catalog()
                    timing('application_lookup', lookup)
                    return resolve_intent(text, catalog)
                finally: timing('intent_recognition', started)
            self.desktop._work(recognize, lambda call,error: recognized(call,error) if self._intent_serial is serial else None)
        else:
            start_inference()

    def attach_desktop(self, service):
        if self.busy:
            raise ValueError('Cannot change tool service during generation.')
        self.desktop = service
        service.result.connect(self._desktop_result)
        service.status.connect(self.action_status)

    def _request_turn(self):
        if not self.busy: return
        self._inference_started = time.monotonic()
        self._generation = self._request('/api/chat', self._payload, True,
            self._turn_finished, lambda error: self._end('failed',error), True)

    def _turn_finished(self, message):
        self._record_inference()
        self._generation = None
        calls = message['tool_calls']
        if not calls:
            self._end('completed')
            return
        if not self._tools_enabled:
            self._end('failed','This model returned tool calls without tool support; nothing was executed.')
            return
        self._rounds += 1
        if self._rounds > 3:
            self._end('failed','Desktop action round limit reached. No further actions were executed.')
            return
        self.response_reset.emit()
        self._payload['messages'].append(message)
        self._tool_queue = list(calls)
        self._next_desktop()

    def _next_desktop(self):
        if not self.busy: return
        if not self._tool_queue:
            self._request_turn()
            return
        function = self._tool_queue.pop(0)['function']
        self._current_tool = function['name']
        try:
            self._tool_token = self.desktop.submit({'name':function['name'],'arguments':function['arguments']})
        except ValueError as error:
            self._end('failed',str(error))

    def _desktop_result(self, token, result):
        if not self.busy or token != self._tool_token: return
        self._tool_token = None
        self.action_result.emit({'tool':self._current_tool,'result':result})
        if self._local_action:
            self.chunk.emit(action_summary(self._current_tool, result))
            self._end('completed')
            return
        self._payload['messages'].append({'role':'tool','tool_name':self._current_tool,
            'content':json.dumps(result,ensure_ascii=True)})
        self._next_desktop()

    def _record_inference(self):
        if self._inference_started is not None:
            timing('ollama_inference', self._inference_started)
            self._inference_started = None

    def _end(self, signal, message=None):
        if not self.busy:
            return
        self._record_inference()
        self._generation = None
        self._tool_token = None
        if self.desktop is not None:
            self.desktop.cancel()
        self.busy = False
        self.busy_changed.emit(False)
        if message is None:
            getattr(self, signal).emit()
        else:
            getattr(self, signal).emit(message)

    def cancel(self):
        self._intent_serial = None
        self._tool_token = None
        self._tool_queue = []
        if self.desktop is not None:
            self.desktop.cancel()
        state = self._generation
        if state is not None and state['retire']():
            state['reply'].abort()
        self._end('cancelled')

    def _abort_discovery(self):
        if self._discovery is not None:
            state, self._discovery = self._discovery, None
            if state['retire']():
                state['reply'].abort()

    def shutdown(self):
        self._abort_discovery()
        self.cancel()
