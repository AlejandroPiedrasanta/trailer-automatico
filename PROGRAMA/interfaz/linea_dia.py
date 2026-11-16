# -*- coding: utf-8 -*-
"""
linea_dia.py - La linea del dia del evento (pagina Material): cada foto y cada video en su hora, pintado con el color
de su momento (MAQUILLAJE morado, IGLESIA verde, FIESTA rosa), con los inicios de IGLESIA y FIESTA para arrastrar.

  LineaDia.poner(items, fecha, momentos)   items del analisis (analizar_material), momentos [[MOMENTO, "HH:MM"], ...]
  LineaDia.limites_cambiados(dict)         al soltar un limite: {"IGLESIA": "15:32", "FIESTA": "18:16"}
  LineaDia.cuentas_vivas(dict)             mientras se arrastra: {momento: (fotos, videos, minutos)}

Lo clasificado por CONTENIDO (camara sin hora) se pinta hueco; lo puesto a mano, con borde blanco.
"""
import datetime

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QPainterPath, QPixmap, QPolygonF
from PySide6.QtWidgets import QWidget, QToolTip

MOMENTOS = ("MAQUILLAJE", "IGLESIA", "FIESTA")
COLOR = {"MAQUILLAJE": QColor("#A67CF2"), "IGLESIA": QColor("#22C47E"), "FIESTA": QColor("#F06AAE")}
NOMBRE = {"MAQUILLAJE": "Maquillaje", "IGLESIA": "Iglesia", "FIESTA": "Fiesta"}
CARRILES = (("foto", "Fotos"), ("video", "Videos"), ("dron", "Dron"))
TENUE = QColor("#8FA3A8")


def _a_min(hhmm):
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def hhmm(minutos):
    minutos = int(round(minutos))
    return "%02d:%02d" % ((minutos // 60) % 24, minutos % 60)


class LineaDia(QWidget):
    limites_cambiados = Signal(dict)
    cuentas_vivas = Signal(dict)

    IZQ, DER, ARRIBA, EJE = 70, 18, 40, 26

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(self.ARRIBA + 3 * 30 + self.EJE + 8)
        self.setMouseTracking(True)
        self.items = []             # dicts: m (minuto), tipo, dur (min), momento, nombre, por, tramos
        self.limites = {}           # {"IGLESIA": minuto, "FIESTA": minuto}
        self.rango = (0.0, 1440.0)
        self.editable = True
        self._arrastra = None
        self._sobre = None
        self._version = 0           # cambia con los datos: la imagen guardada deja de valer
        self._imagen = None         # (clave, QPixmap) de lo ultimo pintado

    # ------------------------------------------------------------------ datos
    def poner(self, items, fecha, momentos):
        self._version += 1
        self.items = []
        self.limites = {}
        if not items or not fecha:
            self.update()
            return
        base = datetime.datetime.combine(datetime.date.fromisoformat(fecha), datetime.time())
        for i in items:
            if i.get("descartar"):
                continue
            try:
                m = (datetime.datetime.fromisoformat(i["hora"]) - base).total_seconds() / 60.0
            except (KeyError, ValueError):
                continue
            self.items.append({"m": m, "tipo": i["tipo"], "dur": i.get("dur", 0) / 60.0 if i["tipo"] != "foto" else 0.0,
                               "momento": i.get("momento"), "nombre": i["nombre"], "por": i.get("por", "hora"),
                               "tramos": i.get("tramos"), "seg": i.get("dur", 0)})
        for mom, h in momentos or []:
            if mom in ("IGLESIA", "FIESTA"):
                try:
                    self.limites[mom] = float(_a_min(h))
                except ValueError:
                    pass
        if self.items:
            lo = min(x["m"] for x in self.items)
            hi = max(x["m"] + x["dur"] for x in self.items)
            for v in self.limites.values():
                lo, hi = min(lo, v), max(hi, v)
            pad = max(8.0, (hi - lo) * 0.03)
            self.rango = (lo - pad, hi + pad)
        self.update()

    def momento_de(self, it):
        """Lo clasificado por hora sigue a los limites (aunque se esten arrastrando); lo demas queda como esta."""
        if it["por"] != "hora" or not self.limites:
            return it["momento"]
        mom = "MAQUILLAJE"
        for nombre in ("IGLESIA", "FIESTA"):
            if nombre in self.limites and it["m"] >= self.limites[nombre]:
                mom = nombre
        return mom

    def cuentas(self):
        c = {m: [0, 0, 0.0] for m in MOMENTOS}
        for it in self.items:
            m = self.momento_de(it)
            if m not in c:
                continue
            if it["tipo"] == "foto":
                c[m][0] += 1
            else:
                c[m][1] += 1
                c[m][2] += it["dur"]
        return {m: tuple(v) for m, v in c.items()}

    # ------------------------------------------------------------------ geometria
    def _ancho(self):
        return max(10.0, self.width() - self.IZQ - self.DER)

    def x_de(self, m):
        r0, r1 = self.rango
        return self.IZQ + (m - r0) / max(1e-6, r1 - r0) * self._ancho()

    def m_de(self, x):
        r0, r1 = self.rango
        return r0 + (x - self.IZQ) / self._ancho() * (r1 - r0)

    def _carril(self):
        """Alto de cada carril (fotos, videos, dron): crece con la ventana, entre 30 y 64 px."""
        return max(30.0, min(64.0, (self.height() - self.ARRIBA - self.EJE - 8) / 3.0))

    def _y_carril(self, k):
        return self.ARRIBA + k * self._carril()

    # ------------------------------------------------------------------ pintura
    def paintEvent(self, _):
        """Cientos de puntos y barras: se dibujan UNA vez en una imagen y despues solo se copia. Antes se redibujaba
        todo cada vez que el cielo de fondo parpadeaba (13 veces por segundo, 13 ms cada una: la pestana Material
        iba a tirones). La imagen se rehace al cambiar los datos, el tamano, los limites o el raton sobre un limite."""
        dpr = self.devicePixelRatioF()
        clave = (self.width(), self.height(), dpr, self._version, self._arrastra, self._sobre, self.editable,
                 tuple(sorted(self.limites.items())), self.font().key())
        if self._imagen is None or self._imagen[0] != clave:
            pm = QPixmap(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            try:
                self._pintar(q)
            finally:
                q.end()
            self._imagen = (clave, pm)
        QPainter(self).drawPixmap(0, 0, self._imagen[1])

    def _pintar(self, p):
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        alto = 3 * self._carril()
        caja = QRectF(self.IZQ, self.ARRIBA, self._ancho(), alto)
        f = QFont(self.font())
        f.setPointSizeF(max(7.5, f.pointSizeF() * 0.82))
        f.setBold(True)
        p.setFont(f)
        if not self.items:
            p.setPen(TENUE)
            p.drawText(QRectF(0, 0, w, self.height()), Qt.AlignCenter, "Sin analizar todavía")
            return
        # bandas de cada momento
        cortes = [self.rango[0]] + [self.limites[m] for m in ("IGLESIA", "FIESTA") if m in self.limites] + [self.rango[1]]
        noms = ["MAQUILLAJE"] + [m for m in ("IGLESIA", "FIESTA") if m in self.limites]
        camino = QPainterPath()
        camino.addRoundedRect(caja, 12, 12)
        p.save()
        p.setClipPath(camino)
        for (a, b), mom in zip(zip(cortes, cortes[1:]), noms):
            c = QColor(COLOR[mom])
            c.setAlpha(34)
            p.fillRect(QRectF(self.x_de(a), caja.top(), self.x_de(b) - self.x_de(a), alto), c)
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(caja, 12, 12)
        # carriles
        for k, (tipo, txt) in enumerate(CARRILES):
            y = self._y_carril(k)
            if k:
                p.setPen(QPen(QColor(255, 255, 255, 18), 1, Qt.DashLine))
                p.drawLine(QPointF(self.IZQ + 6, y), QPointF(self.IZQ + self._ancho() - 6, y))
            p.setPen(TENUE)
            p.drawText(QRectF(0, y, self.IZQ - 10, self._carril()), Qt.AlignVCenter | Qt.AlignRight, txt)
        # eje de horas
        r0, r1 = self.rango
        paso = next(s for s in (15, 30, 60, 120, 180, 240) if (r1 - r0) / s <= max(3, self._ancho() / 90))
        t = (int(r0) // paso + 1) * paso
        y_eje = self.ARRIBA + alto
        while t < r1:
            x = self.x_de(t)
            p.setPen(QPen(QColor(255, 255, 255, 40), 1))
            p.drawLine(QPointF(x, y_eje), QPointF(x, y_eje + 5))
            p.setPen(TENUE)
            p.drawText(QRectF(x - 30, y_eje + 5, 60, self.EJE - 5), Qt.AlignHCenter | Qt.AlignTop, hhmm(t))
            t += paso
        # material
        barra = max(12.0, min(22.0, self._carril() * 0.42))
        for it in self.items:
            k = {"foto": 0, "video": 1, "dron": 2}.get(it["tipo"], 1)
            yc = self._y_carril(k) + self._carril() / 2.0
            mom = self.momento_de(it)
            col = QColor(COLOR.get(mom, TENUE))
            hueco = it["por"] == "contenido"
            if it["tipo"] == "foto":
                col.setAlpha(150)
                p.setPen(QPen(col, 1.4) if hueco else Qt.NoPen)
                p.setBrush(Qt.NoBrush if hueco else QBrush(col))
                jit = (sum(map(ord, it["nombre"])) % 9 - 4) / 4.0 * self._carril() * 0.28   # para que una rafaga no sea un solo punto
                p.drawEllipse(QPointF(self.x_de(it["m"]), yc + jit), 2.6, 2.6)
            else:
                partes = [(a / 60.0, b / 60.0, m) for a, b, m in it["tramos"]] if it.get("tramos") and it["por"] == "hora" \
                    else [(0.0, it["dur"], mom)]
                for a, b, m in partes:
                    c = QColor(COLOR.get(m if it.get("tramos") else mom, TENUE))
                    c.setAlpha(205)
                    x0, x1 = self.x_de(it["m"] + a), self.x_de(it["m"] + b)
                    r = QRectF(x0, yc - barra / 2, max(3.0, x1 - x0), barra)
                    p.setPen(QPen(c, 1.4) if hueco else QPen(QColor(0, 0, 0, 60), 0.8))
                    p.setBrush(Qt.NoBrush if hueco else QBrush(c))
                    p.drawRoundedRect(r, 3, 3)
                if it["por"] == "manual":
                    p.setPen(QPen(QColor("#FFFFFF"), 1.2))
                    p.setBrush(Qt.NoBrush)
                    x0, x1 = self.x_de(it["m"]), self.x_de(it["m"] + it["dur"])
                    p.drawRoundedRect(QRectF(x0 - 1, yc - barra / 2 - 1, max(5.0, x1 - x0 + 2), barra + 2), 3, 3)
        # limites para arrastrar
        for mom in ("IGLESIA", "FIESTA"):
            if mom not in self.limites:
                continue
            x = self.x_de(self.limites[mom])
            activo = self._arrastra == mom or self._sobre == mom
            p.setPen(QPen(QColor(255, 255, 255, 230 if activo else 150), 2 if activo else 1.4))
            p.drawLine(QPointF(x, self.ARRIBA - 4), QPointF(x, self.ARRIBA + alto))
            txt = "%s  %s" % (NOMBRE[mom], hhmm(self.limites[mom]))
            fm = p.fontMetrics()
            ancho = fm.horizontalAdvance(txt) + 26
            pill = QRectF(min(max(x - ancho / 2, 2), w - ancho - 2), 4, ancho, 24)
            c = QColor(COLOR[mom])
            p.setPen(QPen(QColor(255, 255, 255, 200 if activo else 60), 1))
            p.setBrush(c if activo else QColor(c.red(), c.green(), c.blue(), 200))
            p.drawRoundedRect(pill, 12, 12)
            p.setPen(QColor("#04150D"))
            p.drawText(pill.adjusted(16, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, txt)
            # agarradera: dos rayitas
            p.setPen(QPen(QColor(4, 21, 13, 160), 1.2))
            for dx in (8, 11):
                p.drawLine(QPointF(pill.left() + dx, pill.top() + 7), QPointF(pill.left() + dx, pill.bottom() - 7))
            tri = QPolygonF([QPointF(x - 5, pill.bottom()), QPointF(x + 5, pill.bottom()), QPointF(x, pill.bottom() + 6)])
            p.setPen(Qt.NoPen)
            p.drawPolygon(tri)

    # ------------------------------------------------------------------ raton
    def _limite_en(self, pos):
        if not self.editable:
            return None
        mejor = None
        for mom in ("IGLESIA", "FIESTA"):
            if mom in self.limites:
                d = abs(pos.x() - self.x_de(self.limites[mom]))
                cerca = d <= 9 or (pos.y() <= 30 and d <= 60)
                if cerca and (mejor is None or d < mejor[0]):
                    mejor = (d, mom)
        return mejor[1] if mejor else None

    def mousePressEvent(self, e):
        mom = self._limite_en(e.position())
        if mom and e.button() == Qt.LeftButton:
            self._arrastra = mom
            self.update()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._arrastra:
            m = round(self.m_de(pos.x()))
            lo, hi = self.rango
            if self._arrastra == "IGLESIA":
                hi = self.limites.get("FIESTA", hi) - 1
            else:
                lo = self.limites.get("IGLESIA", lo) + 1
            self.limites[self._arrastra] = float(min(max(m, lo), hi))
            self.cuentas_vivas.emit(self.cuentas())
            self.update()
            return
        sobre = self._limite_en(pos)
        if sobre != self._sobre:
            self._sobre = sobre
            self.setCursor(Qt.SizeHorCursor if sobre else Qt.ArrowCursor)
            self.update()
        if not sobre:
            self._mostrar_ayuda(e)

    def mouseReleaseEvent(self, e):
        if self._arrastra:
            self._arrastra = None
            self.update()
            self.limites_cambiados.emit({m: hhmm(v) if v < 1440 else "%02d:%02d" % (int(v) // 60, int(v) % 60)
                                         for m, v in self.limites.items()})
            return
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e):
        self._sobre = None
        self.update()
        super().leaveEvent(e)

    def _mostrar_ayuda(self, e):
        pos = e.position()
        k = int((pos.y() - self.ARRIBA) // self._carril())
        if not 0 <= k < 3:
            QToolTip.hideText()
            return
        tipo = CARRILES[k][0]
        cerca = None
        for it in self.items:
            if it["tipo"] != tipo:
                continue
            x0, x1 = self.x_de(it["m"]), self.x_de(it["m"] + it["dur"])
            d = 0 if x0 - 3 <= pos.x() <= x1 + 3 else min(abs(pos.x() - x0), abs(pos.x() - x1))
            if d <= 5 and (cerca is None or d < cerca[0]):
                cerca = (d, it)
        if cerca is None:
            QToolTip.hideText()
            return
        it = cerca[1]
        extra = {"contenido": " · ordenado por contenido (su cámara no tenía buena hora)",
                 "manual": " · puesto a mano"}.get(it["por"], "")
        dur = " · %d s" % round(it["seg"]) if it["tipo"] != "foto" else ""
        QToolTip.showText(e.globalPosition().toPoint(), "%s\n%s · %s%s%s" % (
            it["nombre"], hhmm(it["m"]), NOMBRE.get(self.momento_de(it), "?"), dur, extra), self)
