"""No real applications or browsers are launched by these tests."""
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, Mock
from urllib.parse import urlsplit, parse_qs
from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton, QPlainTextEdit
from desktop_tools import (validate_call, prepare, execute, Grant, action_key, application_catalog, Cancelled, filename_search)
from desktop_service import DesktopService, ActionLog
from chat_window import ChatWindow
from conversation_store import ConversationStore
from test_hyal import app
import test_local_ai as fixtures


def wait_for(test, predicate):
    deadline=time.monotonic()+3
    while not predicate() and time.monotonic()<deadline:
        QTest.qWait(10)
    test.assertTrue(predicate(),'Timed out waiting for asynchronous operation')


def stop_service(test, service):
    service.shutdown()
    wait_for(test,lambda:not service._jobs)


def stop_window(test, window):
    window.shutdown()
    if window.desktop: wait_for(test,lambda:not window.desktop._jobs)


def call(tool_name,**arguments):
    return {'name':tool_name,'arguments':arguments}


class ToolValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_strict_allowlist_and_argument_types(self):
        bad=[call('shell',command='touch /tmp/no'),call('system_info',confirmed=True),
             call('web_search',query=['bad']),call('search_files',directory='relative',name='file'),
             call('open_application',desktop_id='/tmp/malicious.desktop'),call('open_application',desktop_id='app.desktop;sh'),
             call('draft_bash',script=''),call('web_search',query='hello\nworld'),
             {'name':'system_info','arguments':{},'approved':True},None]
        for item in bad:
            with self.assertRaises(ValueError,msg=str(item)): validate_call(item)
        self.assertEqual(validate_call(call('system_info')),call('system_info'))

    def test_grants_cannot_be_supplied_as_model_arguments_or_reused(self):
        request=call('web_search',query='hello')
        validated,details=prepare(request)
        with patch('desktop_tools.launch_gio') as launch:
            with self.assertRaises(PermissionError): execute(validated,details,threading.Event())
            with self.assertRaises(PermissionError): execute(validated,details,threading.Event(),Grant('different'))
            launch.assert_not_called()
        with self.assertRaises(ValueError): validate_call(call('web_search',query='hello',grant=True))

    def test_browser_query_is_encoded_not_interpreted(self):
        request=call('web_search',query='$(touch /tmp/no); a&b "quoted" café')
        validated,details=prepare(request)
        with patch('desktop_tools.launch_gio',return_value={'status':'launch_requested'}) as launch:
            execute(validated,details,threading.Event(),Grant(action_key(validated)))
        args=launch.call_args[0][0]
        self.assertEqual(args[0],'open')
        self.assertEqual(urlsplit(args[1]).netloc,'duckduckgo.com')
        self.assertEqual(parse_qs(urlsplit(args[1]).query)['q'],[request['arguments']['query']])

    def make_catalog(self):
        apps=self.root/'applications'; apps.mkdir()
        (apps/'test.desktop').write_text('[Desktop Entry]\nType=Application\nName=Test app\nExec=/usr/bin/true\n')
        (apps/'hidden.desktop').write_text('[Desktop Entry]\nType=Application\nHidden=true\nName=Hidden\nExec=/usr/bin/true\n')
        (apps/'terminal.desktop').write_text('[Desktop Entry]\nType=Application\nTerminal=true\nName=Terminal entry\nExec=/usr/bin/true\n')
        return apps

    def test_installed_identifiers_and_change_after_confirmation(self):
        apps=self.make_catalog()
        with patch.dict(os.environ,{'XDG_DATA_HOME':str(self.root),'XDG_DATA_DIRS':str(self.root/'absent')}):
            catalog=application_catalog()
            self.assertEqual(list(catalog),['test.desktop'])
            validated,details=prepare(call('open_application',desktop_id='test.desktop'))
            with patch('desktop_tools.launch_gio',return_value={'status':'launch_requested'}) as launch:
                execute(validated,details,threading.Event(),Grant(action_key(validated)))
                self.assertEqual(launch.call_args[0][0],['launch',str(apps/'test.desktop')])
            (apps/'test.desktop').write_text('[Desktop Entry]\nType=Application\nName=Changed\nExec=/usr/bin/false\n')
            with self.assertRaises(ValueError): execute(validated,details,threading.Event(),Grant(action_key(validated)))
            with self.assertRaises(ValueError): prepare(call('open_application',desktop_id='not-installed.desktop'))

    def test_filename_only_search_skips_symlinks_and_requires_authorization(self):
        allowed=self.root/'approved'; allowed.mkdir()
        secret=self.root/'other'; secret.mkdir()
        (allowed/'report.txt').write_text('content must not be read')
        (secret/'secret-report.txt').write_text('secret')
        (allowed/'link').symlink_to(secret,target_is_directory=True)
        (allowed/'report-link').symlink_to(secret/'secret-report.txt')
        validated,details=prepare(call('search_files',directory=str(allowed),name='report'))
        with self.assertRaises(PermissionError): execute(validated,details,threading.Event())
        with patch.object(Path,'read_text',side_effect=AssertionError('No contents')):
            result=execute(validated,details,threading.Event(),Grant(action_key(validated)))
        self.assertEqual(result['matches'],[str(allowed/'report.txt')])
        allowed.rename(self.root/'renamed')
        allowed.mkdir()
        with self.assertRaises(ValueError): execute(validated,details,threading.Event(),Grant(action_key(validated)))

    def test_script_generation_never_executes_or_writes(self):
        script='#!/bin/bash\necho "$(whoami)"\n'
        with patch('desktop_tools.subprocess.Popen') as process:
            validated,details=prepare(call('draft_bash',script=script))
            result=execute(validated,details,threading.Event())
        process.assert_not_called()
        self.assertEqual(result['script'],script)
        self.assertFalse(result['executed'])
        self.assertEqual(list(self.root.iterdir()),[])

    def test_cancellation_and_system_info(self):
        event=threading.Event(); event.set()
        with self.assertRaises(Cancelled): execute(call('system_info'),{},event)
        result=execute(call('system_info'),{},threading.Event())
        self.assertGreater(result['memory']['MemTotal_kib'],0)
        self.assertGreater(result['uptime_seconds'],0)
        self.assertIn('cpu',result)


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.log=ActionLog(Path(self.temp.name)/'actions.jsonl')
        self.service=DesktopService(log=self.log)
        self.addCleanup(self.cleanup_service)
        self.prompts=[]; self.results=[]
        self.service.permission_needed.connect(lambda *args:self.prompts.append(args))
        self.service.result.connect(lambda *args:self.results.append(args))

    def cleanup_service(self):
        self.service.shutdown()
        wait_for(self,lambda:not self.service._jobs)

    def test_permission_denial_blocks_retries_until_new_user_turn(self):
        with patch('desktop_service.execute') as execute_tool:
            token=self.service.submit(call('web_search',query='hello'))
            wait_for(self,lambda:bool(self.prompts))
            execute_tool.assert_not_called()
            self.assertFalse(self.service.approve('invented-token'))
            self.assertTrue(self.service.deny(token))
            self.assertFalse(self.service.approve(token))  # Consumed immediately, before async audit completes.
            wait_for(self,lambda:len(self.results)==1)
            self.service.submit(call('web_search',query='different bypass query'))
            wait_for(self,lambda:len(self.results)==2)
            self.assertEqual(len(self.prompts),1)
            execute_tool.assert_not_called()
            self.service.begin_turn()
            self.service.submit(call('web_search',query='new explicit user request'))
            wait_for(self,lambda:len(self.prompts)==2)
        self.assertIn('denied',self.log.read())

    def test_one_shot_approval_thread_responsiveness_and_logging(self):
        thread=[]
        def operation(*args):
            thread.append(QThread.currentThread())
            time.sleep(.08)
            return {'status':'launch_requested'}
        with patch('desktop_service.execute',side_effect=operation):
            token=self.service.submit(call('web_search',query='hello'))
            wait_for(self,lambda:bool(self.prompts))
            self.assertTrue(self.service.approve(token))
            self.assertFalse(self.service.approve(token))
            ticks=[]
            QTimer.singleShot(10,lambda:ticks.append(True))
            wait_for(self,lambda:bool(self.results))
            self.assertTrue(ticks)
        self.assertIsNot(thread[0],app.thread())
        statuses=[json.loads(line)['status'] for line in self.log.read().splitlines()]
        self.assertEqual(statuses,['started','completed'])
        self.assertEqual(self.log.path.stat().st_mode&0o777,0o600)

    def test_cancel_pending_permission_prevents_execution_and_late_approval(self):
        with patch('desktop_service.execute') as operation:
            token=self.service.submit(call('web_search',query='hello'))
            wait_for(self,lambda:bool(self.prompts))
            self.service.cancel()
            self.assertFalse(self.service.approve(token))
            wait_for(self,lambda:not self.service._jobs)
            operation.assert_not_called()
            self.assertFalse(self.results)
        self.assertIn('cancelled',self.log.read())

    def test_log_failure_prevents_side_effect_and_unknown_tool_is_logged(self):
        with patch.object(self.log,'write',side_effect=OSError('read-only disk')), patch('desktop_service.execute') as operation:
            token=self.service.submit(call('web_search',query='hello'))
            wait_for(self,lambda:bool(self.prompts))
            self.service.approve(token)
            wait_for(self,lambda:bool(self.results))
            self.assertIn('logging failed',self.results[-1][1]['error'])
            operation.assert_not_called()
        self.service.submit(call('arbitrary_shell',command='rm anything'))
        wait_for(self,lambda:len(self.results)==2)
        self.assertIn('Unknown',self.results[-1][1]['error'])
        self.assertIn('rejected',self.log.read())

    def test_directory_permission_required_before_enumeration(self):
        root=Path(self.temp.name)/'approved'; root.mkdir()
        (root/'file.txt').write_text('not read')
        with patch('desktop_tools.filename_search',wraps=filename_search) as search:
            token=self.service.submit(call('search_files',directory=str(root),name='file'))
            wait_for(self,lambda:bool(self.prompts))
            search.assert_not_called()
            self.assertEqual(self.prompts[-1][1]['arguments']['directory'],str(root))
            self.service.approve(token)
            wait_for(self,lambda:bool(self.results))
            self.assertEqual(self.results[-1][1]['matches'],[str(root/'file.txt')])


class ConversationToolsTests(unittest.TestCase):
    setUp=fixtures.LocalAI.setUp
    discover=fixtures.LocalAI.discover

    def attach(self):
        self.service=DesktopService(log=ActionLog(Path(self.temp.name)/'actions.jsonl'))
        self.addCleanup(lambda:stop_service(self,self.service))
        self.client.attach_desktop(self.service)
        self.prompts=[]
        self.service.permission_needed.connect(lambda *args:self.prompts.append(args))

    def begin(self, tools=True):
        self.discover()
        self.client.generate('tiny:latest',[{'role':'user','content':'help'}])
        caps=['completion','tools'] if tools else ['completion']
        self.manager.calls[-1][2].done(json.dumps({'model_info':{'x':1},'capabilities':caps}).encode())
        return self.manager.calls[-1][2]

    def packet(self,name,args):
        return (json.dumps({'message':{'content':'','thinking':'private reasoning',
            'tool_calls':[{'function':{'name':name,'arguments':args}}]},'done':True})+'\n').encode()

    def test_permission_result_roundtrip_then_final_natural_response(self):
        self.attach()
        reply=self.begin()
        self.assertIn('tools',self.manager.calls[-1][1])
        count=len(self.manager.calls)
        reply.done(self.packet('web_search',{'query':'KDE docs'}))
        wait_for(self,lambda:bool(self.prompts))
        self.assertTrue(self.client.busy)
        self.assertEqual(len(self.manager.calls),count)
        with patch('desktop_service.execute',return_value={'status':'launch_requested'}):
            self.service.approve(self.prompts[-1][0])
            wait_for(self,lambda:len(self.manager.calls)>count)
        payload=self.manager.calls[-1][1]
        self.assertEqual(payload['messages'][-1]['role'],'tool')
        self.assertEqual(payload['messages'][-1]['tool_name'],'web_search')
        self.assertEqual(payload['messages'][-2]['thinking'],'private reasoning')
        self.manager.calls[-1][2].done(b'{"message":{"content":"Search requested."},"done":true}\n')
        self.assertFalse(self.client.busy)

    def test_unsupported_model_normal_chat_no_text_execution(self):
        self.attach()
        capability=[]
        self.client.tool_capability.connect(capability.append)
        reply=self.begin(tools=False)
        payload=self.manager.calls[-1][1]
        self.assertNotIn('tools',payload)
        self.assertIn('unavailable',payload['messages'][0]['content'])
        reply.done(b'{"message":{"content":"Run shell(command=anything)"},"done":true}\n')
        self.assertFalse(self.prompts)
        self.assertEqual(capability,[False])
        self.assertFalse(self.service.log.path.exists())

    def test_cancellation_during_permission_stale_reply_and_next_turn(self):
        self.attach()
        reply=self.begin()
        reply.done(self.packet('web_search',{'query':'hello'}))
        wait_for(self,lambda:bool(self.prompts))
        count=len(self.manager.calls)
        self.client.cancel()
        self.assertFalse(self.service.approve(self.prompts[-1][0]))
        self.assertFalse(self.client.busy)
        QTest.qWait(50)
        self.assertEqual(len(self.manager.calls),count)
        self.assertFalse(self.prompts[-1][0]==self.client._tool_token)
        reply=self.begin(tools=False)
        reply.done(b'{"message":{"content":"normal chat"},"done":true}\n')
        self.assertFalse(self.client.busy)

    def test_unknown_and_malformed_tool_calls_cannot_execute(self):
        self.attach()
        reply=self.begin()
        count=len(self.manager.calls)
        reply.done(self.packet('shell',{'command':'touch /tmp/no'}))
        wait_for(self,lambda:len(self.manager.calls)>count)
        self.assertIn('Unknown',self.manager.calls[-1][1]['messages'][-1]['content'])
        self.assertFalse(self.prompts)
        self.client.cancel()
        reply=self.begin()
        reply.done(b'{"message":{"tool_calls":[{"function":{"name":"web_search","arguments":"unstructured"}}]},"done":true}\n')
        self.assertFalse(self.client.busy)
        self.assertIn('structured',self.errors[-1])

    def test_action_round_limit(self):
        self.attach()
        self.begin()
        for index in range(4):
            count=len(self.manager.calls)
            self.manager.calls[-1][2].done(self.packet('draft_bash',{'script':'echo hello'}))
            if index<3: wait_for(self,lambda:len(self.manager.calls)>count)
        self.assertFalse(self.client.busy)
        self.assertIn('round limit',self.errors[-1])

    def test_chat_permission_dialog_buttons_results_and_compatibility(self):
        owner=fixtures.QWidgetOwner()
        window=ChatWindow(owner,self.settings,ConversationStore(Path(self.temp.name)/'chat.sqlite3'),self.client)
        self.addCleanup(window.deleteLater)
        self.addCleanup(lambda:stop_window(self,window))
        # Replace only audit destination; never write real user data in tests.
        window.desktop.log=ActionLog(Path(self.temp.name)/'ui-actions.jsonl')
        app.processEvents()
        self.manager.calls[-1][2].done(b'{"models":[{"name":"tiny:latest"}]}')
        window.models.setCurrentIndex(1)
        window.show_quick()
        window.input.setPlainText('Search the web')
        window.send()
        self.manager.calls[-1][2].done(b'{"model_info":{"x":1},"capabilities":["completion","tools"]}')
        count=len(self.manager.calls)
        self.manager.calls[-1][2].done(self.packet('web_search',{'query':'hello & <world>'}))
        wait_for(self,lambda:window._permission_dialog is not None)
        dialog=window._permission_dialog
        description=dialog.findChild(QPlainTextEdit).toPlainText()
        self.assertIn('hello & <world>',description)
        self.assertTrue(window.stop_button.isEnabled())
        with patch('desktop_service.execute') as operation:
            deny=next(b for b in dialog.findChildren(QPushButton) if b.text()=='Deny')
            QTest.mouseClick(deny,Qt.LeftButton)
            wait_for(self,lambda:len(self.manager.calls)>count)
            operation.assert_not_called()
        self.assertIsNone(window._permission_dialog)
        self.manager.calls[-1][2].done(b'{"message":{"content":"I did not open the browser."},"done":true}\n')
        self.assertEqual(window.store.messages(window.conversation)[-1]['status'],'complete')
        window.input.setPlainText('normal chat'); window.send()
        self.manager.calls[-1][2].done(b'{"model_info":{"x":1},"capabilities":["completion"]}')
        self.manager.calls[-1][2].done(b'{"message":{"content":"Hello"},"done":true}\n')
        self.assertIn('does not support',window.status.text())
        window.close()

class AdditionalSafetyTests(unittest.TestCase):
    def test_fixed_gio_argv_and_launch_cancellation(self):
        import subprocess
        from desktop_tools import launch_gio
        event=threading.Event()
        process=Mock()
        process.wait.return_value=0
        process.poll.return_value=0
        process.returncode=0
        with patch('desktop_tools.shutil.which',return_value='/usr/bin/gio'), patch('desktop_tools.subprocess.Popen',return_value=process) as spawn:
            launch_gio(['open','https://duckduckgo.com/?q=a%26b'],event)
            self.assertEqual(spawn.call_args[0][0],['/usr/bin/gio','open','https://duckduckgo.com/?q=a%26b'])
            self.assertIs(spawn.call_args[1]['shell'],False)
        def fake_spawn(*args,**kwargs):
            event.set()
            return process
        process.wait.side_effect=[subprocess.TimeoutExpired('gio',.1),0]
        process.poll.return_value=None
        with patch('desktop_tools.shutil.which',return_value='/usr/bin/gio'), patch('desktop_tools.subprocess.Popen',side_effect=fake_spawn):
            with self.assertRaises(Cancelled): launch_gio(['open','https://duckduckgo.com/?q=test'],event)
        process.terminate.assert_called_once()

    def test_cancel_during_worker_drops_result_but_records_actual_outcome(self):
        with tempfile.TemporaryDirectory() as temp:
            service=DesktopService(log=ActionLog(Path(temp)/'actions.jsonl'))
            self.addCleanup(service.shutdown)
            started=threading.Event(); results=[]
            service.result.connect(lambda *args:results.append(args))
            def slow(call,details,event,grant):
                started.set()
                while not event.is_set(): time.sleep(.005)
                raise Cancelled('cancelled in worker')
            with patch('desktop_service.execute',side_effect=slow):
                service.submit(call('system_info'))
                wait_for(self,started.is_set)
                service.cancel()
                wait_for(self,lambda:not service._jobs)
            self.assertFalse(results)
            self.assertIn('cancelled in worker',service.log.read())

    def test_search_is_bounded_and_log_persists_without_script_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'approved'; root.mkdir()
            for index in range(110): (root/f'item-{index}').touch()
            request,details=prepare(call('search_files',directory=str(root),name='item'))
            result=execute(request,details,threading.Event(),Grant(action_key(request)))
            self.assertEqual(len(result['matches']),100)
            self.assertTrue(result['truncated'])
            path=Path(temp)/'audit.jsonl'
            ActionLog(path).write(call('draft_bash',script='secret text'), 'completed')
            text=ActionLog(path).read()
            self.assertIn('script_characters',text)
            self.assertNotIn('secret text',text)

class PermissionUITests(unittest.TestCase):
    setUp=fixtures.LocalAI.setUp

    def test_allow_once_button_and_close_chat_cancel_pending_permission(self):
        owner=fixtures.QWidgetOwner()
        window=ChatWindow(owner,self.settings,ConversationStore(Path(self.temp.name)/'allow.sqlite3'),self.client)
        self.addCleanup(window.deleteLater)
        self.addCleanup(lambda:stop_window(self,window))
        window.desktop.log=ActionLog(Path(self.temp.name)/'allow-actions.jsonl')
        window.settings.local_intents=False  # Exercise the model tool-call permission path.
        app.processEvents()
        self.manager.calls[-1][2].done(b'{"models":[{"name":"tiny:latest"}]}')
        window.models.setCurrentIndex(1)
        window.show_quick()
        for approve in (True,False):
            window.input.setPlainText('Open a search'); window.send()
            self.manager.calls[-1][2].done(b'{"model_info":{"x":1},"capabilities":["completion","tools"]}')
            packet={'message':{'tool_calls':[{'function':{'name':'web_search','arguments':{'query':'KDE'}}}]},'done':True}
            self.manager.calls[-1][2].done((json.dumps(packet)+'\n').encode())
            wait_for(self,lambda:window._permission_dialog is not None)
            count=len(self.manager.calls)
            if approve:
                dialog=window._permission_dialog
                with patch('desktop_service.execute',return_value={'status':'launch_requested'}) as operation:
                    button=next(b for b in dialog.findChildren(QPushButton) if b.text()=='Allow once')
                    QTest.mouseClick(button,Qt.LeftButton)
                    wait_for(self,lambda:len(self.manager.calls)>count)
                    operation.assert_called_once()
                self.client.cancel()
                self.assertIn('cannot be undone',window.status.text())
            else:
                with patch('desktop_service.execute') as operation:
                    window.close()
                    QTest.qWait(40)
                    operation.assert_not_called()
                    self.assertFalse(self.client.busy)
                    self.assertIsNone(window._permission_dialog)
                    self.assertEqual(len(self.manager.calls),count)
        self.assertFalse(owner.ai_activity.busy)
