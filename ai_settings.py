"""Local-only AI settings, independent of character appearance settings."""
from runtime_paths import app_dir
from pathlib import Path
from urllib.parse import urlsplit
from PySide6.QtCore import QSettings, QStandardPaths


def local_endpoint(value):
    url = urlsplit(str(value))
    if (url.scheme != 'http' or url.hostname not in ('127.0.0.1', '::1', 'localhost')
            or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment):
        raise ValueError('Use a local HTTP address, e.g. http://127.0.0.1:11434')
    port = url.port or 11434
    if not 1 <= port <= 65535:
        raise ValueError('Invalid server port')
    # Pin localhost to a numeric loopback address; never use DNS or proxies.
    host = '[::1]' if url.hostname == '::1' else '127.0.0.1'
    return f'http://{host}:{port}'


class AISettings:
    def __init__(self, path=None):
        if path is None:
            path = app_dir('config') / 'ai.ini'
        self.store = QSettings(str(path), QSettings.IniFormat)
        self.store.setFallbacksEnabled(False)
        try:
            self.endpoint = local_endpoint(self.store.value('endpoint', 'http://127.0.0.1:11434'))
        except ValueError:
            self.endpoint = 'http://127.0.0.1:11434'
        self.setup_complete = str(self.store.value('setup_complete', False)).lower() in ('true','1')
        self.ai_enabled = str(self.store.value('ai_enabled', True)).lower() in ('true','1')
        self.model = str(self.store.value('model', ''))
        self.auto_launch_apps = str(self.store.value('auto_launch_apps', True)).lower() in ('true','1')
        self.local_intents = str(self.store.value('local_intents', True)).lower() in ('true','1')
        self.context = self._integer('context', 4096, 512, 32768)
        self.timeout = self._integer('timeout', 300, 10, 3600)
        # Unload after each answer by default: predictable RAM use on small PCs.
        self.keep_alive = self._integer('keep_alive', 0, 0, 300)

    def _integer(self, name, default, low, high):
        try:
            return max(low, min(high, int(self.store.value(name, default))))
        except (TypeError, ValueError):
            return default

    def save(self):
        self.endpoint = local_endpoint(self.endpoint)
        for name in ('endpoint', 'model', 'context', 'timeout', 'keep_alive', 'auto_launch_apps', 'local_intents', 'setup_complete', 'ai_enabled'):
            self.store.setValue(name, getattr(self, name))
        self.store.sync()
        if self.store.status() != QSettings.NoError:
            raise OSError('Could not save AI settings: ' + self.store.fileName())
