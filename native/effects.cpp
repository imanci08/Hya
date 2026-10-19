#include <KWindowEffects>
#include <QWindow>
#include <QPainterPath>
#include <QRegion>

// A narrow C boundary avoids Python depending on mangled C++ symbols/private Qt.
extern "C" void hya_blur(void *handle, int width, int height)
{
    if (!handle || width <= 0 || height <= 0) return;
    QPainterPath outline;
    outline.addRoundedRect(QRectF(0, 0, width, height), 18, 18);
    KWindowEffects::enableBlurBehind(static_cast<QWindow *>(handle), true,
                                     QRegion(outline.toFillPolygon().toPolygon()));
}
