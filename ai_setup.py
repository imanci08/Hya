"""User-only first-run setup. Never reachable through model desktop tools."""
import os
from pathlib import Path
import platform
import re
import shutil
from PySide6.QtCore import QObject, Signal, QProcess, QThreadPool
from ollama_client import OllamaClient, local_model
from desktop_service import Worker, ActionLog

# Conservative estimates, not bundled assets. Extra room covers staging/metadata.
MODELS = {
    'qwen3:0.6b': ('Qwen3 0.6B — smallest starter', 600_000_000),
    'qwen3:1.7b': ('Qwen3 1.7B — better answers', 1_500_000_000),
    'qwen3:4b': ('Qwen3 4B — more capable', 2_600_000_000),
}


def model_name(value):
    value=value.strip()
    pattern=r'(?:[A-Za-z0-9][A-Za-z0-9_-]*/)?[A-Za-z0-9][A-Za-z0-9._-]*(?::[A-Za-z0-9][A-Za-z0-9._-]*)?'
    if len(value)>200 or not re.fullmatch(pattern,value) or ':cloud' in value.casefold() or value.casefold().endswith('-cloud'):
        raise ValueError('Choose a local Ollama library model, e.g. qwen3:0.6b; URLs and cloud models are not supported.')
    return value


def storage_hint():
    configured=os.environ.get('OLLAMA_MODELS','')
    if configured and Path(configured).is_absolute(): return configured
    for name in ('/var/lib/ollama','/usr/share/ollama/.ollama/models'):
        if Path(name).exists(): return name
    return str(Path.home()/'.ollama/models')


def check_space(location, estimate):
    if type(estimate) is not int or not 1_000_000 <= estimate <= 1_000_000_000_000:
        raise ValueError('Enter a realistic estimated model download size.')
    root=Path(location).expanduser()
    if not root.is_absolute(): raise ValueError('The disk-check location must be an absolute path.')
    while not root.exists() and root.parent!=root: root=root.parent
    free=shutil.disk_usage(root).free
    required=estimate*2+512*1024**2
    if free < required:
        raise ValueError(f'Not enough free disk space: {free/1e9:.1f} GB available; allow {required/1e9:.1f} GB for this download. Free some space or choose a smaller model.')
    return {'free':free,'required':required}


def native_command(kind, release=None):
    """Fixed native commands with interactive authorization; no shell/AI args."""
    release=release if release is not None else platform.freedesktop_os_release()
    families={release.get('ID',''),*release.get('ID_LIKE','').split()}
    if not families & {'arch','endeavouros','manjaro'}:
        raise ValueError('Guided native installation currently supports Arch-based systems. Use your distribution software manager or the official Ollama Linux instructions, then Recheck. No remote install script is run by Hya.')
    if kind=='install': args=['/usr/bin/pacman','-S','--needed','ollama']
    elif kind=='start': args=['/usr/bin/systemctl','start','ollama.service']
    else: raise ValueError('Unknown setup operation.')
    if Path('/usr/bin/konsole').is_file(): terminal=['/usr/bin/konsole','--separate','--hold','-e']
    elif Path('/usr/bin/xterm').is_file(): terminal=['/usr/bin/xterm','-hold','-e']
    else: raise ValueError('A supported terminal (Konsole or XTerm) is needed for native package and password prompts.')
    argv=[*terminal,'/usr/bin/sudo','--',*args]
    if any(not os.access(path,os.X_OK) for path in (argv[0],'/usr/bin/sudo',args[0])):
        raise ValueError('Required native package/authorization tools are unavailable. See AI_SETUP.md.')
    return argv


class SetupService(QObject):
    state = Signal(object)
    progress = Signal(object)
    problem = Signal(str)
    downloaded = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None, manager=None, log=None):
        super().__init__(parent)
        self.settings=settings
        self.log=log or ActionLog()
        self._download_call=None
        self.client=OllamaClient(settings,self,manager=manager)
        self._request=None
        self._serial=0
        self._workers={}
        self.busy=False
        self._closed=False

    def _busy(self,value):
        self.busy=value
        self.busy_changed.emit(value)

    def _work(self,fn,callback):
        worker=Worker(fn); key=id(worker); self._workers[key]=worker
        def done(value,error):
            self._workers.pop(key,None)
            if not self._closed: callback(value,error)
        worker.signals.finished.connect(done)
        QThreadPool.globalInstance().start(worker)

    def inspect(self):
        if self._closed: return
        self.cancel(announce=False)
        serial=self._serial
        installed=shutil.which('ollama') is not None
        result={'installed':installed,'reachable':False,'models':[],'excluded':0}
        self._busy(True)
        def failed(message):
            if serial!=self._serial:return
            self._request=None;self._busy(False)
            result['detail']=message
            self.state.emit(result)
        def found(data):
            if serial!=self._serial:return
            rows=data.get('models')
            if not isinstance(rows,list) or len(rows)>500 or not all(isinstance(r,dict) for r in rows):
                failed('Ollama returned an invalid or excessive model list.');return
            result['reachable']=True
            queue=[r for r in rows if local_model(r)]
            result['excluded']=len(rows)-len(queue)
            def next_model():
                if serial!=self._serial:return
                if not queue:
                    self._request=None;self._busy(False);self.state.emit(result);return
                row=queue.pop(0);name=row.get('name',row.get('model'))
                def checked(data):
                    if serial!=self._serial:return
                    caps=data.get('capabilities',[])
                    if (data.get('model_info') and not data.get('remote_host') and not data.get('remote_model')
                        and isinstance(caps,list) and 'completion' in caps):
                        result['models'].append({'name':name,'tools':'tools' in caps})
                    else: result['excluded']+=1
                    next_model()
                def rejected(_):
                    if serial==self._serial:
                        result['excluded']+=1;next_model()
                self._request=self.client._request('/api/show',{'model':name},False,checked,rejected)
            next_model()
        self._request=self.client._request('/api/tags',None,False,found,failed)

    def pull(self,name,estimate,location,approved=False):
        if self._closed: raise RuntimeError('AI setup is closed.')
        if approved is not True: raise PermissionError('A user must explicitly approve the model download.')
        name=model_name(name)
        if self.busy: raise ValueError('Finish or cancel the current setup operation first.')
        self.cancel(announce=False); serial=self._serial;self._busy(True)
        call={'name':'ai_setup_download','arguments':{'model':name,'estimated_bytes':estimate}}
        def ready(value,error):
            if serial!=self._serial:return
            if error:
                self._busy(False);self.problem.emit(str(error));return
            try:self.log.write(call,'started','User approved registry download in AI setup.')
            except OSError as error:
                self._busy(False);self.problem.emit('Could not record download approval: '+str(error));return
            self._download_call=call
            totals={}
            def progress(row):
                if serial!=self._serial:return
                digest=row.get('digest')
                if digest and row.get('total'):
                    totals[digest]=row['total']
                    if sum(totals.values())>estimate:
                        raise ValueError('The model is larger than the approved size estimate. Download stopped; choose a larger estimate or smaller model and try again.')
                self.progress.emit(row)
            def failed(message):
                if serial!=self._serial:return
                self._request=None;self._busy(False)
                self._download_outcome('failed',message)
                if 'space' in message.casefold(): message='The Ollama model disk is full. Free disk space or choose a smaller model. '+message
                self.problem.emit(message)
            def finished(_):
                if serial!=self._serial:return
                self._request=None;self._busy(False)
                self._download_outcome('completed','Model download reported success; chat compatibility still requires verification.')
                self.downloaded.emit(name)
            self._request=self.client._request('/api/pull',{'model':name,'stream':True},True,finished,failed,True,progress=progress)
        self._work(lambda:check_space(location,estimate),ready)

    def launch_native(self,kind,approved=False):
        if self._closed: raise RuntimeError('AI setup is closed.')
        if approved is not True: raise PermissionError('Explicit approval is required before system setup.')
        argv=native_command(kind)
        call={'name':'ai_setup_'+kind,'arguments':{}}
        self.log.write(call,'started','User approved native setup: '+' '.join(argv))
        ok,_=QProcess.startDetached(argv[0],argv[1:])
        self.log.write(call,'launch_requested' if ok else 'failed','Native terminal only; package/service outcome is not verified.')
        if not ok: raise RuntimeError('Could not open the native setup terminal. No installation was verified.')
        return argv

    def _download_outcome(self,status,note):
        call,self._download_call=self._download_call,None
        if call is not None:
            try:self.log.write(call,status,note)
            except OSError as error:self.problem.emit('Could not record setup outcome: '+str(error))

    def cancel(self,announce=True):
        self._serial+=1
        request,self._request=self._request,None
        if request is not None and request['retire']():request['reply'].abort()
        was_busy=self.busy;self._busy(False)
        self._download_outcome('cancelled','Download client disconnected; partial blobs may remain and another pull may continue.')
        if announce and was_busy:
            self.problem.emit('Setup request cancelled. Partial model blobs may remain for resuming; an independently running pull may continue. No installed models were deleted.')

    def shutdown(self):
        self.cancel(announce=False);self._closed=True
