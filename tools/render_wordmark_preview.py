"""Actual cached Hya wordmark against light/dark surfaces; no AI/image assets."""
from pathlib import Path
import sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QWidget,QGridLayout,QLabel
from PySide6.QtCore import QSettings
from appearance import Appearance
from glass_wordmark import GlassWordmark
app=QApplication.instance() or QApplication([])
with tempfile.TemporaryDirectory() as tmp:
 panel=QWidget();grid=QGridLayout(panel);states=[]
 for row,color in enumerate(('Sapphire','Amethyst','Rose Quartz','Midnight','Custom')):
  label=QLabel(color);grid.addWidget(label,row,0)
  for col,bg in enumerate(('#253253','#edf5ff'),1):
   appearance=Appearance(QSettings(str(Path(tmp)/f'{row}-{col}.ini'),QSettings.IniFormat))
   appearance.select(color,'#ffffff' if color=='Custom' else None,persist=False);states.append(appearance)
   surface=QWidget();surface.setStyleSheet('background:'+bg)
   inner=QGridLayout(surface);title=GlassWordmark(appearance);title.setStyleSheet('font-size:25px;font-weight:600')
   inner.addWidget(title,0,0);grid.addWidget(surface,row,col)
 panel.resize(440,340);panel.show();app.processEvents()
 destination=Path(__file__).resolve().parents[1]/'previews'/'glass-wordmarks.png'
 panel.grab().save(str(destination));print(destination)
