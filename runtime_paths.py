"""Stable profile namespaces. Development retains the original hyal data paths."""
from pathlib import Path
from PySide6.QtCore import QStandardPaths

_profile='development'


def set_profile(profile):
    global _profile
    if profile not in ('development','installed'):raise ValueError('Unknown Hya profile')
    _profile=profile


def profile(): return _profile


def app_dir(kind):
    locations={'config':QStandardPaths.GenericConfigLocation,'data':QStandardPaths.GenericDataLocation,
               'cache':QStandardPaths.GenericCacheLocation}
    return Path(QStandardPaths.writableLocation(locations[kind]))/('hya' if _profile=='installed' else 'hyal')


def asset(name):
    root=Path(__file__).resolve().parent
    candidate=(root/name).resolve()
    if not candidate.is_relative_to(root):raise ValueError('Asset must be inside application')
    return candidate
