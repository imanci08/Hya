"""Run with QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v."""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtTest import QTest
from hyal import QApplication, Hyal, PeekArtwork, qmlRegisterType

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)
qmlRegisterType(PeekArtwork, 'Hyal', 1, 0, 'PeekArtwork')


class EdgeTests(unittest.TestCase):
    def setUp(self):
        self.hyal = Hyal(0)
        self.hyal.show()
        app.processEvents()

    def tearDown(self):
        self.hyal.restore()
        self.hyal.hide()
        self.hyal.timer.stop()
        self.hyal.deleteLater()
        app.processEvents()

    def test_original_artwork_preserved(self):
        import runpy
        from PySide6.QtGui import QImage, QPainter
        from appearance import CrystalPalette
        from personality import Pose
        from hyal import paint_hyal, paint_edge
        old = runpy.run_path('tests/fixtures/hyal-v0.4.2.py')
        for side in ('normal', 'bottom', 'left', 'right'):
            for t in (0, 1.5, 4.15):
                for hover in (0, 1):
                    frames = []
                    for previous in (True, False):
                        image = QImage(142, 142, QImage.Format.Format_ARGB32_Premultiplied)
                        image.fill(0)
                        painter = QPainter(image)
                        options = {} if previous else dict(palette=CrystalPalette(), pose=Pose())
                        if side == 'normal':
                            (old['paint_hyal'] if previous else paint_hyal)(painter, t, **options)
                        else:
                            (old['paint_edge'] if previous else paint_edge)(painter, t, side, hover, 1, **options)
                        painter.end()
                        frames.append(image)
                    self.assertEqual(*frames)

    def test_qml_lifecycle(self):
        # Exercises the real installed QML module without claiming compositor placement.
        with patch.object(QApplication, 'platformName', return_value='wayland'):
            for side in ("bottom", "left", "right"):
                self.hyal.hide_at_edge(side)
                self.assertIsNotNone(self.hyal.edge_window)
                self.assertTrue(self.hyal._normal_parked)
                app.processEvents()
                QTest.qWait(750)
                self.assertLess(self.hyal.peek, .02)
                self.assertEqual(self.hyal.edge_phase, "hidden")
                # Enter alone (including a late synthetic enter) must not undo tucking.
                self.hyal.edge_bridge.hover(True)
                self.assertEqual(self.hyal.peek_target, 0)
                from PySide6.QtCore import QPoint
                point = QPoint(71, 120) if side == 'bottom' else QPoint(20 if side == 'left' else 120, 78)
                QTest.mouseMove(self.hyal.edge_window, point)
                QTest.mouseMove(self.hyal.edge_window, point + QPoint(1, 1))
                QTest.qWait(700)
                self.assertGreater(self.hyal.peek, .98)
                QTest.mouseMove(self.hyal.edge_window, QPoint(-10, -10))
                QTest.qWait(700)
                self.assertLess(self.hyal.peek, .02)
                self.hyal.edge_bridge.restore()
                self.assertEqual(self.hyal.edge_phase, "restoring")
                QTest.qWait(750)
                self.assertTrue(self.hyal.isVisible())
                self.assertFalse(self.hyal.hidden_at_edge)
                self.assertIsNone(self.hyal.edge_window)
                app.processEvents()

    def test_original_character_transforms_and_transparency(self):
        from PySide6.QtGui import QImage, QPainter
        from hyal import paint_edge, paint_hyal
        def render(draw):
            image = QImage(142, 142, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)
            painter = QPainter(image)
            draw(painter)
            painter.end()
            return image
        for side, angle in (('bottom', 0), ('left', 90), ('right', -90)):
            for curiosity, offset in ((0, 59 if side == 'bottom' else 94),
                                      (1, 30 if side == 'bottom' else 55)):
                for t in (0, 2.4, 4.15):
                    actual = render(lambda p: paint_edge(p, t, side, curiosity, 1))
                    def expected(p):
                        # Independent full-character transform; no replacement art or fade.
                        cy = 78
                        p.translate(71 + (offset if side == 'right' else -offset if side == 'left' else 0),
                                    cy + (offset if side == 'bottom' else 0))
                        p.rotate(angle)
                        p.translate(-71, -cy)
                        paint_hyal(p, t)
                    self.assertEqual(actual, render(expected))
                    self.assertTrue(any(actual.pixelColor(x,y).alpha() > 200
                                        for y in range(142) for x in range(142)))
                    if side == 'bottom':
                        self.assertEqual(actual.pixelColor(0,0).alpha(), 0)
                        self.assertTrue(all(actual.pixelColor(x,y).alpha() == 0
                                            for y in range(35) for x in range(142)))
            # Both transitions meet the original upright image without a jump.
            self.assertEqual(render(lambda p: paint_edge(p, 0, side, 0, 0)),
                             render(lambda p: paint_hyal(p, 0)))

    def test_initial_retreat_ignores_hover_until_fresh_motion(self):
        for platform in ('wayland', 'xcb'):
            for side in ('bottom', 'left', 'right'):
                self.hyal.timer.stop()
                # Simulate stale hover values left by the last interaction.
                self.hyal.peek = self.hyal.peek_target = 1
                self.hyal._edge_hover_armed = True
                with patch.object(QApplication, 'platformName', return_value=platform):
                    self.hyal.hide_at_edge(side)
                started = self.hyal.transition_start
                self.hyal.set_edge_hover(True)
                self.hyal.edge_pointer_moved(100, 100, True)
                with patch('hyal.time.monotonic', return_value=started + .3):
                    self.hyal.tick()
                self.assertGreater(self.hyal.conceal, 0)
                self.assertLess(self.hyal.conceal, 1)
                self.assertEqual(self.hyal.peek_target, 0)
                with patch('hyal.time.monotonic', return_value=started + .8):
                    self.hyal.tick()
                self.assertEqual(self.hyal.edge_phase, 'hidden')
                self.assertEqual(self.hyal.conceal, 1)
                self.assertEqual(self.hyal.peek, 0)
                # Stationary cursor reports and repeated enters must stay tucked.
                self.hyal.set_edge_hover(True)
                self.hyal.edge_pointer_moved(100, 100, True)
                self.assertEqual(self.hyal.peek_target, 0)
                self.hyal.edge_pointer_moved(101, 100, True)
                self.assertEqual(self.hyal.peek_target, 1)
                self.hyal.tick()
                extended = self.hyal.peek
                self.assertGreater(extended, 0)
                self.hyal.set_edge_hover(False)
                self.hyal.tick()
                self.assertLess(self.hyal.peek, extended)
                self.hyal.restore()
                app.processEvents()

    def test_breathing_direction_from_rendered_face_pixels(self):
        import math
        from PySide6.QtGui import QImage, QPainter
        from hyal import paint_edge, paint_hyal
        times = (math.pi / (2 * 1.8), 3 * math.pi / (2 * 1.8))
        def face_center(side, t):
            # Render unclipped so edge concealment cannot bias the measurements.
            image = QImage(420, 420, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)
            painter = QPainter(image)
            painter.translate(130, 130)
            if side == 'normal':
                paint_hyal(painter, t)
            else:
                paint_edge(painter, t, side, 0, 1)
            painter.end()
            pixels = [(x,y) for y in range(420) for x in range(420)
                      if image.pixelColor(x,y).alpha() > 250
                      and min(image.pixelColor(x,y).getRgb()[:3]) > 248]
            self.assertTrue(pixels)
            return tuple(sum(point[axis] for point in pixels) / len(pixels) for axis in (0,1))
        for side in ('normal', 'bottom', 'left', 'right'):
            a, b = [face_center(side, t) for t in times]
            dx, dy = a[0] - b[0], a[1] - b[1]
            if side in ('normal', 'bottom'):
                self.assertAlmostEqual(dx, 0, delta=.1)
                self.assertAlmostEqual(dy, 5, delta=.1)
            else:
                self.assertAlmostEqual(dy, 0, delta=.1)
                self.assertAlmostEqual(dx, 5 if side == 'right' else -5, delta=.1)

    def test_breathing_direction_from_rendered_diamond_pixels(self):
        import math
        from PySide6.QtGui import QImage, QPainter
        from hyal import paint_edge, paint_hyal
        for side, cx, cy in (('normal', 201, 147), ('bottom', 201, 206),
                             ('right', 234, 208), ('left', 168, 208)):
            centers = []
            for t in (math.pi / (2 * 1.8), 3 * math.pi / (2 * 1.8)):
                image = QImage(420, 420, QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(0)
                painter = QPainter(image)
                painter.translate(130, 130)
                if side == 'normal':
                    paint_hyal(painter, t)
                else:
                    paint_edge(painter, t, side, 0, 1)
                painter.end()
                pixels = []
                for y in range(cy - 14, cy + 15):
                    for x in range(cx - 14, cx + 15):
                        color = image.pixelColor(x, y)
                        if (color.alpha() > 200 and 150 < color.red() < 190
                                and color.green() > 215 and color.blue() > 240):
                            pixels.append((x, y))
                self.assertTrue(pixels)
                centers.append(tuple(sum(p[axis] for p in pixels) / len(pixels) for axis in (0,1)))
            dx, dy = (centers[0][axis] - centers[1][axis] for axis in (0,1))
            # Diamond retains its own original bob frequency/amplitude, on the
            # same local axis as the body, with no sideways-mode vertical drift.
            if side in ('normal', 'bottom'):
                self.assertAlmostEqual(dx, 0, delta=.15)
                self.assertGreater(dy, 1.5)
            else:
                self.assertAlmostEqual(dy, 0, delta=.15)
                self.assertGreater(dx if side == 'right' else -dx, 1.5)

    def test_neutral_edge_geometry_matches_v041_images(self):
        import runpy
        from PySide6.QtGui import QImage, QPainter
        from hyal import paint_edge
        previous = runpy.run_path('tests/fixtures/hyal-v0.4.1.py')['paint_edge']
        for side in ('bottom', 'left', 'right'):
            for curiosity in (0, 1):
                for conceal in (0, .5, 1):
                    frames = []
                    for draw in (previous, paint_edge):
                        image = QImage(142, 142, QImage.Format.Format_ARGB32_Premultiplied)
                        image.fill(0)
                        painter = QPainter(image)
                        draw(painter, 0, side, curiosity, conceal)
                        painter.end()
                        frames.append(image)
                    self.assertEqual(*frames)

    def test_rendered_diamonds_and_faces_point_inward(self):
        from PySide6.QtGui import QImage, QPainter
        from hyal import paint_edge
        for side, diamond_x, eye_x in (('right', 104, 122), ('left', 38, 20)):
            for curiosity in (0, 1):
                image = QImage(142, 142, QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(0)
                painter = QPainter(image)
                paint_edge(painter, 0, side, curiosity, 1)
                painter.end()
                # A visible cyan diamond INWARD of the body is the visual requirement.
                # The old upside-down transforms leave these pixels transparent.
                x = diamond_x + ((-39 if side == 'right' else 39) if curiosity else 0)
                color = image.pixelColor(x, 78)
                self.assertGreater(color.alpha(), 200)
                self.assertGreater(color.green(), 210)
                self.assertGreater(color.blue(), 240)
                self.assertLess(color.red(), 200)
                if curiosity:
                    for y in (65, 91):
                        eye = image.pixelColor(eye_x, y)
                        self.assertGreater(min(eye.red(), eye.green(), eye.blue()), 245)

    def test_panel_strip_stays_transparent_and_click_through(self):
        from PySide6.QtCore import QPoint
        self.hyal.panel_boundary.override = 40
        with patch.object(QApplication, 'platformName', return_value='wayland'):
            self.hyal.hide_at_edge('bottom')
            app.processEvents()
            edge = self.hyal.edge_window
            self.assertEqual(edge.height(), 182)
            self.assertEqual(edge.findChild(__import__('hyal').QObject, 'artwork').height(), 142)
            for curiosity in (0, 1):
                self.hyal.edge_phase = "hidden"
                self.hyal.conceal = 1
                self.hyal.peek = self.hyal.peek_target = curiosity
                self.hyal.tick()
                app.processEvents()
                for y in range(142, 182):
                    self.assertFalse(edge.mask().contains(QPoint(71, y)))
                frame = edge.grabWindow()
                self.assertFalse(frame.isNull())
                scale = frame.devicePixelRatio()
                self.assertTrue(all(frame.pixelColor(x,y).alpha() == 0
                                    for y in range(int(142 * scale), frame.height())
                                    for x in range(frame.width())))
            # Updates move the clipping boundary, preserving the physical anchor.
            self.hyal.panel_boundary.override = 56
            self.hyal.panel_boundary.changed.emit()
            app.processEvents()
            self.assertEqual(edge.height(), 198)

    def test_fallback_geometry_and_restore(self):
        for side in ('bottom', 'left', 'right'):
            saved = self.hyal.pos()
            with patch.object(QApplication, 'platformName', return_value='xcb'):
                self.hyal.hide_at_edge(side)
            area = self.hyal.screen().geometry()
            if side == 'bottom':
                self.assertEqual(self.hyal.y() + self.hyal.height(), area.y() + area.height())
            elif side == 'left':
                self.assertEqual(self.hyal.x(), area.x())
            else:
                self.assertEqual(self.hyal.x() + self.hyal.width(), area.x() + area.width())
            self.hyal.restore()
            self.assertEqual(self.hyal.pos(), saved)

    def test_masks_and_margins(self):
        from hyal import PeekBridge
        from PySide6.QtCore import QRect, QPoint
        class Output:
            def geometry(self):
                return QRect(-1920, -200, 1920, 1080)
        bridge = PeekBridge(self.hyal, Output())
        self.hyal.saved_position = QPoint(-1700, 100)
        for side in ('bottom', 'left', 'right'):
            self.hyal.edge_side = side
            margins = bridge.edgeMargins
            self.assertEqual(margins.left(), 0)
            self.assertEqual(margins.right(), 24 if side == 'bottom' else 0)
            self.assertEqual(margins.top(), 0 if side == 'bottom' else 300)
            self.hyal.edge_phase = 'hidden'
            self.hyal.conceal = 1
            self.hyal.peek = 0
            rest = self.hyal.edge_input_region()
            self.hyal.peek = 1
            hover = self.hyal.edge_input_region()
            self.assertTrue(hover.contains(rest.boundingRect()))
            self.assertFalse(hover.contains(QPoint(71, 0)))
        self.hyal.edge_side = 'bottom'
        self.hyal.saved_position = QPoint(5000, 5000)
        self.assertEqual(bridge.edgeMargins.right(), 24)
        self.hyal.bottom_horizontal_inset = 10000
        self.assertEqual(bridge.edgeMargins.right(), 1920 - 142)


if __name__ == '__main__':
    unittest.main()
