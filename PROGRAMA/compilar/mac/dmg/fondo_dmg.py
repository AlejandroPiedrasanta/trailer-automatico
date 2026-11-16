# -*- coding: utf-8 -*-
"""Fondo de la ventana del .dmg de la Mac (600 x 360 puntos; fondo.png y fondo@2x.png), igual que el de CineCaptions 5.91:
«Arrástralo a Aplicaciones», la flecha entre el programa y la carpeta, y abajo que hacer si macOS no lo abre la primera vez.
CLARO a proposito: con imagen de fondo el Finder escribe los nombres de los iconos en negro (tambien en modo oscuro).
Los iconos los coloca ajustes_dmg.py: el programa en (185, 168) y Aplicaciones en (415, 168); la flecha va entre los dos.

Desde la 1.5.7 el disco de la persona es «Doble clic para instalar» (fondo_instalar.png, como CineSlide 9.62); el de
«Arrástralo a Aplicaciones» (fondo.png) queda para el disco público de las actualizaciones.

    python PROGRAMA/compilar/mac/dmg/fondo_dmg.py        vuelve a dibujar fondo*.png y fondo*@2x.png
"""
import os
import sys
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QColor, QPen, QFont, QFontDatabase, QRadialGradient

W, H = 600, 360
PIE = 285                                                  # desde aqui, la franja blanca del consejo
AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTES = os.path.join(AQUI, "..", "..", "..", "recursos", "fuentes")
TINTA, VERDE, GRIS = "#0F172A", "#10B77F", "#7B8494"


def fuente(px, peso, familias):
    hay = set(QFontDatabase.families())
    f = QFont(next((x for x in familias if x in hay), "Arial"))
    f.setPixelSize(int(px))
    f.setWeight(peso)
    return f


TITULOS = ("Montserrat", "Segoe UI", "Helvetica Neue")
TEXTOS = ("Open Sans", "Segoe UI", "Helvetica Neue")


def centrado(p, y, trozos, px, peso, familias):
    """Escribe varios trozos (texto, color) en un renglon centrado en el ancho de la ventana."""
    p.setFont(fuente(px, peso, familias))
    m = p.fontMetrics()
    x = (W - sum(m.horizontalAdvance(t) for t, _ in trozos)) / 2.0
    for t, color in trozos:
        p.setPen(QColor(color))
        p.drawText(QRectF(x, y, W, px * 1.6), Qt.AlignLeft | Qt.AlignTop, t)
        x += m.horizontalAdvance(t)


def lienzo(esc):
    img = QImage(int(W * esc), int(H * esc), QImage.Format_ARGB32)
    img.fill(QColor("#F7F8FC"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.scale(esc, esc)
    return img, p


def consejo(p):
    """Abajo, en una franja blanca: que hacer si macOS no lo abre la primera vez (sin firma de Apple)."""
    p.fillRect(QRectF(0, PIE, W, H - PIE), QColor("#FFFFFF"))
    p.fillRect(QRectF(0, PIE, W, 1), QColor("#E3E7EF"))
    centrado(p, PIE + 14, [("¿macOS no lo abre la primera vez?", "#374151")], 13, QFont.Weight.Bold, TEXTOS)
    centrado(p, PIE + 34, [("Ajustes del Sistema › Privacidad y seguridad › Abrir igualmente", GRIS)], 12.5,
             QFont.Weight.Normal, TEXTOS)


def dibujar_instalar(esc):
    """El disco de la persona (desde la 1.5.7, como CineSlide 9.62): «Doble clic para instalar» y una sola app,
    «Instalar Trailer automatico», centrada en (300, 160) con 128 px (ajustes_dmg.py, modo instalador)."""
    img, p = lienzo(esc)
    halo = QRadialGradient(QPointF(300, 160), 150)
    halo.setColorAt(0, QColor(16, 183, 127, 46))
    halo.setColorAt(0.55, QColor(16, 183, 127, 14))
    halo.setColorAt(1, QColor(16, 183, 127, 0))
    p.fillRect(QRectF(0, 0, W, PIE), halo)
    centrado(p, 18, [("Doble clic para ", TINTA), ("instalar", VERDE)], 30, QFont.Weight.ExtraBold, TITULOS)
    centrado(p, 58, [("Double-click Instalar Trailer automatico to install", GRIS)], 14, QFont.Weight.Medium, TEXTOS)
    centrado(p, 258, [("Se instala solo en Aplicaciones y se abre al terminar  ·  1 a 2 minutos", GRIS)], 12.5,
             QFont.Weight.Normal, TEXTOS)
    consejo(p)
    p.end()
    return img


def dibujar(esc):
    img, p = lienzo(esc)
    centrado(p, 22, [("Arrástralo a ", TINTA), ("Aplicaciones", VERDE)], 30, QFont.Weight.ExtraBold, TITULOS)
    centrado(p, 62, [("Drag Tráiler automático to Applications", GRIS)], 14, QFont.Weight.Medium, TEXTOS)
    pen = QPen(QColor(VERDE), 3)                           # la flecha, entre los dos iconos (x 258-342, y 168)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.drawLine(QPointF(258, 168), QPointF(341, 168))
    p.drawPolyline([QPointF(331, 158), QPointF(342, 168), QPointF(331, 178)])
    consejo(p)
    p.end()
    return img


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    if os.path.isdir(FUENTES):                             # las mismas fuentes en cualquier computadora
        for f in os.listdir(FUENTES):
            if f.lower().endswith((".ttf", ".otf")):
                QFontDatabase.addApplicationFont(os.path.join(FUENTES, f))
    dibujar(1).save(os.path.join(AQUI, "fondo.png"))
    dibujar(2).save(os.path.join(AQUI, "fondo@2x.png"))
    dibujar_instalar(1).save(os.path.join(AQUI, "fondo_instalar.png"))
    dibujar_instalar(2).save(os.path.join(AQUI, "fondo_instalar@2x.png"))
    print("fondo.png / fondo_instalar.png (%dx%d) y sus @2x" % (W, H))
    del app


if __name__ == "__main__":
    main()
