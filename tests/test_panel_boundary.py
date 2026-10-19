import unittest
from panel_boundary import panel_inset, panel_script
from PySide6.QtQml import QJSEngine
from test_hyal import app


class PanelTests(unittest.TestCase):
    def test_real_script_reads_only_matching_output_panels(self):
        # Execute the actual JS query with a mock Plasma API, not a canned reply.
        engine = QJSEngine()
        engine.evaluate('''
function screenForConnector(name) {return name === 'DP-2' ? 4 : -1;}
function panels() {return [
 {screen:0, location:'bottom', height:100},
 {screen:4, location:'left', height:90},
 {screen:4, location:'bottom', height:40, length:1920, lengthMode:'fill',
  offset:0, alignment:'center', floating:false}
];}
var resultText;
function print(text) {resultText=text;}
''')
        result = engine.evaluate(panel_script('DP-2'))
        self.assertFalse(result.isError(), result.toString())
        import json
        rows = json.loads(engine.globalObject().property('resultText').toString())
        self.assertEqual(len(rows), 1)
        self.assertEqual(panel_inset(rows, 1920, 1800), 40)
        self.assertFalse(rows[0]['floating'])

    def test_panel_lengths_alignment_and_no_panel(self):
        self.assertEqual(panel_inset([], 1920, 100), 0)
        row = dict(height=48, length=600, lengthMode='custom', offset=10,
                   alignment='center', floating=False)
        self.assertEqual(panel_inset([row], 1920, 100), 0)
        self.assertEqual(panel_inset([row], 1920, 960), 48)
        row['alignment'] = 'right'
        self.assertEqual(panel_inset([row], 1920, 1800), 48)
        self.assertEqual(panel_inset([row], 1920, 10), 0)
        row['alignment'] = 'left'
        self.assertEqual(panel_inset([row], 1920, 100), 48)
        self.assertEqual(panel_inset([row], 1920, 960), 0)

    def test_override_clamps_to_physical_screen(self):
        from hyal import Hyal
        window = Hyal(40)
        area = window.screen().geometry()
        self.assertEqual(window.panel_boundary.inset(window.screen()), 40)
        window.panel_boundary.override = 10000
        self.assertEqual(window.panel_boundary.inset(window.screen()), area.height() - 142)
        window.hide()
        window.deleteLater()

    def test_bad_reply_keeps_last_good_panel_boundary(self):
        import contextlib
        import io
        import json
        from hyal import Hyal
        from PySide6.QtDBus import QDBusMessage
        window = Hyal(0)
        monitor = window.panel_boundary
        request = QDBusMessage.createMethodCall('org.kde.plasmashell', '/PlasmaShell',
                                               'org.kde.PlasmaShell', 'evaluateScript')
        rows = [dict(height=40, length=1920, lengthMode='fill', offset=0,
                     alignment='center', floating=False)]
        monitor._read_reply(request.createReply(json.dumps(rows)), 'DP-1')
        self.assertEqual(monitor.rows['DP-1'], rows)
        with contextlib.redirect_stderr(io.StringIO()) as error:
            monitor._read_reply(request.createErrorReply('org.freedesktop.DBus.Error.AccessDenied',
                                                        'blocked'), 'DP-1')
            monitor._read_reply(request.createReply('not JSON'), 'DP-1')
        self.assertEqual(monitor.rows['DP-1'], rows)
        self.assertIn('--bottom-panel-inset', error.getvalue())
        self.assertEqual(error.getvalue().count('Hya:'), 1)
        window.deleteLater()
