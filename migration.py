"""Explicit one-time copy into an empty installed profile, never a shared DB."""
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from PySide6.QtCore import QStandardPaths


def import_development():
    config=Path(QStandardPaths.writableLocation(QStandardPaths.GenericConfigLocation))
    data=Path(QStandardPaths.writableLocation(QStandardPaths.GenericDataLocation))
    targets=[]
    for name in ('appearance.ini','ai.ini','permissions.json'):
        targets.append((config/'hyal'/name,config/'hya'/name))
    targets.append((data/'hyal'/'conversations.sqlite3',data/'hya'/'conversations.sqlite3'))
    available=[(a,b) for a,b in targets if a.exists()]
    if not available:raise ValueError('No development settings or history were found in the current XDG directories.')
    if any(a.is_symlink() or not a.is_file() for a,b in available):raise ValueError('Refusing symlinked or non-file development data.')
    if any(b.exists() or b.is_symlink() for a,b in targets):raise ValueError('Installed destination data already exists. Nothing was overwritten.')
    staged=[];published=[]
    try:
        for source,target in available:
            target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            fd,name=tempfile.mkstemp(dir=target.parent,prefix='.hya-import-');os.close(fd)
            staged.append((Path(name),target))
            if source.suffix=='.sqlite3':
                with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as original,closing(sqlite3.connect(name)) as destination:
                    original.backup(destination)
            else:shutil.copyfile(source,name)
            os.chmod(name,0o600)
        for temp,target in staged:
            # Atomic no-overwrite publication, including a competing first launch.
            os.link(temp,target);published.append(target)
        return [str(path) for path in published]
    except Exception:
        for path in published:path.unlink()
        raise
    finally:
        for temp,target in staged:temp.unlink(missing_ok=True)
