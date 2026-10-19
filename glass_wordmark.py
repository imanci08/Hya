"""Cached, palette-derived lettering; no animation or graphics-effect pipeline."""
from PySide6.QtCore import Qt,QPointF,QPoint,QEvent,QRect
from PySide6.QtGui import QColor,QPixmap,QPainter,QPainterPath,QLinearGradient,QPen,QFontMetricsF,QRegion
from PySide6.QtWidgets import QLabel,QWidget


def mix(color,white):
    color=QColor(color)
    return QColor(*(round(channel+(255-channel)*white) for channel in (color.red(),color.green(),color.blue())))


class _WordmarkOverflow(QWidget):
    def __init__(self,title):
        super().__init__()
        self.title=title
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self,event):
        self.title._prepare_image()
        painter=QPainter(self);painter.drawPixmap(0,0,self.title._image);painter.end()


class GlassWordmark(QLabel):
    VISUAL_SCALE=1.28
    def __init__(self,appearance=None,parent=None):
        super().__init__('Hya',parent)
        self.appearance=appearance
        self.setObjectName('title')
        self.setAccessibleName('Hya')
        self._key=None;self._image=None
        self._overflow=_WordmarkOverflow(self)
        if appearance is not None:appearance.changed.connect(self.invalidate)

    def sizeHint(self):
        size=super().sizeHint()
        size.setWidth(round(size.width()*self.VISUAL_SCALE)+2)
        return size

    @property
    def tint(self):return QColor(self.appearance.color if self.appearance else '#2873eb')

    def invalidate(self):
        self._key=None;self.update();self._overflow.update()

    def event(self,event):
        result=super().event(event)
        if event.type() in (QEvent.ParentChange,QEvent.Move,QEvent.Resize,QEvent.Show,QEvent.Hide) and hasattr(self,'_overflow'):
            header=self.parentWidget()
            parent=header.parentWidget() if header else None
            if parent:
                if self._overflow.parentWidget() is not parent:self._overflow.setParent(parent)
                self._overflow.setGeometry(QRect(self.mapTo(parent,QPoint()),self.size()))
                self._overflow.resize(self.width(),self.height()+12)
                self._overflow.setMask(QRegion(0,self.height(),self.width(),12))
                self._overflow.setVisible(self.isVisible());self._overflow.raise_()
        return result

    def _prepare_image(self):
        key=(self.tint.name(),self.width(),self.height(),self.devicePixelRatioF(),self.font().toString())
        if self._key!=key:
            self._key=key
            dpr=self.devicePixelRatioF()
            self._image=QPixmap(round(self.width()*dpr),round((self.height()+12)*dpr))
            self._image.setDevicePixelRatio(dpr);self._image.fill(Qt.transparent)
            painter=QPainter(self._image);painter.setRenderHint(QPainter.Antialiasing)
            # Retain the original 25 px layout metrics and top/left anchor.
            font=self.font();font.setPixelSize(round(font.pixelSize()*self.VISUAL_SCALE))
            metrics=QFontMetricsF(self.font())
            baseline=(self.height()-metrics.height())/2+metrics.ascent()
            original=QPainterPath();original.addText(QPointF(0,baseline),self.font(),self.text())
            path=QPainterPath();path.addText(QPointF(0,baseline),font,self.text())
            path.translate(original.boundingRect().left()-path.boundingRect().left(),
                           original.boundingRect().top()-path.boundingRect().top())
            glow=mix(self.tint,.45)
            for width,alpha in ((4,12),(2.5,24)):
                glow.setAlpha(alpha);painter.strokePath(path,QPen(glow,width))
            # Dark edge gives light-background contrast without harsh bloom.
            painter.strokePath(path,QPen(QColor(18,25,54,195),1.5))
            gradient=QLinearGradient(0,path.boundingRect().top(),0,path.boundingRect().bottom())
            for stop,white,alpha in ((0,.93,240),(.38,.7,232),(.55,.44,220),(1,.68,232)):
                color=mix(self.tint,white);color.setAlpha(alpha);gradient.setColorAt(stop,color)
            painter.fillPath(path,gradient);painter.end()
    def paintEvent(self,event):
        self._prepare_image()
        painter=QPainter(self);painter.drawPixmap(0,0,self._image);painter.end()
