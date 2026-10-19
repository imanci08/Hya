"""Asynchronous permission broker and local action audit trail, separate from UI/LLM."""
from runtime_paths import app_dir
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import uuid
import time
from diagnostics import timing
from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, QTimer, QStandardPaths
from smart_permissions import PermissionPolicy
from desktop_tools import schemas, prepare, execute, Grant, action_key, PROTECTED, Cancelled, check_cancel


class ActionLog:
    def __init__(self, path=None):
        self.path = Path(path) if path else app_dir('data')/'desktop-actions.jsonl'
        self.lock = threading.Lock()

    def write(self, call, status, note=''):
        arguments = call.get('arguments',{})
        if call.get('name')=='draft_bash':
            arguments={'script_characters':len(arguments.get('script',''))}
        row = {'time': datetime.now(timezone.utc).isoformat(), 'tool': call.get('name','invalid'),
               'arguments': arguments, 'status': status, 'note': str(note)[:1000]}
        data = (json.dumps(row,ensure_ascii=True)+'\n').encode()
        with self.lock:
            self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            fd = os.open(self.path,os.O_CREAT|os.O_APPEND|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            try:
                os.fchmod(fd,0o600)
                with os.fdopen(fd,'ab',closefd=False) as stream:
                    stream.write(data)
                    stream.flush()
            finally:
                os.close(fd)

    def read(self):
        if not self.path.exists(): return 'No desktop actions recorded.'
        with self.lock, self.path.open('rb') as stream:
            stream.seek(0,2)
            stream.seek(max(0,stream.tell()-100000))
            text=stream.read().decode('utf-8',errors='replace')
        return text or 'No desktop actions recorded.'


class WorkerSignals(QObject):
    finished = Signal(object, object)


class Worker(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    def run(self):
        try: self.signals.finished.emit(self.function(),None)
        except Exception as error: self.signals.finished.emit(None,error)


class DesktopService(QObject):
    permission_needed = Signal(str, object)
    permission_cleared = Signal()
    result = Signal(str, object)
    status = Signal(str)
    log_ready = Signal(str)

    def __init__(self,parent=None,log=None,pool=None,policy=None,settings=None):
        super().__init__(parent)
        self.log = log or ActionLog()
        self.pool = pool or QThreadPool.globalInstance()
        self.policy = policy or PermissionPolicy(settings=settings)
        self._active = None
        self._jobs = {}
        self._closed = False
        self._permission_denied = False

    def begin_turn(self):
        self._permission_denied = False

    def schemas(self):
        return schemas()

    def _work(self,function,callback):
        worker=Worker(function)
        identifier=uuid.uuid4().hex
        self._jobs[identifier]=worker
        def done(value,error):
            self._jobs.pop(identifier,None)
            if not self._closed: callback(value,error)
        worker.signals.finished.connect(done)
        self.pool.start(worker)

    def submit(self,call):
        if self._closed or self._active is not None:
            raise ValueError('Desktop action service is busy or closed.')
        token=uuid.uuid4().hex
        event=threading.Event()
        self._active={'token':token,'call':call,'event':event,'waiting':False}
        self.status.emit('Preparing desktop action…')
        # Asynchronous even for bad input; caller receives token before results.
        QTimer.singleShot(0,lambda: self._prepare(token,call,event))
        return token

    def _prepare(self,token,call,event):
        if not self._matches(token): return
        def work():
            check_cancel(event)
            started = time.monotonic()
            try: return prepare(call)
            finally:
                if isinstance(call,dict) and call.get('name')=='open_application':
                    timing('application_lookup',started)
        def ready(value,error):
            if not self._matches(token): return
            if error:
                self._finish(token,{'error':str(error)},'rejected')
                return
            validated,details=value
            self._active.update(call=validated,details=details)
            self._route(token)
        self._work(work,ready)

    def _route(self,token):
        if not self._matches(token): return
        state=self._active
        call,details=state['call'],state['details']
        if call['name'] in PROTECTED and self._permission_denied:
            self._finish(token,{'error':'Permission was denied in this turn. Further protected actions are blocked until the user sends a new message.'},'denied')
            return
        if details.get('choices'):
            state['waiting']=True
            self.permission_needed.emit(token,details)
            return
        def decided(automatic,error):
            if not self._matches(token): return
            if error:
                self._finish(token,{'error':'Permission policy failed: '+str(error)},'rejected')
            elif automatic:
                grant=Grant(action_key(call),'automatic') if call['name'] in PROTECTED else None
                self._execute(token,grant)
            else:
                state['waiting']=True
                self.status.emit('Waiting for your desktop-action permission…')
                self.permission_needed.emit(token,details)
        self._work(lambda:self.policy.automatic(call,details),decided)

    def _matches(self,token):
        return self._active is not None and self._active['token']==token

    def select_application(self,token,desktop_id):
        if not self._matches(token) or not self._active['waiting']: return False
        details=self._active['details']
        choice=next((row for row in details.get('choices',[]) if row['desktop_id']==desktop_id),None)
        if choice is None: return False
        call={'name':'open_application','arguments':{'desktop_id':desktop_id}}
        self._active.update(call=call,details={'action':'open_application','arguments':call['arguments'],
            'requested_application':details['requested_application'],'application':choice['application']})
        self.permission_cleared.emit()
        if not self._matches(token): return False
        self._active['waiting']=False
        self._route(token)
        return True

    def approve(self,token):
        if not self._matches(token) or not self._active['waiting'] or self._active['details'].get('choices'): return False
        self._active['waiting']=False
        grant=Grant(action_key(self._active['call']))
        self.permission_cleared.emit()
        if not self._matches(token): return False
        self._execute(token,grant)
        return True

    def deny(self,token):
        if not self._matches(token) or not self._active['waiting']: return False
        self._permission_denied = True
        self._active['waiting'] = False
        self.permission_cleared.emit()
        self._finish(token,{'error':'User denied permission. Do not retry without a new user request.'},'denied')
        return True

    def _execute(self,token,grant):
        if not self._matches(token): return
        state=self._active
        call,details,event=state['call'],state['details'],state['event']
        self.status.emit('Running approved desktop action…' if grant else 'Reading desktop information…')
        def work():
            # Fail closed if an attempt cannot be logged BEFORE any side effect.
            mode=grant.mode if grant else 'read-only'
            self.log.write(call,'started','permission: '+mode)
            try:
                check_cancel(event)
                if grant and grant.mode=='automatic' and not self.policy.automatic(call,details):
                    raise PermissionError('Automatic permission no longer applies. Request again for confirmation.')
                if grant and grant.mode=='confirmed':
                    self.policy.remember(call,details)
                value=execute(call,details,event,grant)
                status='completed'
            except Cancelled as error:
                value,status={'error':str(error)},'cancelled'
            except Exception as error:
                value,status={'error':str(error)},'failed'
            audit = dict(value)
            if call['name']=='draft_bash' and 'script' in audit:
                audit['script_characters'] = len(audit.pop('script'))
            self.log.write(call,status,json.dumps(audit,ensure_ascii=True))
            return value
        def done(value,error):
            if not self._matches(token): return
            if error: value={'error':'Desktop action or logging failed (an action may already have completed): '+str(error)}
            self._active=None
            self.result.emit(token,value)
        self._work(work,done)

    def _finish(self,token,result,status):
        if not self._matches(token): return
        call=self._active['call']
        safe=call if isinstance(call,dict) else {}
        def work():
            self.log.write(safe,status,result.get('error',''))
            return result
        def done(value,error):
            if not self._matches(token): return
            self._active=None
            self.result.emit(token,value if not error else {'error':'Could not log desktop action: '+str(error)})
        self._work(work,done)

    def cancel(self):
        if self._active:
            state,self._active=self._active,None
            state['event'].set()
            self.permission_cleared.emit()
            # A worker that passed the execution gate logs its final outcome even
            # after cancellation; a launch already accepted cannot be undone.
            if state['waiting']:
                self._work(lambda:self.log.write(state['call'],'cancelled','Cancelled before permission'),lambda *_:None)

    def forget_directories(self):
        self._work(self.policy.forget,lambda value,error:self.status.emit(str(error) if error else 'Remembered search-directory permissions cleared.'))

    def read_log(self):
        self._work(self.log.read,lambda value,error:self.log_ready.emit(str(error) if error else value))

    def shutdown(self):
        self.cancel()
        self._closed=True
