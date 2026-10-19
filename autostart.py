"""Opt-in per-user XDG autostart; never modifies system-wide startup."""
import os
from pathlib import Path
import tempfile
from PySide6.QtCore import QStandardPaths
from runtime_paths import profile


class Autostart:
    def __init__(self,path=None,executable='/usr/bin/hya'):
        root=Path(QStandardPaths.writableLocation(QStandardPaths.GenericConfigLocation))
        self.path=Path(path) if path else root/'autostart'/'io.hyalos.Hya.desktop'
        self.executable=executable

    def enabled(self):
        if not self.path.is_file() or self.path.is_symlink():return False
        text=self.path.read_text(errors='replace')
        return 'X-Hya-Autostart=true' in text and 'Hidden=true' not in text

    def set_enabled(self,enabled):
        if enabled:
            if profile()!='installed' or self.executable!='/usr/bin/hya':
                raise ValueError('Start on Login is available in the installed Hya application. Development startup is not changed.')
            if self.path.is_symlink():raise ValueError('Refusing to replace a symlinked autostart entry.')
            if self.path.exists() and 'X-Hya-Autostart=true' not in self.path.read_text():
                raise ValueError('An unmanaged Hya autostart entry exists; it was not overwritten.')
            self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            data='[Desktop Entry]\nType=Application\nName=Hya\nComment=Your local orb desktop companion\nExec=/usr/bin/hya\nTryExec=/usr/bin/hya\nIcon=hya\nTerminal=false\nX-Hya-Autostart=true\n'
            fd,temp=tempfile.mkstemp(dir=self.path.parent,prefix='.hya-')
            try:
                with os.fdopen(fd,'w') as stream:stream.write(data)
                os.replace(temp,self.path)
            finally:
                if os.path.exists(temp):os.unlink(temp)
        elif self.path.exists():
            if self.path.is_symlink() or 'X-Hya-Autostart=true' not in self.path.read_text():
                raise ValueError('An unmanaged autostart entry was not removed.')
            self.path.unlink()
