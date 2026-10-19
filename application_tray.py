"""Native StatusNotifier tray; suspend the existing desktop surface for hiding."""
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon,QMenu,QMessageBox
from runtime_paths import asset, profile
from autostart import Autostart


class HyaTray(QObject):
    def __init__(self,owner,autostart=None):
        super().__init__(owner)
        self.owner=owner
        self.autostart=autostart or Autostart()
        self.icon=QSystemTrayIcon(QIcon(str(asset('assets/hya.svg'))),self)
        self.icon.setToolTip('Hya — Orb desktop companion')
        self.menu=QMenu()
        self.actions={}
        for label,callback in (('Show Hya',self.show_hya),('Hide Hya',self.hide_hya),
            ('Open Chat',self.open_chat),('Settings',self.settings),('Start on Login',self._autostart),('Quit Hya',owner.close)):
            action=self.menu.addAction(label)
            if label=='Start on Login':
                action.setCheckable(True);action.setChecked(self.autostart.enabled())
                action.setEnabled(profile()=='installed')
                action.setToolTip('Opt-in startup for the installed application')
            action.triggered.connect(callback);self.actions[label]=action
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        self.watch=QTimer(self);self.watch.setInterval(2000);self.watch.timeout.connect(self._check_host)
        self.icon.show()  # Qt registers automatically if a tray host appears later.

    def _activated(self,reason):
        if reason in (QSystemTrayIcon.Trigger,QSystemTrayIcon.DoubleClick):self.show_hya()

    def show_hya(self):
        self.watch.stop();self.owner._tray_hidden=False
        chat=getattr(self.owner,'_chat_window',None)
        if chat and chat.isVisible():chat.close()
        self.owner.undock_from_chat()

    def hide_hya(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False  # Never strand Hya without a recovery surface.
        self.owner._tray_hidden=True
        chat=getattr(self.owner,'_chat_window',None)
        if chat and chat.isVisible():chat.close()
        if not self.owner._docked:self.owner.dock_to_chat()
        if self.owner.edge_window:self.owner.edge_window.hide()
        self.watch.start()
        return True

    def open_chat(self):
        self.watch.stop();self.owner._tray_hidden=False
        self.owner.open_chat()

    def settings(self):
        self.open_chat()
        chat=getattr(self.owner,'_chat_window',None)
        if chat:
            chat.show_workspace();chat.edit_settings()

    def _autostart(self,enabled):
        try:self.autostart.set_enabled(enabled)
        except (OSError,ValueError) as error:
            QMessageBox.warning(None,'Hya — Start on Login',str(error))
        self.actions['Start on Login'].setChecked(self.autostart.enabled())

    def _check_host(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():self.show_hya()

    def activate(self):
        chat=getattr(self.owner,'_chat_window',None)
        if chat and chat.isVisible():chat._activate_input()
        else:self.show_hya()

    def shutdown(self):
        self.watch.stop();self.icon.hide();self.menu.close()
