"""Friendly modeless setup, independent of chat and the character animator."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QComboBox,QLineEdit,QProgressBar,QDoubleSpinBox,QFormLayout,QMessageBox,QScrollArea,QWidget,QApplication)
from ai_setup import SetupService, MODELS, storage_hint, native_command, model_name


class AISetupWizard(QDialog):
    def __init__(self,settings,parent=None,service=None):
        super().__init__(parent)
        self.settings=settings
        self.service=service or SetupService(settings,self)
        self._initial=not settings.setup_complete
        self._models=[];self._layers={}
        self.setWindowTitle('Welcome to Hya — Local AI setup')
        self.resize(570,650)
        outer=QVBoxLayout(self)
        scroll=QScrollArea();scroll.setWidgetResizable(True)
        body=QWidget();layout=QVBoxLayout(body);scroll.setWidget(body)
        outer.addWidget(scroll,1)
        heading=QLabel('Give Hya a local AI brain')
        heading.setStyleSheet('font-size:22px;font-weight:600;');layout.addWidget(heading)
        intro=QLabel('Chat privately on your computer with Ollama. AI is optional — you can skip this and keep enjoying Hya’s animations, colors and desktop presence.')
        intro.setWordWrap(True);layout.addWidget(intro)
        self.status=QLabel('Checking your computer…');self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText);layout.addWidget(self.status)
        row=QHBoxLayout();self.install=QPushButton('Install Ollama…');self.start=QPushButton('Start local service…');self.refresh=QPushButton('Recheck')
        for b in (self.install,self.start,self.refresh):row.addWidget(b)
        layout.addLayout(row)
        self.guidance=QLabel();self.guidance.setWordWrap(True);self.guidance.setTextFormat(Qt.PlainText);layout.addWidget(self.guidance)
        form=QFormLayout();layout.addLayout(form)
        self.existing=QComboBox();self.existing.setAccessibleName('Compatible installed Ollama model')
        form.addRow('Use an installed model',self.existing)
        self.choice=QComboBox()
        for name,(label,size) in MODELS.items(): self.choice.addItem(f'{label} (about {size/1e9:.1f} GB)',name)
        self.choice.addItem('Another model…','custom')
        form.addRow('Or download a model',self.choice)
        self.custom=QLineEdit();self.custom.setPlaceholderText('e.g. qwen3:1.7b')
        form.addRow('Custom model name',self.custom)
        self.estimate=QDoubleSpinBox();self.estimate.setRange(.01,1000);self.estimate.setValue(4);self.estimate.setSuffix(' GB estimated download')
        form.addRow('Custom size estimate',self.estimate)
        self.location=QLineEdit(storage_hint());form.addRow('Disk-check location',self.location)
        self.location.setToolTip('This only checks free space. It does not change Ollama storage. Confirm this is on the same disk as the server model storage.')
        self.details=QLabel();self.details.setWordWrap(True);layout.addWidget(self.details)
        self.download=QPushButton('Download');layout.addWidget(self.download)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setValue(0);layout.addWidget(self.progress)
        self.progress_label=QLabel('No download started.');self.progress_label.setWordWrap(True);self.progress_label.setTextFormat(Qt.PlainText);layout.addWidget(self.progress_label)
        self.cancel_download=QPushButton('Cancel current check / download');self.cancel_download.clicked.connect(self.service.cancel);layout.addWidget(self.cancel_download)
        row=QHBoxLayout();self.skip=QPushButton('Skip AI setup');self.finish=QPushButton('Use selected model')
        row.addWidget(self.skip);row.addWidget(self.finish);outer.addLayout(row)
        for b in self.findChildren(QPushButton):b.setAutoDefault(False)
        self.install.clicked.connect(lambda:self._native('install'))
        self.start.clicked.connect(lambda:self._native('start'))
        self.refresh.clicked.connect(self.service.inspect)
        self.choice.currentIndexChanged.connect(self._details)
        self.estimate.valueChanged.connect(self._details)
        self.download.clicked.connect(self._download)
        self.skip.clicked.connect(lambda:self._finish(False))
        self.finish.clicked.connect(lambda:self._finish(True))
        self.service.state.connect(self._state)
        self.service.problem.connect(self._problem)
        self.service.progress.connect(self._progress)
        self.service.downloaded.connect(self._downloaded)
        self.service.busy_changed.connect(self._busy)
        self.existing.currentIndexChanged.connect(lambda:self.finish.setEnabled(bool(self.existing.currentData()) and not self.service.busy))
        self._reachable=False;self._details();self._busy(False)
        screen=QApplication.primaryScreen()
        if screen:self.resize(self.size().boundedTo(screen.availableGeometry().size()))
        QTimer.singleShot(0,self.service.inspect)

    def _size(self):
        key=self.choice.currentData()
        return int(self.estimate.value()*1e9) if key=='custom' else MODELS[key][1]

    def _details(self):
        custom=self.choice.currentData()=='custom'
        self.custom.setEnabled(custom);self.estimate.setEnabled(custom)
        size=self._size();required=size*2+512*1024**2
        self.details.setText(f'Estimated download: {size/1e9:.1f} GB. Allow at least {required/1e9:.1f} GB free for staging and model storage. RAM is needed in addition. The smallest model is a starter; answers and tool use are less reliable than larger models.\nDownload contacts Ollama’s model registry; no conversations are sent. Sizes can change. Confirm the disk-check location matches your Ollama server storage (the API cannot report it). No models are bundled with Hya.')

    def _busy(self,busy):
        self.refresh.setEnabled(not busy);self.download.setEnabled(not busy and self._reachable)
        self.finish.setEnabled(not busy and bool(self.existing.currentData()))
        self.cancel_download.setEnabled(busy)
        self.install.setEnabled(not busy and not self._reachable)
        self.start.setEnabled(not busy and not self._reachable)
        for widget in (self.existing,self.choice,self.location):widget.setEnabled(not busy)
        self.custom.setEnabled(not busy and self.choice.currentData()=='custom')
        self.estimate.setEnabled(not busy and self.choice.currentData()=='custom')

    def _state(self,state):
        self._reachable=state['reachable'];self._models=state['models']
        previous=self.existing.currentData() or self.settings.model
        self.existing.clear();self.existing.addItem('Choose a local chat model…',None)
        for row in self._models:
            self.existing.addItem(row['name']+(' · desktop tools' if row['tools'] else ' · chat only'),row['name'])
        index=self.existing.findData(previous)
        if index<0 and self._models:index=1
        self.existing.setCurrentIndex(max(0,index))
        installed='found' if state['installed'] else 'not found on PATH'
        self.status.setText(f"Ollama executable: {installed}. Local service: {'available' if self._reachable else 'unavailable'}. Compatible local chat models: {len(self._models)}." + (f" {state['excluded']} other models could not be verified as compatible local chat models." if state['excluded'] else ''))
        if self._reachable:
            self.guidance.setText('Choose an installed model, or download a starter model below. A reachable local service works even if its executable is not on Hya’s PATH.')
        else:
            try:
                native_command('install')
                self.guidance.setText('Install opens your native package manager in a terminal, with its normal dependency, download and password prompts. Then use Start local service and Recheck. No packages are installed automatically. If a setup terminal is already open, finish it first.')
            except (ValueError,OSError) as error:self.guidance.setText(str(error))
            if state.get('detail'):self.guidance.setText(self.guidance.text()+'\n'+state['detail'])
        self.install.setVisible(not state['installed'] and not self._reachable)
        self.start.setVisible(state['installed'] and not self._reachable)
        self._busy(False)

    def _native(self,kind):
        try: argv=native_command(kind)
        except (ValueError,OSError) as error:self._problem(str(error));return
        text=('Install Ollama and its dependencies through your distribution package manager?' if kind=='install' else 'Start the system Ollama service for this session?')
        text+='\n\n'+' '.join(argv)+'\n\nYou will approve native prompts and authorize with sudo in the terminal. Nothing runs through a shell. Closing this wizard does not cancel a package transaction. Close the terminal when finished, then Recheck.'
        if QMessageBox.question(self,'Approve native AI setup',text,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:
            self.service.launch_native(kind,approved=True)
            self.guidance.setText('The native setup terminal was requested. Complete or decline its prompts, close it when finished, then Recheck. Hya has not verified installation or service startup.')
        except (ValueError,OSError,RuntimeError) as error:self._problem(str(error))

    def _download(self):
        name=self.custom.text() if self.choice.currentData()=='custom' else self.choice.currentData()
        try:name=model_name(name)
        except ValueError as error:self._problem(str(error));return
        text=f'Download {name}?\nApproximately {self._size()/1e9:.1f} GB; allow {(self._size()*2+512*1024**2)/1e9:.1f} GB free.\nOllama will contact its registry and store this model locally. No conversation is uploaded.'
        if QMessageBox.question(self,'Download local AI model',text,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        self._layers={};self.progress.setRange(0,100);self.progress.setValue(0)
        self.progress_label.setText('Checking free disk space…')
        try:self.service.pull(name,self._size(),self.location.text(),approved=True)
        except (ValueError,OSError,PermissionError) as error:self._problem(str(error))

    def _progress(self,row):
        digest=row.get('digest')
        if digest and row.get('total'):
            self._layers[digest]=(min(row.get('completed',0),row['total']),row['total'])
        total=sum(r[1] for r in self._layers.values());done=sum(r[0] for r in self._layers.values())
        self.progress.setRange(0,100 if total else 0)
        if total:self.progress.setValue(min(99,int(100*done/total)))
        self.progress_label.setText(row['status']+(f' · {done/1e6:.0f} / {total/1e6:.0f} MB (reported layers)' if total else ''))

    def _downloaded(self,name):
        self.progress.setRange(0,100);self.progress.setValue(100)
        self.progress_label.setText('Download complete. Verifying local chat compatibility…')
        self.existing.addItem(name,name);self.existing.setCurrentIndex(self.existing.count()-1)
        self.service.inspect()  # Only verified models remain selectable.
        self.finish.setEnabled(False)

    def _problem(self,text):
        self.progress.setRange(0,100)
        self.progress_label.setText(text)

    def _finish(self,enabled):
        name=self.existing.currentData()
        if enabled and (self.service.busy or name not in {r['name'] for r in self._models}):return
        before=(self.settings.model,self.settings.ai_enabled,self.settings.setup_complete)
        if enabled:self.settings.model=name
        self.settings.ai_enabled=enabled;self.settings.setup_complete=True
        try:self.settings.save()
        except (OSError,ValueError) as error:
            self.settings.model,self.settings.ai_enabled,self.settings.setup_complete=before
            self._problem('Could not save setup: '+str(error));return
        self.service.cancel(announce=False)
        self.accept()

    def reject(self):
        if self._initial:self._finish(False)
        else:
            self.service.cancel(announce=False);super().reject()

    def done(self,result):
        self.service.shutdown()
        super().done(result)

    def shutdown(self):
        self.service.shutdown();self.hide()
