"""Generate raster previews; the panel in the contact sheet is simulated.
Run: QT_QPA_PLATFORM=offscreen python tools/render_previews.py
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QColor, QFont
from hyal import paint_edge

app = QApplication.instance() or QApplication([])
output = ROOT / 'previews'
output.mkdir(exist_ok=True)
canvas = QImage(960, 580, QImage.Format.Format_ARGB32_Premultiplied)
canvas.fill(QColor('#131a29'))
p = QPainter(canvas)
p.setFont(QFont('Sans', 11))
for row, curiosity in enumerate((0, 1)):
    for col, side in enumerate(('bottom', 'left', 'right')):
        inset = 40 if side == 'bottom' else 0
        image = QImage(142, 142 + inset, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        art = QPainter(image)
        art.setClipRect(0, 0, 142, 142)
        paint_edge(art, 0, side, curiosity, 1)
        art.end()
        state = 'hover' if curiosity else 'idle'
        image.save(str(output / f'{side}-{state}.png'))
        x, y = 10 + col * 320, 30 + row * 275
        p.setPen(QColor('#e5efff'))
        p.drawText(x, y - 9, f'{side.title()} — {state}')
        p.fillRect(x, y, 300, 240, QColor('#344760'))
        px = 80 if side == 'bottom' else 0 if side == 'left' else 158
        py = 58 if side == 'bottom' else 48
        p.drawImage(x + px, y + py, image)
        if side == 'bottom':
            p.fillRect(x, y + 200, 300, 40, QColor('#1b2940'))
            p.setPen(QColor('#94b4d9'))
            p.drawText(x + 8, y + 224, 'Simulated panel (40 logical px)')
p.end()
canvas.save(str(output / 'edge-peeks.png'))
print(output / 'edge-peeks.png')
