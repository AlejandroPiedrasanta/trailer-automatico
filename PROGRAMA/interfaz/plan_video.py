# -*- coding: utf-8 -*-
"""
plan_video.py - «Qué entra al video» (Material): el plan de la version elegida, plano por plano, y lo que queda fuera.

(18-nov) La persona, de la Linea del dia: «no entiendo qué hace... rediseña para que sea algo útil de verdad, que
aporte algo», y de tres propuestas (docs/capturas/propuestas_material) eligio la A. Antes de armar se ve lo que el
programa va a poner en cada video (con las miniaturas, en orden y con su minuto) y, debajo, las tomas que no entran con
el motivo en pocas palabras. Clic en una toma: «No la uses» o «Úsala de todos modos»; queda en el estado (tomas_no /
tomas_si) y build_trailers.decisiones lo respeta al armar.

    PlanVideo.poner(datos)            datos = receta.plan_ventana(...)
    PlanVideo.elegir(clave)           la version que se ve («1min», «V 1min»...)
    PlanVideo.pide_minis([(ruta, tipo, None)])   las miniaturas que faltan para lo que se ve
    PlanVideo.decidida(nombre, que)   que = "no" | "si" | "auto"
"""
import time

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPainterPath
from PySide6.QtWidgets import QWidget, QMenu, QToolTip

import piezas
from piezas import px

COLOR = {"INTRO": QColor("#E2B04F"), "MAQUILLAJE": QColor("#8B57E0"), "IGLESIA": QColor("#1FA36A"),
         "FIESTA": QColor("#E0559A")}
NOMBRE = {"INTRO": "Intro (fotos)", "MAQUILLAJE": "Maquillaje", "IGLESIA": "Iglesia", "FIESTA": "Fiesta"}
ROJO = QColor("#E24B4A")
TENUE = QColor("#9DB0B6")
FUERA_MAX = 3                # filas de «se quedaron fuera» a la vista (el resto, con «ver todas»)
POSIBLES_MAX = 2             # filas de «podrían entrar» a la vista


def _mmss(s):
    return "%d:%02d" % (int(s) // 60, int(s) % 60)


class PlanVideo(QWidget):
    pide_minis = Signal(list)
    decidida = Signal(str, str)
    # (18-nov, la persona: «que pueda mover el orden de las tomas para hacer la corrección del video de una vez») arrastrar
    # una toma del plan a otra posicion: (version, [id de cada plano en el orden nuevo]); [] = el orden del programa
    reordenada = Signal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.datos, self.clave = {}, None
        self.minis, self._pedidas = {}, set()
        self._celdas = []            # [(QRectF, toma dict, fuera?)]
        self._sobre = None
        self._todas = False
        self._ver_todas = None       # QRectF del texto «ver todas»
        self._todas_pos, self._ver_pos = False, None
        self._secciones = {}
        self._t0 = time.monotonic()  # las miniaturas aparecen en cascada al cambiar de version
        self._reloj = QTimer(self, interval=piezas.CUADRO_MS if hasattr(piezas, "CUADRO_MS") else 16)
        self._reloj.timeout.connect(self._tic)
        self.editable = True
        self._arrastre = None        # {"toma", "desde" (indice), "pos" (QPointF), "inicio", "activo"}
        self.reescalar()

    # ------------------------------------------------------------------ datos
    def poner(self, datos):
        self.datos = datos or {}
        claves = [c for c, _ in self.datos.get("versiones") or []]
        if self.clave not in claves:
            self.clave = claves[0] if claves else None
        self._acomodar()

    def elegir(self, clave):
        if clave != self.clave and clave in (self.datos.get("planos") or {}):
            self.clave = clave
            self._acomodar()

    def poner_minis(self, minis):
        self.minis.update(minis)
        self.update()

    def reescalar(self):
        self.M = px(14)
        self.GW, self.GH, self.SEP, self.PIE = px(190), px(108), px(12), px(34)
        self.FW, self.FH, self.FPIE = px(220), px(124), px(58)
        self._acomodar()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._acomodar()

    def _acomodar(self):
        """Reparte las celdas a lo ancho y fija el alto (la pagina de Material se desplaza)."""
        w = max(px(400), self.width())
        self._celdas = []
        planos = (self.datos.get("planos") or {}).get(self.clave) or []
        cols = max(1, int((w - 2 * self.M + self.SEP) // (self.GW + self.SEP)))
        gw = (w - 2 * self.M - (cols - 1) * self.SEP) / float(cols)
        gh = gw * self.GH / float(self.GW)
        y = px(64)
        for n, p in enumerate(planos):
            self._celdas.append((QRectF(self.M + (n % cols) * (gw + self.SEP), y + (n // cols) * (gh + self.PIE), gw, gh),
                                 p, False))
        filas = (len(planos) + cols - 1) // cols
        y += filas * (gh + self.PIE) + px(46)          # leyenda
        fcols = max(1, int((w - 2 * self.M + self.SEP) // (self.FW + self.SEP)))
        fw = (w - 2 * self.M - (fcols - 1) * self.SEP) / float(fcols)
        fh = fw * self.FH / float(self.FW)
        # (19-nov, la persona) debajo del plan: las que podrian entrar (buenas sin usar) y luego las descartadas
        self._secciones = {}
        for tipo, lista in (("posible", (self.datos.get("posibles") or {}).get(self.clave) or []),
                            (True, self.datos.get("fuera") or [])):
            if tipo == "posible" and not lista:
                continue
            todas = self._todas if tipo is True else self._todas_pos
            visibles = lista if todas else lista[:fcols * (FUERA_MAX if tipo is True else POSIBLES_MAX)]
            self._secciones[tipo] = (y, len(lista), len(lista) - len(visibles))
            y += px(70)
            for n, f in enumerate(visibles):
                self._celdas.append((QRectF(self.M + (n % fcols) * (fw + self.SEP), y + (n // fcols) * (fh + self.FPIE),
                                            fw, fh), f, tipo))
            y += ((len(visibles) + fcols - 1) // fcols) * (fh + self.FPIE) + px(16)
        self._y_fuera = self._secciones.get("posible", self._secciones.get(True, (y, 0, 0)))[0]
        self.setMinimumHeight(int(y + px(4)))
        self._t0 = time.monotonic()
        self._reloj.start()
        falta = []
        for _r, t, _f in self._celdas:
            ruta = t.get("ruta")
            if ruta and ruta not in self.minis and ruta not in self._pedidas:
                self._pedidas.add(ruta)
                falta.append((ruta, t.get("tipo"), None))
        if falta:
            self.pide_minis.emit(falta)
        self.update()

    def _tic(self):
        arrastrando = bool(self._arrastre and self._arrastre.get("activo"))
        if (time.monotonic() - self._t0 > 0.9 and not arrastrando) or not self.isVisible():
            self._reloj.stop()
        self.update()

    # ------------------------------------------------------------------ pintar
    def _fuente(self, tam, peso=QFont.Normal):
        f = QFont(self.font())
        f.setPixelSize(max(9, px(tam)))
        f.setWeight(peso)
        return f

    def _mini(self, p, r, toma, borde, apagada):
        marco = QPainterPath()
        marco.addRoundedRect(r, px(10), px(10))
        p.save()
        p.setClipPath(marco)
        pm = self.minis.get(toma.get("ruta"))
        if pm is not None and not pm.isNull():
            esc = max(r.width() / pm.width(), r.height() / pm.height())
            tw, th = pm.width() * esc, pm.height() * esc
            p.drawPixmap(QRectF(r.center().x() - tw / 2, r.center().y() - th / 2, tw, th), pm, QRectF(pm.rect()))
        else:
            p.fillRect(r, QColor(18, 38, 46))
        if apagada:
            p.fillRect(r, QColor(4, 14, 18, 140))
        p.restore()
        sobre = self._sobre is toma
        p.setPen(QPen(QColor("#FFFFFF") if sobre else borde, max(1.5, px(4) if sobre else px(3))))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, px(10), px(10))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        d = self.datos
        planos = (d.get("planos") or {}).get(self.clave) or []
        w = self.width()
        if not d.get("versiones"):
            p.setFont(self._fuente(26))
            p.setPen(TENUE)
            p.drawText(QRectF(0, 0, w, px(120)), Qt.AlignCenter, "Cuando el material esté analizado, aquí verás qué entra a cada video.")
            return
        texto = dict(d["versiones"]).get(self.clave, "")
        p.setFont(self._fuente(30, QFont.Bold))
        p.setPen(QColor("#F1F5F6"))
        es_pl = self._es_plantilla()
        p.drawText(QRectF(self.M, 0, w, px(50)), Qt.AlignLeft | Qt.AlignVCenter,
                   ("Así queda con la %s" % texto.lower()) if es_pl else "Así queda el de %s" % texto.lower())
        p.setFont(self._fuente(22))
        p.setPen(TENUE)
        huecos = len([x for x in planos if x.get("id")]) if es_pl else len(planos)
        p.drawText(QRectF(0, 0, w - self.M, px(50)), Qt.AlignRight | Qt.AlignVCenter, (
            "%d huecos de la plantilla · %d tomas distintas" if es_pl else "%d planos · %d tomas distintas") % (
            huecos, len({x.get("ruta") for x in planos})))
        edad = time.monotonic() - self._t0
        n_plano = 0
        arr = self._arrastre if (self._arrastre and self._arrastre.get("activo")) else None
        for r, toma, fuera in self._celdas:
            if fuera:
                continue
            k = min(1.0, max(0.0, (edad - 0.012 * min(n_plano, 40)) / 0.28))      # cascada al cambiar de version
            n_plano += 1
            if k <= 0.0:
                continue
            p.setOpacity((1.0 - (1.0 - k) ** 3) * (0.25 if arr and arr["toma"] is toma else 1.0))
            self._mini(p, r, toma, COLOR.get(toma.get("momento"), COLOR["FIESTA"]), False)
            p.setFont(self._fuente(18))
            p.setPen(TENUE)
            pie = _mmss(toma.get("t", 0))
            if self._es_plantilla() and toma.get("dur"):
                pie += " · %s s" % ("%.1f" % toma["dur"]).replace(".", ",")
            p.drawText(QRectF(r.left(), r.bottom(), r.width(), self.PIE * 0.8), Qt.AlignCenter, pie)
        p.setOpacity(1.0)
        if arr:                                          # donde va a caer: una barra que respira + la toma en la mano
            destino = self._destino(arr["pos"])
            if destino is not None:
                r0 = destino[0]
                brillo = 0.6 + 0.4 * abs(((time.monotonic() * 1.6) % 2.0) - 1.0)
                c = QColor("#7CF5C0")
                c.setAlphaF(brillo)
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                x = r0.left() - self.SEP / 2.0 if destino[1] else r0.right() + self.SEP / 2.0
                p.drawRoundedRect(QRectF(x - px(3), r0.top() - px(4), px(6), r0.height() + px(8)), px(3), px(3))
            rr = QRectF(0, 0, self._celdas[0][0].width() * 0.9, self._celdas[0][0].height() * 0.9)
            rr.moveCenter(arr["pos"])
            p.setOpacity(0.92)
            self._mini(p, rr, arr["toma"], QColor("#FFFFFF"), False)
            p.setOpacity(1.0)
        # leyenda
        y, x = self._y_fuera - px(40), self.M
        p.setFont(self._fuente(20))
        for k in ("INTRO", "MAQUILLAJE", "IGLESIA", "FIESTA"):
            p.setPen(Qt.NoPen)
            p.setBrush(COLOR[k])
            p.drawRoundedRect(QRectF(x, y + px(4), px(20), px(20)), px(5), px(5))
            p.setPen(QColor("#C9D6D9"))
            ancho = p.fontMetrics().horizontalAdvance(NOMBRE[k])
            p.drawText(QRectF(x + px(30), y, ancho + px(10), px(28)), Qt.AlignLeft | Qt.AlignVCenter, NOMBRE[k])
            x += px(30) + ancho + px(40)
        cortos = d.get("cortos") or []
        if cortos:
            p.setPen(QColor("#F2B84B"))
            p.drawText(QRectF(x, y, w - x - self.M, px(28)), Qt.AlignRight | Qt.AlignVCenter, " · ".join(
                "%s: solo %d toma%s buena%s, los videos largos van a repetir" % (
                    NOMBRE.get(m, m), n, "" if n == 1 else "s", "" if n == 1 else "s") for m, n in cortos))
        # (19-nov) «Podrían entrar» (buenas sin usar, en verde) y «Se quedaron fuera» (descartadas, en rojo)
        self._ver_todas = self._ver_pos = None
        for tipo, (y, total, ocultas) in self._secciones.items():
            p.setPen(QPen(QColor(255, 255, 255, 28), 1))
            p.drawLine(QPointF(self.M, y), QPointF(w - self.M, y))
            p.setFont(self._fuente(30, QFont.Bold))
            p.setPen(QColor("#F1F5F6"))
            p.drawText(QRectF(self.M, y + px(10), w, px(50)), Qt.AlignLeft | Qt.AlignVCenter,
                       "Podrían entrar" if tipo == "posible" else "Se quedaron fuera")
            p.setFont(self._fuente(22))
            p.setPen(TENUE)
            if tipo == "posible":
                pie = "%d tomas buenas que no se usaron · doble clic para meterla" % total
                todas = self._todas_pos
            else:
                pie = "%d de %d tomas · doble clic en una para usarla" % (total, d.get("videos", 0))
                todas = self._todas
            der = w - self.M
            if ocultas > 0 or todas:
                enlace = "ver menos" if todas else "ver las %d" % total
                ancho = p.fontMetrics().horizontalAdvance(enlace)
                rect = QRectF(w - self.M - ancho, y + px(10), ancho, px(50))
                if tipo == "posible":
                    self._ver_pos = rect
                else:
                    self._ver_todas = rect
                p.setPen(QColor("#7CF5C0"))
                p.drawText(rect, Qt.AlignRight | Qt.AlignVCenter, enlace)
                p.setPen(TENUE)
                der -= ancho + px(24)
            p.drawText(QRectF(0, y + px(10), der, px(50)), Qt.AlignRight | Qt.AlignVCenter, pie)
        for r, toma, es_fuera in self._celdas:
            if not es_fuera:
                continue
            posible = es_fuera == "posible"
            borde = QColor("#7CC9A0") if posible else QColor("#F2B84B") if toma.get("a_mano") == "no" else ROJO
            self._mini(p, r, toma, borde, not posible)
            p.setFont(self._fuente(18))
            p.setPen(QColor("#A8D8BC") if posible else QColor("#F09595"))
            p.drawText(QRectF(r.left() - px(4), r.bottom() + px(4), r.width() + px(8), self.FPIE - px(8)),
                       Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                       NOMBRE.get(toma.get("momento"), "") if posible else toma.get("motivo", ""))
    def _es_plantilla(self):
        return str(self.clave or "").upper().startswith("PLANTILLA")

    # ------------------------------------------------------------------ raton
    def _en(self, pos):
        for r, toma, fuera in self._celdas:
            if r.contains(pos):
                return toma, fuera
        return None, False

    def _videos_plan(self):
        """[(rect, toma)] de los planos de video del plan (las fotos de la intro no se mueven)."""
        return [(r, t) for r, t, fuera in self._celdas if not fuera and t.get("tipo") != "foto"]

    def _destino(self, pos):
        """Donde caeria la toma arrastrada: (rect de la celda, antes?, indice entre los videos del plan) o None."""
        vids = self._videos_plan()
        if not vids:
            return None
        n, (r, _t) = min(enumerate(vids), key=lambda x: (x[1][0].center() - pos).manhattanLength())
        antes = pos.x() < r.center().x()
        return r, antes, n if antes else n + 1

    def mouseMoveEvent(self, e):
        pos = e.position()
        arr = self._arrastre
        if arr is not None:
            if not arr["activo"] and (pos - arr["inicio"]).manhattanLength() > px(14):
                arr["activo"] = True
                self.setCursor(Qt.ClosedHandCursor)
                self._reloj.start()
            if arr["activo"]:
                arr["pos"] = pos
                self.update()
                return
        toma, fuera = self._en(pos)
        mano = toma is not None or any(v is not None and v.contains(pos) for v in (self._ver_todas, self._ver_pos))
        self.setCursor((Qt.OpenHandCursor if toma is not None and not fuera and toma.get("tipo") != "foto" else
                        Qt.PointingHandCursor) if mano else Qt.ArrowCursor)
        if toma is not self._sobre:
            self._sobre = toma
            self.update()
            if toma is not None:
                QToolTip.showText(e.globalPosition().toPoint(), "%s\nArrastra para cambiar el orden · doble clic para %s"
                                  % (toma.get("nombre") or "", "usarla" if fuera else "sacarla"), self)

    def leaveEvent(self, _):
        if self._sobre is not None:
            self._sobre = None
            self.update()

    def mousePressEvent(self, e):
        pos = e.position()
        if e.button() == Qt.RightButton:
            self._menu(pos, e.globalPosition().toPoint())
            return
        if e.button() != Qt.LeftButton:
            return
        if self._ver_todas is not None and self._ver_todas.contains(pos):
            self._todas = not self._todas
            self._acomodar()
            return
        if self._ver_pos is not None and self._ver_pos.contains(pos):
            self._todas_pos = not self._todas_pos
            self._acomodar()
            return
        toma, fuera = self._en(pos)
        if toma is not None and not fuera and self.editable and toma.get("tipo") != "foto":
            self._arrastre = {"toma": toma, "inicio": pos, "pos": pos, "activo": False}

    def mouseReleaseEvent(self, e):
        arr, self._arrastre = self._arrastre, None
        if not arr or not arr["activo"]:
            return
        self.setCursor(Qt.ArrowCursor)
        destino = self._destino(e.position())
        vids = [t for _r, t in self._videos_plan()]
        if destino is None or arr["toma"] not in vids:
            self.update()
            return
        desde, hasta = vids.index(arr["toma"]), destino[2]
        if hasta in (desde, desde + 1):                   # la solto donde estaba
            self.update()
            return
        vids.insert(hasta if hasta < desde else hasta - 1, vids.pop(desde))
        self.reordenada.emit(self.clave or "", [t.get("id") for t in vids])
        self.update()

    def mouseDoubleClickEvent(self, e):
        """(18-nov, la persona: «doble clic poner en tomas se quedaron fuera, igual para las que se quedaron fuera»)"""
        self._arrastre = None
        if e.button() != Qt.LeftButton:
            return
        toma, fuera = self._en(e.position())
        if toma is None or not self.editable or toma.get("tipo") == "foto":
            return
        self.decidida.emit(toma.get("nombre") or "", "si" if fuera else "no")

    def _menu(self, pos, global_pos):
        """Clic derecho: lo de siempre y volver al orden del programa."""
        toma, fuera = self._en(pos)
        if not self.editable:
            return
        m = QMenu(self)
        if toma is not None and toma.get("tipo") != "foto":
            nombre = toma.get("nombre") or ""
            if fuera:
                if toma.get("a_mano") == "no":
                    m.addAction("Volver a lo que decidió el programa", lambda: self.decidida.emit(nombre, "auto"))
                m.addAction("Úsala de todos modos", lambda: self.decidida.emit(nombre, "si"))
            else:
                m.addAction("No la uses", lambda: self.decidida.emit(nombre, "no"))
                if nombre in (self.datos.get("a_mano_si") or []):
                    m.addAction("Volver a lo que decidió el programa", lambda: self.decidida.emit(nombre, "auto"))
        if self.datos.get("a_mano_orden", {}).get(self.clave):
            m.addAction("Volver al orden del programa", lambda: self.reordenada.emit(self.clave or "", []))
        if not m.isEmpty():
            m.exec(global_pos)
