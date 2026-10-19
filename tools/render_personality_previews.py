"""Native QPainter previews; no external image assets or image libraries.
Run: QT_QPA_PLATFORM=offscreen python tools/render_personality_previews.py
"""
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QColor, QFont
from appearance import PRESETS, CrystalPalette
from personality import Personality, Pose
from hyal import paint_hyal, paint_edge

app = QApplication.instance() or QApplication([])
output = ROOT / 'previews'
(output / 'colors').mkdir(parents=True, exist_ok=True)
(output / 'expressions').mkdir(exist_ok=True)


def character(palette=None, pose=None, side='normal'):
    image = QImage(142,142,QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    p = QPainter(image)
    if side == 'normal':
        paint_hyal(p,.8,palette,pose)
    else:
        paint_edge(p,.8,side,1,1,palette,pose)
    p.end()
    return image


def sheet(entries, columns, destination):
    rows = (len(entries) + columns - 1) // columns
    image = QImage(columns*190,rows*195,QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor('#1e293c'))
    p = QPainter(image)
    p.setFont(QFont('Sans',10))
    p.setPen(QColor('#e4efff'))
    for index,(label,frame) in enumerate(entries):
        x,y = (index % columns)*190, (index//columns)*195
        p.drawText(x+15,y+23,label)
        p.drawImage(x+24,y+36,frame)
    p.end()
    image.save(str(output/destination))


colors = []
for name,color in PRESETS.items():
    frame = character(CrystalPalette(None if name == 'Sapphire' else color))
    frame.save(str(output/'colors'/f'{name.lower().replace(" ","-")}.png'))
    colors.append((name,frame))
sheet(colors,4,'crystal-colors.png')

actor = Personality(clock=lambda:0,rng=random.Random(4))
expressions = [('Neutral',Pose())]
for label,state,elapsed in [('Curious left','curious',1.4),('Curious right','curious',1.4),
                            ('Curious up','curious',1.4),('Thinking','thinking',1.5),
                            ('Yawning','yawning',1),('Dozing','dozing',1.7),
                            ('Sleeping','sleeping',1),('Sniffle','sniffle',.65),
                            ('Sneeze','sneeze',.24),('Surprised','rebound',.4)]:
    actor.start(state,0)
    if label.startswith('Curious'):
        actor.direction = {'Curious left':(-4,0),'Curious right':(4,0),'Curious up':(0,-3)}[label]
    expressions.append((label,actor.sample(elapsed)))
frames = []
for label,pose in expressions:
    frame = character(pose=pose)
    frame.save(str(output/'expressions'/f'{label.lower().replace(" ","-")}.png'))
    frames.append((label,frame))
sheet(frames,4,'facial-expressions.png')

oriented = []
for label,pose in expressions:
    if label in ('Neutral','Thinking','Sleeping','Sneeze'):
        for side in ('normal','bottom','left','right'):
            oriented.append((f'{label} / {side}',character(CrystalPalette(PRESETS['Amethyst']),pose,side)))
sheet(oriented,4,'living-orientations.png')
print('Created crystal-colors.png, facial-expressions.png, living-orientations.png in', output)
