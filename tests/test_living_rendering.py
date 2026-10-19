import math
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, QPointF
from PySide6.QtGui import QImage, QPainter, QColor, QTransform
from appearance import Appearance, CrystalPalette, PRESETS
from personality import Personality
from hyal import Hyal, QApplication, paint_hyal, paint_edge
from test_hyal import app


def render(draw):
    image = QImage(142, 142, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    draw(painter)
    painter.end()
    return image


class LivingRenderingTests(unittest.TestCase):
    def test_all_colors_keep_white_faces_and_transparent_backgrounds(self):
        colors = []
        for value in PRESETS.values():
            image = render(lambda p: paint_hyal(p, 0, CrystalPalette(value)))
            self.assertEqual(image.pixelColor(58,74), QColor('white'))
            self.assertEqual(image.pixelColor(84,74), QColor('white'))
            self.assertEqual(image.pixelColor(0,0).alpha(), 0)
            colors.append(image.pixel(90,78))
        self.assertEqual(len(set(colors)), len(PRESETS))

    def test_every_expression_transforms_as_one_character_on_all_edges(self):
        actor = Personality(clock=lambda: 0)
        for state in ('curious','thinking','yawning','dozing','sleeping','sniffle','sneeze','rebound'):
            actor.start(state, 0)
            pose = actor.sample(actor.DURATIONS.get(state, 1) / 2)
            palette = CrystalPalette(PRESETS['Amethyst'])
            for side, angle, dx, dy in (('bottom',0,0,30), ('left',90,-55,0), ('right',-90,55,0)):
                actual = render(lambda p: paint_edge(p, .5, side, 1, 1, palette, pose))
                def expected(p):
                    p.translate(71+dx,78+dy)
                    p.rotate(angle)
                    p.translate(-71,-78)
                    paint_hyal(p,.5,palette,pose)
                self.assertEqual(actual, render(expected))
                self.assertTrue(any(actual.pixelColor(x,y).alpha() > 200
                                    for y in range(142) for x in range(142)))
                self.assertEqual(actual.pixelColor(0,0).alpha(), 0)

    def test_actual_qml_surface_uses_live_palette_and_sleep_pose(self):
        with tempfile.TemporaryDirectory() as directory:
            appearance = Appearance(QSettings(str(Path(directory)/'appearance.ini'), QSettings.Format.IniFormat))
            appearance.set_idle_enabled(False)
            window = Hyal(0, appearance=appearance)
            window.show()
            try:
                with patch.object(QApplication, 'platformName', return_value='wayland'):
                    for side in ('bottom','left','right'):
                        window.hide_at_edge(side)
                        window.timer.stop()
                        window.edge_phase = 'hidden'
                        window.conceal = 1
                        window.peek = window.peek_target = 1
                        window.tick()
                        app.processEvents()
                        appearance.select('Emerald')
                        window.tick()
                        app.processEvents()
                        frame = window.edge_window.grabWindow()
                        self.assertFalse(frame.isNull())
                        x,y = (71,108) if side == 'bottom' else (20,80) if side == 'left' else (120,80)
                        color = frame.pixelColor(x,y)
                        self.assertGreater(color.green(), color.red())
                        self.assertGreater(color.green(), color.blue())
                        appearance.set_idle_enabled(True)
                        window.personality.start('sleeping')
                        window.tick()
                        app.processEvents()
                        self.assertEqual(window.pose.mouth, 'sleep')
                        self.assertFalse(window.pose.blink)
                        asleep = window.edge_window.grabWindow()
                        self.assertNotEqual(frame, asleep)
                        # Fresh interaction wakes, without changing the edge's geometry.
                        geometry = window.edge_window.geometry()
                        window.edge_pointer_moved(100,100,True)
                        window.edge_pointer_moved(101,100,True)
                        self.assertEqual(window.personality.state, 'waking')
                        self.assertEqual(window.edge_window.geometry(), geometry)
                        window.restore()
                        app.processEvents()
                        appearance.set_idle_enabled(False)
            finally:
                window.restore()
                window.hide()
                window.timer.stop()
                window.deleteLater()
                app.processEvents()
