# -*- coding: utf-8 -*-
"""
plantillas_ui.py - (18-nov) Material > «Plantillas de video»: las plantillas de referencia (plantilla_ref.py) en
tarjetas con su portada; clic = usarla / dejarla (varias a la vez); soltar un video encima = convertirlo en plantilla.

La persona (18-nov): «crea una sección para escoger qué plantilla quiero usar en la página de Material».

    PlantillasRef.poner([info])        las plantillas (plantilla_ref.lista())
    PlantillasRef.elegidas([nombres])  las marcadas (estado plantillas_ref)
    señal cambio(list)                 la persona marco o desmarco una
    señal soltado(list)                videos soltados encima (para importar)
Animada: las tarjetas entran en cascada, se elevan al pasar el raton y la marca verde crece al elegir.
"""
import os
import time

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget

import piezas
from piezas import px

VERDE = QColor("#2BD68A")
TENUE = QColor("#9DB0B6")
VIDEO_EXT = (".mov", ".mp4", ".m4v", ".mkv", ".avi", ".webm")


class PlantillasRef(QWidget):
    cambio = Signal(list)
    soltado = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.infos, self.marcadas = [], set()
        self._portadas, self._celdas = {}, []
        self._sobre, self._t0, self._encima = None, time.monotonic(), False
        self._anim = {}                        # nombre -> (cuando cambio, marcada)
        self._reloj = QTimer(self, interval=getattr(piezas, "CUADRO_MS", 16))
        self._reloj.timeout.connect(self._tic)
        self.CW, self.CH = px(210), px(373)     # 9:16
        self.setMinimumHeight(self.CH + px(110))

    def poner(self, infos):
        self.infos = list(infos or [])
        for d in self.infos:
            ruta = os.path.join(d.get("carpeta", ""), "portada.jpg")
            if d["nombre"] not in self._portadas and os.path.exists(ruta):
                self._portadas[d["nombre"]] = QPixmap(ruta)
        self._t0 = time.monotonic()
        self._acomodar()
        self._reloj.start()

    def elegidas(self, nombres):
        self.marcadas = set(nombres or [])
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._acomodar()

    def _acomodar(self):
        w = max(px(400), self.width())
        sep = px(22)
        cols = max(1, int((w + sep) // (self.CW + sep)))
        self._celdas = []
        for n, d in enumerate(self.infos):
            self._celdas.append((QRectF((n % cols) * (self.CW + sep), (n // cols) * (self.CH + px(90)) + px(8),
                                        self.CW, self.CH), d))
        filas = max(1, (len(self.infos) + cols - 1) // cols)
        self.setMinimumHeight(int(filas * (self.CH + px(90)) + px(20)))
        self.update()

    def _tic(self):
        ahora = time.monotonic()
        vivo = ahora - self._t0 < 1.0 or self._sobre is not None or self._encima or \
            any(ahora - t < 0.4 for t, _m in self._anim.values())
        if not vivo or not self.isVisible():
            self._reloj.stop()
        self.update()

    def _fuente(self, tam, peso=QFont.Normal):
        f = QFont(self.font())
        f.setPixelSize(max(9, px(tam)))
        f.setWeight(peso)
        return f

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        ahora = time.monotonic()
        if not self.infos:
            p.setFont(self._fuente(24))
            p.setPen(TENUE)
            p.drawText(self.rect(), Qt.AlignCenter, "Suelta aquí un video (Reel, TikTok, CapCut) para convertirlo en "
                                                    "plantilla: sus cortes y su música.")
        for n, (r, d) in enumerate(self._celdas):
            k = min(1.0, max(0.0, (ahora - self._t0 - 0.06 * n) / 0.35))           # entrada en cascada
            if k <= 0:
                continue
            sobre = self._sobre is d
            alza = px(8) if sobre else 0.0
            rr = r.translated(0, -alza + (1.0 - k) * px(30))
            p.setOpacity(1.0 - (1.0 - k) ** 3)
            marco = QPainterPath()
            marco.addRoundedRect(rr, px(18), px(18))
            p.save()
            p.setClipPath(marco)
            pm = self._portadas.get(d["nombre"])
            if pm is not None and not pm.isNull():
                esc = max(rr.width() / pm.width(), rr.height() / pm.height())
                tw, th = pm.width() * esc, pm.height() * esc
                p.drawPixmap(QRectF(rr.center().x() - tw / 2, rr.center().y() - th / 2, tw, th), pm, QRectF(pm.rect()))
            else:
                p.fillRect(rr, QColor(18, 38, 46))
            p.restore()
            marcada = d["nombre"] in self.marcadas
            t_cambio, _m = self._anim.get(d["nombre"], (0.0, marcada))
            crece = min(1.0, (ahora - t_cambio) / 0.3)
            p.setPen(QPen(VERDE if marcada else (QColor("#FFFFFF") if sobre else QColor(255, 255, 255, 60)),
                          px(5) if marcada else px(3)))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rr, px(18), px(18))
            if marcada:                                  # la marca verde crece al elegirla
                rad = px(26) * (0.6 + 0.4 * crece)
                c = QPointF(rr.right() - px(34), rr.top() + px(34))
                p.setPen(Qt.NoPen)
                p.setBrush(VERDE)
                p.drawEllipse(c, rad, rad)
                p.setPen(QPen(QColor("#06261A"), px(5), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPolyline([QPointF(c.x() - rad * 0.42, c.y()), QPointF(c.x() - rad * 0.1, c.y() + rad * 0.32),
                                QPointF(c.x() + rad * 0.45, c.y() - rad * 0.35)])
            p.setFont(self._fuente(24, QFont.DemiBold))
            p.setPen(QColor("#F1F5F6"))
            p.drawText(QRectF(rr.left(), rr.bottom() + px(10), rr.width(), px(32)), Qt.AlignHCenter | Qt.AlignVCenter,
                       d["nombre"].title())
            p.setFont(self._fuente(19))
            p.setPen(TENUE)
            n_planos = len(d.get("planos") or [])
            # (19-nov, visto en la ventana) «25 s · 10 planos · vertical» no cabia y se cortaba por los dos lados
            p.drawText(QRectF(rr.left() - px(20), rr.bottom() + px(42), rr.width() + px(40), px(28)),
                       Qt.AlignHCenter | Qt.AlignVCenter, "%.0f s · %d planos" % (d.get("dur", 0), n_planos))
        p.setOpacity(1.0)
        if self._encima:                                 # soltando un video: borde que respira
            brillo = 0.5 + 0.5 * abs(((ahora * 1.4) % 2.0) - 1.0)
            c = QColor(VERDE)
            c.setAlphaF(0.35 + 0.5 * brillo)
            p.setPen(QPen(c, px(4), Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(px(3), px(3), -px(3), -px(3)), px(20), px(20))

    def _en(self, pos):
        return next((d for r, d in self._celdas if r.contains(pos)), None)

    def mouseMoveEvent(self, e):
        d = self._en(e.position())
        self.setCursor(Qt.PointingHandCursor if d is not None else Qt.ArrowCursor)
        if d is not self._sobre:
            self._sobre = d
            self._reloj.start()
            self.update()

    def leaveEvent(self, _):
        self._sobre = None
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        d = self._en(e.position())
        if d is None:
            return
        n = d["nombre"]
        if n in self.marcadas:
            self.marcadas.discard(n)
        else:
            self.marcadas.add(n)
        self._anim[n] = (time.monotonic(), n in self.marcadas)
        self._reloj.start()
        self.cambio.emit(sorted(self.marcadas))
        self.update()

    # soltar videos
    def _videos(self, e):
        return [u.toLocalFile() for u in (e.mimeData().urls() or []) if u.toLocalFile().lower().endswith(VIDEO_EXT)]

    def dragEnterEvent(self, e):
        if self._videos(e):
            e.acceptProposedAction()
            self._encima = True
            self._reloj.start()

    def dragLeaveEvent(self, _):
        self._encima = False
        self.update()

    def dropEvent(self, e):
        self._encima = False
        v = self._videos(e)
        if v:
            e.acceptProposedAction()
            self.soltado.emit(v)
        self.update()
