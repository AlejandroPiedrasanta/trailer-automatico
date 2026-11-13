# -*- coding: utf-8 -*-
"""Dibuja banner.jpg del instalador (1760 x 472, como el de CineCaptions): cielo esmeralda con rayos y motas, tarjetas de
vidrio con el lema y el sitio libre donde el instalador hace girar el astrolabio (centro 1385, 236)."""
import sys
import math
import random
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QGuiApplication, QImage, QPainter, QColor, QRadialGradient, QLinearGradient, QPen, QFont,
                           QPainterPath, QFontDatabase)

W, H = 1760, 472
AX, AY = 1385, 236


def fuente(familias, px, peso):
    hay = set(QFontDatabase.families())
    f = QFont(next((x for x in familias if x in hay), "Segoe UI"))
    f.setPixelSize(px)
    f.setWeight(peso)
    return f


def tarjeta(p, cx, cy, ancho, alto, giro, arriba, badge, color_badge, abajo, color_abajo, tam_badge=44):
    p.save()
    p.translate(cx, cy)
    p.rotate(giro)
    r = QRectF(-ancho / 2, -alto / 2, ancho, alto)
    camino = QPainterPath()
    camino.addRoundedRect(r, 22, 22)
    sombra = QPainterPath()
    sombra.addRoundedRect(r.translated(0, 10), 22, 22)
    p.fillPath(sombra, QColor(0, 0, 0, 90))
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, QColor(32, 52, 58, 225))
    g.setColorAt(1, QColor(12, 26, 30, 235))
    p.fillPath(camino, g)
    brillo = QLinearGradient(r.topLeft(), QPointF(r.left(), r.top() + alto * 0.5))
    brillo.setColorAt(0, QColor(255, 255, 255, 34))
    brillo.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillPath(camino, brillo)
    p.setPen(QPen(QColor(255, 255, 255, 60), 1.6))
    p.drawPath(camino)
    p.setPen(QColor(235, 245, 240))
    p.setFont(fuente(["Montserrat", "Segoe UI"], 26, QFont.Weight.Black))
    p.drawText(QRectF(-ancho / 2, -alto / 2 + 18, ancho, 34), Qt.AlignCenter, arriba)
    fb = fuente(["Montserrat", "Segoe UI"], tam_badge, QFont.Weight.Black)
    p.setFont(fb)
    anchob = p.fontMetrics().horizontalAdvance(badge) + 40
    rb = QRectF(-anchob / 2, -alto / 2 + 56, anchob, 62)
    cb = QPainterPath()
    cb.addRoundedRect(rb, 12, 12)
    p.fillPath(cb, QColor(color_badge))
    p.setPen(QColor(14, 18, 16))
    p.drawText(rb, Qt.AlignCenter, badge)
    p.setPen(QColor(color_abajo))
    p.setFont(fuente(["Montserrat", "Segoe UI"], 28, QFont.Weight.DemiBold))
    p.drawText(QRectF(-ancho / 2, -alto / 2 + 124, ancho, 40), Qt.AlignCenter, abajo)
    p.restore()


def dibujar():
    img = QImage(W, H, QImage.Format_RGB32)
    img.fill(QColor(5, 10, 14))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    g = QRadialGradient(QPointF(AX, AY), 980)
    g.setColorAt(0.0, QColor(46, 170, 120))
    g.setColorAt(0.35, QColor(22, 110, 82))
    g.setColorAt(0.7, QColor(10, 46, 40))
    g.setColorAt(1.0, QColor(5, 10, 14))
    p.fillRect(img.rect(), g)
    calido = QRadialGradient(QPointF(880, H + 60), 420)
    calido.setColorAt(0, QColor(196, 140, 52, 120))
    calido.setColorAt(1, QColor(196, 140, 52, 0))
    p.fillRect(img.rect(), calido)
    p.setPen(Qt.NoPen)
    for i in range(22):                                        # rayos
        a = math.radians(i * (360 / 22) + 7)
        rayo = QPainterPath()
        rayo.moveTo(AX, AY)
        largo = 1500
        rayo.lineTo(AX + math.cos(a - 0.025) * largo, AY + math.sin(a - 0.025) * largo)
        rayo.lineTo(AX + math.cos(a + 0.025) * largo, AY + math.sin(a + 0.025) * largo)
        rayo.closeSubpath()
        lg = QRadialGradient(QPointF(AX, AY), largo)
        lg.setColorAt(0, QColor(160, 255, 210, 46))
        lg.setColorAt(1, QColor(160, 255, 210, 0))
        p.fillPath(rayo, lg)
    # cinta de oro y cian (la linea de tiempo que se arma)
    for col, fase, amp in ((QColor(232, 196, 120, 170), 0.0, 26), (QColor(90, 220, 255, 150), 1.7, 20),
                           (QColor(124, 242, 192, 140), 3.1, 16)):
        camino = QPainterPath()
        camino.moveTo(690, 300)
        for x in range(690, W + 10, 8):
            env = min(1.0, (x - 690) / 260.0)
            camino.lineTo(x, 300 + env * amp * math.sin((x - 690) / 70.0 + fase))
        p.setPen(QPen(col, 2.0))
        p.setBrush(Qt.NoBrush)
        p.drawPath(camino)
    rnd = random.Random(11)
    p.setPen(Qt.NoPen)
    for _ in range(260):                                       # motas
        x = 650 + rnd.random() * (W - 650)
        y = rnd.random() * H
        r = rnd.choice((0.8, 1.2, 1.6, 2.2, 3.0))
        c = rnd.choice((QColor(255, 255, 255), QColor(150, 255, 200), QColor(90, 220, 255), QColor(255, 210, 120)))
        c.setAlpha(rnd.randint(70, 220))
        p.setBrush(c)
        p.drawEllipse(QPointF(x, y), r, r)
    for x, y, r in ((1050, 62, 7), (1385, 236, 0), (1500, 430, 6), (860, 238, 5)):     # destellos grandes
        if r:
            halo = QRadialGradient(QPointF(x, y), r * 4)
            halo.setColorAt(0, QColor(255, 255, 255, 230))
            halo.setColorAt(1, QColor(255, 255, 255, 0))
            p.setBrush(halo)
            p.drawEllipse(QPointF(x, y), r * 4, r * 4)
    tarjeta(p, 1088, 156, 258, 176, -4, "TU EVENTO", "EN TRÁILER", "#FFC24B", "1 · 3 · 15 · 30 min", "#B9A2FF", 36)
    tarjeta(p, 1635, 372, 206, 160, 4, "HAZLO EN", "1 CLIC", "#22C47E", "y listo", "#C9F5DF")
    # ficha de arriba
    chip = QRectF(1176, 24, 236, 34)
    cp = QPainterPath()
    cp.addRoundedRect(chip, 17, 17)
    p.fillPath(cp, QColor(10, 30, 40, 220))
    p.setPen(QPen(QColor(90, 220, 255, 150), 1.4))
    p.drawPath(cp)
    p.setPen(QColor(220, 240, 255))
    p.setFont(fuente(["Montserrat", "Segoe UI"], 15, QFont.Weight.Bold))
    p.drawText(chip, Qt.AlignCenter, "✨ XV · BODA · BAUTIZO")
    p.setFont(fuente(["Segoe UI Emoji", "Apple Color Emoji"], 44, QFont.Weight.Normal))
    for txt, x, y, rot in (("🎬", 900, 395, -10), ("💍", 1080, 420, 8), ("✨", 1548, 150, 0)):
        p.save()
        p.translate(x, y)
        p.rotate(rot)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(-40, -40, 80, 80), Qt.AlignCenter, txt)
        p.restore()
    p.end()
    return img


if __name__ == "__main__":
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    salida = sys.argv[1] if len(sys.argv) > 1 else "banner.jpg"
    dibujar().save(salida, "JPG", 92)
    print("banner:", salida)

