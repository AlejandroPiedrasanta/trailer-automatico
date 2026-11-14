# -*- coding: utf-8 -*-
"""
hacer_portada.py - Dibuja la portada que el programa muestra AL INSTANTE al abrirse en Windows (recursos/portada.bmp).

Por que un .bmp ya hecho: Qt tarda mas de un segundo en poder mostrar su primera ventana (en una PC de edicion, con
miles de fuentes instaladas, lo que tarda es armar su lista de fuentes). El programa pone este .bmp con una ventanita
de Windows ANTES de cargar Qt (trailer_xv._portada_nativa), asi que al doble clic ya se ve algo.

  python PROGRAMA/herramientas/hacer_portada.py        vuelve a hacer recursos/portada.bmp (si cambia el icono o el nombre)

Mide 660 x 375: se ve nitida al 100 % y al 150 % de escala de Windows.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
PROG = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(PROG, "nucleo"))
import rutas  # noqa: E402  (pone las carpetas de codigo en sys.path)

from PySide6.QtCore import Qt, QRectF  # noqa: E402
from PySide6.QtGui import (QBrush, QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter,  # noqa: E402
                           QPen)

import icono_app  # noqa: E402

ANCHO, ALTO = 660, 375
TITULO = "Tráiler automático"


def dibujar():
    img = QImage(ANCHO, ALTO, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.setRenderHint(QPainter.TextAntialiasing)
    g = QLinearGradient(0, 0, 0, ALTO)
    g.setColorAt(0.0, QColor("#0D2630"))
    g.setColorAt(1.0, QColor("#06131A"))
    p.fillRect(0, 0, ANCHO, ALTO, QBrush(g))
    p.setPen(QPen(QColor(201, 162, 103, 120), 2))
    p.drawRect(1, 1, ANCHO - 2, ALTO - 2)
    lado = 132
    p.drawImage(QRectF(ANCHO / 2 - lado / 2, 54, lado, lado), icono_app.dibujar(lado * 2))
    f = QFont("Segoe UI", 1)
    f.setPixelSize(30)
    f.setWeight(QFont.DemiBold)
    p.setFont(f)
    p.setPen(QColor("#EAF2F0"))
    p.drawText(QRectF(0, 212, ANCHO, 44), Qt.AlignCenter, TITULO)
    f2 = QFont("Segoe UI", 1)
    f2.setPixelSize(17)
    p.setFont(f2)
    p.setPen(QColor("#8FA3A8"))
    p.drawText(QRectF(0, 268, ANCHO, 30), Qt.AlignCenter, "Abriendo…")
    p.end()
    return img


def main():
    app = QGuiApplication(sys.argv[:1])
    destino = os.path.join(rutas.RECURSOS, "portada.bmp")
    if not dibujar().save(destino, "BMP"):
        print("No se pudo guardar", destino)
        return 1
    print("%s (%d x %d, %.0f KB)" % (destino, ANCHO, ALTO, os.path.getsize(destino) / 1024.0))
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
