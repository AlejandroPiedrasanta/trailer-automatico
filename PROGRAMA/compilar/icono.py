# -*- coding: utf-8 -*-
"""Dibuja el icono del programa (engranaje de bronce + play esmeralda) y lo guarda como .ico y .png."""
import sys
import math
from PySide6.QtCore import Qt, QPointF, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient, \
    QLinearGradient


def dibujar(t):
    img = QImage(t, t, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    c = QPointF(t / 2.0, t / 2.0)
    R = t / 2.0 - 1
    dientes, ro, ri = 16, R, R * 0.84
    camino = QPainterPath()
    paso = 2 * math.pi / dientes
    for i in range(dientes):
        for frac, rad in ((0.0, ri), (0.2, ro), (0.5, ro), (0.7, ri)):
            a = i * paso + frac * paso
            q = QPointF(c.x() + math.cos(a) * rad, c.y() + math.sin(a) * rad)
            camino.moveTo(q) if (i == 0 and frac == 0.0) else camino.lineTo(q)
    camino.closeSubpath()
    g = QLinearGradient(0, 0, t, t)
    g.setColorAt(0, QColor("#EBCB8F"))
    g.setColorAt(0.5, QColor("#C9A267"))
    g.setColorAt(1, QColor("#6E4C24"))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawPath(camino)
    rd = R * 0.66
    d = QRadialGradient(QPointF(c.x() - rd * 0.3, c.y() - rd * 0.35), rd * 1.4)
    d.setColorAt(0, QColor("#2FD893"))
    d.setColorAt(0.5, QColor("#12804F"))
    d.setColorAt(1, QColor("#06301F"))
    p.setBrush(d)
    p.setPen(QPen(QColor("#EBCB8F"), max(1.0, t / 64.0)))
    p.drawEllipse(c, rd, rd)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#E9FFF5"))
    p.drawPolygon(QPolygonF([QPointF(c.x() - rd * 0.32, c.y() - rd * 0.45), QPointF(c.x() + rd * 0.5, c.y()),
                             QPointF(c.x() - rd * 0.32, c.y() + rd * 0.45)]))
    p.end()
    return img


def guardar(ruta_ico):
    from PIL import Image
    import io
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    imgs = []
    for t in (256, 128, 64, 48, 32, 16):
        buf = QByteArray()
        b = QBuffer(buf)
        b.open(QIODevice.WriteOnly)
        dibujar(t).save(b, "PNG")
        imgs.append(Image.open(io.BytesIO(bytes(buf))).convert("RGBA"))
    imgs[0].save(ruta_ico, format="ICO", sizes=[(i.width, i.height) for i in imgs])
    imgs[0].save(ruta_ico.replace(".ico", ".png"))


if __name__ == "__main__":
    guardar(sys.argv[1])
