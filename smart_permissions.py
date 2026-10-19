"""Application-owned permission policy. Model arguments cannot choose categories."""
from runtime_paths import app_dir
import json
import os
import re
from pathlib import Path
import shlex
import stat
import tempfile
import threading
from PySide6.QtCore import QStandardPaths

PRIVATE_NAMES={'private','secret','secrets','credentials','password','passwords','vault','keyrings',
 'financial','finance','medical','health','tax','taxes','banking'}
SAFE_PROGRAMS={'dolphin','kcalc','kate','kwrite','firefox','chromium','google-chrome','brave',
 'libreoffice','okular','gwenview','spectacle','vlc','mpv','gimp','inkscape','kdenlive',
 'audacity','nautilus','thunar','nemo','evince','eog','gedit','gnome-calculator','galculator',
 'qalculate-gtk','speedcrunch','file-roller','ark'}
SENSITIVE_CATEGORIES={'Settings','PackageManager','Security','TerminalEmulator','Shell','Monitor','Filesystem','DiskTools'}
ORDINARY_CATEGORIES={'Office','Graphics','AudioVideo','Game','Education','Science','TextEditor','WebBrowser','FileManager','Calculator','Archiving'}
RISKY_WORDS={'sudo','su','pkexec','kdesu','doas','konsole','xterm','uxterm','gnome-terminal','xfce4-terminal',
 'kitty','alacritty','wezterm','foot','tilix','terminator','qterminal','bash','sh','zsh','fish','dash',
 'python','python3','perl','ruby','node','env','flatpak','snap','systemsettings','partitionmanager',
 'gparted','gnome-disks','synaptic','pamac','pacman','dnf','apt','apt-get','yum','zypper','yast',
 'kdesudo','kcm','kcmshell5','kcmshell6','systemctl','loginctl','regedit'}


def private_component(name):
    words=re.split(r'[\W_]+',re.sub(r'([a-z])([A-Z])',r'\1 \2',name).casefold())
    return name.startswith('.') or bool(set(words)&PRIVATE_NAMES)


def trusted_system_file(value):
    """Trust installed system paths only, with root-owned non-writable ancestors."""
    try:
        path=Path(value)
        if path.is_symlink() and path.suffix=='.desktop': return False
        path=path.resolve(strict=True)
        if not any(path.is_relative_to(root) for root in (Path('/usr'),Path('/opt'))): return False
        if not path.is_file(): return False
        for item in (path,*path.parents):
            info=item.stat()
            if info.st_uid!=0 or info.st_mode & (stat.S_IWGRP|stat.S_IWOTH): return False
        return True
    except (OSError,ValueError): return False


def ordinary_application(entry):
    if not entry or not trusted_system_file(entry['path']): return False
    if entry.get('terminal') or entry.get('privileged'): return False
    categories=set(entry.get('categories',[]))
    if categories & SENSITIVE_CATEGORIES: return False
    try: argv=shlex.split(entry.get('exec',''),posix=True)
    except ValueError: return False
    if not argv: return False  # D-Bus-only/unclassified entries still need confirmation.
    executable=argv[0]
    # Resolve bare programs against fixed system directories, never a user PATH.
    if '/' not in executable:
        executable=next((str(Path(root)/executable) for root in ('/usr/bin','/bin') if (Path(root)/executable).is_file()),'')
    elif not Path(executable).is_absolute(): return False
    if not executable or not trusted_system_file(executable): return False
    program=Path(executable).name.casefold()
    words={Path(token).name.casefold() for token in argv}
    if words & RISKY_WORDS or program in RISKY_WORDS: return False
    if any(token in ('-e','-c','--command','--execute','--admin','--root') for token in argv[1:]): return False
    safe_flags={'-b','--','--new-window','--standalone','--no-splash','--gapplication-service'}
    if any(token not in safe_flags|{'%u','%U','%f','%F','%i','%c','%k'} for token in argv[1:]): return False
    if not (program in SAFE_PROGRAMS or categories & ORDINARY_CATEGORIES): return False
    if 'System' in categories and program not in SAFE_PROGRAMS: return False
    return True


class PermissionPolicy:
    def __init__(self,settings=None,path=None,home=None):
        self.settings=settings
        self.path=Path(path) if path else app_dir('config')/'permissions.json'
        self.home=Path(home or Path.home()).resolve()
        self.lock=threading.RLock()
        self.roots=[]
        try:
            rows=json.loads(self.path.read_text()).get('search_roots',[])
            if isinstance(rows,list):
                self.roots=[row for row in rows if isinstance(row,dict) and set(row)=={'path','identity'} and
                    isinstance(row['path'],str) and Path(row['path']).is_absolute() and
                    isinstance(row['identity'],list) and len(row['identity'])==2 and all(type(x)is int for x in row['identity'])]
        except (OSError,ValueError,TypeError,AttributeError): pass

    def automatic(self,call,details):
        name=call['name']
        if details.get('choices'): return False
        if name=='open_application':
            return getattr(self.settings,'auto_launch_apps',True) and ordinary_application(details.get('application'))
        if name=='open_directory':
            root=Path(call['arguments']['directory'])
            return root.is_relative_to(self.home) and not any(private_component(part) for part in root.relative_to(self.home).parts)
        if name=='search_files':
            root=Path(call['arguments']['directory'])
            with self.lock: rows=list(self.roots)
            for row in rows:
                approved=Path(row['path'])
                if not root.is_relative_to(approved): continue
                if any(private_component(part) for part in root.relative_to(approved).parts): continue
                try:
                    info=approved.stat()
                    if [info.st_dev,info.st_ino]==row['identity']: return True
                except OSError: pass
            return False
        return name in ('list_applications','system_info','draft_bash')

    def remember(self,call,details):
        if call['name']!='search_files': return
        row={'path':call['arguments']['directory'],'identity':details['directory_identity']}
        with self.lock:
            rows=[old for old in self.roots if old['path']!=row['path']]+[row]
            self._save(rows)
            self.roots=rows

    def forget(self):
        with self.lock:
            self._save([])
            self.roots=[]

    def _save(self,rows):
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd,name=tempfile.mkstemp(prefix='.permissions-',dir=self.path.parent)
        try:
            with os.fdopen(fd,'w') as stream:
                json.dump({'search_roots':rows},stream,ensure_ascii=True)
            os.replace(name,self.path)
        finally:
            Path(name).unlink(missing_ok=True)
