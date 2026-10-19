"""Capture the actual Qt studio UI offscreen for review.
Run: QT_QPA_PLATFORM=offscreen python tools/render_expression_studio.py
"""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import QApplication, QMenu
from appearance import Appearance
from personality import ExpressionController
from hyal import Hya

app = QApplication.instance() or QApplication([])
app.setApplicationDisplayName('Hya')
with tempfile.TemporaryDirectory() as directory:
    appearance = Appearance(QSettings(str(Path(directory)/'appearance.ini'),QSettings.Format.IniFormat))
    appearance.set_idle_enabled(False)
    controller = ExpressionController(enabled=False,clock=lambda:1000)
    window = Hya(0,appearance=appearance,personality=controller)
    window.timer.stop()
    window.start = 1000
    with patch('hyal.time.monotonic',return_value=1001.1):
        window.play_expression('sneeze')
        window.show_expression_studio()
        window.tick()
        app.processEvents()
        dialog = window._studio_dialog.grab().toImage()
        root = QMenu()
        window.add_expression_menu(root)
        menu = root.actions()[0].menu()
        menu.ensurePolished()
        menu.resize(menu.sizeHint())
        menu_image = menu.grab().toImage()
        canvas = QImage(dialog.width()+menu_image.width()+60,max(dialog.height(),menu_image.height())+40,
                        QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(QColor('#1e293c'))
        p = QPainter(canvas)
        p.drawImage(20,20,menu_image)
        p.drawImage(menu_image.width()+40,20,dialog)
        p.end()
        output = ROOT/'previews'/'expression-studio.png'
        canvas.save(str(output))
    window._studio_dialog.close()
    window.hide()
    window.deleteLater()
    app.processEvents()
print(output)
