"""Setup tests never install packages, start services or download real models."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QMessageBox
from ai_settings import AISettings
from ai_setup import SetupService, model_name, check_space, native_command
from ai_setup_window import AISetupWizard
from desktop_service import ActionLog
from conversation_store import ConversationStore
from chat_window import ChatWindow
from test_hyal import app
from test_desktop_tools import wait_for
from test_local_ai import Manager, QWidgetOwner


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.settings=AISettings(Path(self.temp.name)/'ai.ini')
        self.manager=Manager();self.service=SetupService(self.settings,manager=self.manager,log=ActionLog(Path(self.temp.name)/'setup-actions.jsonl'))
        self.addCleanup(self.cleanup_service)
        self.states=[];self.problems=[];self.completed=[];self.progress=[]
        self.service.state.connect(self.states.append);self.service.problem.connect(self.problems.append)
        self.service.downloaded.connect(self.completed.append);self.service.progress.connect(self.progress.append)

    def cleanup_service(self):
        self.service.shutdown();wait_for(self,lambda:not self.service._workers)

    def inspect(self, rows=None):
        self.service.inspect()
        self.manager.calls[-1][2].done(json.dumps({'models':rows or []}).encode())

    def pull(self,estimate=600_000_000):
        count=len(self.problems)
        self.service.pull('qwen3:0.6b',estimate,self.temp.name,approved=True)
        wait_for(self,lambda:self.service._request is not None or len(self.problems)>count)
        return self.manager.calls[-1][2] if self.manager.calls else None

    def test_missing_executable_and_unreachable_service_are_distinct(self):
        with patch('ai_setup.shutil.which',return_value=None):self.service.inspect()
        reply=self.manager.calls[-1][2];reply.status=503;reply.done(b'{"error":"service unavailable"}')
        self.assertFalse(self.states[-1]['installed']);self.assertFalse(self.states[-1]['reachable'])
        self.assertFalse(self.service.busy)

    def test_reachable_service_without_path_and_local_chat_compatibility(self):
        with patch('ai_setup.shutil.which',return_value=None):
            self.inspect([{'name':'chat'},{'name':'embed'},{'name':'remote:cloud'},{'name':'disguised'}])
        self.manager.calls[-1][2].done(b'{"model_info":{"x":1},"capabilities":["completion","tools"]}')
        self.manager.calls[-1][2].done(b'{"model_info":{"x":1},"capabilities":["embedding"]}')
        self.manager.calls[-1][2].done(b'{"model_info":{"x":1},"capabilities":["completion"],"remote_host":"cloud"}')
        state=self.states[-1]
        self.assertTrue(state['reachable']);self.assertFalse(state['installed'])
        self.assertEqual(state['models'],[{'name':'chat','tools':True}]);self.assertEqual(state['excluded'],3)

    def test_no_models_and_invalid_catalog(self):
        self.inspect();self.assertEqual(self.states[-1]['models'],[])
        self.service.inspect();self.manager.calls[-1][2].done(b'{"models":"invalid"}')
        self.assertFalse(self.states[-1]['reachable'])

    def test_download_requires_approval_and_valid_local_model_name(self):
        with self.assertRaises(PermissionError):self.service.pull('qwen3:0.6b',600_000_000,self.temp.name)
        for name in ('https://evil/model','--command','model;echo hi','x:cloud','model:latest-cloud','../../file','host.com/model:tag'):
            with self.assertRaises(ValueError):model_name(name)
        self.assertEqual(model_name('namespace/qwen2.5:0.5b'),'namespace/qwen2.5:0.5b')

    def test_streamed_download_progress_success_and_fragmented_lines(self):
        reply=self.pull()
        self.assertTrue(self.service.busy)
        self.assertEqual(self.manager.calls[-1][1],{'model':'qwen3:0.6b','stream':True})
        reply.feed(b'{"status":"pulling","digest":"a","total":100,"completed":5')
        reply.feed(b'0}\n')
        self.assertEqual(self.progress[-1]['completed'],50)
        reply.done(b'{"status":"success"}\n')
        self.assertEqual(self.completed,['qwen3:0.6b']);self.assertFalse(self.service.busy)

    def test_download_cancellation_and_late_callbacks(self):
        reply=self.pull();self.service.cancel()
        self.assertTrue(reply.aborted);self.assertFalse(self.service.busy)
        reply.done(b'{"status":"success"}\n')
        self.assertEqual(self.completed,[])

    def test_insufficient_disk_prevents_network_and_can_retry(self):
        with patch('ai_setup.shutil.disk_usage') as usage:
            usage.return_value.free=1
            self.pull()
        self.assertTrue(self.problems);self.assertEqual(self.manager.calls,[])
        self.assertIn('Not enough free',self.problems[-1]);self.assertFalse(self.service.busy)

    def test_http_disk_full_malformed_stream_and_wrong_estimate(self):
        for payload in (b'{"error":"no space left on device"}\n',b'{"status":"pulling","total":-1}\n',
                        b'{"status":"pulling","digest":"a","total":900000000}\n'):
            reply=self.pull();reply.done(payload)
            self.assertFalse(self.service.busy);self.assertFalse(self.completed)
        self.assertEqual(len(self.problems),3)

    def test_missing_success_and_request_timeout_fail_gracefully(self):
        reply=self.pull();reply.done(b'{"status":"pulling"}\n')
        self.assertFalse(self.completed);self.assertTrue(self.problems)
        self.pull();self.service._request['timer'].timeout.emit()
        self.assertIn('timed out',self.problems[-1]);self.assertFalse(self.service.busy)

    def test_native_setup_is_fixed_interactive_and_requires_consent(self):
        with patch('ai_setup.Path.is_file',return_value=True),patch('ai_setup.os.access',return_value=True):
            args=native_command('install',{'ID':'endeavouros','ID_LIKE':'arch'})
            self.assertEqual(args[-5:],['--','/usr/bin/pacman','-S','--needed','ollama'])
            self.assertNotIn('--noconfirm',args)
            with self.assertRaises(ValueError):native_command('install',{'ID':'unknown'})
            with self.assertRaises(ValueError):native_command('arbitrary',{'ID':'arch'})
        with patch('ai_setup.QProcess.startDetached') as launch:
            with self.assertRaises(PermissionError):self.service.launch_native('install')
            launch.assert_not_called()
        with patch('ai_setup.native_command',return_value=args),patch('ai_setup.QProcess.startDetached',return_value=(False,0)):
            with self.assertRaises(RuntimeError):self.service.launch_native('install',approved=True)

    def wizard(self):
        w=AISetupWizard(self.settings,service=self.service)
        self.addCleanup(w.hide);app.processEvents();return w

    def test_skip_persists_without_changing_existing_model_or_preferences(self):
        self.settings.model='previous-model';self.settings.auto_launch_apps=False
        w=self.wizard();w.skip.click()
        saved=AISettings(Path(self.temp.name)/'ai.ini')
        self.assertTrue(saved.setup_complete);self.assertFalse(saved.ai_enabled)
        self.assertEqual(saved.model,'previous-model');self.assertFalse(saved.auto_launch_apps)
        self.assertTrue(self.manager.calls[-1][2].aborted)

    def test_existing_compatible_selection_and_finish(self):
        w=self.wizard()
        self.manager.calls[-1][2].done(b'{"models":[{"name":"existing"}]}')
        self.manager.calls[-1][2].done(b'{"model_info":{"x":1},"capabilities":["completion"]}')
        self.assertTrue(w.finish.isEnabled());w.finish.click()
        saved=AISettings(Path(self.temp.name)/'ai.ini')
        self.assertEqual(saved.model,'existing');self.assertTrue(saved.ai_enabled)

    def test_wizard_native_and_download_denial_no_side_effect(self):
        w=self.wizard();self.manager.calls[-1][2].done(b'{"models":[]}')
        with patch('ai_setup_window.native_command',return_value=['/usr/bin/konsole','fixed']),patch.object(self.service,'launch_native') as launch,patch.object(self.service,'pull') as pull,patch('ai_setup_window.QMessageBox.question',return_value=QMessageBox.No):
            w._native('install');w._download();launch.assert_not_called();pull.assert_not_called()

    def test_skipped_ai_chat_keeps_history_and_does_not_contact_server(self):
        self.settings.ai_enabled=False
        store=ConversationStore(Path(self.temp.name)/'history');conversation=store.new()
        msg=store.begin(conversation,'old question','old');store.finish(msg,'old answer','complete')
        w=ChatWindow(QWidgetOwner(),self.settings,store,self.service.client)
        self.addCleanup(w.shutdown);app.processEvents()
        self.assertEqual(self.manager.calls,[]);self.assertIn('AI is off',w.status.text())
        w.input.setPlainText('hello');w.send();self.assertEqual(self.manager.calls,[])
        self.assertEqual(len(store.messages(conversation)),2)

    def test_new_setup_close_skips_but_reopening_cancel_keeps_prior_choice(self):
        self.settings.model='keep-me'
        w=self.wizard();w.reject()
        self.assertFalse(self.settings.ai_enabled);self.assertEqual(self.settings.model,'keep-me')
        self.settings.ai_enabled=True
        later=AISetupWizard(self.settings,service=self.service)
        self.addCleanup(later.hide);later.reject()
        self.assertTrue(self.settings.ai_enabled)

    def test_download_log_and_failure_to_log_blocks_transfer(self):
        with patch.object(self.service.log,'write',side_effect=OSError('read-only log')):
            self.pull()
        self.assertEqual(self.manager.calls,[]);self.assertIn('approval',self.problems[-1])
        reply=self.pull();reply.done(b'{"status":"success"}\n')
        log=self.service.log.read()
        self.assertIn('ai_setup_download',log);self.assertIn('completed',log)

    def test_first_run_is_offered_once_without_creating_chat(self):
        from hya import Hya
        from appearance import Appearance
        from PySide6.QtCore import QSettings
        appearance=Appearance(QSettings(str(Path(self.temp.name)/'appearance.ini'),QSettings.IniFormat))
        owner=Hya(40,appearance=appearance)
        self.addCleanup(owner.timer.stop);self.addCleanup(owner.hide)
        self.addCleanup(owner.deleteLater)
        with patch('ai_settings.AISettings',return_value=self.settings),patch('ai_setup_window.AISetupWizard',return_value=self.wizard()) as create:
            owner.open_ai_setup(first_run=True)
            create.assert_called_once();self.assertIsNone(owner._chat_window)
            owner._ai_setup.skip.click()
            owner.open_ai_setup(first_run=True)
            create.assert_called_once()

    def test_skip_before_scheduled_initial_check_makes_no_request(self):
        w=AISetupWizard(self.settings,service=self.service)
        self.addCleanup(w.hide)
        w.skip.click();app.processEvents()
        self.assertEqual(self.manager.calls,[])
