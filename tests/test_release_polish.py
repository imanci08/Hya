"""Rendered/geometry checks for the intentionally small v0.9.1 polish."""
from pathlib import Path
import unittest
from unittest.mock import patch,Mock
from PySide6.QtCore import QPoint,QRect,Qt
from PySide6.QtGui import QImage,QPainter,QColor
from PySide6.QtWidgets import QApplication
from chat_window import ChatWindow
from chat_widgets import DockedCharacter
from glass_wordmark import GlassWordmark
from glass_effects import request_blur
from conversation_store import ConversationStore
from appearance import Appearance
from PySide6.QtCore import QSettings
from test_hyal import app
from test_desktop_tools import stop_window
import test_local_ai as fixtures


def alpha_bounds(image):
    xs=[];ys=[]
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x,y).alpha()>100:xs.append(x);ys.append(y)
    return QRect(min(xs),min(ys),max(xs)-min(xs)+1,max(ys)-min(ys)+1)


class PolishTests(unittest.TestCase):
    setUp=fixtures.LocalAI.setUp

    def chat(self,name='polish'):
        owner=fixtures.QWidgetOwner()
        owner.appearance=Appearance(QSettings(str(Path(self.temp.name)/(name+'.ini')),QSettings.IniFormat))
        window=ChatWindow(owner,self.settings,ConversationStore(Path(self.temp.name)/(name+'.sqlite3')),self.client)
        self.addCleanup(lambda:stop_window(self,window))
        app.processEvents();self.manager.calls[-1][2].done(b'{"models":[{"name":"tiny:latest"}]}')
        return window

    def geometry(self,w):
        return {name:getattr(w,name).geometry() for name in ('header','character','status','scroll','input','expand_button','close_button')}

    def test_enlargement_keeps_header_slot_messages_input_and_dimensions(self):
        with patch.object(DockedCharacter,'VISUAL_SCALE',1),patch.object(GlassWordmark,'VISUAL_SCALE',1):
            w=self.chat('baseline');w.show_quick();app.processEvents()
            compact=self.geometry(w);quick=w.size();w.show_workspace();app.processEvents()
            expanded=self.geometry(w);workspace=w.size()
        # Same widgets/same layout; only the painted canvas and cached lettering grow.
        w.show_quick();w.character._sync_canvas();w.title.invalidate();app.processEvents()
        self.assertEqual(w.size(),quick);self.assertEqual(self.geometry(w),compact)
        self.assertEqual(w.character._canvas.width(),round(w.character.width()*1.25))
        w.show_workspace();w.character._sync_canvas();app.processEvents()
        self.assertEqual(w.size(),workspace);self.assertEqual(self.geometry(w),expanded)

    def test_rendered_character_bounds_clear_other_controls_and_canvas_edges(self):
        w=self.chat();w.show_quick();app.processEvents()
        for expanded in (False,True):
            if expanded:w.show_workspace();app.processEvents()
            canvas=w.character._canvas
            image=QImage(canvas.size(),QImage.Format_ARGB32_Premultiplied);image.fill(Qt.transparent)
            painter=QPainter(image);w.character.paint_character(painter,canvas.size());painter.end()
            bounds=alpha_bounds(image)
            self.assertGreater(bounds.left(),0);self.assertLess(bounds.right(),image.width()-1)
            self.assertGreater(bounds.top(),0);self.assertLess(bounds.bottom(),image.height()-1)
            painted=bounds.translated(canvas.pos())
            for widget in (w.header,w.status,w.workspace_controls,w.scroll,w.input):
                if widget.isVisible() and widget is not w.header:
                    self.assertFalse(painted.intersects(widget.geometry()),(painted,widget.geometry()))
            center=canvas.geometry().center();slot=w.character.geometry().center()
            self.assertLessEqual(abs(center.x()-slot.x()),1);self.assertLessEqual(abs(center.y()-slot.y()),1)

    def test_wordmark_descender_is_not_clipped_and_live_palette_remains(self):
        w=self.chat();w.show_quick();app.processEvents();title=w.title
        title._prepare_image();bounds=alpha_bounds(title._image.toImage())
        self.assertLess(bounds.bottom(),title._image.height()-1)
        self.assertTrue(title._overflow.isVisible())
        self.assertGreater(bounds.width(),50)
        self.assertLess(title.geometry().right()+20,w.expand_button.geometry().left())
        w.owner.appearance.select('Ruby');title._prepare_image()
        self.assertEqual(title.tint.name(),'#c73558')

    def test_effective_glass_alpha_reduced_without_fading_controls(self):
        w=self.chat();w.show_quick();app.processEvents()
        image=w.grab().toImage()
        # Empty main pane: no stacked opaque palette/window background underneath.
        alpha=image.pixelColor(10,100).alpha()
        self.assertGreaterEqual(alpha, 175)
        self.assertLessEqual(alpha, 185)
        self.assertTrue(.70 <= alpha/255 <= .75)
        # Conversation panel uses a more opaque background for readability.
        self.assertIn(
            'background:rgba(20,30,55,242)',
            w.styleSheet().replace(' ', '')
        )
        button=w.close_button.mapTo(w,QPoint(w.close_button.width()//2,5))
        self.assertGreater(image.pixelColor(button).alpha(),alpha)
        for bg in (QColor('#fafafa'),QColor('#111522')):
            result=QImage(image.size(),QImage.Format_ARGB32_Premultiplied);result.fill(bg)
            p=QPainter(result);p.drawImage(0,0,image);p.end()
            sample=result.pixelColor(10,100)
            def luminance(color):
                values=[v/255 for v in (color.red(),color.green(),color.blue())]
                values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
                return sum(v*k for v,k in zip(values,(.2126,.7152,.0722)))
            contrast=(luminance(QColor('#eef5ff'))+.05)/(luminance(sample)+.05)
            self.assertGreaterEqual(contrast,4.5)

    def test_blur_is_optional_and_uses_only_the_native_public_bridge(self):
        w=self.chat();w.show_quick();app.processEvents()
        self.assertFalse(request_blur(w))  # No native blur on offscreen.
        native=Mock()
        with patch('glass_effects.QApplication.platformName',return_value='wayland'),patch('glass_effects.asset') as path,patch('glass_effects._bridge',native):
            path.return_value.is_file.return_value=True
            self.assertTrue(request_blur(w));native.hya_blur.assert_called_once()
            args=native.hya_blur.call_args.args
            self.assertEqual(args[1:],(w.width(),w.height()))
