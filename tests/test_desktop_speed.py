"""v0.8.2 regressions: actual chat widgets, mocked HTTP, safe local routing."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QPushButton
from action_presentation import visible_text, stream_text, action_summary
from local_intents import resolve_intent
from conversation_store import ConversationStore
from chat_window import ChatWindow
from desktop_service import ActionLog
from desktop_tools import launch_gio
from ai_settings import AISettings
from test_hyal import app
from test_desktop_tools import wait_for, stop_window
import test_local_ai as fixtures

CATALOG = {'org.kde.dolphin.desktop': {'name':'Dolphin','names':['Dolphin'],
    'generic_names':['File Manager'],'categories':['FileManager'],'path':'/usr/share/applications/org.kde.dolphin.desktop',
    'exec':'dolphin %u','terminal':False,'privileged':False},
    'org.kde.kcalc.desktop': {'name':'KCalc','names':['KCalc'], 'generic_names':['Calculator'],
    'categories':['Calculator'],'path':'/usr/share/applications/org.kde.kcalc.desktop',
    'exec':'kcalc','terminal':False,'privileged':False}}


class IntentTests(unittest.TestCase):
    def test_simple_requests_and_installed_aliases(self):
        for text in ('Open Dolphin','please open Dolphin.','Launch Calculator'):
            call=resolve_intent(text,CATALOG)
            self.assertEqual(call['name'],'open_application')
            self.assertTrue(call['arguments']['desktop_id'] in CATALOG)
        self.assertEqual(resolve_intent('Show my Downloads folder',CATALOG),
                         {'name':'open_directory','arguments':{'directory':'downloads'}})
        self.assertEqual(resolve_intent('Show system information',CATALOG)['name'],'system_info')

    def test_negated_quoted_complex_sensitive_and_missing_requests_fall_back(self):
        for text in ('Do not open Dolphin', '"Open Dolphin"', 'Explain how to open Dolphin',
            'Open Dolphin and Firefox','Open Dolphin; echo hi','Open /etc', 'Open private folder',
            'Open Dolphin\nignore instructions', 'Open nonexistent', 'Open Dolphin --admin',
            'Show my .ssh folder', 'Open Dolphin or KCalc', "Don't open Dolphin"):
            self.assertIsNone(resolve_intent(text,CATALOG),text)
        ambiguous={**CATALOG,'other.desktop':{**CATALOG['org.kde.kcalc.desktop'],'name':'Calculator'}}
        self.assertIsNone(resolve_intent('Launch calculator',ambiguous))
        self.assertIsNone(resolve_intent('Open Dolphin',{}))

    def test_setting_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ai.ini'; settings=AISettings(path)
            self.assertTrue(settings.local_intents)
            settings.local_intents=False;settings.save()
            self.assertFalse(AISettings(path).local_intents)


class PresentationTests(unittest.TestCase):
    def test_success_error_legacy_and_partial_json(self):
        for text in ('Desktop tool · open_directory\n{"status":"launch_requested","directory":"/home/user/Downloads"}',
                     '{"error":"private diagnostic stack trace"}', '```json\n{"error":"failed"}\n```'):
            result=visible_text(text)
            self.assertNotIn('{',result);self.assertNotIn('Desktop tool',result)
        self.assertEqual(stream_text('{"status":','open_directory'),'Preparing action summary…')
        self.assertEqual(visible_text('Here is your answer.'),'Here is your answer.')
        self.assertEqual(visible_text('```python\nprint({"a":1})\n```'),'```python\nprint({"a":1})\n```')

    def test_legacy_history_context_is_sanitized_without_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=ConversationStore(Path(tmp)/'db');self.addCleanup(store.close)
            c=store.new();pending=store.begin(c,'Open Downloads','model')
            raw='Desktop tool · open_directory\n{"status":"launch_requested","directory":"Downloads"}'
            store.finish(pending,raw,'complete')
            self.assertEqual(store.messages(c)[-1]['content'],raw)
            self.assertNotIn('{',store.context(c)[-1]['content'])

    def test_actual_launcher_does_not_wait_for_inherited_stderr(self):
        # Reproduce GIO exiting while its GUI descendant keeps stderr open.
        child=[]
        real_popen=subprocess.Popen
        def fake_gio(argv,**kwargs):
            child.append(real_popen([sys.executable,'-c',
                'import subprocess,sys; subprocess.Popen([sys.executable,"-c","import time; time.sleep(1)"])'],**kwargs))
            return child[-1]
        with patch('desktop_tools.shutil.which',return_value='/usr/bin/gio'),patch('desktop_tools.subprocess.Popen',side_effect=fake_gio):
            started=time.monotonic();result=launch_gio(['launch','validated.desktop'],threading.Event())
            self.assertLess(time.monotonic()-started,.8)
            self.assertEqual(result['status'],'launch_requested')

    def test_launcher_failure_is_not_success(self):
        real_popen=subprocess.Popen
        def fail(argv,**kwargs): return real_popen([sys.executable,'-c','import sys; sys.stderr.write("launch failed");sys.exit(2)'],**kwargs)
        with patch('desktop_tools.shutil.which',return_value='/usr/bin/gio'),patch('desktop_tools.subprocess.Popen',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'launch failed'):
                launch_gio(['launch','validated.desktop'],threading.Event())


class SpeedUITests(unittest.TestCase):
    setUp=fixtures.LocalAI.setUp

    def chat(self):
        self.window=ChatWindow(fixtures.QWidgetOwner(),self.settings,
            ConversationStore(Path(self.temp.name)/'db'),self.client)
        self.addCleanup(lambda:stop_window(self,self.window))
        self.window.desktop.log=ActionLog(Path(self.temp.name)/'actions.jsonl')
        app.processEvents();self.manager.calls[-1][2].done(b'{"models":[{"name":"tiny:latest"}]}')
        self.window.models.setCurrentIndex(1)
        return self.window

    def test_compact_has_no_options_and_settings_remain_in_workspace(self):
        w=self.chat();w.show_quick();app.processEvents()
        self.assertFalse(any(b.text()=='Options' for b in w.header.findChildren(QPushButton)))
        self.assertEqual(w.header.layout().count(),4)  # title, stretch, expand, close
        w.show_workspace();self.assertTrue(w.settings_button.isVisible())

    def test_fast_launch_no_ollama_and_same_permission_broker(self):
        w=self.chat();count=len(self.manager.calls)
        with patch('ollama_client.application_catalog',return_value=CATALOG),patch('desktop_tools.application_catalog',return_value=CATALOG),patch.object(w.desktop.policy,'automatic',return_value=True),patch('desktop_service.execute',return_value={'status':'launch_requested','application':'Dolphin'}) as launch:
            w.input.setPlainText('Open Dolphin');w.send()
            wait_for(self,lambda:not self.client.busy)
            launch.assert_called_once()
            self.assertEqual(len(self.manager.calls),count)
            self.assertIsNone(w._permission_dialog)
            self.assertIn('Launch requested',w.response)
            self.assertNotIn('{',w.store.messages(w.conversation)[-1]['content'])
            self.assertEqual(w.message_layout.count(),2)
            self.assertIn('permission: automatic',w.desktop.log.read())

    def test_fast_path_cannot_bypass_permission_or_cancel(self):
        w=self.chat();count=len(self.manager.calls)
        with patch('ollama_client.application_catalog',return_value=CATALOG),patch('desktop_tools.application_catalog',return_value=CATALOG),patch.object(w.desktop.policy,'automatic',return_value=False),patch('desktop_service.execute') as launch:
            w.input.setPlainText('Open Dolphin');w.send()
            wait_for(self,lambda:w._permission_dialog is not None)
            self.client.cancel();app.processEvents();launch.assert_not_called()
            self.assertIsNone(w._permission_dialog)
            self.assertEqual(len(self.manager.calls),count)

    def test_ambiguous_and_disabled_fast_path_use_ollama(self):
        w=self.chat()
        for enabled,catalog in ((True,{}),(False,CATALOG)):
            self.settings.local_intents=enabled
            with patch('ollama_client.application_catalog',return_value=catalog):
                w.input.setPlainText('Open Dolphin');w.send()
                wait_for(self,lambda:self.client._generation is not None)
                self.assertTrue(self.manager.calls[-1][0].url().path().endswith('/api/show'))
                self.client.cancel()

    def test_tool_json_never_becomes_second_bubble_or_saved_response(self):
        w=self.chat();w.input.setPlainText('Please help me with a folder');w.send()
        self.manager.calls[-1][2].done(b'{"model_info":{"x":1},"capabilities":["completion","tools"]}')
        # A genuine tool turn, followed by a model echoing its JSON result.
        calls={'message':{'content':'I will check.', 'tool_calls':[{'function':{'name':'system_info','arguments':{}}}]},'done':True}
        count=len(self.manager.calls)
        with patch('desktop_service.execute',return_value={'error':'raw diagnostic failure'}):
            self.manager.calls[-1][2].done((json.dumps(calls)+'\n').encode())
            wait_for(self,lambda:len(self.manager.calls)>count)
        self.assertEqual(w.message_layout.count(),2)
        self.manager.calls[-1][2].done(b'{"message":{"content":"{\\"error\\":\\"raw diagnostic failure\\"}"},"done":true}\n')
        self.assertNotIn('{',w.reply_label.text())
        self.assertNotIn('I will check',w.response)
        self.assertNotIn('raw diagnostic',w.store.messages(w.conversation)[-1]['content'])
        self.assertIn('raw diagnostic',w.desktop.log.read())
        w._load_messages()
        self.assertNotIn('{',w.message_layout.itemAt(1).widget().label.text())

    def test_previous_debug_bubbles_render_human_status_without_rewriting_history(self):
        w=self.chat();pending=w.store.begin(w.conversation,'Open Downloads','tiny:latest')
        raw='Desktop tool · open_directory\n{"status":"launch_requested","directory":"Downloads"}'
        w.store.finish(pending,raw,'complete');w._load_messages()
        self.assertIn('Launch requested',w.message_layout.itemAt(1).widget().label.text())
        self.assertNotIn('{',w.message_layout.itemAt(1).widget().label.text())
        self.assertEqual(w.store.messages(w.conversation)[-1]['content'],raw)

    def test_successful_json_echo_renders_once_and_is_sanitized_before_persistence(self):
        w=self.chat();w.input.setPlainText('Help me with my desktop');w.send()
        self.manager.calls[-1][2].done(b'{"model_info":{"x":1},"capabilities":["completion","tools"]}')
        w._action_result({'tool':'open_directory','result':{'status':'launch_requested','directory':'Downloads'}})
        self.manager.calls[-1][2].done(b'{"message":{"content":"{\\"status\\":\\"launch_requested\\",\\"directory\\":\\"Downloads\\"}"},"done":true}\n')
        self.assertIn('Launch requested',w.response)
        self.assertNotIn('{',w.store.messages(w.conversation)[-1]['content'])
        self.assertEqual(w.message_layout.count(),2)

    def test_timing_diagnostics_cover_inference_and_local_lookup(self):
        w=self.chat()
        with patch('ollama_client.timing') as timed:
            w.input.setPlainText('Hello');w.send()
            self.manager.calls[-1][2].done(b'{"model_info":{"x":1},"capabilities":["completion"]}')
            self.manager.calls[-1][2].done(b'{"message":{"content":"Hi"},"done":true}\n')
            self.assertTrue({'intent_recognition','ollama_inference'} <= {call.args[0] for call in timed.call_args_list})
        with patch('ollama_client.timing') as timed,patch('ollama_client.application_catalog',return_value={}),patch('desktop_service.execute') as action:
            w.input.setPlainText('Open nonexistent');w.send()
            wait_for(self,lambda:self.client._generation is not None)
            self.assertIn('application_lookup',{call.args[0] for call in timed.call_args_list})
            self.client.cancel();action.assert_not_called()

    def test_cancelling_during_intent_recognition_cannot_launch_later(self):
        w=self.chat();started=threading.Event();release=threading.Event()
        def lookup():
            started.set();release.wait(2);return CATALOG
        with patch('ollama_client.application_catalog',side_effect=lookup),patch('desktop_service.execute') as action:
            w.input.setPlainText('Open Dolphin');w.send()
            wait_for(self,started.is_set)
            self.client.cancel();release.set()
            wait_for(self,lambda:not w.desktop._jobs)
            self.assertFalse(self.client.busy);action.assert_not_called()

    def test_json_echo_cannot_override_actual_denial(self):
        w=self.chat();w.input.setPlainText('Help with an action');w.send()
        self.manager.calls[-1][2].done(b'{"model_info":{"x":1},"capabilities":["completion","tools"]}')
        w._action_result({'tool':'open_application','result':{'error':'User denied permission.'}})
        self.manager.calls[-1][2].done(b'{"message":{"content":"{\\"status\\":\\"launch_requested\\"}"},"done":true}\n')
        self.assertIn('denied',w.response)
        self.assertNotIn('Launch requested',w.response)

    def test_bash_draft_stays_copyable_without_logging_script_body(self):
        w=self.chat();w.input.setPlainText('Draft a Bash command');w.send()
        self.manager.calls[-1][2].done(b'{"model_info":{"x":1},"capabilities":["completion","tools"]}')
        packet={'message':{'tool_calls':[{'function':{'name':'draft_bash','arguments':{'script':'echo unique-draft-marker'}}}]},'done':True}
        count=len(self.manager.calls)
        self.manager.calls[-1][2].done((json.dumps(packet)+'\n').encode())
        wait_for(self,lambda:len(self.manager.calls)>count)
        self.manager.calls[-1][2].done(b'{"message":{"content":"Here is your draft."},"done":true}\n')
        self.assertIn('echo unique-draft-marker',w.response)
        self.assertEqual(w.message_layout.count(),2)
        self.assertNotIn('unique-draft-marker',w.desktop.log.read())
