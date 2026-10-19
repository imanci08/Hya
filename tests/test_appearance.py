from pathlib import Path
import tempfile
import unittest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor
from appearance import Appearance, CrystalPalette, PRESETS
from test_hyal import app


class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'appearance.ini'
        self.appearance = self.load()

    def tearDown(self):
        self.temp.cleanup()

    def load(self):
        return Appearance(QSettings(str(self.path), QSettings.Format.IniFormat))

    def test_presets_custom_idle_and_reset_persist(self):
        self.assertEqual(self.appearance.preset, 'Sapphire')
        self.assertFalse(self.path.exists())
        for preset in PRESETS:
            self.appearance.select(preset)
            self.assertEqual(self.load().preset, preset)
        self.appearance.select('Custom', '#E6507A')
        self.appearance.set_idle_enabled(False)
        restored = self.load()
        self.assertEqual((restored.preset, restored.color, restored.idle_enabled), ('Custom', '#e6507a', False))
        restored.select('Sapphire')
        restored = self.load()
        self.assertEqual(restored.preset, 'Sapphire')
        self.assertFalse(restored.idle_enabled)  # color reset does not reset other settings

    def test_settings_survive_a_fresh_process(self):
        import subprocess
        import sys
        self.appearance.select('Custom', '#1da783')
        self.appearance.set_idle_enabled(False)
        code = """from PySide6.QtCore import QCoreApplication, QSettings
from appearance import Appearance
import sys, json
app=QCoreApplication([])
a=Appearance(QSettings(sys.argv[1], QSettings.Format.IniFormat))
print(json.dumps([a.preset,a.color,a.idle_enabled]))
"""
        result = subprocess.run([sys.executable, '-c', code, str(self.path)],
                                capture_output=True, text=True, check=True)
        import json
        self.assertEqual(json.loads(result.stdout), ['Custom', '#1da783', False])

    def test_palette_preserves_alpha_depth_and_caches(self):
        for hex_color in (*PRESETS.values(), '#000000', '#ffffff', '#818181'):
            palette = CrystalPalette(hex_color)
            bright = palette.color(130,225,255,235)
            dark = palette.color(64,45,174,240)
            self.assertEqual(bright.alpha(), 235)
            self.assertEqual(dark.alpha(), 240)
            self.assertGreater(bright.value(), dark.value())
            self.assertIs(bright, palette.color(130,225,255,235))
        original = CrystalPalette()
        self.assertEqual(original.color(64,45,174,240), QColor(64,45,174,240))

    def test_white_custom_crystal_preserves_face_contrast(self):
        from PySide6.QtGui import QImage, QPainter
        from hyal import paint_hyal
        image = QImage(142,142,QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        paint_hyal(painter,0,CrystalPalette('#ffffff'))
        painter.end()
        self.assertEqual(image.pixelColor(58,74),QColor('white'))
        self.assertLess(max(image.pixelColor(64,74).getRgb()[:3]),240)

    def test_invalid_saved_values_fall_back(self):
        self.path.write_text('[crystal]\npreset=Custom\ncustom=not-a-color\n')
        restored = self.load()
        self.assertEqual(restored.preset, 'Sapphire')
        with self.assertRaises(ValueError):
            restored.select('Custom', 'transparent')
        with self.assertRaises(ValueError):
            restored.select('missing')

    def test_picker_previews_cancel_and_accept_without_leaking_settings(self):
        from hyal import Hyal
        window = Hyal(0, appearance=self.appearance)
        window.choose_custom_color()
        dialog = window._color_dialog
        dialog.setCurrentColor(QColor('#db507a'))
        self.assertEqual(self.appearance.color, '#db507a')
        self.assertFalse(self.path.exists())
        dialog.reject()
        app.processEvents()
        self.assertEqual(self.appearance.preset, 'Sapphire')
        window.choose_custom_color()
        window._color_dialog.setCurrentColor(QColor('#32aa77'))
        window._color_dialog.accept()
        app.processEvents()
        self.assertEqual(self.load().color, '#32aa77')
        window.timer.stop()
        window.deleteLater()
        app.processEvents()

    def test_menu_contains_presets_and_persisted_idle_toggle(self):
        from hyal import Hyal, QMenu
        window = Hyal(0, appearance=self.appearance)
        menu = QMenu()
        window.add_appearance_menu(menu)
        appearance_menu = menu.actions()[0].menu()
        colors = appearance_menu.actions()[0].menu()
        self.assertEqual([a.text() for a in colors.actions()[:8]], list(PRESETS))
        colors.actions()[3].trigger()
        self.assertEqual(self.load().preset, 'Emerald')
        idle = appearance_menu.actions()[1]
        idle.trigger()
        self.assertFalse(self.load().idle_enabled)
        self.assertFalse(window.personality.enabled)
        window.timer.stop()
        window.deleteLater()
