# -*- coding: utf-8 -*-
"""Fondo de la ventana del .dmg de la Mac (660 x 460 puntos; fondo.png y fondo@2x.png), como el de CineCaptions:
logo + nombre arriba, dos tarjetas («1 Doble clic para instalar» y «2 Ábrelo desde Aplicaciones») con el sitio de cada icono
y los consejos abajo. CLARO a proposito: con imagen de fondo el Finder escribe los nombres de los iconos en negro.
Los iconos los coloca ajustes_dmg.py: Instalar (165, 232), Aplicaciones (495, 232), Desinstalar (555, 380)."""
import os
import sys
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QGuiApplication, QImage, QPainter, QColor, QLinearGradient, QRadialGradient, QPen, QFont,
                           QPainterPath, QFontDatabase)

W, H = 660, 460
AQUI = os.path.dirname(os.path.abspath(__file__))


def fuente(px, peso, familias=("Montserrat", "Segoe UI", "Helvetica Neue")):
    hay = set(QFontDatabase.families())
    f = QFont(next((x for x in familias if x in hay), "Arial"))
    f.setPixelSize(int(px))
    f.setWeight(peso)
    return f


def texto(p, x, y, t, px, peso, color, familias=("Montserrat", "Segoe UI", "Helvetica Neue"), ancho=600, centro=False):
    p.setFont(fuente(px, peso, familias))
    p.setPen(QColor(color))
    r = QRectF(x - (ancho / 2 if centro else 0), y, ancho, px * 1.6)
    p.drawText(r, (Qt.AlignHCenter if centro else Qt.AlignLeft) | Qt.AlignTop, t)
    return p.fontMetrics().horizontalAdvance(t)


def tarjeta(p, r, n, titulo, sub):
    sombra = QPainterPath()
    sombra.addRoundedRect(r.translated(0, 4), 20, 20)
    p.fillPath(sombra, QColor(40, 60, 90, 22))
    c = QPainterPath()
    c.addRoundedRect(r, 20, 20)
    p.fillPath(c, QColor(255, 255, 255, 242))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(210, 222, 236), 1))
    p.drawPath(c)
    # numero en circulo verde + titulo, centrados
    f = fuente(16.5, QFont.Weight.Bold)
    p.setFont(f)
    ancho_t = p.fontMetrics().horizontalAdvance(titulo)
    total = 26 + 10 + ancho_t
    x0 = r.center().x() - total / 2
    y = r.top() + 22
    g = QLinearGradient(QPointF(x0, y), QPointF(x0 + 26, y + 26))
    g.setColorAt(0, QColor(52, 211, 153))
    g.setColorAt(1, QColor(16, 163, 106))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QRectF(x0, y, 26, 26))
    p.setPen(QColor(255, 255, 255))
    p.setFont(fuente(14, QFont.Weight.Bold))
    p.drawText(QRectF(x0, y, 26, 26), Qt.AlignCenter, str(n))
    p.setPen(QColor(20, 24, 32))
    p.setFont(f)
    p.drawText(QRectF(x0 + 36, y - 2, ancho_t + 4, 30), Qt.AlignLeft | Qt.AlignVCenter, titulo)
    texto(p, r.center().x(), y + 32, sub, 11.5, QFont.Weight.Normal, "#6B7686", ("Segoe UI", "Helvetica Neue"), r.width(), True)
    # flecha hacia el icono
    pen = QPen(QColor(16, 185, 129), 2.4)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    cx, cy = r.center().x(), y + 64
    p.drawPolyline([QPointF(cx - 7, cy - 3), QPointF(cx, cy + 4), QPointF(cx + 7, cy - 3)])


def icono(p, x, y, lado):
    """El icono del programa (engranaje de bronce + play), el mismo de la app, en un cuadro claro redondeado."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("icono", os.path.join(AQUI, "..", "..", "icono.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    c = QPainterPath()
    c.addRoundedRect(QRectF(x, y, lado, lado), lado * 0.24, lado * 0.24)
    p.fillPath(c.translated(0, 2), QColor(30, 50, 80, 30))
    p.fillPath(c, QColor(255, 255, 255))
    p.setPen(QPen(QColor(220, 228, 238), 1))
    p.drawPath(c)
    img = m.dibujar(int(lado * 0.78 * 4))
    p.drawImage(QRectF(x + lado * 0.11, y + lado * 0.11, lado * 0.78, lado * 0.78), img)


def dibujar(esc):
    img = QImage(int(W * esc), int(H * esc), QImage.Format_ARGB32)
    img.fill(QColor(246, 248, 252))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.scale(esc, esc)
    luz = QRadialGradient(QPointF(W - 40, 0), 360)
    luz.setColorAt(0, QColor(178, 236, 240, 200))
    luz.setColorAt(0.5, QColor(214, 236, 250, 110))
    luz.setColorAt(1, QColor(246, 248, 252, 0))
    p.fillRect(QRectF(0, 0, W, H), luz)
    icono(p, 28, 22, 64)
    x = 108
    p.setFont(fuente(30, QFont.Weight.ExtraBold))
    p.setPen(QColor(12, 16, 24))
    p.drawText(QRectF(x, 22, 400, 40), Qt.AlignLeft | Qt.AlignVCenter, "Tráiler")
    w1 = p.fontMetrics().horizontalAdvance("Tráiler ")
    p.setPen(QColor(16, 163, 106))
    p.drawText(QRectF(x + w1, 22, 400, 40), Qt.AlignLeft | Qt.AlignVCenter, "automático")
    texto(p, x, 62, "Instalador para Mac · By Cinema Productions", 13, QFont.Weight.Medium, "#4B5563", ("Segoe UI", "Helvetica Neue"))
    tarjeta(p, QRectF(22, 112, 286, 222), 1, "Doble clic para instalar", "Double-click to install")
    tarjeta(p, QRectF(352, 112, 286, 222), 2, "Ábrelo desde Aplicaciones", "Then open it from Applications")
    # pie con los consejos
    p.fillRect(QRectF(0, 352, W, H - 352), QColor(232, 238, 246))
    p.setPen(QPen(QColor(214, 222, 234), 1))
    p.drawLine(QPointF(0, 352), QPointF(W, 352))
    filas = [("¿macOS no lo deja abrir? ", "Clic derecho sobre «Instalar Tráiler automático» › Abrir.",
              "macOS won’t open it? Right-click “Instalar Tráiler automático” › Open."),
             ("En DaVinci Resolve: ", "Preferencias › Sistema › General › Scripting externo: Local.",
              "In DaVinci Resolve: Preferences › System › General › External scripting: Local.")]
    y = 366
    for neg, resto, ingles in filas:
        p.setFont(fuente(11.5, QFont.Weight.Bold))
        p.setPen(QColor(15, 20, 30))
        p.drawText(QRectF(26, y, 480, 18), Qt.AlignLeft | Qt.AlignVCenter, neg)
        wn = p.fontMetrics().horizontalAdvance(neg)
        p.setFont(fuente(11.5, QFont.Weight.Normal, ("Segoe UI", "Helvetica Neue")))
        p.setPen(QColor(40, 48, 60))
        p.drawText(QRectF(26 + wn, y, 500 - wn, 18), Qt.AlignLeft | Qt.AlignVCenter, resto)
        texto(p, 26, y + 18, ingles, 10.5, QFont.Weight.Normal, "#8A94A6", ("Segoe UI", "Helvetica Neue"), 500)
        y += 44
    p.end()
    return img


if __name__ == "__main__":
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    dibujar(1).save(os.path.join(AQUI, "fondo.png"))
    dibujar(2).save(os.path.join(AQUI, "fondo@2x.png"))
    print("fondo.png y fondo@2x.png listos")
