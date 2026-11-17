# -*- coding: utf-8 -*-
"""
piezas.py - (1.6.0) Piezas del diseño nuevo de la ventana, IGUAL a las maquetas de Higgsfield (la persona, 17-nov:
«hazlo 100% igual»; docs/capturas/propuesta_1..5). Las medidas son las de la maqueta (2048 x 1360) por ESCALA (el ancho
de la ventana / 2048): px(36) es «36 px de la maqueta».

  icono(tipo, color, lado) / qicono(...)   iconos de trazo dibujados (Segoe UI no trae ✓ ☰ ✎ ▶)
  Astrolabio      el boton GO: el astrolabio de la maqueta VIVO (videos de Higgsfield en recursos/animaciones: reposo,
                  despertar, trabajo, hecho, dormir) con el avance real dibujado encima; sin videos, la imagen quieta
                  (recursos/astrolabio_*.png). Misma API que boton_go.BotonGo (poner_estado, poner_progreso...)
  Titulo, Adorno, Chip, Segmentado, Pasos, Versiones, Pila, VistaTitulo, BarraUso, Interruptor, BotonIcono, tarjeta()

Solo PySide6: nada pesado al abrir (regla de arranque).
"""
import math
import os
import random
import re
import time

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, Signal, QTimer, QVariantAnimation, QEasingCurve
from PySide6.QtGui import (QColor, QPainter, QPen, QFont, QFontDatabase, QFontMetricsF, QIcon, QImage,
                           QLinearGradient, QPainterPath, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

import animacion

ORO = "#E2B04F"
ORO_CLARO = "#F6E3B4"
ESMERALDA = "#22C47E"
VERDE_TXT = "#2BD388"
TEXTO = "#EEF4F5"
TENUE = "#8FA3A8"
AZULADO = "#8FA9C0"
AMBAR = "#F2B84B"
ROJO = "#F07A6A"
OSCURO = "#04150D"

ESCALA = 0.605                       # la ventana la cambia al cambiar de tamaño (ancho / 2048 de la maqueta)


def px(v):
    """Medida de la maqueta (2048 de ancho) a pixeles de la ventana."""
    return max(1, int(round(v * ESCALA)))


# ---------------------------------------------------------------------------------------------------- iconos
def _dibujar(p, tipo, col, s, grosor=None):
    p.setPen(QPen(col, grosor or max(1.2, s * 0.075), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    c = QPainterPath()

    def R(x, y, w, h, r=0.12):
        c.addRoundedRect(QRectF(x * s, y * s, w * s, h * s), r * s, r * s)

    def L(*pts):
        c.moveTo(pts[0][0] * s, pts[0][1] * s)
        for x, y in pts[1:]:
            c.lineTo(x * s, y * s)

    def O(cx, cy, r, ry=None):
        c.addEllipse(QPointF(cx * s, cy * s), r * s, (ry if ry is not None else r) * s)

    relleno = None
    if tipo == "palomita":
        L((0.16, 0.54), (0.40, 0.77), (0.86, 0.25))
    elif tipo == "lapiz":
        L((0.12, 0.88), (0.18, 0.64), (0.68, 0.14), (0.86, 0.32), (0.36, 0.82))
        c.closeSubpath()
        L((0.57, 0.25), (0.75, 0.43))
    elif tipo == "foto":
        R(0.06, 0.16, 0.88, 0.68, 0.10)
        L((0.14, 0.74), (0.38, 0.48), (0.55, 0.64), (0.66, 0.54), (0.86, 0.74))
        O(0.68, 0.34, 0.07)
    elif tipo == "video":
        R(0.05, 0.25, 0.62, 0.50, 0.10)
        L((0.67, 0.43), (0.93, 0.29), (0.93, 0.71), (0.67, 0.57))
    elif tipo == "dron":
        R(0.38, 0.40, 0.24, 0.20, 0.06)
        for (x0, y0), (x1, y1) in (((0.38, 0.45), (0.22, 0.30)), ((0.62, 0.45), (0.78, 0.30)),
                                   ((0.38, 0.55), (0.22, 0.70)), ((0.62, 0.55), (0.78, 0.70))):
            L((x0, y0), (x1, y1))
        for cx, cy in ((0.20, 0.27), (0.80, 0.27), (0.20, 0.73), (0.80, 0.73)):
            O(cx, cy, 0.16, 0.055)
    elif tipo == "reloj":
        O(0.5, 0.5, 0.40)
        L((0.5, 0.26), (0.5, 0.5), (0.67, 0.62))
    elif tipo == "carpeta":
        L((0.06, 0.24), (0.38, 0.24), (0.47, 0.34), (0.94, 0.34), (0.94, 0.82), (0.06, 0.82))
        c.closeSubpath()
    elif tipo == "check":
        O(0.5, 0.5, 0.42)
        L((0.31, 0.52), (0.45, 0.66), (0.70, 0.38))
    elif tipo == "info":
        O(0.5, 0.5, 0.42)
        L((0.5, 0.46), (0.5, 0.71))
        relleno = [(0.5, 0.31, 0.05)]
    elif tipo == "chip":
        R(0.24, 0.24, 0.52, 0.52, 0.10)
        for t in (0.37, 0.5, 0.63):
            L((t, 0.08), (t, 0.24))
            L((t, 0.76), (t, 0.92))
            L((0.08, t), (0.24, t))
            L((0.76, t), (0.92, t))
    elif tipo == "onda":
        for x, h in ((0.12, 0.22), (0.26, 0.46), (0.40, 0.80), (0.54, 0.56), (0.68, 0.34), (0.82, 0.18)):
            L((x, 0.5 - h / 2), (x, 0.5 + h / 2))
    elif tipo == "disco":
        c.addEllipse(QRectF(0.16 * s, 0.10 * s, 0.68 * s, 0.24 * s))
        L((0.16, 0.22), (0.16, 0.78))
        L((0.84, 0.22), (0.84, 0.78))
        for y in (0.50, 0.78):
            c.moveTo(0.16 * s, y * s)
            c.quadTo(0.5 * s, (y + 0.16) * s, 0.84 * s, y * s)
    elif tipo == "engrane":
        O(0.5, 0.5, 0.13)
        dientes = QPainterPath()
        for k in range(16):
            a = k * math.pi / 8
            r = 0.42 if k % 2 == 0 else 0.32
            x, y = 0.5 + r * math.cos(a), 0.5 + r * math.sin(a)
            (dientes.moveTo if k == 0 else dientes.lineTo)(x * s, y * s)
        dientes.closeSubpath()
        c.addPath(dientes)
    elif tipo == "texto":
        L((0.18, 0.20), (0.82, 0.20))
        L((0.5, 0.20), (0.5, 0.84))
    elif tipo == "papelera":
        L((0.14, 0.24), (0.86, 0.24))
        L((0.37, 0.24), (0.41, 0.12), (0.59, 0.12), (0.63, 0.24))
        L((0.22, 0.24), (0.28, 0.88), (0.72, 0.88), (0.78, 0.24))
        L((0.42, 0.40), (0.43, 0.74))
        L((0.58, 0.40), (0.57, 0.74))
    elif tipo == "refrescar":
        caja = QRectF(0.16 * s, 0.16 * s, 0.68 * s, 0.68 * s)
        c.arcMoveTo(caja, 40)
        c.arcTo(caja, 40, 150)
        L((0.20, 0.30), (0.17, 0.46), (0.32, 0.42))
        c.arcMoveTo(caja, 220)
        c.arcTo(caja, 220, 150)
        L((0.80, 0.70), (0.83, 0.54), (0.68, 0.58))
    elif tipo == "pelicula":
        R(0.10, 0.12, 0.80, 0.76, 0.08)
        L((0.30, 0.12), (0.30, 0.88))
        L((0.70, 0.12), (0.70, 0.88))
        for y in (0.31, 0.50, 0.69):
            L((0.10, y), (0.30, y))
            L((0.70, y), (0.90, y))
    elif tipo == "claqueta":
        R(0.10, 0.36, 0.80, 0.54, 0.06)
        L((0.10, 0.36), (0.12, 0.16), (0.88, 0.10), (0.90, 0.30))
        for x in (0.28, 0.48, 0.68):
            L((x, 0.15), (x + 0.07, 0.33))
        L((0.42, 0.52), (0.42, 0.76), (0.62, 0.64))
        c.closeSubpath()
    elif tipo == "corazon":
        c.moveTo(0.5 * s, 0.86 * s)
        c.cubicTo(0.04 * s, 0.56 * s, 0.12 * s, 0.10 * s, 0.5 * s, 0.32 * s)
        c.cubicTo(0.88 * s, 0.10 * s, 0.96 * s, 0.56 * s, 0.5 * s, 0.86 * s)
    elif tipo == "anillo":
        O(0.5, 0.62, 0.28)
        L((0.38, 0.30), (0.5, 0.12), (0.62, 0.30), (0.5, 0.36))
        c.closeSubpath()
    elif tipo in ("brillo", "aplausos"):
        if tipo == "brillo":
            L((0.5, 0.06), (0.59, 0.41), (0.94, 0.5), (0.59, 0.59), (0.5, 0.94), (0.41, 0.59), (0.06, 0.5), (0.41, 0.41))
            c.closeSubpath()
        else:                                            # dos manos que aplauden (contorno simplificado) y chispas
            L((0.22, 0.86), (0.18, 0.52), (0.36, 0.26), (0.48, 0.36), (0.44, 0.58), (0.58, 0.40), (0.70, 0.50),
              (0.54, 0.86))
            L((0.40, 0.22), (0.52, 0.12), (0.66, 0.26), (0.62, 0.38))
            L((0.74, 0.18), (0.84, 0.10))
            L((0.80, 0.30), (0.92, 0.28))
            L((0.18, 0.18), (0.12, 0.08))
    elif tipo == "pastel":
        R(0.10, 0.54, 0.80, 0.32, 0.06)
        R(0.24, 0.34, 0.52, 0.20, 0.05)
        L((0.40, 0.34), (0.40, 0.16))
        L((0.60, 0.34), (0.60, 0.16))
    elif tipo == "copa":
        L((0.30, 0.10), (0.36, 0.42), (0.5, 0.50), (0.64, 0.42), (0.70, 0.10))
        c.closeSubpath()
        L((0.5, 0.50), (0.5, 0.84))
        L((0.34, 0.88), (0.66, 0.88))
    elif tipo == "nota":
        O(0.34, 0.72, 0.12)
        L((0.46, 0.72), (0.46, 0.16), (0.80, 0.26), (0.80, 0.38), (0.46, 0.30))
    elif tipo == "pincel":                               # brocha de maquillaje
        c.addEllipse(QPointF(0.30 * s, 0.70 * s), 0.16 * s, 0.10 * s)
        L((0.40, 0.62), (0.88, 0.14))
        L((0.36, 0.56), (0.80, 0.10), (0.92, 0.22), (0.46, 0.66))
    elif tipo == "iglesia":
        L((0.5, 0.04), (0.5, 0.22))
        L((0.42, 0.11), (0.58, 0.11))
        L((0.36, 0.40), (0.5, 0.22), (0.64, 0.40))
        L((0.40, 0.36), (0.40, 0.92))
        L((0.60, 0.36), (0.60, 0.92))
        L((0.12, 0.60), (0.40, 0.48))
        L((0.88, 0.60), (0.60, 0.48))
        L((0.16, 0.58), (0.16, 0.92), (0.84, 0.92), (0.84, 0.58))
        L((0.46, 0.92), (0.46, 0.72), (0.54, 0.72), (0.54, 0.92))
    elif tipo in ("fiesta", "globo"):                    # bola de disco
        O(0.5, 0.5, 0.40)
        c.addEllipse(QPointF(0.5 * s, 0.5 * s), 0.18 * s, 0.40 * s)
        L((0.10, 0.5), (0.90, 0.5))
        L((0.16, 0.30), (0.84, 0.30))
        L((0.16, 0.70), (0.84, 0.70))
    elif tipo == "cancelar":
        O(0.5, 0.5, 0.40)
        L((0.36, 0.36), (0.64, 0.64))
        L((0.64, 0.36), (0.36, 0.64))
    elif tipo == "min":
        L((0.18, 0.5), (0.82, 0.5))
    elif tipo == "max":
        R(0.20, 0.20, 0.60, 0.60, 0.04)
    elif tipo == "x":
        L((0.20, 0.20), (0.80, 0.80))
        L((0.80, 0.20), (0.20, 0.80))
    elif tipo == "play":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        tri = QPainterPath()
        tri.moveTo(0.28 * s, 0.16 * s)
        tri.lineTo(0.86 * s, 0.5 * s)
        tri.lineTo(0.28 * s, 0.84 * s)
        tri.closeSubpath()
        p.drawPath(tri)
        return
    elif tipo == "punto":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(0.5 * s, 0.5 * s), 0.38 * s, 0.38 * s)
        return
    elif tipo == "check_lleno":                           # circulo verde lleno con palomita blanca (Material)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(0.5 * s, 0.5 * s), 0.46 * s, 0.46 * s)
        p.setPen(QPen(QColor("#FFFFFF"), s * 0.11, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        pal = QPainterPath()
        pal.moveTo(0.29 * s, 0.52 * s)
        pal.lineTo(0.44 * s, 0.67 * s)
        pal.lineTo(0.72 * s, 0.37 * s)
        p.drawPath(pal)
        return
    p.drawPath(c)
    for cx, cy, r in relleno or []:
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(cx * s, cy * s), r * s, r * s)


_MASCARAS = {}                       # (1.6.0) tipo -> QImage de recursos/iconos (Higgsfield) o None
_ICONOS = {}                         # (tipo, color, lado, grosor) -> QPixmap ya hecho (se piden en cada pintada)
# los de controles (palomita, x, play...) quedan dibujados: son geometria simple y se ven mejor exactos
SOLO_DIBUJADOS = {"palomita", "check", "check_lleno", "cancelar", "min", "max", "x", "play", "punto"}


def _mascara(tipo):
    if tipo not in _MASCARAS:
        img = None
        if tipo not in SOLO_DIBUJADOS:
            try:
                import rutas
                archivo = {"globo": "fiesta"}.get(tipo, tipo)
                ruta = os.path.join(rutas.RECURSOS, "iconos", archivo + ".png")
                if os.path.isfile(ruta):
                    img = QImage(ruta).convertToFormat(QImage.Format_ARGB32_Premultiplied)
                    img = None if img.isNull() else img
            except Exception:
                img = None
        _MASCARAS[tipo] = img
    return _MASCARAS[tipo]


def _de_mascara(m, color, lado, k):
    """El icono de Higgsfield del color pedido, con un degradado apenas perceptible (mas claro arriba, como el oro
    de la maqueta)."""
    T = max(4, int(round(lado * k)))
    chica = m.scaled(T, T, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out = QImage(T, T, QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawImage(QPointF((T - chica.width()) / 2.0, (T - chica.height()) / 2.0), chica)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    c = QColor(color)
    g = QLinearGradient(0, 0, 0, T)
    g.setColorAt(0.0, c.lighter(118))
    g.setColorAt(0.55, c)
    g.setColorAt(1.0, c.darker(110))
    p.fillRect(QRectF(0, 0, T, T), g)
    p.end()
    pm = QPixmap.fromImage(out)
    pm.setDevicePixelRatio(k)
    return pm


def icono(tipo, color, lado=16, grosor=None):
    """QPixmap del icono (a 4x: nitido en pantallas al 150 %). (1.6.0) Los de dibujo (fotos, video, dron, iglesia...)
    salen de los iconos de Higgsfield (recursos/iconos, herramientas/preparar_iconos.py); si falta uno, el dibujo de
    siempre. Se guardan hechos: se piden en cada pintada."""
    clave = (tipo, QColor(color).name(QColor.HexArgb), int(round(lado * 4)), grosor)
    pm = _ICONOS.get(clave)
    if pm is not None:
        return pm
    k = 4
    m = _mascara(tipo)
    if m is not None:
        pm = _de_mascara(m, color, lado, k)
    else:
        pm = QPixmap(int(lado * k), int(lado * k))
        pm.setDevicePixelRatio(k)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        _dibujar(p, tipo, QColor(color), float(lado), grosor)
        p.end()
    if len(_ICONOS) > 500:
        _ICONOS.clear()
    _ICONOS[clave] = pm
    return pm


def qicono(tipo, color, lado=16):
    return QIcon(icono(tipo, color, lado))


def punto_latido(color, lado, f):
    """(1.6.0) El punto de la pastilla de estado con un halo que late (f de 0 a 1)."""
    k = 3
    pm = QPixmap(int(lado * k), int(lado * k))
    pm.setDevicePixelRatio(k)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c, m = QColor(color), lado / 2.0
    h0, h1 = QColor(c), QColor(c)
    h0.setAlpha(int(50 + 120 * f))
    h1.setAlpha(0)
    halo = QRadialGradient(QPointF(m, m), m * (0.62 + 0.38 * f))
    halo.setColorAt(0.0, h0)
    halo.setColorAt(1.0, h1)
    p.setPen(Qt.NoPen)
    p.setBrush(halo)
    p.drawEllipse(QPointF(m, m), m, m)
    p.setBrush(c)
    p.drawEllipse(QPointF(m, m), lado * 0.21, lado * 0.21)
    p.end()
    return pm


def _degradado_verde(r):
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0.0, QColor("#2BD08C"))
    g.setColorAt(1.0, QColor("#118A57"))
    return g


# ---------------------------------------------------------------------------------------------------- piezas
class Chip(QPushButton):
    """Pastilla de vidrio con icono: «442 fotos», «XV años · Valeria». Propiedad tipo: falta (ambar) / oro."""

    def __init__(self, texto="", tipo_icono=None, color=TEXTO, parent=None, nombre="chip2", lado=48):
        super().__init__(texto, parent)
        self.setObjectName(nombre)
        self.setCursor(Qt.PointingHandCursor)
        self._ic = (tipo_icono, color, lado)
        if tipo_icono:
            self.poner_icono(tipo_icono, color, lado)

    def poner_icono(self, tipo, color, lado=48):
        self._ic = (tipo, color, lado)
        self.setIconSize(QSize(px(lado), px(lado)))
        self.setIcon(qicono(tipo, color, px(lado)))

    def reescalar(self):
        if self._ic[0]:
            self.poner_icono(*self._ic)


class Segmentado(QFrame):
    """Opciones exclusivas juntas en una caja (Horizontal | Vertical; Voz original)."""
    cambio = Signal(int)

    def __init__(self, opciones, actual=0, parent=None, nombre="segb", exclusivo=True, caja="seg"):
        super().__init__(parent)
        self.setObjectName(caja)
        h = QHBoxLayout(self)
        h.setContentsMargins(3, 3, 3, 3)
        h.setSpacing(2)
        self.grupo = QButtonGroup(self)
        self.grupo.setExclusive(exclusivo)
        self.botones = []
        for i, t in enumerate(opciones):
            b = QPushButton(t, objectName=nombre, checkable=True)
            b.setCursor(Qt.PointingHandCursor)
            self.grupo.addButton(b, i)
            h.addWidget(b)
            self.botones.append(b)
        if self.botones and actual is not None and exclusivo:
            self.botones[max(0, min(actual, len(self.botones) - 1))].setChecked(True)
        self.grupo.idClicked.connect(self.cambio.emit)

    def actual(self):
        return self.grupo.checkedId()

    def poner(self, i):
        if 0 <= i < len(self.botones):
            self.botones[i].setChecked(True)


class Pastillas(QWidget):
    """Opciones exclusivas SEPARADAS, cada una en su pastilla (Tipo de evento; pestañas de la vista previa)."""
    cambio = Signal(int)

    def __init__(self, opciones, actual=0, parent=None, nombre="pill_tipo", espacio=12, estirar=False):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(px(espacio))
        self.grupo = QButtonGroup(self)
        self.botones = []
        for i, t in enumerate(opciones):
            b = QPushButton(t, objectName=nombre, checkable=True)
            b.setCursor(Qt.PointingHandCursor)
            self.grupo.addButton(b, i)
            h.addWidget(b, 1 if estirar else 0)
            self.botones.append(b)
        if self.botones:
            self.botones[max(0, min(actual, len(self.botones) - 1))].setChecked(True)
        self.grupo.idClicked.connect(self.cambio.emit)

    def actual(self):
        return self.grupo.checkedId()

    def poner(self, i):
        if 0 <= i < len(self.botones):
            self.botones[i].setChecked(True)


def separador_v(alto=60):
    s = QFrame()
    s.setFixedSize(1, px(alto))
    s.setStyleSheet("background: rgba(255,255,255,0.14);")
    return s


def separador_h():
    s = QFrame()
    s.setFixedHeight(1)
    s.setStyleSheet("background: rgba(255,255,255,0.12);")
    return s


def tarjeta(titulo, tipo_icono, color=TEXTO):
    """Tarjeta de vidrio con icono y titulo (Ajustes). Devuelve (frame, layout del contenido)."""
    f = QFrame(objectName="tarjeta")
    v = QVBoxLayout(f)
    v.setContentsMargins(px(46), px(34), px(46), px(36))
    v.setSpacing(px(22))
    cab = QHBoxLayout()
    cab.setSpacing(px(30))
    ic = QLabel()
    ic.setPixmap(icono(tipo_icono, color, px(64)))
    cab.addWidget(ic)
    t = QLabel(titulo, objectName="tarjeta_t")
    cab.addWidget(t)
    cab.addStretch(1)
    v.addLayout(cab)
    v.addWidget(separador_h())
    return f, v


class BotonIcono(QPushButton):
    """Boton sin caja con un icono de trazo (los de la ventana: minimizar, maximizar, cerrar)."""

    def __init__(self, tipo, ayuda="", rojo=False, parent=None):
        super().__init__(parent)
        self.tipo, self.rojo = tipo, rojo
        self.setObjectName("cerrar" if rojo else "ctrl")
        self.setToolTip(ayuda)
        self.setCursor(Qt.PointingHandCursor)
        self.reescalar()

    def reescalar(self):
        self.setFixedSize(px(72), px(60))
        self.setIconSize(QSize(px(34), px(34)))
        self.setIcon(qicono(self.tipo, "#F2F6F7", px(34)))


class Interruptor(QCheckBox):
    """El interruptor verde de la maqueta (Ajustes): pista redonda con perilla blanca que se desliza."""

    def __init__(self, texto=""):
        super().__init__(texto)
        self.setCursor(Qt.PointingHandCursor)
        self._x = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._mover)
        self.toggled.connect(self._cambio)

    def _mover(self, v):
        self._x = float(v)
        self.update()

    def _cambio(self, on):
        if not self.isVisible():
            self._x = 1.0 if on else 0.0
            return
        self._anim.stop()
        self._anim.setStartValue(self._x)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def sizeHint(self):
        return QSize(px(90), px(50))

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = float(px(88)), float(px(46))
        y = (self.height() - h) / 2
        r = QRectF(self.width() - w - 1, y, w, h)
        t = self._x
        if t > 0.5:
            p.setPen(Qt.NoPen)
            p.setBrush(_degradado_verde(r))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 60), 1))
            p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(r, h / 2, h / 2)
        d = h - px(10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#FFFFFF") if self.isEnabled() else QColor(TENUE))
        p.drawEllipse(QRectF(r.left() + px(5) + t * (w - d - px(10)), y + px(5), d, d))


BRILLO_CICLO = 6.0               # (1.6.0) cada cuanto pasa una luz por el titulo y sus adornos, en segundos


def brillo_fase():
    """Segundos dentro del ciclo de la luz: cruza el adorno izquierdo (0,0-0,6), el oro del titulo (0,5-1,7) y el
    adorno derecho (1,6-2,2); el resto del ciclo, quieto. Todas las piezas usan el mismo reloj: van juntas."""
    return time.monotonic() % BRILLO_CICLO


def _suave(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class Titulo(QWidget):
    """«Un clic y listo» como en la maqueta: blanco, y «listo» con un degradado dorado. setText acepta el
    <span ...>texto</span> de antes: lo de adentro va en oro. (1.6.0) Vivo: una luz cruza el oro cada pocos segundos
    y los puntos de «Trabajando…» laten uno tras otro."""
    LUZ = (0.5, 1.7)

    def __init__(self, texto="", parent=None, tam=100):
        super().__init__(parent)
        self.tam = tam
        self._texto, self._partes = "", [("", False)]
        self._pintado_luz = False
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setText(texto)
        self._reloj = QTimer(self, interval=33)
        self._reloj.timeout.connect(self._tic)
        self._reloj.start()

    def text(self):
        return self._texto

    def setText(self, texto):
        self._texto = texto or ""
        m = re.match(r"^(.*?)<span[^>]*>(.*?)</span>(.*)$", self._texto, re.S)
        self._partes = [(m.group(1), False), (m.group(2), True), (m.group(3), False)] if m else [(self._texto, False)]
        self.updateGeometry()
        self.update()

    def _puntos(self):
        return len(self._partes) == 1 and self._texto.endswith("…")

    def _tic(self):
        if not self.isVisible() or self.window().isMinimized():
            return
        f = brillo_fase()
        luz = self.LUZ[0] <= f <= self.LUZ[1] and any(oro for _, oro in self._partes)
        if luz or self._pintado_luz or self._puntos():
            self._pintado_luz = luz
            self.update()

    def _fuente(self):
        f = QFont(self.font())
        f.setPixelSize(px(self.tam))
        f.setWeight(QFont.Bold)
        return f

    def sizeHint(self):
        fm = QFontMetricsF(self._fuente())
        return QSize(int(fm.horizontalAdvance("".join(t for t, _ in self._partes))) + 24, int(fm.height() * 1.12))

    def minimumSizeHint(self):
        return QSize(80, self.sizeHint().height())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = self._fuente()
        fm = QFontMetricsF(f)
        partes = self._partes
        puntos = self._puntos()
        if puntos:                                   # «Trabajando» + tres puntos que laten
            partes = [(self._texto[:-1], False)]
        total = fm.horizontalAdvance("".join(t for t, _ in self._partes))
        esc = min(1.0, (self.width() - 8) / max(1.0, total))
        x = (self.width() - total * esc) / 2.0
        base = (self.height() + fm.ascent() * esc - fm.descent() * esc) / 2.0
        p.translate(x, base)
        p.scale(esc, esc)
        cx = 0.0
        fase = brillo_fase()
        for txt, oro in partes:
            if not txt:
                continue
            camino = QPainterPath()
            camino.addText(cx, 0, f, txt)
            if oro:
                caja = camino.boundingRect()
                g = QLinearGradient(0, caja.top(), 0, caja.bottom())
                g.setColorAt(0.0, QColor("#FBE7B0"))
                g.setColorAt(0.5, QColor("#E7B85A"))
                g.setColorAt(1.0, QColor("#B98935"))
                p.fillPath(camino, g)
                u = (fase - self.LUZ[0]) / (self.LUZ[1] - self.LUZ[0])
                if 0.0 < u < 1.0:                    # la luz que cruza el oro, en diagonal
                    u = _suave(u)
                    bw = caja.height() * 0.55
                    xc = caja.left() - bw + (caja.width() + 2 * bw) * u
                    yc = caja.center().y()
                    luz = QLinearGradient(QPointF(xc - bw, yc - bw * 0.35), QPointF(xc + bw, yc + bw * 0.35))
                    luz.setColorAt(0.0, QColor(255, 248, 225, 0))
                    luz.setColorAt(0.5, QColor(255, 250, 232, 215))
                    luz.setColorAt(1.0, QColor(255, 248, 225, 0))
                    p.fillPath(camino, luz)
            else:
                p.fillPath(camino, QColor("#FFFFFF"))
            cx += fm.horizontalAdvance(txt)
        if puntos:
            ancho = fm.horizontalAdvance("…") / 3.0
            t = time.monotonic()
            for i in range(3):
                a = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(t * 4.2 - i * 0.9))
                c = QColor("#FFFFFF")
                c.setAlphaF(a)
                camino = QPainterPath()
                camino.addText(cx + i * ancho, 0, f, ".")
                p.fillPath(camino, c)


class Adorno(QWidget):
    """Linea dorada con un rombo, a los lados del titulo (como en la maqueta). (1.6.0) Una luz la recorre hacia la
    derecha y el rombo destella al pasar (el mismo reloj que la luz del titulo)."""

    def __init__(self, lado="izq", parent=None):
        super().__init__(parent)
        self.lado = lado
        self.ventana = (0.0, 0.6) if lado == "izq" else (1.6, 2.2)
        self._pintado_luz = False
        self.reescalar()
        self._reloj = QTimer(self, interval=33)
        self._reloj.timeout.connect(self._tic)
        self._reloj.start()

    def reescalar(self):
        self.setFixedSize(px(270), px(20) + px(24))

    def _tic(self):
        if not self.isVisible() or self.window().isMinimized():
            return
        f = brillo_fase()
        luz = self.ventana[0] <= f <= self.ventana[1]
        if luz or self._pintado_luz:
            self._pintado_luz = luz
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, y = float(self.width()), self.height() / 2.0
        g = QLinearGradient(0, 0, w, 0)
        c0, c1 = QColor(ORO), QColor(ORO)
        c0.setAlpha(0)
        c1.setAlpha(230)
        g.setColorAt(0.0, c0 if self.lado == "izq" else c1)
        g.setColorAt(1.0, c1 if self.lado == "izq" else c0)
        p.setPen(QPen(g, max(1.0, px(3))))
        p.drawLine(QPointF(0, y), QPointF(w, y))
        x = w * 0.52
        d = px(9)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#F3CF7A"))
        rombo = QPainterPath()
        rombo.moveTo(x, y - d)
        rombo.lineTo(x + d * 0.7, y)
        rombo.lineTo(x, y + d)
        rombo.lineTo(x - d * 0.7, y)
        rombo.closeSubpath()
        p.drawPath(rombo)
        u = (brillo_fase() - self.ventana[0]) / (self.ventana[1] - self.ventana[0])
        if not 0.0 < u < 1.0:
            return
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        lx = w * u                                       # la luz que corre por la linea
        luz = QRadialGradient(QPointF(lx, y), px(26))
        luz.setColorAt(0.0, QColor(255, 236, 190, 230))
        luz.setColorAt(0.3, QColor(240, 190, 90, 120))
        luz.setColorAt(1.0, QColor(240, 190, 90, 0))
        p.setBrush(luz)
        p.drawEllipse(QPointF(lx, y), px(26), px(26))
        brillo = max(0.0, 1.0 - abs(lx - x) / (w * 0.16))  # el rombo destella cuando pasa la luz
        if brillo > 0:
            largo = d * (1.4 + 2.6 * brillo)
            for dx, dy in ((1, 0), (0, 1)):
                rayo = QLinearGradient(QPointF(x - dx * largo, y - dy * largo), QPointF(x + dx * largo, y + dy * largo))
                rayo.setColorAt(0.0, QColor(255, 240, 200, 0))
                rayo.setColorAt(0.5, QColor(255, 246, 220, int(240 * brillo)))
                rayo.setColorAt(1.0, QColor(255, 240, 200, 0))
                p.setPen(QPen(rayo, max(1.0, px(3))))
                p.drawLine(QPointF(x - dx * largo, y - dy * largo), QPointF(x + dx * largo, y + dy * largo))


class Astrolabio(QWidget):
    """El boton GO de la maqueta, vivo: los videos de Higgsfield (recursos/animaciones, animacion.Pelicula) del
    astrolabio en reposo (bucle), despertando al empezar, trabajando (bucle, con el avance real encima: arco verde y
    «62%»), celebrando al terminar y volviendo a dormir; al apretar, una onda y chispas. Sin ffmpeg o sin los videos
    queda la imagen quieta (recursos/astrolabio_*.png) con la esmeralda que respira. Misma API que boton_go.BotonGo."""
    clicked = Signal()
    # en astrolabio_trabajo.png: centro de la ventana verde y radio del arco (medidos sobre la imagen)
    CENTRO_T, RADIO_T = (0.523, 0.466), 0.178
    # en astrolabio_inicio.png: centro de la esmeralda y su radio
    CENTRO_I, RADIO_I = (0.502, 0.534), 0.150
    BUCLES = {"reposo": "astro_reposo.mp4", "trabajo": "astro_trabajo.mp4"}
    PASOS = {"despertar": ("astro_despertar.mp4", "trabajo"), "hecho": ("astro_hecho.mp4", "trabajo"),
             "dormir": ("astro_dormir.mp4", "reposo")}
    CRUCE = 0.32                                      # segundos de fundido al cambiar de video

    def __init__(self, ruta_inicio, ruta_trabajo, parent=None):
        super().__init__(parent)
        self.img = {"inicio": QImage(ruta_inicio), "trabajo": QImage(ruta_trabajo)}
        self.estado = "reposo"
        self._prog = self._prog_visto = 0.0
        self._sobre = self._apretado = False
        self._t = 0.0
        self._cache = {}
        self._vuelta = QTimer(self, singleShot=True)
        self._vuelta.timeout.connect(lambda: self.poner_estado("reposo"))
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        # los videos: se arrancan un rato despues de verse la ventana (regla de arranque)
        self._peli = None
        self._cuadro = self._previo = None            # (QImage, bytes): el que se ve y el de antes (fundido)
        self._t_cambio = 0.0
        self._sonando, self._lazo, self._cola = None, "reposo", []
        self._velo = 0.0                              # el arco y el % encima del video (0..1)
        self._onda, self._chispas = -1.0, []
        self._t_tam = QTimer(self, singleShot=True, interval=260)
        self._t_tam.timeout.connect(self._retomar)
        self._reloj = QTimer(self)
        self._reloj.timeout.connect(self._tic)
        self._reloj.start(40)

    # ---- la API de boton_go.BotonGo que usa la ventana
    def poner_estado(self, estado, centro=None, tono=None):
        antes = self.estado
        self.estado = estado or "reposo"
        if self.estado in ("hecho", "error"):
            self._vuelta.start(6000)                    # el 100 % (o el error) se ve un rato y vuelve al astrolabio
        if self.estado == "trabajando":
            self._vuelta.stop()
        self._encadenar(celebrar=self.estado == "hecho" and antes == "trabajando")
        self.update()

    def poner_progreso(self, f):
        self._prog = max(0.0, min(1.0, float(f)))
        if self._prog < self._prog_visto:
            self._prog_visto = self._prog

    def poner_fase(self, clave):
        pass

    def seguir_a(self, escena):
        pass

    def poner_lado(self, lado):
        img = self.img["inicio"]
        asp = img.width() / float(img.height()) if not img.isNull() else 1.3
        self.setFixedSize(int(lado * asp), int(lado))

    # ---- los videos
    def _trabajando(self):
        return self.estado in ("trabajando", "hecho", "error")

    def _encadenar(self, celebrar=False):
        """Lo que va despues de lo que suena: el paso al estado pedido y su bucle (o la celebracion)."""
        destino = "trabajo" if self._trabajando() else "reposo"
        if celebrar:
            self._cola = ["hecho", "trabajo"]
        elif destino != self._lazo:
            self._cola = ["despertar" if destino == "trabajo" else "dormir", destino]
        else:
            self._cola = [c for c in self._cola if c in ("hecho", destino)]
        if self._peli is not None and self._sonando in self.BUCLES and self._cola:
            self._siguiente()                         # un bucle se corta ya; un paso termina primero

    def _siguiente(self):
        clave = self._cola.pop(0) if self._cola else self._lazo
        self._tocar(clave)

    def _tam_video(self):
        dpr = self.devicePixelRatioF()
        return int(self.width() * dpr), int(self.height() * dpr)

    def _tocar(self, clave, fundir=True):
        if clave in self.BUCLES:
            archivo, lazo, bucle = self.BUCLES[clave], clave, True
        else:
            (archivo, lazo), bucle = self.PASOS[clave], False
        self._lazo = lazo
        ruta = animacion.ruta(archivo)
        if fundir and self._cuadro is not None:
            self._previo, self._t_cambio = self._cuadro, time.monotonic()
        w, h = self._tam_video()
        if ruta and self._peli.reproducir(ruta, w, h, fps=24, bucle=bucle, alfa=True):
            self._sonando = clave
            return
        self._sonando = None                          # sin video: la imagen quieta
        if not bucle:
            self._siguiente()

    def _al_cuadro(self, img, datos):
        self._cuadro = (img, datos)
        self.update()

    def _arrancar_videos(self):
        if self._peli is not None or not animacion.ruta(self.BUCLES["reposo"]):
            return
        self._peli = animacion.Pelicula(self._al_cuadro, self._siguiente, self)
        self._lazo, self._cola = ("trabajo" if self._trabajando() else "reposo"), []
        self._tocar(self._lazo, fundir=False)

    def _retomar(self):
        """Cambio de tamaño: un bucle sigue al tamaño nuevo (mientras, el ultimo cuadro escalado); un paso
        (despertar, hecho, dormir) no se corta: termina escalado y lo que sigue ya sale del tamaño nuevo."""
        if self._peli is not None and self._sonando in self.BUCLES and \
                self._peli.tam != tuple(v // 2 * 2 for v in self._tam_video()):
            self._tocar(self._sonando, fundir=False)

    def showEvent(self, e):
        super().showEvent(e)
        if self._peli is None:
            QTimer.singleShot(1200, self._arrancar_videos)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._peli is not None:
            self._t_tam.start()

    # ---- animacion y raton
    def _tic(self):
        self._t += 0.04
        ver = self.isVisible() and not self.window().isMinimized()
        if self._peli is not None:
            self._peli.pausar(not ver)
            self._peli.lento(not self.window().isActiveWindow())
        if self._prog_visto < self._prog:
            self._prog_visto = min(self._prog, self._prog_visto + 0.008)
        if self._sonando is None:                     # sin video: el arco se ve mientras trabaja
            quiere = 1.0 if self._trabajando() else 0.0
        else:                                         # con video: solo en el bucle de trabajo (no al despertar)
            quiere = 1.0 if self._sonando == "trabajo" else 0.0
        self._velo += (quiere - self._velo) * 0.12
        if self._onda >= 0:
            self._onda += 0.04 / 0.7
            if self._onda > 1.0:
                self._onda = -1.0
        ahora = time.monotonic()
        self._chispas = [c for c in self._chispas if ahora - c[4] < c[5]]
        if ver and (self._sonando is None or self._onda >= 0 or self._chispas or 0.01 < self._velo < 0.99
                    or self._previo is not None or self.estado == "reposo"):
            self.update()

    def enterEvent(self, e):
        self._sobre = True
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._sobre = self._apretado = False
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._apretado = True
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._apretado:
            self._apretado = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
                if not self._trabajando():
                    self._explotar()
                self.clicked.emit()

    def _explotar(self):
        """Al apretar: una onda verde desde la esmeralda y chispas de oro y esmeralda."""
        self._onda = 0.0
        ahora = time.monotonic()
        rnd = random.Random()
        for _ in range(46):
            ang = rnd.uniform(0, math.tau)
            vel = rnd.uniform(0.35, 1.25)
            col = QColor("#F6D27A") if rnd.random() < 0.45 else QColor("#5CF2B0")
            self._chispas.append((math.cos(ang) * vel, math.sin(ang) * vel, rnd.uniform(1.2, 3.2), col, ahora,
                                  rnd.uniform(0.7, 1.4)))

    def _caja(self, clave, w, h):
        img = self.img[clave]
        if img.isNull():
            return QRectF(0, 0, w, h)
        esc = min(w / img.width(), h / img.height())
        tw, th = img.width() * esc, img.height() * esc
        return QRectF((w - tw) / 2.0, (h - th) / 2.0, tw, th)

    def _escalada(self, clave, w, h):
        """La imagen ya escalada al tamaño (se escala una vez por tamaño, no en cada cuadro)."""
        dpr = self.devicePixelRatioF()
        k = (clave, w, h, dpr)
        if k not in self._cache:
            img = self.img[clave]
            if img.isNull():
                return None, QRectF()
            r = self._caja(clave, w, h)
            pm = QPixmap.fromImage(img.scaled(int(r.width() * dpr), int(r.height() * dpr), Qt.KeepAspectRatio,
                                              Qt.SmoothTransformation))
            pm.setDevicePixelRatio(dpr)
            self._cache = {kk: v for kk, v in self._cache.items() if kk[0] != clave}
            self._cache[k] = (pm, r)
        return self._cache[k]

    def _pintar_cuadro(self, p, cuadro, w, h, opacidad=1.0):
        img = cuadro[0]
        dpr = self.devicePixelRatioF()
        iw, ih = img.width() / dpr, img.height() / dpr
        p.setOpacity(opacidad)
        if abs(iw - w) < 2.5 and abs(ih - h) < 2.5:     # mismo tamaño: se copia tal cual (rapido)
            p.drawImage(QRectF((w - iw) / 2.0, (h - ih) / 2.0, iw, ih), img)
        else:
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawImage(QRectF(0, 0, w, h), img)
        p.setOpacity(1.0)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())
        trabajando = self._trabajando()
        if self._apretado:
            p.translate(w / 2, h / 2)
            p.scale(0.985, 0.985)
            p.translate(-w / 2, -h / 2)
        ahora = time.monotonic()
        if self._cuadro is not None:                  # el video (y el de antes, desvaneciendose)
            fundido = (ahora - self._t_cambio) / self.CRUCE if self._previo is not None else 1.0
            if self._previo is not None and fundido >= 1.0:
                self._previo = None
            if self._previo is not None and self._previo is not self._cuadro:
                self._pintar_cuadro(p, self._previo, w, h)
                self._pintar_cuadro(p, self._cuadro, w, h, min(1.0, max(0.0, fundido)))
            else:
                self._pintar_cuadro(p, self._cuadro, w, h)
            en_reposo = self._lazo == "reposo" and self._sonando == "reposo"
        else:                                         # la imagen quieta
            pm, r = self._escalada("trabajo" if trabajando else "inicio", w, h)
            if pm is None:
                return
            p.drawPixmap(r.topLeft(), pm)
            en_reposo = not trabajando
        ri = self._caja("inicio", w, h)
        cx, cy = ri.left() + ri.width() * self.CENTRO_I[0], ri.top() + ri.height() * self.CENTRO_I[1]
        rad = ri.width() * self.RADIO_I
        if en_reposo:                                 # la esmeralda respira (y brilla mas con el raton encima)
            a = 16 + 16 * (0.5 + 0.5 * math.sin(self._t * 2.2)) + (36 if self._sobre else 0)
            g = QRadialGradient(QPointF(cx, cy), rad * 1.35)
            g.setColorAt(0.0, QColor(90, 255, 180, int(a)))
            g.setColorAt(1.0, QColor(90, 255, 180, 0))
            p.setCompositionMode(QPainter.CompositionMode_Plus)
            p.fillRect(QRectF(cx - rad * 1.4, cy - rad * 1.4, rad * 2.8, rad * 2.8), g)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        self._pintar_onda(p, cx, cy, rad, ahora)
        if self._velo > 0.01:
            self._pintar_avance(p, w, h)

    def _pintar_onda(self, p, cx, cy, rad, ahora):
        if self._onda < 0 and not self._chispas:
            return
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        if self._onda >= 0:                           # el anillo que se abre desde la esmeralda
            t = self._onda
            r = rad * (1.0 + 1.6 * (1 - (1 - t) ** 3))
            col = QColor(110, 255, 190, int(210 * (1 - t)))
            p.setPen(QPen(col, max(1.0, rad * 0.10 * (1 - t))))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(Qt.NoPen)
        for vx, vy, tam, col, t0, vida in self._chispas:
            t = (ahora - t0) / vida
            if t >= 1.0:
                continue
            d = rad * (0.6 + 2.1 * (1 - (1 - t) ** 2))
            x, y = cx + vx * d, cy + vy * d + rad * 0.5 * t * t
            c = QColor(col)
            c.setAlpha(int(255 * (1 - t)))
            p.setBrush(c)
            p.drawEllipse(QPointF(x, y), tam * (1 - 0.5 * t), tam * (1 - 0.5 * t))
            c.setAlpha(int(60 * (1 - t)))
            p.setBrush(c)
            p.drawEllipse(QPointF(x, y), tam * 3, tam * 3)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)

    def _pintar_avance(self, p, w, h):
        """Trabajando: el arco verde del avance y el porcentaje en la ventana verde."""
        r = self._caja("trabajo", w, h)
        cx, cy = r.left() + r.width() * self.CENTRO_T[0], r.top() + r.height() * self.CENTRO_T[1]
        rad = r.width() * self.RADIO_T
        f = 1.0 if self.estado == "hecho" else self._prog_visto
        p.setOpacity(self._velo)
        caja = QRectF(cx - rad, cy - rad, rad * 2, rad * 2)
        grueso = max(3.0, r.width() * 0.022)
        p.setPen(QPen(QColor(0, 0, 0, 90), grueso, Qt.SolidLine, Qt.FlatCap))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(caja)
        if f > 0.002:
            col = QColor(ROJO) if self.estado == "error" else QColor("#36F0A0")
            halo = QColor(col)
            halo.setAlpha(70)
            p.setPen(QPen(halo, grueso * 2.4, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(caja, 90 * 16, int(-f * 360 * 16))
            p.setPen(QPen(col, grueso, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(caja, 90 * 16, int(-f * 360 * 16))
            if self.estado == "trabajando":           # la punta del arco brilla y late
                ang = math.radians(90 - f * 360)
                px_, py_ = cx + rad * math.cos(ang), cy - rad * math.sin(ang)
                lat = 0.5 + 0.5 * math.sin(self._t * 5.0)
                g = QRadialGradient(QPointF(px_, py_), grueso * (2.6 + 1.2 * lat))
                g.setColorAt(0.0, QColor(220, 255, 235, 230))
                g.setColorAt(0.35, QColor(54, 240, 160, 150))
                g.setColorAt(1.0, QColor(54, 240, 160, 0))
                p.setPen(Qt.NoPen)
                p.setBrush(g)
                p.drawEllipse(QPointF(px_, py_), grueso * 4, grueso * 4)
        fuente = QFont(self.font())
        fuente.setPixelSize(max(12, int(rad * 0.62)))
        fuente.setWeight(QFont.Bold)
        texto = "%d%%" % int(round(f * 100))
        camino = QPainterPath()
        camino.addText(0, 0, fuente, texto)
        bb = camino.boundingRect()
        camino.translate(cx - bb.center().x(), cy - bb.center().y())
        p.fillPath(camino.translated(0, rad * 0.03), QColor(0, 0, 0, 110))
        p.fillPath(camino, QColor("#FFFFFF"))
        p.setOpacity(1.0)


class Pasos(QWidget):
    """Los pasos del trabajo en una fila (como la maqueta): hecho (verde con palomita), activo (oro), pendiente.
    (1.6.0) Vivos: el activo late y lo rodea un arco que gira, una luz corre por la linea hacia el y, al quedar hecho,
    la palomita se dibuja con una onda verde."""
    POP = 0.7                                         # segundos de la onda y la palomita al quedar hecho

    def __init__(self, pasos, parent=None):
        super().__init__(parent)
        self.pasos = list(pasos)
        self.estado = {c: "pendiente" for c, _ in self.pasos}
        self._cuando = {}                             # clave -> cuando quedo hecho
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._reloj = QTimer(self, interval=33)
        self._reloj.timeout.connect(self._tic)
        self.reescalar()

    def reescalar(self):
        self.setFixedHeight(px(118))
        self.update()

    def sizeHint(self):
        return QSize(px(1500), px(118))

    def reiniciar(self):
        self.estado = {c: "pendiente" for c, _ in self.pasos}
        self._cuando = {}
        self.update()

    def _marcar(self, clave, estado):
        if estado == "hecho" and self.estado.get(clave) != "hecho":
            self._cuando[clave] = time.monotonic()
        self.estado[clave] = estado

    def poner(self, clave, estado):
        if clave not in self.estado:
            return
        if estado == "activo":
            for c, _ in self.pasos:
                if c == clave:
                    break
                if self.estado[c] in ("pendiente", "activo"):
                    self._marcar(c, "hecho")
        self._marcar(clave, estado)
        if not self._reloj.isActive():
            self._reloj.start()
        self.update()

    def activo(self):
        return next((c for c, _ in self.pasos if self.estado[c] == "activo"), None)

    def _anima(self):
        ahora = time.monotonic()
        return "activo" in self.estado.values() or any(ahora - t < self.POP for t in self._cuando.values())

    def _tic(self):
        if not self._anima():
            self._reloj.stop()
        if self.isVisible() and not self.window().isMinimized():
            self.update()

    def showEvent(self, e):
        super().showEvent(e)
        if self._anima():
            self._reloj.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self.pasos)
        if not n:
            return
        ahora = time.monotonic()
        w = float(self.width())
        margen = px(80)
        xs = [margen + (w - 2 * margen) * i / max(1, n - 1) for i in range(n)]
        r = float(px(25))
        y = r + px(4)
        for i in range(n - 1):
            a, b = self.estado[self.pasos[i][0]], self.estado[self.pasos[i + 1][0]]
            x0, x1 = xs[i] + r, xs[i + 1] - r
            if a == "hecho" and b == "activo":
                g = QLinearGradient(xs[i], 0, xs[i + 1], 0)
                g.setColorAt(0.0, QColor(ESMERALDA))
                g.setColorAt(1.0, QColor(ORO))
                p.setPen(QPen(g, px(4)))
                p.drawLine(QPointF(x0, y), QPointF(x1, y))
                u = (ahora % 1.4) / 1.4                   # una luz corre por la linea hacia el paso activo
                lx = x0 + (x1 - x0) * _suave(u)
                luz = QRadialGradient(QPointF(lx, y), px(16))
                luz.setColorAt(0.0, QColor(255, 244, 205, int(235 * (1 - u * 0.4))))
                luz.setColorAt(0.4, QColor(240, 200, 100, 110))
                luz.setColorAt(1.0, QColor(240, 200, 100, 0))
                p.setPen(Qt.NoPen)
                p.setBrush(luz)
                p.drawEllipse(QPointF(lx, y), px(16), px(16))
                continue
            if a == "hecho":
                p.setPen(QPen(QColor(ESMERALDA), px(4)))
            else:
                p.setPen(QPen(QColor(150, 165, 175, 110), px(3)))
            p.drawLine(QPointF(x0, y), QPointF(x1, y))
        f = QFont(self.font())
        f.setPixelSize(px(32))
        f.setWeight(QFont.Medium)
        p.setFont(f)
        for i, (clave, texto) in enumerate(self.pasos):
            e, x = self.estado[clave], xs[i]
            caja = QRectF(x - r, y - r, 2 * r, 2 * r)
            if e == "hecho":
                k = min(1.0, (ahora - self._cuando.get(clave, 0.0)) / self.POP)
                esc = 1.0 + 0.28 * math.sin(math.pi * k) * (1 - k)
                if k < 1.0:                               # la onda verde al quedar hecho
                    p.setPen(QPen(QColor(54, 240, 160, int(200 * (1 - k))), max(1.0, px(4) * (1 - k))))
                    p.setBrush(Qt.NoBrush)
                    p.drawEllipse(QPointF(x, y), r * (1 + 1.3 * k), r * (1 + 1.3 * k))
                halo = QRadialGradient(QPointF(x, y), r * 1.7)
                halo.setColorAt(0.0, QColor(34, 196, 126, 90))
                halo.setColorAt(1.0, QColor(34, 196, 126, 0))
                p.setPen(Qt.NoPen)
                p.setBrush(halo)
                p.drawEllipse(QPointF(x, y), r * 1.7, r * 1.7)
                rc = QRectF(x - r * esc, y - r * esc, 2 * r * esc, 2 * r * esc)
                p.setBrush(_degradado_verde(rc))
                p.drawEllipse(rc)
                p.setPen(QPen(QColor("#FFFFFF"), max(2.0, px(5)), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.setBrush(Qt.NoBrush)
                pts = [QPointF(x - 0.42 * r, y + 0.02 * r), QPointF(x - 0.10 * r, y + 0.32 * r),
                       QPointF(x + 0.44 * r, y - 0.30 * r)]
                trazo = min(1.0, k * 1.8)                 # la palomita se dibuja
                l1 = math.hypot(pts[1].x() - pts[0].x(), pts[1].y() - pts[0].y())
                l2 = math.hypot(pts[2].x() - pts[1].x(), pts[2].y() - pts[1].y())
                hasta = trazo * (l1 + l2)
                pal = QPainterPath(pts[0])
                if hasta <= l1:
                    pal.lineTo(pts[0] + (pts[1] - pts[0]) * (hasta / l1))
                else:
                    pal.lineTo(pts[1])
                    pal.lineTo(pts[1] + (pts[2] - pts[1]) * ((hasta - l1) / l2))
                p.drawPath(pal)
            elif e == "activo":
                lat = 0.5 + 0.5 * math.sin(ahora * 4.0)
                rh = r * (1.6 + 0.4 * lat)
                halo = QRadialGradient(QPointF(x, y), rh)
                halo.setColorAt(0.0, QColor(226, 176, 79, int(90 + 70 * lat)))
                halo.setColorAt(1.0, QColor(226, 176, 79, 0))
                p.setPen(Qt.NoPen)
                p.setBrush(halo)
                p.drawEllipse(QPointF(x, y), rh, rh)
                p.setPen(QPen(QColor(ORO), max(2.0, px(5))))
                p.setBrush(QColor(28, 24, 12))
                p.drawEllipse(caja)
                giro = int(-(ahora * 360.0 / 1.6) % 360 * 16)   # un arco claro gira alrededor
                ra = r * 1.36
                p.setPen(QPen(QColor(255, 226, 150, 220), max(1.5, px(3)), Qt.SolidLine, Qt.RoundCap))
                p.setBrush(Qt.NoBrush)
                p.drawArc(QRectF(x - ra, y - ra, 2 * ra, 2 * ra), giro, 80 * 16)
                p.setPen(QPen(QColor(255, 226, 150, 80), max(1.5, px(3)), Qt.SolidLine, Qt.RoundCap))
                p.drawArc(QRectF(x - ra, y - ra, 2 * ra, 2 * ra), giro + 180 * 16, 50 * 16)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#F3CF7A"))
                rd = r * (0.36 + 0.10 * lat)
                p.drawEllipse(QPointF(x, y), rd, rd)
            elif e == "error":
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(ROJO))
                p.drawEllipse(caja)
            else:
                p.setPen(QPen(QColor(150, 165, 175, 160), max(1.5, px(4))))
                p.setBrush(QColor(16, 30, 38))
                p.drawEllipse(caja)
            p.setPen(QColor(ORO) if e == "activo" else QColor(TEXTO) if e == "hecho" else
                     QColor(ROJO) if e == "error" else QColor(AZULADO))
            p.drawText(QRectF(x - px(150), y + r + px(10), px(300), px(50)), Qt.AlignHCenter | Qt.AlignTop, texto)


class _FilaVersion(QWidget):
    """Una version en el avance (como la maqueta): claqueta, «15 min · 62% · plano 87 de 140», barra y palomita.
    (1.6.0) Viva: la barra avanza suave con un brillo que la recorre, «Armando…» sin porcentaje es una luz que va y
    viene, y la palomita aparece con un rebote."""

    def __init__(self, etiqueta, parent=None):
        super().__init__(parent)
        self.etiqueta = etiqueta
        self.estado, self.pct, self.texto, self.detalle = "cola", 0.0, "En cola", ""
        self.ultima = False
        self._visto, self._t_listo = 0.0, -10.0
        self._reloj = QTimer(self, interval=33)
        self._reloj.timeout.connect(self._tic)
        self.reescalar()

    def reescalar(self):
        self.setFixedHeight(px(82))
        self.update()

    def poner(self, estado, texto, pct=None, detalle=""):
        if estado == "listo" and self.estado != "listo":
            self._t_listo = time.monotonic()
        self.estado, self.texto, self.detalle = estado, texto, detalle or ""
        if pct is not None:
            self.pct = max(0.0, min(1.0, pct))
        if not self._reloj.isActive():
            self._reloj.start()
        self.update()

    def _meta(self):
        return 1.0 if self.estado in ("listo", "armada") else self.pct if self.estado in ("render", "armando") else 0.0

    def _anima(self):
        return (abs(self._meta() - self._visto) > 0.002 or self.estado in ("render", "armando")
                or time.monotonic() - self._t_listo < 0.6)

    def _tic(self):
        meta = self._meta()
        self._visto = meta if meta < self._visto else self._visto + (meta - self._visto) * 0.10
        if not self._anima():
            self._reloj.stop()
        if self.isVisible() and not self.window().isMinimized():
            self.update()

    def showEvent(self, e):
        super().showEvent(e)
        if self._anima():
            self._reloj.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())
        ahora = time.monotonic()
        p.drawPixmap(QPointF(px(26), (h - px(50)) / 2), icono("claqueta", "#C9D6DA", px(50)))
        f = QFont(self.font())
        f.setPixelSize(px(34))
        f.setWeight(QFont.Medium)
        fb = QFont(f)
        fb.setWeight(QFont.Bold)
        nombre = self.etiqueta.replace("min", " min").replace("VERTICAL", "Vertical")
        partes = [(nombre, f, TEXTO), ("  ·  ", f, TEXTO)]
        if self.estado in ("listo", "armada"):
            partes.append((self.texto, f, VERDE_TXT))
        elif self.estado == "render":
            partes.append((self.texto, fb, TEXTO))
            if self.detalle:
                partes += [("  ·  ", f, TEXTO), (self.detalle, f, AZULADO)]
        elif self.estado == "error":
            partes.append((self.texto, f, ROJO))
        elif self.estado == "armando":
            partes.append((self.texto, f, ORO))
        else:
            partes.append((self.texto, f, AZULADO))
        x = float(px(110))
        for txt, fuente, col in partes:
            p.setFont(fuente)
            p.setPen(QColor(col))
            p.drawText(QRectF(x, 0, w, h), Qt.AlignVCenter | Qt.AlignLeft, txt)
            x += QFontMetricsF(fuente).horizontalAdvance(txt)
        barra = QRectF(w * 0.40, h / 2 - px(8), w * 0.50, px(16))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(120, 140, 150, 70))
        p.drawRoundedRect(barra, barra.height() / 2, barra.height() / 2)
        llena = self._visto
        if self.estado == "armando" and self.pct <= 0.001:  # sin porcentaje: una luz dorada que va y viene
            u = 0.5 + 0.5 * math.sin(ahora * 2.4)
            ancho = barra.width() * 0.22
            seg = QRectF(barra.left() + (barra.width() - ancho) * u, barra.top(), ancho, barra.height())
            g = QLinearGradient(seg.topLeft(), seg.topRight())
            g.setColorAt(0.0, QColor(226, 176, 79, 0))
            g.setColorAt(0.5, QColor(246, 210, 122, 230))
            g.setColorAt(1.0, QColor(226, 176, 79, 0))
            p.setBrush(g)
            p.drawRoundedRect(seg, seg.height() / 2, seg.height() / 2)
        elif llena > 0:
            lr = QRectF(barra.left(), barra.top(), max(barra.height(), barra.width() * llena), barra.height())
            g = QLinearGradient(lr.topLeft(), lr.bottomLeft())
            g.setColorAt(0.0, QColor("#3BEE9F"))
            g.setColorAt(1.0, QColor("#16B06E"))
            p.setBrush(g)
            p.drawRoundedRect(lr, lr.height() / 2, lr.height() / 2)
            if self.estado in ("render", "armando"):   # un brillo recorre lo ya hecho
                u = (ahora % 1.8) / 1.8
                bw = max(lr.height() * 4, lr.width() * 0.25)
                xc = lr.left() - bw + (lr.width() + 2 * bw) * u
                brillo = QLinearGradient(QPointF(xc - bw, 0), QPointF(xc + bw, 0))
                brillo.setColorAt(0.0, QColor(255, 255, 255, 0))
                brillo.setColorAt(0.5, QColor(255, 255, 255, 120))
                brillo.setColorAt(1.0, QColor(255, 255, 255, 0))
                p.setBrush(brillo)
                p.drawRoundedRect(lr, lr.height() / 2, lr.height() / 2)
                pu = QRadialGradient(QPointF(lr.right() - lr.height() / 2, lr.center().y()), lr.height() * 1.6)
                pu.setColorAt(0.0, QColor(200, 255, 225, int(150 + 80 * math.sin(ahora * 5))))
                pu.setColorAt(1.0, QColor(59, 238, 159, 0))
                p.setBrush(pu)
                p.drawEllipse(QPointF(lr.right() - lr.height() / 2, lr.center().y()), lr.height() * 1.6,
                              lr.height() * 1.6)
        if self.estado == "listo":                     # la palomita aparece con un rebote
            k = min(1.0, (ahora - self._t_listo) / 0.5)
            esc = (1.0 + 0.35 * math.sin(math.pi * k) * (1 - k)) if k < 1.0 else 1.0
            lado = px(44)
            c = QPointF(w - px(80) + lado / 2.0, h / 2.0)
            p.save()
            p.translate(c)
            p.scale(max(0.01, esc * min(1.0, k * 3)), max(0.01, esc * min(1.0, k * 3)))
            p.drawPixmap(QPointF(-lado / 2.0, -lado / 2.0), icono("check", "#2FD98F", lado))
            p.restore()
        if not self.ultima:
            p.setPen(QPen(QColor(255, 255, 255, 26), 1))
            p.drawLine(QPointF(px(0), h - 0.5), QPointF(w - px(0), h - 0.5))


class Versiones(QFrame):
    """El avance de cada version mientras trabaja, la hora en que termina y «Cancelar» (como la maqueta)."""
    cancelar = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("vidrio")
        v = QVBoxLayout(self)
        v.setContentsMargins(px(44), px(16), px(40), px(26))
        v.setSpacing(0)
        self._filas_lay = QVBoxLayout()
        self._filas_lay.setSpacing(0)
        v.addLayout(self._filas_lay)
        v.addWidget(separador_h())
        pie = QHBoxLayout()
        pie.setContentsMargins(px(6), px(24), 0, 0)
        pie.setSpacing(px(20))
        self.l_reloj = QLabel()
        self.l_reloj.setPixmap(icono("reloj", ORO, px(46)))
        pie.addWidget(self.l_reloj)
        self.l_eta = QLabel("", objectName="eta_t")
        self.l_eta.setTextFormat(Qt.RichText)
        pie.addWidget(self.l_eta, 1)
        self.b_cancelar = QPushButton("Cancelar", objectName="cancelar")
        self.b_cancelar.setCursor(Qt.PointingHandCursor)
        self.b_cancelar.clicked.connect(self.cancelar.emit)
        pie.addWidget(self.b_cancelar)
        v.addLayout(pie)
        self.filas = {}

    def poner_versiones(self, etiquetas):
        for f in self.filas.values():
            f.setParent(None)
            f.deleteLater()
        self.filas = {}
        for e in etiquetas:
            f = _FilaVersion(e)
            self._filas_lay.addWidget(f)
            self.filas[e] = f
        for i, f in enumerate(self.filas.values()):
            f.ultima = i == len(self.filas) - 1
        self.b_cancelar.setEnabled(True)
        self.b_cancelar.setText("Cancelar")

    def poner(self, etiqueta, estado, texto, pct=None, detalle=""):
        f = self.filas.get(etiqueta)
        if f is not None:
            f.poner(estado, texto, pct, detalle)

    def poner_eta(self, html):
        self.l_eta.setText(html)


class Pila(QWidget):
    """Tres fotos en abanico (como la maqueta): la de adelante grande a la izquierda y dos detras, giradas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fotos = []
        self._t_abre = -10.0                          # (1.6.0) al llegar las fotos se abren en abanico
        self._reloj = QTimer(self, interval=40)       # y despues flotan suave, cada una a su ritmo
        self._reloj.timeout.connect(self._tic)
        self._reloj.start()
        self.reescalar()

    def _tic(self):
        if self.isVisible() and not self.window().isMinimized():
            self.update()

    def reescalar(self):
        self.setFixedSize(px(340), px(178))
        self.update()

    def poner(self, pixmaps):
        nuevas = [x for x in pixmaps if x is not None and not x.isNull()][:3]
        if len(nuevas) != len(self.fotos):
            self._t_abre = time.monotonic()
        self.fotos = nuevas
        self.update()

    def _foto(self, p, pm, cx, cy, w, h, ang):
        p.save()
        p.translate(cx, cy)
        p.rotate(ang)
        r = QRectF(-w / 2, -h / 2, w, h)
        sombra = QPainterPath()
        sombra.addRoundedRect(r.translated(px(6), px(8)), px(10), px(10))
        p.fillPath(sombra, QColor(0, 0, 0, 110))
        marco = QPainterPath()
        marco.addRoundedRect(r, px(10), px(10))
        p.fillPath(marco, QColor("#F4F6F7") if pm is not None else QColor(24, 44, 54))
        dentro = QPainterPath()
        borde = px(5)
        dentro.addRoundedRect(r.adjusted(borde, borde, -borde, -borde), px(7), px(7))
        p.setClipPath(dentro)
        if pm is not None:
            esc = max((w - 2 * borde) / pm.width(), (h - 2 * borde) / pm.height())
            tw, th = pm.width() * esc, pm.height() * esc
            p.drawPixmap(QRectF(-tw / 2, -th / 2, tw, th), pm, QRectF(pm.rect()))
        else:
            p.fillRect(r, QColor(16, 32, 40))
        p.restore()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        fotos = list(self.fotos) + [None] * (3 - len(self.fotos))
        W, H = float(self.width()), float(self.height())
        fw, fh = W * 0.70, H * 0.86                   # la de adelante
        ahora = time.monotonic()
        k = 1.0 - (1.0 - min(1.0, max(0.0, (ahora - self._t_abre) / 0.7))) ** 3   # 0 = juntas, 1 = en abanico
        ondas = [math.sin(ahora * v + f) for v, f in ((0.9, 0.0), (0.75, 2.1), (0.6, 4.2))]
        self._foto(p, fotos[2], W * (0.38 + 0.42 * k), H * 0.52 + ondas[2] * px(3), fw * 0.62, fh * 0.80,
                   -3 + 12 * k + ondas[2] * 1.2)
        self._foto(p, fotos[1], W * (0.38 + 0.32 * k), H * 0.51 + ondas[1] * px(3), fw * 0.66, fh * 0.86,
                   -3 + 8 * k + ondas[1] * 1.0)
        self._foto(p, fotos[0], W * 0.38, H * 0.50 + ondas[0] * px(2), fw, fh, -3 + ondas[0] * 0.6)


class BarraUso(QWidget):
    """Barra dorada (y gruesa, como la maqueta) de lo que ocupa la cache."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frac = self._visto = 0.0                 # (1.6.0) la barra se llena suave y un brillo la recorre
        self._reloj = QTimer(self, interval=40)
        self._reloj.timeout.connect(self._tic)
        self._reloj.start()
        self.reescalar()

    def _tic(self):
        if not self.isVisible() or self.window().isMinimized():
            return
        self._visto += (self.frac - self._visto) * 0.12
        if abs(self.frac - self._visto) > 0.001 or time.monotonic() % 5.0 < 1.3:
            self.update()

    def reescalar(self):
        self.setFixedHeight(px(32))
        self.update()

    def poner(self, frac):
        self.frac = max(0.0, min(1.0, float(frac)))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 1, 0, -1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(120, 140, 150, 70))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        if self._visto > 0.001:
            lr = QRectF(r.left(), r.top(), max(r.height(), r.width() * self._visto), r.height())
            g = QLinearGradient(lr.topLeft(), lr.bottomLeft())
            g.setColorAt(0.0, QColor("#FBD772"))
            g.setColorAt(1.0, QColor("#D69A2D"))
            p.setBrush(g)
            p.drawRoundedRect(lr, lr.height() / 2, lr.height() / 2)
            u = (time.monotonic() % 5.0) / 1.3
            if u < 1.0:
                bw = max(lr.height() * 3, lr.width() * 0.3)
                xc = lr.left() - bw + (lr.width() + 2 * bw) * _suave(u)
                luz = QLinearGradient(QPointF(xc - bw, 0), QPointF(xc + bw, 0))
                luz.setColorAt(0.0, QColor(255, 255, 255, 0))
                luz.setColorAt(0.5, QColor(255, 250, 230, 140))
                luz.setColorAt(1.0, QColor(255, 255, 255, 0))
                p.setBrush(luz)
                p.drawRoundedRect(lr, lr.height() / 2, lr.height() / 2)


class FondoPagina(QWidget):
    """Ajustes: el bodegon de la maqueta (claqueta, camara, rosa, tiara, anillos) abajo a la izquierda. (1.6.0) Recortado
    en Higgsfield (recursos/ajustes_bodegon.png) sobre el cielo que se mueve, y vivo: brillos en el oro, la tiara y
    la lente (recursos/animaciones/bodegon.mp4, con su mascara). Sin el video, el recorte quieto."""
    LIENZO = (2048.0, 1360.0)                         # la maqueta de Ajustes
    CAJA = (0.0, 242.0, 624.0, 1054.0)                # donde esta el bodegon en la maqueta

    def __init__(self, ruta, parent=None):
        super().__init__(parent)
        self.img = QImage(ruta) if ruta and os.path.isfile(ruta) else QImage()
        self._cache = None
        self._peli = self._cuadro = None
        self._t_tam = QTimer(self, singleShot=True, interval=350)
        self._t_tam.timeout.connect(self._video)
        self._reloj = QTimer(self, interval=200)
        self._reloj.timeout.connect(self._tic)
        self._reloj.start()

    def _caja(self):
        """El lugar del bodegon como lo ponia la imagen de la maqueta: cubriendo la pagina, anclada abajo."""
        W, H = float(self.width()), float(self.height())
        esc = max(W / self.LIENZO[0], H / self.LIENZO[1])
        x, y, w, h = self.CAJA
        return QRectF(x * esc, H - self.LIENZO[1] * esc + y * esc, w * esc, h * esc)

    def _tic(self):
        if self._peli is not None:
            ver = self.isVisible() and not self.window().isMinimized()
            self._peli.pausar(not ver)
            self._peli.lento(not self.window().isActiveWindow())

    def showEvent(self, e):
        super().showEvent(e)
        if self._peli is None:
            QTimer.singleShot(400, self._video)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._peli is not None:
            self._t_tam.start()

    def _video(self):
        ruta = animacion.ruta("bodegon.mp4")
        if not ruta:
            return
        if self._peli is None:
            self._peli = animacion.Pelicula(self._al_cuadro, None, self)
        r, dpr = self._caja(), self.devicePixelRatioF()
        w, h = int(r.width() * dpr) // 2 * 2, int(r.height() * dpr) // 2 * 2
        if self._peli.ruta and self._peli.tam == (w, h):
            return
        self._peli.reproducir(ruta, w, h, fps=24, bucle=True, alfa=True)

    def _al_cuadro(self, img, datos):
        self._cuadro = (img, datos)
        self.update(self._caja().toAlignedRect().adjusted(-2, -2, 2, 2))

    def paintEvent(self, _):
        r = self._caja()
        p = QPainter(self)
        if self._cuadro is not None:
            img = self._cuadro[0]
            dpr = self.devicePixelRatioF()
            if abs(img.width() / dpr - r.width()) < 2.5 and abs(img.height() / dpr - r.height()) < 2.5:
                p.drawImage(QRectF(r.left(), r.top(), img.width() / dpr, img.height() / dpr), img)
            else:
                p.setRenderHint(QPainter.SmoothPixmapTransform)
                p.drawImage(r, img)
            return
        if self.img.isNull():
            return
        dpr = self.devicePixelRatioF()
        clave = (self.width(), self.height(), dpr)
        if self._cache is None or self._cache[0] != clave:
            pm = QPixmap.fromImage(self.img.scaled(int(r.width() * dpr), int(r.height() * dpr), Qt.IgnoreAspectRatio,
                                                   Qt.SmoothTransformation))
            pm.setDevicePixelRatio(dpr)
            self._cache = (clave, pm)
        p.drawPixmap(r.topLeft(), self._cache[1])


class VistaTitulo(QWidget):
    """La vista previa en vivo del titulo (Textos), como la maqueta: la foto de fondo y, a la derecha, el nombre en
    letra de los titulos (Great Vibes) en oro, el adorno y la frase en mayusculas espaciadas."""
    _familias = None

    def __init__(self, carpeta_fuentes, parent=None):
        super().__init__(parent)
        self.carpeta = carpeta_fuentes
        self.fondo = None
        self.modo = "titulo"
        self.textos = {}
        self.setMinimumSize(320, 200)
        sp = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        # (1.6.0) viva, como el titulo en el video: la foto con un zoom lento (Ken Burns) y el texto que aparece
        self._t_modo = time.monotonic()
        self._base = None                             # (ancho, alto, dpr, QPixmap) la foto ya escalada
        self._reloj = QTimer(self, interval=50)
        self._reloj.timeout.connect(self._tic)
        self._reloj.start()

    def _tic(self):
        if self.isVisible() and not self.window().isMinimized():
            self.update()

    def showEvent(self, e):
        super().showEvent(e)
        self._t_modo = time.monotonic()               # al entrar a Textos el titulo aparece

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return int(w * 0.625)                         # 1312 x 820 en la maqueta

    def _fuentes(self):
        if VistaTitulo._familias is None:
            fid = QFontDatabase.addApplicationFont(os.path.join(self.carpeta, "GreatVibes-Regular.ttf"))
            fam = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
            VistaTitulo._familias = (fam[0] if fam else "Segoe Script", "Georgia")
        return VistaTitulo._familias

    def poner_fondo(self, pm):
        self.fondo = pm if pm is not None and not pm.isNull() else None
        self._base = None
        self._t_modo = time.monotonic()
        self.update()

    def poner(self, modo=None, **textos):
        if modo and modo != self.modo:
            self._t_modo = time.monotonic()           # otro titulo: aparece de nuevo
        if modo:
            self.modo = modo
        self.textos.update(textos)
        self.update()

    def _oro(self, p, texto, fuente, cx, cy, ancho_max):
        camino = QPainterPath()
        camino.addText(0, 0, fuente, texto)
        caja = camino.boundingRect()
        esc = min(1.0, ancho_max / max(1.0, caja.width()))
        p.save()
        p.translate(cx - caja.center().x() * esc, cy - caja.center().y() * esc)
        p.scale(esc, esc)
        g = QLinearGradient(0, caja.top(), 0, caja.bottom())
        g.setColorAt(0.0, QColor("#FFF3D2"))
        g.setColorAt(0.45, QColor("#EFC979"))
        g.setColorAt(1.0, QColor("#B9862F"))
        p.setPen(Qt.NoPen)
        p.fillPath(camino.translated(2, 3), QColor(0, 0, 0, 90))
        p.fillPath(camino, g)
        u = (time.monotonic() - self._t_modo - 0.5) % 7.0 / 1.6     # una luz cruza el nombre cada 7 s
        if 0.0 < u < 1.0:
            u = _suave(u)
            bw = caja.height() * 0.6
            xc = caja.left() - bw + (caja.width() + 2 * bw) * u
            yc = caja.center().y()
            luz = QLinearGradient(QPointF(xc - bw, yc - bw * 0.4), QPointF(xc + bw, yc + bw * 0.4))
            luz.setColorAt(0.0, QColor(255, 250, 230, 0))
            luz.setColorAt(0.5, QColor(255, 252, 240, 200))
            luz.setColorAt(1.0, QColor(255, 250, 230, 0))
            p.fillPath(camino, luz)
        p.restore()

    def _caps(self, p, texto, fuente, cx, cy, color=ORO_CLARO, espacio=175):
        f = QFont(fuente)
        f.setLetterSpacing(QFont.PercentageSpacing, espacio)
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(QRectF(cx - self.width(), cy - 40, self.width() * 2, 80), Qt.AlignCenter, texto)

    def _flor(self, p, cx, cy, k, ancho):
        p.setPen(QPen(QColor(226, 176, 79, 200), max(1.0, k * 0.06)))
        p.drawLine(QPointF(cx - ancho, cy), QPointF(cx - k * 0.9, cy))
        p.drawLine(QPointF(cx + k * 0.9, cy), QPointF(cx + ancho, cy))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#EBC271"))
        for ang in (-35, 0, 35):                      # tres petalos (la flor de lis de la maqueta)
            p.save()
            p.translate(cx, cy + k * 0.15)
            p.rotate(ang)
            petalo = QPainterPath()
            petalo.moveTo(0, 0)
            petalo.cubicTo(-k * 0.28, -k * 0.35, -k * 0.12, -k * 0.75, 0, -k * 0.85)
            petalo.cubicTo(k * 0.12, -k * 0.75, k * 0.28, -k * 0.35, 0, 0)
            p.drawPath(petalo)
            p.restore()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect())
        marco = QPainterPath()
        marco.addRoundedRect(r, px(22), px(22))
        p.setClipPath(marco)
        ahora = time.monotonic()
        if self.fondo is not None:
            dpr = self.devicePixelRatioF()
            if self._base is None or self._base[:3] != (self.width(), self.height(), dpr):
                pm = self.fondo                       # la foto escalada una vez (con margen para el zoom)
                esc = max(r.width() / pm.width(), r.height() / pm.height()) * 1.10
                base = pm.scaled(int(pm.width() * esc * dpr), int(pm.height() * esc * dpr), Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation)
                base.setDevicePixelRatio(dpr)
                self._base = (self.width(), self.height(), dpr, base)
            base = self._base[3]
            bw, bh = base.width() / dpr, base.height() / dpr
            u = 0.5 - 0.5 * math.cos(ahora * math.tau / 16.0)          # ida y vuelta en 16 s
            z = (1.0 + 0.09 * u) / 1.10                                 # de 100 % a 109 % de la vista
            tw, th = bw * z, bh * z
            dx, dy = (r.width() - tw) / 2 + (tw - r.width()) * 0.25 * (u - 0.5), (r.height() - th) / 2
            p.drawPixmap(QRectF(dx, dy, tw, th), base, QRectF(base.rect()))
        else:
            g = QLinearGradient(0, 0, 0, r.height())
            g.setColorAt(0.0, QColor("#2A1A22"))
            g.setColorAt(1.0, QColor("#0B0F14"))
            p.fillRect(r, g)
        # el lado del titulo un poco mas oscuro para que se lea (como el velo de los titulos del video)
        vel = QLinearGradient(0, 0, r.width(), 0)
        vel.setColorAt(0.0, QColor(0, 0, 0, 0))
        vel.setColorAt(0.45, QColor(0, 0, 0, 40))
        vel.setColorAt(1.0, QColor(0, 0, 0, 120))
        p.fillRect(r, vel)
        script, serif = self._fuentes()
        h, w = r.height(), r.width()
        cx = w * 0.69
        fs = QFont(script)
        fs.setPixelSize(max(20, int(h * 0.30)))
        fsub = QFont(serif)
        fsub.setPixelSize(max(9, int(h * 0.052)))
        t = self.textos
        k = 1.0 - (1.0 - min(1.0, max(0.0, (ahora - self._t_modo) / 1.1))) ** 3   # el texto aparece (1,1 s)
        p.translate(0, (1.0 - k) * h * 0.035)
        p.setOpacity(k)
        esp = 120 + 55 * k                            # las mayusculas se abren al aparecer
        flor = w * 0.14 * (0.15 + 0.85 * k)           # y las lineas de la flor crecen desde el centro
        if self.modo == "capitulo":
            self._caps(p, (t.get("capitulo_n") or "CAPÍTULO I").upper(), fsub, cx, h * 0.33, espacio=esp)
            self._oro(p, t.get("capitulo") or "Los preparativos", fs, cx, h * 0.52, w * 0.56)
        elif self.modo == "gracias":
            self._oro(p, "Gracias", fs, cx, h * 0.44, w * 0.56)
            self._flor(p, cx, h * 0.585, h * 0.03, flor)
            fg = QFont(fsub)
            fg.setPixelSize(max(8, int(h * 0.036)))
            self._caps(p, (t.get("gracias") or "").upper(), fg, cx, h * 0.66, espacio=esp)
        elif self.modo == "final":
            self._oro(p, t.get("nombre") or "Valeria", fs, cx, h * 0.44, w * 0.56)
            self._flor(p, cx, h * 0.585, h * 0.03, flor)
            self._caps(p, t.get("fecha") or "", fsub, cx, h * 0.66, espacio=esp)
        else:
            self._oro(p, t.get("nombre") or "Valeria", fs, cx, h * 0.44, w * 0.58)
            self._flor(p, cx, h * 0.585, h * 0.03, flor)
            self._caps(p, (t.get("frase") or "").upper(), fsub, cx, h * 0.66, espacio=esp)
        p.setOpacity(1.0)
        p.resetTransform()
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 34), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), px(22), px(22))
