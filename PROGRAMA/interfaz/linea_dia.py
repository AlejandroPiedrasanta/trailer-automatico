# -*- coding: utf-8 -*-
"""
linea_dia.py - La «Línea del día» del evento (página Material), IGUAL a la maqueta de Higgsfield (1.6.0,
docs/capturas/propuesta_2_material.png): un carril por momento (Maquillaje morado, Iglesia verde, Fiesta rosa) con su
bloque de color e icono, las miniaturas de las tomas en su hora, y abajo los momentos clave (beso, anillos, aplausos,
pastel) unidos con una linea punteada dorada a la toma donde pasan. Las medidas son las de la maqueta (piezas.px).

  LineaDia.poner(items, fecha, momentos)   items del analisis, momentos [[MOMENTO, "HH:MM"], ...]
  LineaDia.poner_minis({ruta: QPixmap})    las miniaturas (miniaturas.py, en un hilo)
  LineaDia.pide_minis([(ruta, tipo, t)])   las que faltan para lo que se ve
  LineaDia.toma_movida(nombre, momento)    se arrastro una toma a otro carril («Arrastra una toma para cambiarla de
                                           momento»): la ventana la guarda como excepcion a mano
  LineaDia.limites_cambiados(dict)         se arrastro el rombo de inicio de Iglesia o Fiesta
  LineaDia.cuentas_vivas(dict)             mientras se arrastra: {momento: (fotos, videos, minutos)}
"""
import datetime
import math
import time

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPainterPath, QPixmap, QLinearGradient, QRadialGradient
from PySide6.QtWidgets import QWidget, QToolTip

import piezas
from piezas import px

MOMENTOS = ("MAQUILLAJE", "IGLESIA", "FIESTA")
COLOR = {"MAQUILLAJE": QColor("#8B57E0"), "IGLESIA": QColor("#1FA36A"), "FIESTA": QColor("#E0559A")}
COLOR_OSCURO = {"MAQUILLAJE": QColor("#5B33A8"), "IGLESIA": QColor("#0F7A4D"), "FIESTA": QColor("#A82E6C")}
NOMBRE = {"MAQUILLAJE": "Maquillaje", "IGLESIA": "Iglesia", "FIESTA": "Fiesta"}
ICONO = {"MAQUILLAJE": "pincel", "IGLESIA": "iglesia", "FIESTA": "fiesta"}
TENUE = QColor("#8FA3A8")
# momentos clave (etiquetas de vision_ia y «aplausos» del oido): texto e icono
CLAVES = {"entrada": ("Entrada", "brillo"), "anillos": ("Anillos", "anillo"), "votos": ("Votos", "anillo"),
          "beso": ("Beso", "corazon"), "aplausos": ("Aplausos", "aplausos"), "brindis": ("Brindis", "copa"),
          "primer_baile": ("Primer baile", "nota"), "pastel": ("Pastel", "pastel")}


def _a_min(hhmm):
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def hhmm(minutos):
    minutos = int(round(minutos))
    return "%02d:%02d" % ((minutos // 60) % 24, minutos % 60)


class LineaDia(QWidget):
    limites_cambiados = Signal(dict)
    cuentas_vivas = Signal(dict)
    pide_minis = Signal(list)
    toma_movida = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.items, self.limites, self.marcas = [], {}, []
        self.rango = (0.0, 1440.0)
        self.editable = True
        self.minis = {}
        self._pedidas = set()
        self._colocadas = []         # [(QRectF, item)]
        self._arrastra = None        # inicio de IGLESIA / FIESTA que se arrastra
        self._sobre = None
        self._toma = None            # (item, punto inicial) de la toma que se empieza a arrastrar
        self._llevando = None        # (item, QPointF actual) mientras se lleva una toma
        self._version = 0
        self._imagen = None
        self._destellos = []         # (1.6.0) [(pastilla, punto de la toma, punto de la pastilla)] de los momentos clave
        self._reloj = QTimer(self, interval=33)
        self._reloj.timeout.connect(self._tic)
        self._reloj.start()
        self.reescalar()

    def _tic(self):
        if self.isVisible() and not self.window().isMinimized() and (self._destellos or self.items):
            self.update()

    def reescalar(self):
        self.IZQ, self.DER = px(300), px(40)
        self.ARRIBA, self.CARRIL, self.GAP, self.ABAJO = px(92), px(108), px(24), px(104)
        self.setMinimumHeight(self.ARRIBA + 3 * self.CARRIL + 2 * self.GAP + self.ABAJO)
        self._version += 1
        self.update()

    # ------------------------------------------------------------------ datos
    def poner(self, items, fecha, momentos):
        self._version += 1
        self.items, self.limites, self.marcas = [], {}, []
        if not items or not fecha:
            self.update()
            return
        base = datetime.datetime.combine(datetime.date.fromisoformat(fecha), datetime.time())
        primeras = {}
        for i in items:
            if i.get("descartar"):
                continue
            try:
                m = (datetime.datetime.fromisoformat(i["hora"]) - base).total_seconds() / 60.0
            except (KeyError, ValueError, TypeError):
                continue
            it = {"m": m, "tipo": i["tipo"], "dur": i.get("dur", 0) / 60.0 if i["tipo"] != "foto" else 0.0,
                  "momento": i.get("momento"), "nombre": i["nombre"], "por": i.get("por", "hora"),
                  "seg": i.get("dur", 0), "ruta": i.get("ruta")}
            self.items.append(it)
            for x in (i.get("ia") or {}).get("instantes") or []:          # lo que vio la IA, segundo a segundo
                if len(x) > 2 and x[2] is not False:
                    for k in x[1]:
                        t = m + x[0] / 60.0
                        if k in CLAVES and (k not in primeras or t < primeras[k][0]):
                            primeras[k] = (t, it)
            oido = i.get("oido") or {}
            ap, paso = oido.get("aplausos") or [], oido.get("paso")
            if ap and paso and max(ap) >= 0.45:                            # el aplauso mas claro de la toma
                j = max(range(len(ap)), key=lambda q: ap[q])
                t = m + (j * paso + oido.get("ventana", paso) / 2.0) / 60.0
                if "aplausos" not in primeras or t < primeras["aplausos"][0]:
                    primeras["aplausos"] = (t, it)
        self.marcas = sorted((t, k, it) for k, (t, it) in primeras.items())
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
            lo = (int(lo) // 60) * 60.0                                    # el eje empieza y acaba en hora redonda
            hi = (int(hi) // 60 + 1) * 60.0
            self.rango = (lo, max(hi, lo + 240.0))
        self.update()

    def poner_minis(self, minis):
        self.minis.update(minis)
        self._version += 1
        self.update()

    def momento_de(self, it):
        """Lo puesto a mano manda; lo clasificado por hora sigue a los limites (aunque se arrastren)."""
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

    def _y_carril(self, k):
        return self.ARRIBA + k * (self.CARRIL + self.GAP)

    def _carril_en(self, y):
        for k in range(3):
            y0 = self._y_carril(k)
            if y0 - self.GAP / 2 <= y <= y0 + self.CARRIL + self.GAP / 2:
                return k
        return None

    # ------------------------------------------------------------------ pintura
    def paintEvent(self, _):
        dpr = self.devicePixelRatioF()
        clave = (self.width(), self.height(), dpr, self._version, self._arrastra, self._sobre, self.editable,
                 tuple(sorted(self.limites.items())), self.font().key(),
                 None if self._llevando is None else self._carril_en(self._llevando[1].y()))
        if self._imagen is None or self._imagen[0] != clave:
            pm = QPixmap(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            self._destellos = []
            try:
                self._pintar(q)
            finally:
                q.end()
            self._imagen = (clave, pm)
        p = QPainter(self)
        p.drawPixmap(0, 0, self._imagen[1])
        self._pintar_vida(p)
        if self._llevando is not None:                   # la toma que se lleva, siguiendo al raton
            it, pos = self._llevando
            w, h = px(210), px(105)
            r = QRectF(pos.x() - w / 2, pos.y() - h / 2, w, h)
            p.setRenderHint(QPainter.Antialiasing)
            p.setOpacity(0.85)
            self._miniatura(p, it, r, QColor("#FFFFFF"))

    def _pintar_vida(self, p):
        """(1.6.0) Lo que se mueve encima del dibujo guardado: una luz recorre las horas y en cada momento clave una
        chispa baja por la linea punteada y la pastilla brilla (cada una a su tiempo)."""
        ahora = time.monotonic()
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        if self.items:
            u = (ahora % 11.0) / 3.2                   # la luz cruza los carriles cada 11 s
            if u < 1.0:
                x = self.IZQ + self._ancho() * u
                y0, y1 = self._y_carril(0), self._y_carril(2) + self.CARRIL
                g = QLinearGradient(QPointF(x - px(70), 0), QPointF(x + px(70), 0))
                g.setColorAt(0.0, QColor(255, 236, 190, 0))
                g.setColorAt(0.5, QColor(255, 236, 190, int(26 * math.sin(math.pi * u))))
                g.setColorAt(1.0, QColor(255, 236, 190, 0))
                p.fillRect(QRectF(x - px(70), y0, px(140), y1 - y0), g)
        p.setPen(Qt.NoPen)
        for i, (pill, arriba, abajo) in enumerate(self._destellos):
            fase = (ahora * 0.55 + i * 0.37) % 1.0
            y = arriba.y() + (abajo.y() - arriba.y()) * fase       # la chispa que baja hasta la pastilla
            g = QRadialGradient(QPointF(arriba.x(), y), px(14))
            g.setColorAt(0.0, QColor(255, 240, 200, int(220 * math.sin(math.pi * fase))))
            g.setColorAt(1.0, QColor(240, 190, 90, 0))
            p.setBrush(g)
            p.drawEllipse(QPointF(arriba.x(), y), px(14), px(14))
            lat = 0.5 + 0.5 * math.sin(ahora * 2.6 + i * 1.3)       # la pastilla late
            borde = QColor(246, 210, 122, int(40 + 90 * lat))
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(borde, max(1.0, px(5))))
            p.drawRoundedRect(pill.adjusted(-px(3), -px(3), px(3), px(3)), px(30), px(30))
            p.setPen(Qt.NoPen)
        p.restore()

    def _miniatura(self, p, it, r, borde):
        marco = QPainterPath()
        marco.addRoundedRect(r, px(10), px(10))
        pm = self.minis.get(it["ruta"])
        p.save()
        p.setClipPath(marco)
        if pm is not None and not pm.isNull():
            esc = max(r.width() / pm.width(), r.height() / pm.height())
            tw, th = pm.width() * esc, pm.height() * esc
            p.drawPixmap(QRectF(r.center().x() - tw / 2, r.center().y() - th / 2, tw, th), pm, QRectF(pm.rect()))
        else:
            p.fillRect(r, QColor(12, 28, 36))
        p.restore()
        p.setPen(QPen(borde, max(1.0, px(3))))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, px(10), px(10))
        c = QPointF(r.center().x(), r.bottom() - r.height() * 0.30)        # el play de la maqueta, abajo al centro
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 120))
        p.drawEllipse(c, px(22), px(22))
        p.drawPixmap(QPointF(c.x() - px(12), c.y() - px(13)), piezas.icono("play", "#FFFFFF", px(26)))

    def _pintar(self, p):
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w = self.width()
        f = QFont(self.font())
        f.setPixelSize(px(26))
        p.setFont(f)
        if not self.items:
            p.setPen(TENUE)
            f2 = QFont(f)
            f2.setPixelSize(px(32))
            p.setFont(f2)
            p.drawText(QRectF(0, 0, w, self.height()), Qt.AlignCenter,
                       "Todavía sin analizar: pulsa «Analizar ahora» o el botón de Inicio")
            return
        # eje de horas (cada 4 h, como la maqueta; menos si el dia es corto)
        r0, r1 = self.rango
        paso = next(s for s in (60, 120, 180, 240, 360) if (r1 - r0) / s <= 6)
        y_eje = self.ARRIBA - px(34)
        p.setPen(QPen(QColor(200, 215, 220, 110), max(1.0, px(2))))
        p.drawLine(QPointF(self.x_de(r0), y_eje), QPointF(self.x_de(r1), y_eje))
        t = r0
        while t <= r1 + 0.1:
            x = self.x_de(t)
            p.setPen(QPen(QColor(200, 215, 220, 150), max(1.0, px(2))))
            p.drawLine(QPointF(x, y_eje - px(12)), QPointF(x, y_eje + px(12)))
            p.setPen(QColor("#C8D3D6"))
            p.drawText(QRectF(x - px(80), y_eje - px(70), px(160), px(44)), Qt.AlignHCenter | Qt.AlignBottom, hhmm(t))
            t += paso
        destino = None if self._llevando is None else self._carril_en(self._llevando[1].y())
        # carriles: el bloque de color con icono y nombre, y el carril que se va apagando a la derecha
        fl = QFont(self.font())
        fl.setPixelSize(px(30))
        fl.setWeight(QFont.Bold)
        for k, mom in enumerate(MOMENTOS):
            y = self._y_carril(k)
            caja = QRectF(0, y, w - 2, self.CARRIL)
            c, co = COLOR[mom], COLOR_OSCURO[mom]
            g = QLinearGradient(caja.left(), 0, caja.right(), 0)
            g.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 95))
            g.setColorAt(0.5, QColor(co.red(), co.green(), co.blue(), 60))
            g.setColorAt(1.0, QColor(co.red(), co.green(), co.blue(), 35))
            borde = QColor(c)
            borde.setAlpha(230 if destino == k else 120)
            p.setPen(QPen(borde, max(1.0, px(3 if destino == k else 2))))
            p.setBrush(g)
            p.drawRoundedRect(caja, px(16), px(16))
            et = QRectF(0, y, px(258), self.CARRIL)
            ge = QLinearGradient(et.left(), 0, et.right(), 0)
            ge.setColorAt(0.0, co)
            ge.setColorAt(1.0, c)
            camino = QPainterPath()
            camino.addRoundedRect(et, px(16), px(16))
            p.setPen(Qt.NoPen)
            p.fillPath(camino, ge)
            p.drawPixmap(QPointF(et.left() + px(26), et.center().y() - px(26)),
                         piezas.icono(ICONO[mom], "#FFFFFF", px(52)))
            p.setFont(fl)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(et.adjusted(px(96), 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, NOMBRE[mom])
        p.setFont(f)
        # las tomas: miniaturas donde caben (en su hora), las fotos como puntos
        self._colocadas, faltan = [], []
        tw, th = float(px(210)), float(self.CARRIL - px(6))
        fin = {m: -1e9 for m in MOMENTOS}
        for it in sorted(self.items, key=lambda x: x["m"]):
            mom = self.momento_de(it)
            if mom not in fin:
                continue
            k = MOMENTOS.index(mom)
            y = self._y_carril(k)
            x = max(px(262), min(self.x_de(it["m"]), w - tw - px(4)))
            if it["tipo"] == "foto":
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 110))
                p.drawEllipse(QPointF(self.x_de(it["m"]), y + self.CARRIL - px(10)), px(3), px(3))
                continue
            if x < fin[mom] + px(14):
                x = fin[mom] + px(14)                    # en fila, como la maqueta, si cabe antes de la siguiente hora
                if x + tw > w - px(4) or x - self.x_de(it["m"]) > tw * 1.6:
                    continue
            r = QRectF(x, y + px(3), tw, th)
            fin[mom] = r.right()
            if self._llevando is not None and self._llevando[0] is it:
                continue
            self._miniatura(p, it, r, COLOR[mom])
            if it["por"] == "manual":
                p.setPen(QPen(QColor("#FFFFFF"), max(1.0, px(3))))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r.adjusted(-px(3), -px(3), px(3), px(3)), px(12), px(12))
            if it["ruta"] and it["ruta"] not in self.minis and it["ruta"] not in self._pedidas:
                faltan.append((it["ruta"], it["tipo"], None))
            self._colocadas.append((r, it))
        # inicios de IGLESIA y FIESTA: un rombo dorado en el eje (se arrastra)
        abajo = self._y_carril(2) + self.CARRIL
        for mom in ("IGLESIA", "FIESTA"):
            if mom not in self.limites:
                continue
            x = self.x_de(self.limites[mom])
            activo = self._arrastra == mom or self._sobre == mom
            if activo:
                p.setPen(QPen(QColor(226, 176, 79, 200), max(1.0, px(2)), Qt.DashLine))
                p.drawLine(QPointF(x, y_eje), QPointF(x, abajo))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(piezas.ORO))
            rombo = QPainterPath()
            d = px(15 if activo else 11)
            rombo.moveTo(x, y_eje - d)
            rombo.lineTo(x + d * 0.8, y_eje)
            rombo.lineTo(x, y_eje + d)
            rombo.lineTo(x - d * 0.8, y_eje)
            rombo.closeSubpath()
            p.drawPath(rombo)
            if activo:
                txt = "%s  %s" % (NOMBRE[mom], hhmm(self.limites[mom]))
                ancho = p.fontMetrics().horizontalAdvance(txt) + px(36)
                pill = QRectF(min(max(x - ancho / 2, 2), w - ancho - 2), y_eje + px(16), ancho, px(46))
                p.setBrush(COLOR[mom])
                p.drawRoundedRect(pill, px(23), px(23))
                p.setPen(QColor("#FFFFFF"))
                p.drawText(pill, Qt.AlignCenter, txt)
        # momentos clave: pastillas doradas abajo, unidas con linea punteada a su toma
        y_m = abajo + px(44)
        fm_f = QFont(self.font())
        fm_f.setPixelSize(px(31))
        p.setFont(fm_f)
        ultimo = -1e9
        self._destellos = []
        donde = {id(it): r for r, it in self._colocadas}
        for t, clave, it in self.marcas:
            if not self.rango[0] <= t <= self.rango[1]:
                continue
            texto, ic = CLAVES[clave]
            ancho = p.fontMetrics().horizontalAdvance(texto) + px(100)
            rt = donde.get(id(it))
            x = rt.center().x() if rt is not None else self.x_de(t)
            pill = QRectF(min(max(x - ancho / 2, px(262)), w - ancho - px(4)), y_m, ancho, px(54))
            if pill.left() < ultimo + px(20):
                continue
            ultimo = pill.right()
            y0 = rt.bottom() if rt is not None else self._y_carril(MOMENTOS.index(self.momento_de(it))) + self.CARRIL
            p.setPen(QPen(QColor(226, 176, 79, 210), max(1.0, px(3)), Qt.DotLine))
            p.drawLine(QPointF(x, y0 + px(2)), QPointF(x, y_m))
            self._destellos.append((pill, QPointF(x, y0 + px(2)), QPointF(x, y_m)))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#F3CF7A"))
            p.drawEllipse(QPointF(x, y_m), px(5), px(5))
            p.setPen(QPen(QColor(226, 176, 79, 230), max(1.0, px(3))))
            p.setBrush(QColor(28, 24, 12, 225))
            p.drawRoundedRect(pill, px(27), px(27))
            p.drawPixmap(QPointF(pill.left() + px(24), pill.center().y() - px(20)), piezas.icono(ic, "#F3CF7A", px(40)))
            p.setPen(QColor("#FFFFFF"))
            p.drawText(pill.adjusted(px(76), 0, -px(18), 0), Qt.AlignVCenter | Qt.AlignLeft, texto)
        if faltan:
            self._pedidas.update(r for r, _, _ in faltan)
            QTimer.singleShot(0, lambda lista=faltan: self.pide_minis.emit(lista))

    # ------------------------------------------------------------------ raton
    def _limite_en(self, pos):
        if not self.editable:
            return None
        y_eje = self.ARRIBA - px(34)
        for mom in ("IGLESIA", "FIESTA"):
            if mom in self.limites:
                if abs(pos.x() - self.x_de(self.limites[mom])) <= px(22) and abs(pos.y() - y_eje) <= px(26):
                    return mom
        return None

    def _toma_en(self, pos):
        return next((it for r, it in self._colocadas if r.contains(pos)), None)

    def mousePressEvent(self, e):
        pos = e.position()
        mom = self._limite_en(pos)
        if mom and e.button() == Qt.LeftButton:
            self._arrastra = mom
            self.update()
            e.accept()
            return
        it = self._toma_en(pos) if self.editable else None
        if it is not None and e.button() == Qt.LeftButton:
            self._toma = (it, QPointF(pos))
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
        if self._toma is not None:
            it, ini = self._toma
            if self._llevando is not None or (pos - ini).manhattanLength() > px(14):
                self._llevando = (it, QPointF(pos))
                self.setCursor(Qt.ClosedHandCursor)
                self.update()
            return
        sobre = self._limite_en(pos)
        if sobre != self._sobre:
            self._sobre = sobre
            self.update()
        toma = self._toma_en(pos) if self.editable else None
        self.setCursor(Qt.SizeHorCursor if sobre else Qt.OpenHandCursor if toma is not None else Qt.ArrowCursor)
        if sobre:
            QToolTip.showText(e.globalPosition().toPoint(), "Arrastra para cambiar dónde empieza %s" % NOMBRE[sobre],
                              self)
        elif toma is not None:
            extra = {"contenido": " · ordenado por lo que se ve", "manual": " · puesto a mano"}.get(toma["por"], "")
            QToolTip.showText(e.globalPosition().toPoint(), "%s\n%s · %s · %d s%s\nArrástrala a otro carril para "
                              "cambiarla de momento" % (toma["nombre"], hhmm(toma["m"]),
                                                        NOMBRE.get(self.momento_de(toma), "?"), round(toma["seg"]),
                                                        extra), self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self, e):
        if self._arrastra:
            self._arrastra = None
            self.update()
            self.limites_cambiados.emit({m: hhmm(v) if v < 1440 else "%02d:%02d" % (int(v) // 60, int(v) % 60)
                                         for m, v in self.limites.items()})
            return
        if self._toma is not None:
            llevando = self._llevando
            self._toma = self._llevando = None
            self.setCursor(Qt.ArrowCursor)
            if llevando is not None:
                it, pos = llevando
                k = self._carril_en(pos.y())
                if k is not None and MOMENTOS[k] != self.momento_de(it):
                    it["momento"], it["por"] = MOMENTOS[k], "manual"
                    self._version += 1
                    self.toma_movida.emit(it["nombre"], MOMENTOS[k])
                    self.cuentas_vivas.emit(self.cuentas())
            self.update()
            return
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e):
        self._sobre = None
        self.update()
        super().leaveEvent(e)
