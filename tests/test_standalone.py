"""Standalone entry/profile/tray/wordmark checks without system installation."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QSettings,QSize
from PySide6.QtWidgets import QMenu,QSystemTrayIcon
from appearance import Appearance,PRESETS
from ai_settings import AISettings
from conversation_store import ConversationStore
from runtime_paths import app_dir,asset,set_profile,profile
from migration import import_development
from autostart import Autostart
from application_tray import HyaTray
from single_instance import SingleInstance
from glass_wordmark import GlassWordmark
from test_hyal import app
import test_local_ai as fixtures
from test_desktop_tools import stop_window
from hya import Hya
from chat_window import ChatWindow


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,{'XDG_CONFIG_HOME':self.temp.name+'/config','XDG_DATA_HOME':self.temp.name+'/data','XDG_CACHE_HOME':self.temp.name+'/cache'})
        self.env.start();self.addCleanup(self.env.stop)
        self.old=profile();self.addCleanup(lambda:set_profile(self.old))

    def test_development_and_installed_config_data_cache_are_isolated(self):
        set_profile('development');dev=app_dir('config');settings=AISettings();settings.model='dev';settings.save()
        store=ConversationStore();devdb=store.path;store.new();store.close()
        set_profile('installed');installed=AISettings();self.assertEqual(installed.model,'')
        self.assertNotEqual(app_dir('config'),dev)
        store=ConversationStore();self.assertNotEqual(store.path,devdb);self.assertFalse(store.conversations());store.close()
        self.assertEqual(app_dir('cache').name,'hya')
        set_profile('development');self.assertEqual(AISettings().model,'dev')

    def test_explicit_sqlite_backup_and_no_overwrite_import(self):
        set_profile('development');AISettings().save()
        store=ConversationStore();conversation=store.new();message=store.begin(conversation,'question','tiny');store.finish(message,'answer','complete');store.close()
        copied=import_development();self.assertEqual(len(copied),2)
        set_profile('installed');store=ConversationStore();self.assertEqual(store.messages(conversation)[-1]['content'],'answer');store.close()
        with self.assertRaises(ValueError):import_development()
        set_profile('development');store=ConversationStore();self.assertEqual(store.path.name,'conversations.sqlite3');store.close()

    def test_autostart_opt_in_toggle_and_development_guard(self):
        auto=Autostart()
        self.assertFalse(auto.enabled());self.assertFalse(auto.path.exists())
        set_profile('development')
        with self.assertRaises(ValueError):auto.set_enabled(True)
        set_profile('installed');auto.set_enabled(True);auto.set_enabled(True)
        self.assertTrue(auto.enabled());self.assertEqual(len(list(auto.path.parent.glob('*.desktop'))),1)
        self.assertIn('Exec=/usr/bin/hya',auto.path.read_text())
        auto.set_enabled(False);self.assertFalse(auto.enabled())
        auto.path.write_text('[Desktop Entry]\nName=My launcher\n')
        with self.assertRaises(ValueError):auto.set_enabled(True)
        self.assertIn('My launcher',auto.path.read_text())

    def test_single_instance_reactivation_and_separate_profile(self):
        set_profile('installed');first=SingleInstance();self.addCleanup(first.shutdown)
        self.assertTrue(first.acquire());seen=[];first.activated.connect(lambda:seen.append(True))
        second=SingleInstance()
        if first.server.isListening():
            self.assertFalse(second.acquire());app.processEvents();self.assertTrue(seen)
        else:
            self.assertTrue(first.ipc_error)
            with self.assertRaises(RuntimeError):second.acquire()
        set_profile('development');dev=SingleInstance();self.addCleanup(dev.shutdown)
        self.assertTrue(dev.acquire());self.assertNotEqual(first.name,dev.name)

    def test_assets_are_absolute_and_cwd_independent(self):
        previous=Path.cwd()
        try:
            os.chdir(self.temp.name)
            self.assertTrue(asset('peek.qml').is_file());self.assertTrue(asset('assets/hya.svg').is_file())
            with self.assertRaises(ValueError):asset('../outside')
        finally:os.chdir(previous)


class StandaloneUITests(unittest.TestCase):
    setUp=fixtures.LocalAI.setUp

    def companion(self):
        owner=Hya(40,appearance=Appearance(QSettings(str(Path(self.temp.name)/'appearance.ini'),QSettings.IniFormat)))
        window=ChatWindow(owner,self.settings,ConversationStore(Path(self.temp.name)/'db'),self.client)
        owner._chat_window=window
        tray=HyaTray(owner,Autostart(Path(self.temp.name)/'autostart.desktop'))
        def cleanup():
            tray.show_hya();tray.shutdown();window.close();stop_window(self,window)
            owner.timer.stop();owner._dispose_edge_surface();owner.hide();owner.deleteLater()
        self.addCleanup(cleanup);app.processEvents()
        self.manager.calls[-1][2].done(b'{"models":[]}')
        return owner,window,tray

    def test_orb_menu_preserves_legacy_color_settings(self):
        owner,window,tray=self.companion();menu=QMenu();owner.add_appearance_menu(menu)
        appearance=menu.actions()[0].menu()
        self.assertIn('Orb Color',[a.text() for a in appearance.actions()])
        owner.appearance.select('Ruby')
        self.assertEqual(owner.appearance.settings.value('crystal/preset'),'Ruby')
        self.assertEqual(Appearance(owner.appearance.settings).preset,'Ruby')
        self.assertEqual(set(PRESETS),{'Sapphire','Amethyst','Rose Quartz','Emerald','Ruby','Amber','Arctic','Midnight'})

    def test_tray_actions_and_normal_show_hide_preserve_position(self):
        owner,window,tray=self.companion();owner.move(80,100);owner.show();position=owner.pos()
        self.assertEqual(set(tray.actions),{'Show Hya','Hide Hya','Open Chat','Settings','Start on Login','Quit Hya'})
        with patch.object(QSystemTrayIcon,'isSystemTrayAvailable',return_value=True):
            self.assertTrue(tray.hide_hya());self.assertTrue(owner._docked);self.assertTrue(owner._tray_hidden)
            tray.show_hya();self.assertFalse(owner._docked);self.assertEqual(owner.pos(),position)
        with patch.object(QSystemTrayIcon,'isSystemTrayAvailable',return_value=False):
            self.assertFalse(tray.hide_hya());self.assertFalse(owner._tray_hidden)

    def test_hide_chat_then_reopen_and_close_restores_each_edge(self):
        owner,window,tray=self.companion()
        for edge in ('bottom','left','right'):
            with patch.object(fixtures.QApplication,'platformName',return_value='wayland'):
                owner.hide_at_edge(edge)
            window.show_quick();app.processEvents()
            with patch.object(QSystemTrayIcon,'isSystemTrayAvailable',return_value=True):tray.hide_hya()
            self.assertFalse(window.isVisible());self.assertTrue(owner._docked)
            self.assertFalse(owner.edge_window.isVisible())
            tray.open_chat();self.assertTrue(window.isVisible());self.assertFalse(owner._tray_hidden)
            self.assertTrue(owner._docked);window.close();app.processEvents()
            self.assertFalse(owner._docked);self.assertTrue(owner.edge_window.isVisible())
            self.assertEqual(owner.edge_side,edge);owner.restore()

    def test_lost_tray_host_restores_recovery_surface(self):
        owner,window,tray=self.companion();owner.show()
        with patch.object(QSystemTrayIcon,'isSystemTrayAvailable',return_value=True):tray.hide_hya()
        with patch.object(QSystemTrayIcon,'isSystemTrayAvailable',return_value=False):tray._check_host()
        self.assertFalse(owner._tray_hidden);self.assertFalse(owner._docked)

    def test_glass_wordmark_uses_live_appearance_and_is_cached_in_both_views(self):
        owner,window,tray=self.companion();window.show_quick();app.processEvents()
        title=window.title;self.assertIsInstance(title,GlassWordmark);self.assertEqual(title.text(),'Hya')
        first=title.grab().toImage();key=title._key;image=title._image.cacheKey()
        title.grab();self.assertEqual(title._image.cacheKey(),image)
        owner.appearance.select('Rose Quartz');self.assertIsNone(title._key)
        second=title.grab().toImage();self.assertNotEqual(first,second)
        self.assertEqual(title.tint.name(),PRESETS['Rose Quartz'])
        window.show_workspace();self.assertIs(window.title,title)
        owner.appearance.select('Custom','#ffffff');self.assertEqual(title.tint.name(),'#ffffff')
        self.assertFalse(title.grab().isNull())


class PackagingTests(unittest.TestCase):
    def test_package_template_runtime_dependencies_and_files(self):
        root=Path(__file__).resolve().parents[1]
        template=(root/'packaging/PKGBUILD.in').read_text()
        for package in ('pyside6','qt6-base','qt6-declarative','qt6-svg','layer-shell-qt','glib2'):
            self.assertIn("'"+package+"'",template)
        self.assertIn('optdepends=(\'ollama:',template)
        self.assertIn('/usr/bin/hya',template);self.assertIn('io.hyalos.Hya.desktop',template)
        self.assertNotIn('curl',template);self.assertNotIn('install=',template)
        entry=(root/'packaging/io.hyalos.Hya.desktop').read_text()
        self.assertIn('Exec=hya\n',entry);self.assertIn('Icon=hya\n',entry);self.assertIn('Terminal=false',entry)

    def test_release_is_deterministic_and_excludes_development_data(self):
        import importlib.util
        import tarfile
        root=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('release',root/'tools/prepare_release.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            source,first=module.prepare(a);other,second=module.prepare(b)
            self.assertEqual(first,second);self.assertEqual(source.read_bytes(),other.read_bytes())
            with tarfile.open(source) as archive:
                names=archive.getnames()
                self.assertTrue(any(n.endswith('/peek.qml') for n in names))
                self.assertFalse(any(n.endswith('.sqlite3') or '/.git/' in n or '/dist/' in n for n in names))

class TraySettingsTests(unittest.TestCase):
    setUp=fixtures.LocalAI.setUp

    def test_settings_action_preserves_settings_access_and_quit_dispatches(self):
        from PySide6.QtWidgets import QWidget
        from unittest.mock import Mock
        owner=QWidget();owner._chat_window=Mock();owner._docked=False
        owner.close=Mock();owner.open_chat=Mock();owner.undock_from_chat=Mock()
        tray=HyaTray(owner,Autostart(Path(self.temp.name)/'login.desktop'))
        self.addCleanup(tray.shutdown);self.addCleanup(owner.deleteLater)
        tray.actions['Settings'].trigger()
        owner.open_chat.assert_called_once()
        owner._chat_window.show_workspace.assert_called_once()
        owner._chat_window.edit_settings.assert_called_once()
        tray.actions['Quit Hya'].trigger();owner.close.assert_called_once()
