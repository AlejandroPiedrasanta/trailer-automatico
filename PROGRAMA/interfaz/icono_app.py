# -*- coding: utf-8 -*-
"""
icono_app.py - El icono del programa (el diseno que eligio la persona): cuadro redondeado morado-azul con borde neon,
un play con perforaciones de pelicula, dentro una pareja bailando con luz dorada y el publico de fiesta, una cinta de
pelicula que lo envuelve, tijeras de edicion y destellos.

  dibujar(t) -> QImage t x t con fondo transparente. Lo usan la ventana (barra de tareas) y compilar/icono/icono.py
  (.ico de Windows, .icns de la Mac). Se dibuja con vectores: nitido en todos los tamanos; en los chicos (16-48 px)
  se simplifica para que se lea el play.
  Si existe recursos/icono_fuente.png (una imagen del icono hecha aparte), se usa esa: se recorta el cuadro y se le
  quitan el fondo y la sombra.
"""
import os
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QColor, QImage, QPainter, QPainterPath, QPen, QBrush, QPolygonF, QRadialGradient,
                           QLinearGradient, QPainterPathStroker)

TRIANGULO = ((0.285, 0.235), (0.345, 0.800), (0.805, 0.500))      # el play, algo inclinado como en el diseno


def _fuente():
    try:
        import rutas
        p = os.path.join(rutas.RECURSOS, "icono_fuente.png")
        return p if os.path.exists(p) else None
    except Exception:
        return None


CHICO, MEDIANO = 24, 48        # hasta CHICO px: version simplificada; hasta MEDIANO: la imagen, afilada


def dibujar(t):
    """El icono a t x t. La imagen de la persona es muy detallada: a 16-24 px (barra de tareas, pestanas, lista de
    programas) se volvia una mancha borrosa. En esos tamanos va la version simplificada (el mismo cuadro morado con
    borde neon y el play dorado, que si se lee); de 25 a 48 px, la imagen con mascara de enfoque; mas grande, tal cual."""
    f = _fuente()
    if f and t > CHICO:
        img = _desde_imagen(f, t)
        if img is not None:
            return _afilar(img, 1.1) if t <= MEDIANO else img
    return _vectorial(t)


def _afilar(img, cuanto):
    """Mascara de enfoque 3 x 3 (solo para iconos chicos: recorre pixel a pixel)."""
    w, h = img.width(), img.height()
    src = [[img.pixelColor(x, y) for x in range(w)] for y in range(h)]
    out = QImage(img)
    for y in range(h):
        for x in range(w):
            c = src[y][x]
            if c.alpha() == 0:
                continue
            r = g = b = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    v = src[min(h - 1, max(0, y + dy))][min(w - 1, max(0, x + dx))]
                    r += v.red()
                    g += v.green()
                    b += v.blue()
            out.setPixelColor(x, y, QColor(*[int(max(0, min(255, a + cuanto * (a - m / 9.0))))
                                             for a, m in ((c.red(), r), (c.green(), g), (c.blue(), b))], c.alpha()))
    return out


# ------------------------------------------------------------------ con la imagen de la persona
def _desde_imagen(ruta, t):
    src = QImage(ruta)
    if src.isNull():
        return None
    if src.hasAlphaChannel():                             # ya limpia (compilar/icono/icono.py limpiar): solo escalar
        return src.scaled(t, t, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format_ARGB32)
    src = src.convertToFormat(QImage.Format_ARGB32)
    w, h = src.width(), src.height()
    fondo = QColor(src.pixel(2, 2))

    def es_fondo(x, y):
        c = QColor(src.pixel(x, y))
        return abs(c.red() - fondo.red()) + abs(c.green() - fondo.green()) + abs(c.blue() - fondo.blue()) < 60

    # caja del icono: filas y columnas con bastante "no fondo" (la sombra suave no cuenta)
    paso = max(1, min(w, h) // 300)
    cols = [x for x in range(0, w, paso) if sum(1 for y in range(0, h, paso * 3) if not es_fondo(x, y)) > h / (paso * 3) * 0.25]
    filas = [y for y in range(0, h, paso) if sum(1 for x in range(0, w, paso * 3) if not es_fondo(x, y)) > w / (paso * 3) * 0.25]
    if not cols or not filas:
        return None
    x0, x1, y0, y1 = min(cols), max(cols), min(filas), max(filas)
    lado = max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    caja = QRectF(cx - lado / 2.0, cy - lado / 2.0, lado, lado)
    img = QImage(t, t, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    m = t * 0.02
    rect = QRectF(m, m, t - 2 * m, t - 2 * m)
    camino = QPainterPath()
    camino.addRoundedRect(rect, rect.width() * 0.225, rect.width() * 0.225)
    p.setClipPath(camino)
    p.drawImage(rect, src, caja)
    p.end()
    return img


# ------------------------------------------------------------------ dibujado con vectores
def _estrella(p, c, r, color, alfa=255):
    """Destello de 4 puntas."""
    col = QColor(color)
    col.setAlpha(alfa)
    k = r * 0.22
    pol = QPolygonF([QPointF(c.x(), c.y() - r), QPointF(c.x() + k, c.y() - k), QPointF(c.x() + r, c.y()),
                     QPointF(c.x() + k, c.y() + k), QPointF(c.x(), c.y() + r), QPointF(c.x() - k, c.y() + k),
                     QPointF(c.x() - r, c.y()), QPointF(c.x() - k, c.y() - k)])
    g = QRadialGradient(c, r * 1.6)
    halo = QColor(col)
    halo.setAlpha(int(alfa * 0.35))
    g.setColorAt(0, halo)
    g.setColorAt(1, QColor(0, 0, 0, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(c, r * 1.6, r * 1.6)
    p.setBrush(col)
    p.drawPolygon(pol)


def _figura(P, cabeza, r, cuerpo):
    """Silueta: cabeza + cuerpo (poligono), en coordenadas 0-1."""
    camino = QPainterPath()
    camino.addEllipse(P(*cabeza), r, r)
    pol = QPainterPath()
    pol.addPolygon(QPolygonF([P(x, y) for x, y in cuerpo]))
    pol.closeSubpath()
    return camino.united(pol)


def _curva(P, puntos):
    """Camino suave que pasa por los puntos (0-1): curvas de Catmull-Rom cerradas."""
    pts = [P(x, y) for x, y in puntos]
    n = len(pts)
    c = QPainterPath(pts[0])
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c.cubicTo(QPointF(p1.x() + (p2.x() - p0.x()) / 6.0, p1.y() + (p2.y() - p0.y()) / 6.0),
                  QPointF(p2.x() - (p3.x() - p1.x()) / 6.0, p2.y() - (p3.y() - p1.y()) / 6.0), p2)
    c.closeSubpath()
    return c


def _pareja(P, t):
    """Los novios bailando: el de la izquierda de traje, ella con vestido largo; las manos unidas en alto."""
    el = _curva(P, [(0.452, 0.428), (0.474, 0.436), (0.488, 0.404), (0.500, 0.356), (0.510, 0.352), (0.506, 0.372),
                    (0.492, 0.442), (0.482, 0.470), (0.478, 0.530), (0.486, 0.640), (0.490, 0.712), (0.472, 0.714),
                    (0.462, 0.600), (0.454, 0.600), (0.446, 0.714), (0.428, 0.712), (0.432, 0.600), (0.436, 0.530),
                    (0.428, 0.480), (0.432, 0.444)])
    cabeza_el = QPainterPath()
    cabeza_el.addEllipse(P(0.452, 0.404), t * 0.0215, t * 0.0235)
    ella = _curva(P, [(0.522, 0.420), (0.514, 0.398), (0.507, 0.360), (0.514, 0.356), (0.522, 0.392), (0.532, 0.424),
                      (0.546, 0.436), (0.546, 0.470), (0.538, 0.500), (0.552, 0.580), (0.572, 0.660), (0.590, 0.712),
                      (0.536, 0.718), (0.490, 0.714), (0.502, 0.640), (0.516, 0.560), (0.520, 0.500), (0.514, 0.470),
                      (0.514, 0.440)])
    cabeza_ella = QPainterPath()
    cabeza_ella.addEllipse(P(0.528, 0.398), t * 0.0185, t * 0.020)
    pelo = _curva(P, [(0.530, 0.380), (0.552, 0.392), (0.560, 0.430), (0.552, 0.462), (0.540, 0.440), (0.536, 0.410)])
    return el.united(cabeza_el).united(ella).united(cabeza_ella).united(pelo)


def _bailarin(P, t, x, y, s, brazo):
    """Una persona del publico con un brazo arriba."""
    cuerpo = _curva(P, [(x - 0.020 * s, y + 0.030 * s), (x + 0.020 * s, y + 0.030 * s), (x + 0.028 * s, y + 0.110 * s),
                        (x + 0.032 * s, y + 0.240 * s), (x - 0.032 * s, y + 0.240 * s), (x - 0.028 * s, y + 0.110 * s)])
    cabeza = QPainterPath()
    cabeza.addEllipse(P(x, y), t * 0.0165 * s, t * 0.018 * s)
    b = brazo
    mano = _curva(P, [(x + 0.010 * s * b, y + 0.040 * s), (x + 0.040 * s * b, y - 0.030 * s), (x + 0.052 * s * b, y - 0.075 * s),
                      (x + 0.062 * s * b, y - 0.070 * s), (x + 0.054 * s * b, y - 0.020 * s), (x + 0.026 * s * b, y + 0.060 * s)])
    return cuerpo.united(cabeza).united(mano)


def _vectorial(t):
    img = QImage(t, t, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    detalle = 2 if t >= 96 else (1 if t >= 56 else 0)

    def P(x, y):
        return QPointF(x * t, y * t)

    # --- el cuadro redondeado
    m = t * (0.03 if detalle else 0.0)
    rect = QRectF(m, m, t - 2 * m, t - 2 * m)
    radio = rect.width() * 0.225
    cuadro = QPainterPath()
    cuadro.addRoundedRect(rect, radio, radio)
    g = QLinearGradient(P(0.1, 0.05), P(0.9, 0.95))
    g.setColorAt(0.0, QColor("#2B1E78"))
    g.setColorAt(0.5, QColor("#35166E"))
    g.setColorAt(1.0, QColor("#5C1258"))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawPath(cuadro)
    p.save()
    p.setClipPath(cuadro)
    resplandor = QRadialGradient(P(0.47, 0.42), t * 0.48)
    resplandor.setColorAt(0.0, QColor(255, 196, 110, 150))
    resplandor.setColorAt(0.35, QColor(214, 110, 170, 70))
    resplandor.setColorAt(1.0, QColor(40, 20, 90, 0))
    p.setBrush(resplandor)
    p.drawRect(rect)
    if detalle >= 1:                                       # rayos de luz desde atras del play
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        c = P(0.46, 0.42)
        for k, ang in enumerate((-150, -128, -105, -80, -55, -30, 190, 160)):
            a = math.radians(ang)
            largo = t * (0.42 if k % 2 else 0.34)
            ancho = math.radians(3.5 if k % 2 else 2.2)
            rayo = QPolygonF([c, QPointF(c.x() + math.cos(a - ancho) * largo, c.y() + math.sin(a - ancho) * largo),
                              QPointF(c.x() + math.cos(a + ancho) * largo, c.y() + math.sin(a + ancho) * largo)])
            gr = QRadialGradient(c, largo)
            gr.setColorAt(0, QColor(255, 200, 120, 90))
            gr.setColorAt(1, QColor(255, 200, 120, 0))
            p.setBrush(gr)
            p.drawPolygon(rayo)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)

    # --- la cinta de pelicula (detras del play)
    if detalle >= 1:
        cinta = QPainterPath(P(0.04, 0.80))
        cinta.cubicTo(P(0.30, 0.66), P(0.50, 0.18), P(0.97, 0.20))
        ancho = t * 0.10
        st = QPainterPathStroker()
        st.setWidth(ancho)
        st.setCapStyle(Qt.FlatCap)
        banda = st.createStroke(cinta)
        gb = QLinearGradient(P(0.05, 0.8), P(0.95, 0.2))
        gb.setColorAt(0, QColor(150, 140, 235, 200))
        gb.setColorAt(0.5, QColor(225, 220, 255, 225))
        gb.setColorAt(1, QColor(170, 150, 240, 200))
        p.setBrush(gb)
        p.drawPath(banda)
        n = 34 if detalle == 2 else 20
        for i in range(n + 1):
            q = i / float(n)
            c = cinta.pointAtPercent(q)
            a = math.radians(-cinta.angleAtPercent(q))
            nx, ny = -math.sin(a), math.cos(a)
            tx, ty = math.cos(a), math.sin(a)
            for lado in (-1, 1):                           # perforaciones de los dos bordes
                d = lado * ancho * 0.36
                h = QPointF(c.x() + nx * d, c.y() + ny * d)
                s = ancho * 0.085
                p.setBrush(QColor(50, 24, 100, 230))
                p.drawPolygon(QPolygonF([QPointF(h.x() + (tx * s - nx * s), h.y() + (ty * s - ny * s)),
                                         QPointF(h.x() + (tx * s + nx * s), h.y() + (ty * s + ny * s)),
                                         QPointF(h.x() + (-tx * s + nx * s), h.y() + (-ty * s + ny * s)),
                                         QPointF(h.x() + (-tx * s - nx * s), h.y() + (-ty * s - ny * s))]))
            if detalle == 2 and i % 3 == 1:                # cuadros de pelicula en el medio
                s1, s2 = ancho * 0.24, ancho * 0.20
                p.setBrush(QColor(90, 60, 170, 120))
                p.drawPolygon(QPolygonF([QPointF(c.x() + tx * s1 - nx * s2, c.y() + ty * s1 - ny * s2),
                                         QPointF(c.x() + tx * s1 + nx * s2, c.y() + ty * s1 + ny * s2),
                                         QPointF(c.x() - tx * s1 + nx * s2, c.y() - ty * s1 + ny * s2),
                                         QPointF(c.x() - tx * s1 - nx * s2, c.y() - ty * s1 - ny * s2)]))

    # --- el play
    tri = QPainterPath(P(*TRIANGULO[0]))
    tri.lineTo(P(*TRIANGULO[1]))
    tri.lineTo(P(*TRIANGULO[2]))
    tri.closeSubpath()
    borde = t * (0.040 if detalle else 0.075)
    for w, a in ((borde * 4.6, 7), (borde * 4.0, 8), (borde * 3.4, 10), (borde * 2.8, 13), (borde * 2.2, 18),
                 (borde * 1.6, 26)):                                                # brillo neon suave alrededor
        p.setPen(QPen(QColor(130, 150, 255, a), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(tri)
    dentro = QRadialGradient(P(0.47, 0.44), t * 0.36)
    dentro.setColorAt(0.0, QColor("#FFE6A8"))
    dentro.setColorAt(0.30, QColor("#F7B055"))
    dentro.setColorAt(0.70, QColor("#B85A86"))
    dentro.setColorAt(1.0, QColor("#4A2178"))
    p.setPen(QPen(QColor(0, 0, 0, 0), 0))
    p.setBrush(dentro)
    st = QPainterPathStroker()
    st.setWidth(borde)
    st.setJoinStyle(Qt.RoundJoin)
    relleno = tri.united(st.createStroke(tri))
    p.drawPath(relleno)
    if detalle >= 1:                                       # lo que se ve dentro del play: luces, pareja y fiesta
        p.save()
        p.setClipPath(tri)
        if detalle == 2:
            for i in range(11):                            # guirnalda de luces
                q = i / 10.0
                x = 0.33 + q * 0.30
                y = 0.330 + math.sin(q * math.pi) * 0.035 - q * 0.02
                g2 = QRadialGradient(P(x, y), t * 0.016)
                g2.setColorAt(0, QColor(255, 236, 170, 255))
                g2.setColorAt(1, QColor(255, 200, 100, 0))
                p.setBrush(g2)
                p.setPen(Qt.NoPen)
                p.drawEllipse(P(x, y), t * 0.016, t * 0.016)
            for x, y, s, brazo, a in ((0.600, 0.470, 1.00, 1, 150), (0.648, 0.500, 0.85, -1, 135),
                                      (0.690, 0.515, 0.72, 1, 120), (0.380, 0.500, 0.80, -1, 120)):
                p.setBrush(QColor(80, 34, 104, a))                  # el publico, al fondo y mas claro
                p.drawPath(_bailarin(P, t, x, y, s, brazo))
        p.setBrush(QColor(34, 12, 56, 245))
        p.setPen(Qt.NoPen)
        p.drawPath(_pareja(P, t))
        p.restore()
    # borde del play: neon azul-violeta con perforaciones de pelicula
    gl = QLinearGradient(P(*TRIANGULO[0]), P(*TRIANGULO[2]))
    gl.setColorAt(0.0, QColor("#55B6FF"))
    gl.setColorAt(0.55, QColor("#7C7BFF"))
    gl.setColorAt(1.0, QColor("#C760FF"))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QBrush(gl), borde, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(tri)
    if detalle >= 1:
        p.setPen(QPen(QColor(44, 20, 92, 225), borde * 0.38, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(tri)
        n = 40 if detalle == 2 else 24
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(225, 235, 255, 245))
        s = borde * 0.12
        for i in range(n):
            c = tri.pointAtPercent((i + 0.5) / n)
            p.drawRect(QRectF(c.x() - s, c.y() - s, 2 * s, 2 * s))

    # --- tijeras de edicion (abajo) y destellos
    if detalle == 2:
        p.setPen(QPen(QColor(225, 225, 255, 235), t * 0.010, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(P(0.500, 0.835), t * 0.020, t * 0.020)
        p.drawEllipse(P(0.555, 0.845), t * 0.020, t * 0.020)
        p.drawLine(P(0.512, 0.815), P(0.585, 0.745))
        p.drawLine(P(0.540, 0.822), P(0.520, 0.735))
    if detalle >= 1:
        for (x, y, r, col) in ((0.60, 0.205, 0.034, "#FFD27A"), (0.20, 0.33, 0.026, "#FFD27A"),
                               (0.84, 0.60, 0.030, "#9FD0FF"), (0.27, 0.62, 0.016, "#FFE7B0"),
                               (0.72, 0.30, 0.014, "#FFFFFF"), (0.66, 0.78, 0.016, "#9FD0FF")):
            if detalle == 1 and r < 0.02:
                continue
            _estrella(p, P(x, y), t * r, col)
        if detalle == 2:
            confeti = ((0.15, 0.45, "#FFB347"), (0.23, 0.18, "#8FB8FF"), (0.42, 0.14, "#FF7AC0"), (0.78, 0.40, "#FFD27A"),
                       (0.88, 0.75, "#FF7AC0"), (0.30, 0.86, "#8FB8FF"), (0.70, 0.88, "#FFD27A"), (0.12, 0.62, "#FF7AC0"),
                       (0.90, 0.40, "#8FB8FF"), (0.52, 0.10, "#FFE7B0"))
            p.setPen(Qt.NoPen)
            for x, y, col in confeti:
                p.setBrush(QColor(col))
                p.drawEllipse(P(x, y), t * 0.008, t * 0.008)
    p.restore()

    # --- borde neon del cuadro
    gb = QLinearGradient(P(0.0, 0.0), P(1.0, 1.0))
    gb.setColorAt(0.0, QColor("#5C8BFF"))
    gb.setColorAt(0.5, QColor("#9B5CFF"))
    gb.setColorAt(1.0, QColor("#FF4FA8"))
    ancho_b = max(1.0, t * (0.018 if detalle else 0.04))
    p.setPen(QPen(QBrush(gb), ancho_b))
    p.setBrush(Qt.NoBrush)
    r2 = rect.adjusted(ancho_b / 2, ancho_b / 2, -ancho_b / 2, -ancho_b / 2)
    p.drawRoundedRect(r2, radio - ancho_b / 2, radio - ancho_b / 2)
    p.end()
    return img
