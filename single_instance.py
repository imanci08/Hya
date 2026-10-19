"""Profile-specific local IPC with a lock; stale sockets removed only by owner."""
import os
from PySide6.QtCore import QObject,Signal,QLockFile
from PySide6.QtNetwork import QLocalServer,QLocalSocket
from runtime_paths import app_dir,profile


class SingleInstance(QObject):
    activated=Signal()
    def __init__(self,parent=None):
        super().__init__(parent)
        root=app_dir('cache');root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self._owns_lock=False
        self.ipc_error=''
        self.name=str(root/'instance.sock')
        self.lock=QLockFile(str(root/'instance.lock'))
        self.server=QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.server.newConnection.connect(self._accept)

    def acquire(self):
        socket=QLocalSocket()
        socket.connectToServer(self.name)
        if socket.waitForConnected(200):
            socket.write(b'show');socket.waitForBytesWritten(200);socket.disconnectFromServer()
            return False
        if not self.lock.tryLock(0):
            raise RuntimeError('Hya is already starting, or its instance lock is unavailable. Try again shortly.')
        self._owns_lock=True
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            # Restricted containers can disallow local sockets. Keep the lock,
            # so the app remains usable and duplicates still cannot start.
            self.ipc_error=self.server.errorString()
        return True

    def _accept(self):
        while self.server.hasPendingConnections():
            socket=self.server.nextPendingConnection()
            # No arbitrary IPC commands: connecting only requests visibility.
            socket.disconnectFromServer();socket.deleteLater();self.activated.emit()

    def shutdown(self):
        if self.server.isListening():self.server.close()
        if self._owns_lock:self.lock.unlock();self._owns_lock=False
