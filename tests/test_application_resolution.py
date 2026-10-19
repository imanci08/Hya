"""Friendly app names resolve only to actual installed desktop entries."""
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QLabel, QPushButton, QComboBox
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from application_resolver import resolve_applications
from desktop_tools import application_catalog,prepare,execute,Grant,action_key,schemas
from desktop_service import DesktopService,ActionLog
from chat_window import ChatWindow
from conversation_store import ConversationStore
from test_hyal import app
import test_local_ai as fixtures
from test_desktop_tools import wait_for,stop_service,stop_window


def request(text):
    return {'name':'open_application','arguments':{'application':text}}


class ApplicationResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.apps=self.root/'applications'; self.apps.mkdir()
        self.environment=patch.dict(os.environ,{'XDG_DATA_HOME':str(self.root),'XDG_DATA_DIRS':str(self.root/'absent')})
        self.environment.start(); self.addCleanup(self.environment.stop)

    def entry(self,identifier,name,generic='',categories='',extra=''):
        (self.apps/identifier).write_text('[Desktop Entry]\nType=Application\nName='+name+'\nGenericName='+generic+
            '\nCategories='+categories+'\nExec=/usr/bin/true\n'+extra)

    def test_common_aliases_use_actual_installed_entries(self):
        self.entry('org.kde.kcalc.desktop','KCalc','Scientific Calculator','Qt;KDE;Calculator;')
        self.entry('org.kde.dolphin.desktop','Dolphin','File Manager','Qt;KDE;FileManager;')
        self.entry('org.kde.konsole.desktop','Konsole','Terminal','Qt;KDE;TerminalEmulator;')
        for query,expected in [('calculator','kcalc'),('Open calculator','kcalc'),('please open the calculator app','kcalc'),
                ('file manager','dolphin'),('file browser','dolphin'),('terminal','konsole'),('KONSOLE','konsole')]:
            call,details=prepare(request(query))
            self.assertEqual(call['arguments'],{'desktop_id':f'org.kde.{expected}.desktop'})
            self.assertIn('application',details)
            self.assertNotIn('choices',details)
        self.assertIn('application',next(item for item in schemas() if item['function']['name']=='open_application')['function']['parameters']['properties'])

    def test_alias_does_not_assume_kde_or_install_missing_programs(self):
        self.entry('org.gnome.Calculator.desktop','Calculator','Calculator','Calculator;')
        call,details=prepare(request('calculator'))
        self.assertEqual(call['arguments']['desktop_id'],'org.gnome.Calculator.desktop')
        with self.assertRaisesRegex(ValueError,'No installed application matches'):
            prepare(request('file manager'))
        with self.assertRaisesRegex(ValueError,'No installed application matches'):
            prepare(request('KCalc'))
        for text in ('/usr/bin/true','calculator; touch /tmp/no','nonexistent application'):
            with self.assertRaises(ValueError):prepare(request(text))

    def test_multiple_calculators_are_ambiguous_but_exact_brand_is_strong(self):
        self.entry('org.kde.kcalc.desktop','KCalc','Scientific Calculator','Calculator;')
        self.entry('org.gnome.Calculator.desktop','Calculator','Calculator','Calculator;')
        call,details=prepare(request('calculator'))
        self.assertEqual({row['application']['name'] for row in details['choices']},{'KCalc','Calculator'})
        with self.assertRaises(ValueError):execute(call,details,threading.Event(),Grant(action_key(call)))
        call,details=prepare(request('KCalc'))
        self.assertEqual(call['arguments']['desktop_id'],'org.kde.kcalc.desktop')
        self.assertNotIn('choices',details)

    def test_generic_keywords_localized_names_and_short_choice_list(self):
        self.entry('example.math.desktop','Math Helper','Arithmetic Tool','Utility;',
                   'Keywords=calculator;math;\nName[de]=Rechenhilfe\nGenericName[de]=Rechner\n')
        call,details=prepare(request('calculator'))
        self.assertEqual(details['application']['name'],'Math Helper')
        call,_=prepare(request('Rechner'))
        self.assertEqual(call['arguments']['desktop_id'],'example.math.desktop')
        for index in range(8):self.entry(f'calc{index}.desktop',f'Calculator {index}','Calculator','Calculator;')
        call,details=prepare(request('calculator'))
        self.assertEqual(len(details['choices']),6)
        self.assertTrue(details['more_matches'])

    def test_hidden_and_terminal_wrapped_entries_are_not_candidates(self):
        self.entry('hidden.desktop','KCalc','Calculator','Calculator;','Hidden=true\n')
        self.entry('wrapped.desktop','Konsole','Terminal','TerminalEmulator;','Terminal=true\n')
        self.assertFalse(application_catalog())
        with self.assertRaises(ValueError):prepare(request('calculator'))

    def test_broker_requires_choice_then_separate_confirmation(self):
        self.entry('org.kde.kcalc.desktop','KCalc','Calculator','Calculator;')
        self.entry('other.desktop','Other Calculator','Calculator','Calculator;')
        service=DesktopService(log=ActionLog(self.root/'audit.jsonl'))
        self.addCleanup(lambda:stop_service(self,service))
        prompts=[];results=[]
        service.permission_needed.connect(lambda *args:prompts.append(args))
        service.result.connect(lambda *args:results.append(args))
        token=service.submit(request('calculator'))
        wait_for(self,lambda:len(prompts)==1)
        with patch('desktop_tools.launch_gio',return_value={'status':'launch_requested'}) as launch:
            self.assertFalse(service.approve(token))
            self.assertFalse(service.select_application(token,'not-installed.desktop'))
            self.assertTrue(service.select_application(token,'org.kde.kcalc.desktop'))
            wait_for(self,lambda:len(prompts)==2)
            launch.assert_not_called()
            self.assertTrue(service.approve(token))
            self.assertFalse(service.approve(token))
            wait_for(self,lambda:bool(results))
            self.assertEqual(launch.call_args[0][0],['launch',str(self.apps/'org.kde.kcalc.desktop')])
        self.assertIn('org.kde.kcalc.desktop',service.log.read())

    def test_choice_cancel_and_changed_entry_cannot_launch(self):
        self.entry('one.desktop','One Calculator','Calculator','Calculator;')
        self.entry('two.desktop','Two Calculator','Calculator','Calculator;')
        service=DesktopService(log=ActionLog(self.root/'audit.jsonl'))
        self.addCleanup(lambda:stop_service(self,service))
        prompts=[];results=[]
        service.permission_needed.connect(lambda *args:prompts.append(args))
        service.result.connect(lambda *args:results.append(args))
        token=service.submit(request('calculator'))
        wait_for(self,lambda:bool(prompts))
        service.cancel()
        self.assertFalse(service.select_application(token,'one.desktop'))
        token=service.submit(request('calculator'))
        wait_for(self,lambda:len(prompts)==2)
        service.select_application(token,'one.desktop')
        wait_for(self,lambda:len(prompts)==3)
        self.entry('one.desktop','Changed Calculator','Calculator','Calculator;')
        with patch('desktop_tools.launch_gio') as launch:
            service.approve(token)
            wait_for(self,lambda:bool(results))
            launch.assert_not_called()
        self.assertIn('changed since confirmation',results[-1][1]['error'])


class ApplicationPermissionUITests(unittest.TestCase):
    setUp=fixtures.LocalAI.setUp

    def test_friendly_choices_then_friendly_launch_confirmation(self):
        root=Path(self.temp.name); apps=root/'applications'; apps.mkdir()
        for identifier,name in [('one.desktop','KCalc'),('two.desktop','Other Calculator')]:
            (apps/identifier).write_text(f'[Desktop Entry]\nType=Application\nName={name}\nGenericName=Calculator\nCategories=Calculator;\nExec=/usr/bin/true\n')
        environment=patch.dict(os.environ,{'XDG_DATA_HOME':str(root),'XDG_DATA_DIRS':str(root/'missing')})
        environment.start();self.addCleanup(environment.stop)
        owner=fixtures.QWidgetOwner()
        window=ChatWindow(owner,self.settings,ConversationStore(root/'chat.sqlite3'),self.client)
        self.addCleanup(window.deleteLater);self.addCleanup(lambda:stop_window(self,window))
        window.desktop.log=ActionLog(root/'log.jsonl')
        app.processEvents()
        self.manager.calls[-1][2].done(b'{"models":[]}')
        window.show_quick()
        token=window.desktop.submit(request('calculator'))
        wait_for(self,lambda:window._permission_dialog is not None)
        dialog=window._permission_dialog
        selector=dialog.findChild(QComboBox)
        self.assertIn('KCalc',selector.itemText(1)+selector.itemText(2))
        button=next(b for b in dialog.findChildren(QPushButton) if b.text()=='Continue')
        self.assertFalse(button.isEnabled())
        selector.setCurrentIndex(selector.findData('one.desktop'))
        with patch('desktop_tools.launch_gio',return_value={'status':'launch_requested'}) as launch:
            QTest.mouseClick(button,Qt.LeftButton)
            wait_for(self,lambda:window._permission_dialog is not None and window._permission_dialog is not dialog)
            launch.assert_not_called()
            confirm=window._permission_dialog
            self.assertIsNot(confirm,dialog)
            self.assertTrue(any(label.text()=='Open KCalc?' for label in confirm.findChildren(QLabel)))
            open_button=next(b for b in confirm.findChildren(QPushButton) if b.text()=='Open KCalc')
            QTest.mouseClick(open_button,Qt.LeftButton)
            wait_for(self,lambda:window.desktop._active is None)
            launch.assert_called_once()
