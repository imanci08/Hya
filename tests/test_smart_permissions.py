"""Policy is application code, never a model-controlled permission category."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QCheckBox, QDialogButtonBox, QPushButton
from PySide6.QtTest import QTest
from ai_settings import AISettings
from smart_permissions import PermissionPolicy, ordinary_application, trusted_system_file
from desktop_tools import prepare, execute, Grant, action_key
from desktop_service import DesktopService, ActionLog
from chat_window import ChatWindow
from conversation_store import ConversationStore
from test_hyal import app
from test_desktop_tools import wait_for, stop_service, stop_window
import test_local_ai as fixtures


def request(tool,**arguments):return {'name':tool,'arguments':arguments}


class SmartPermissionsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.home=self.root/'home';self.home.mkdir()
        self.apps=self.root/'data/applications';self.apps.mkdir(parents=True)
        env=patch.dict(os.environ,{'XDG_DATA_HOME':str(self.root/'data'),'XDG_DATA_DIRS':str(self.root/'none')})
        env.start();self.addCleanup(env.stop)
        self.settings=AISettings(self.root/'ai.ini')
        self.policy=PermissionPolicy(self.settings,self.root/'permissions.json',home=self.home)
        self.service=DesktopService(log=ActionLog(self.root/'audit.jsonl'),policy=self.policy)
        self.addCleanup(lambda:stop_service(self,self.service))
        self.prompts=[];self.results=[]
        self.service.permission_needed.connect(lambda *args:self.prompts.append(args))
        self.service.result.connect(lambda *args:self.results.append(args))

    def entry(self,name,command,categories='Utility;',extra=''):
        path=self.apps/(name.casefold()+'.desktop')
        path.write_text(f'[Desktop Entry]\nType=Application\nName={name}\nExec={command}\nCategories={categories}\n'+extra)
        return path

    def test_ordinary_apps_launch_without_dialog_and_keep_output_and_log(self):
        for name in ('Dolphin','KCalc','Kate','Firefox'):
            self.entry(name,'/usr/bin/'+name.casefold(),{'Dolphin':'System;FileManager;', 'KCalc':'Calculator;', 'Kate':'Development;TextEditor;', 'Firefox':'Network;WebBrowser;'}[name])
        with patch('smart_permissions.trusted_system_file',return_value=True),patch('desktop_tools.launch_gio',return_value={'status':'launch_requested'}) as launch:
            for index,name in enumerate(('Dolphin','KCalc','Kate','Firefox'),1):
                self.service.submit(request('open_application',application=name))
                wait_for(self,lambda:len(self.results)==index)
                self.assertFalse(self.prompts)
                result=self.results[-1][1]
                self.assertEqual(result['status'],'launch_requested')
                self.assertEqual(result['application'],name)
                self.assertNotIn('opened',result)
            self.assertEqual(launch.call_count,4)
        rows=[json.loads(line) for line in self.service.log.read().splitlines()]
        self.assertEqual(sum(row['status']=='completed' for row in rows),4)
        self.assertTrue(all('automatic' in row['note'] for row in rows if row['status']=='started'))

    def test_disabled_auto_launch_persists_and_requires_confirmation(self):
        self.settings.auto_launch_apps=False;self.settings.save()
        reloaded=AISettings(self.root/'ai.ini')
        self.assertFalse(reloaded.auto_launch_apps)
        self.policy.settings=reloaded
        self.entry('Dolphin','/usr/bin/dolphin')
        with patch('smart_permissions.trusted_system_file',return_value=True),patch('desktop_tools.launch_gio',return_value={'status':'launch_requested'}) as launch:
            token=self.service.submit(request('open_application',application='Dolphin'))
            wait_for(self,lambda:bool(self.prompts))
            launch.assert_not_called()
            self.service.approve(token)
            wait_for(self,lambda:bool(self.results))
            launch.assert_called_once()

    def test_admin_terminal_interpreter_and_unknown_launches_never_automatic(self):
        samples=[('Konsole','/usr/bin/konsole','TerminalEmulator;',''),
          ('Settings','/usr/bin/systemsettings','Settings;',''),
          ('Disks','/usr/bin/gnome-disks','System;',''),
          ('Root','pkexec /usr/bin/kate','TextEditor;',''),
          ('Wrapped','sh -c kate','TextEditor;',''),
          ('Dangerous','/usr/bin/kate --execute payload','TextEditor;',''),
          ('Privileged','/usr/bin/kate','TextEditor;','X-KDE-SubstituteUID=true\n')]
        with patch('smart_permissions.trusted_system_file',return_value=True),patch('desktop_tools.launch_gio') as launch:
            for index,(name,command,categories,extra) in enumerate(samples,1):
                self.entry(name,command,categories,extra)
                self.service.submit(request('open_application',application=name))
                wait_for(self,lambda:len(self.prompts)==index)
                self.service.cancel()
            launch.assert_not_called()

    def test_user_owned_entry_is_not_automatic_and_unknown_id_is_rejected(self):
        path=self.entry('Dolphin','/usr/bin/dolphin')
        self.assertFalse(trusted_system_file(path))
        self.service.submit(request('open_application',application='Dolphin'))
        wait_for(self,lambda:bool(self.prompts));self.service.cancel()
        self.service.submit(request('open_application',desktop_id='invented.desktop'))
        wait_for(self,lambda:bool(self.results))
        self.assertIn('not installed',self.results[-1][1]['error'])
        self.assertFalse(trusted_system_file('/tmp/not-a-program'))
        with self.assertRaises(ValueError):prepare(request('open_application',desktop_id='/usr/bin/kate'))
        with self.assertRaises(ValueError):prepare(request('open_application',application='Dolphin',automatic=True))

    def test_external_search_still_requires_confirmation(self):
        with patch('desktop_tools.launch_gio') as launch:
            self.service.submit(request('web_search',query='private document name'))
            wait_for(self,lambda:bool(self.prompts))
            launch.assert_not_called()
            self.assertEqual(self.prompts[-1][1]['action'],'web_search')

    def test_ordinary_directories_open_automatically_private_and_external_need_permission(self):
        downloads=self.home/'Downloads';downloads.mkdir()
        private=self.home/'.ssh';private.mkdir()
        outside=self.root/'outside';outside.mkdir()
        with patch('desktop_tools.launch_gio',return_value={'status':'launch_requested'}) as launch:
            self.service.submit(request('open_directory',directory=str(downloads)))
            wait_for(self,lambda:bool(self.results))
            self.assertFalse(self.prompts)
            self.assertEqual(launch.call_args[0][0],['open',downloads.as_uri()])
            self.assertFalse(self.policy.roots)  # Opening a folder never grants searches.
            for index,path in enumerate((private,outside),1):
                self.service.submit(request('open_directory',directory=str(path)))
                wait_for(self,lambda:len(self.prompts)==index)
                self.service.cancel()
            self.assertEqual(launch.call_count,1)

    def test_search_authorization_reused_after_restart_and_forget_revokes(self):
        documents=self.home/'Documents';documents.mkdir()
        (documents/'report.txt').write_text('not read')
        self.service.submit(request('search_files',directory=str(documents),name='report'))
        wait_for(self,lambda:bool(self.prompts))
        self.service.approve(self.prompts[-1][0])
        wait_for(self,lambda:len(self.results)==1)
        self.assertEqual(self.results[-1][1]['matches'],[str(documents/'report.txt')])
        self.service.policy=PermissionPolicy(self.settings,self.policy.path,home=self.home)
        self.service.submit(request('search_files',directory=str(documents),name='txt'))
        wait_for(self,lambda:len(self.results)==2)
        self.assertEqual(len(self.prompts),1)
        self.service.policy.forget()
        self.service.submit(request('search_files',directory=str(documents),name='txt'))
        wait_for(self,lambda:len(self.prompts)==2)
        self.assertEqual(self.policy.path.stat().st_mode&0o777,0o600)

    def test_private_subdirectories_require_separate_scope_and_are_skipped(self):
        docs=self.home/'Documents';docs.mkdir()
        secret=docs/'private';secret.mkdir()
        (secret/'hidden.txt').write_text('secret')
        ordinary=docs/'work';ordinary.mkdir();(ordinary/'report.txt').touch()
        call,details=prepare(request('search_files',directory=str(docs),name='txt'))
        self.policy.remember(call,details)
        self.assertTrue(self.policy.automatic(*prepare(request('search_files',directory=str(ordinary),name='txt'))))
        self.assertFalse(self.policy.automatic(*prepare(request('search_files',directory=str(secret),name='txt'))))
        result=execute(call,details,__import__('threading').Event(),Grant(action_key(call)))
        self.assertEqual(result['matches'],[str(ordinary/'report.txt')])
        (secret/'tax.txt').touch()
        self.service.submit(request('search_files',directory=str(secret),name='tax'))
        wait_for(self,lambda:bool(self.prompts))
        self.service.approve(self.prompts[-1][0])
        wait_for(self,lambda:bool(self.results))
        self.assertEqual(self.results[-1][1]['matches'],[str(secret/'tax.txt')])

    def test_stale_approved_directory_and_symlink_escape_require_new_permission(self):
        docs=self.home/'Documents';docs.mkdir()
        call,details=prepare(request('search_files',directory=str(docs),name='txt'))
        self.policy.remember(call,details)
        docs.rename(self.home/'old');docs.mkdir()
        call,details=prepare(request('search_files',directory=str(docs),name='txt'))
        self.assertFalse(self.policy.automatic(call,details))
        external=self.root/'external';external.mkdir()
        (docs/'link').symlink_to(external,target_is_directory=True)
        self.policy.remember(call,details)
        call,details=prepare(request('search_files',directory=str(docs/'link'),name='txt'))
        self.assertFalse(self.policy.automatic(call,details))

    def test_system_info_bash_stay_automatic_and_unsupported_sensitive_tools_rejected(self):
        for index,call in enumerate((request('system_info'),request('draft_bash',script='echo hello'),request('read_file',path='/etc/shadow')),1):
            self.service.submit(call)
            wait_for(self,lambda:len(self.results)==index)
        self.assertFalse(self.prompts)
        self.assertFalse(self.results[1][1]['executed'])
        self.assertIn('Unknown',self.results[-1][1]['error'])

    def test_ambiguous_ordinary_choice_launches_without_second_confirmation(self):
        self.entry('KCalc','/usr/bin/kcalc','Calculator;')
        self.entry('Calculator','/usr/bin/gnome-calculator','Calculator;')
        with patch('smart_permissions.trusted_system_file',return_value=True),patch('desktop_tools.launch_gio',return_value={'status':'launch_requested'}) as launch:
            token=self.service.submit(request('open_application',application='calculator'))
            wait_for(self,lambda:bool(self.prompts))
            self.assertTrue(self.service.select_application(token,'kcalc.desktop'))
            wait_for(self,lambda:bool(self.results))
            self.assertEqual(len(self.prompts),1)
            launch.assert_called_once()


class SmartSettingsUITests(unittest.TestCase):
    setUp=fixtures.LocalAI.setUp

    def test_settings_toggle_is_visible_persisted_and_used_by_broker(self):
        owner=fixtures.QWidgetOwner()
        window=ChatWindow(owner,self.settings,ConversationStore(Path(self.temp.name)/'chat.sqlite3'),self.client)
        self.addCleanup(window.deleteLater);self.addCleanup(lambda:stop_window(self,window))
        app.processEvents()
        self.manager.calls[-1][2].done(b'{"models":[]}')
        def change():
            dialog=app.activeModalWidget()
            checkbox=dialog.findChild(QCheckBox,'auto_launch_apps')
            self.assertIsNotNone(checkbox)
            checkbox.setChecked(False)
            box=dialog.findChild(QDialogButtonBox)
            QTest.mouseClick(box.button(QDialogButtonBox.Save),Qt.LeftButton)
        QTimer.singleShot(10,change)
        window.edit_settings()
        self.assertFalse(self.settings.auto_launch_apps)
        self.assertFalse(window.desktop.policy.settings.auto_launch_apps)
        self.assertFalse(AISettings(self.settings.store.fileName()).auto_launch_apps)

class TrustBoundaryTests(unittest.TestCase):
    def test_trust_requires_root_ownership_and_no_writeable_ancestors(self):
        info=SimpleNamespace(st_uid=0,st_mode=0o100755)
        with patch.object(Path,'resolve',lambda self,strict=False:self),patch.object(Path,'stat',return_value=info):
            self.assertTrue(trusted_system_file('/usr/bin/kcalc'))
            info.st_uid=1000
            self.assertFalse(trusted_system_file('/usr/bin/kcalc'))
            info.st_uid=0;info.st_mode=0o100777
            self.assertFalse(trusted_system_file('/usr/bin/kcalc'))
        self.assertFalse(trusted_system_file('/home/user/custom.desktop'))

    def test_standard_directory_alias_resolves_without_shell_expansion(self):
        from PySide6.QtCore import QStandardPaths
        from desktop_tools import validate_call
        result=validate_call(request('open_directory',directory='Downloads'))
        self.assertEqual(result['arguments']['directory'],QStandardPaths.writableLocation(QStandardPaths.DownloadLocation))
        with self.assertRaises(ValueError):validate_call(request('open_directory',directory='$(touch bad)'))
