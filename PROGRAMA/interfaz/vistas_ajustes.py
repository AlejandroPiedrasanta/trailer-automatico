# -*- coding: utf-8 -*-
"""
vistas_ajustes.py - Lo que se abre con DOBLE CLIC en Ajustes > Sonido (18-nov).

La persona: «si doy doble click, que me salga el pop up con todas las canciones de cada música de estilo, y en las
intro igual: doble click me da el ejemplo de cómo se ve».

    ListaCanciones(carpeta)        las pistas de un estilo, cada una con su boton para oirla (un trozo)
    VistaIntro(cortes, fotos, sfx) las 8 fotos de la apertura entrando con ESE ritmo (y su efecto de sonido), en bucle
    sonar(ruta, desde, seg) / callar()

El sonido no usa QtMultimedia (no va en el instalador): ffmpeg saca un trozo a WAV en un hilo y lo toca winsound
(Windows) o afplay (Mac). Sin ffmpeg o sin sonido, las piezas siguen funcionando calladas.
"""
import os
import sys
import time
import shutil
import tempfile
import threading
import subprocess

from PySide6.QtCore import Qt, QRectF, QTimer, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPainterPath, QImageReader, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

import rutas
import piezas
from piezas import px

_sonando = {"n": 0, "proc": None}
PAPELES = {"INTRO": "apertura (con las fotos)", "ROMANTICA": "romántica (maquillaje, iglesia)", "FIESTA": "fiesta",
           "EPICA": "épica (final)"}


def _mci(orden):
    """Una orden al reproductor de Windows (MCI). Devuelve (codigo de error, respuesta)."""
    import ctypes
    buf = ctypes.create_unicode_buffer(256)
    err = ctypes.windll.winmm.mciSendStringW(orden, buf, 255, None)
    return err, buf.value


def estado():
    """«playing» mientras suena (Windows); '' si no."""
    if os.name != "nt":
        return "playing" if _sonando["proc"] is not None and _sonando["proc"].poll() is None else ""
    try:
        return _mci("status trailer_oir mode")[1]
    except Exception:
        return ""


def callar():
    _sonando["n"] += 1
    try:
        if os.name == "nt":
            _mci("stop trailer_oir")
            _mci("close trailer_oir")
            import winsound
            winsound.PlaySound(None, 0)
        elif _sonando["proc"] is not None:
            _sonando["proc"].kill()
    except Exception:
        pass
    _sonando["proc"] = None


def sonar(ruta, desde=0.0, seg=25.0):
    """Toca un trozo del archivo sin trabar la ventana. Otra llamada o callar() lo corta.

    (18-nov, la persona en el instalado: «hay un error en el pop up, no me deja reproducir») En Windows lo toca el
    reproductor del sistema (MCI) directo del MP3 o WAV, desde el hilo de la ventana (son ordenes que vuelven al
    instante): no depende de ffmpeg ni de hilos. Si MCI no puede, queda el camino de antes (ffmpeg + winsound)."""
    callar()
    turno = _sonando["n"]
    if os.name == "nt":
        try:
            corto = ruta
            try:                                  # MCI no quiere rutas largas ni con caracteres raros: la corta (8.3)
                import ctypes
                b = ctypes.create_unicode_buffer(600)
                if ctypes.windll.kernel32.GetShortPathNameW(ruta, b, 600):
                    corto = b.value
            except Exception:
                pass
            err, _ = _mci('open "%s" type mpegvideo alias trailer_oir' % corto)
            if not err:
                _mci("set trailer_oir time format milliseconds")
                a = int(desde * 1000)
                err, _ = _mci("play trailer_oir from %d to %d" % (a, a + int(seg * 1000)))
                if err:                           # mas corta que el trozo pedido: entera
                    err, _ = _mci("play trailer_oir from 0")
                if not err:
                    return
            _mci("close trailer_oir")
        except Exception:
            pass

    def correr():
        try:
            if sys.platform == "darwin":
                _sonando["proc"] = subprocess.Popen(["afplay", "-t", "%.1f" % seg, ruta])
                return
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg or os.name != "nt":
                return
            wav = os.path.join(tempfile.gettempdir(), "trailer_oir_%d.wav" % (turno % 4))
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.2f" % desde, "-t", "%.2f" % seg,
                            "-i", ruta, "-ac", "2", "-ar", "44100", wav], capture_output=True, timeout=60,
                           creationflags=rutas.SIN_VENTANA)
            if turno == _sonando["n"] and os.path.exists(wav):       # nadie pidio otra cosa mientras tanto
                import winsound
                winsound.PlaySound(wav, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception:
            pass
    threading.Thread(target=correr, daemon=True, name="oir").start()


def _papel(nombre):
    base = os.path.splitext(nombre)[0].upper()
    for k, v in PAPELES.items():
        if k in base:
            return v
    return ""


class ListaCanciones(QWidget):
    """Las pistas de un estilo de música. Clic en una fila: suena un trozo (del segundo 12 al 37); otro clic, calla."""

    def __init__(self, carpeta, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(px(10))
        self._filas, self._activa = [], None
        try:
            pistas = sorted(f for f in os.listdir(carpeta) if f.lower().endswith((".mp3", ".wav", ".m4a")))
        except OSError:
            pistas = []
        for f in pistas:
            b = QPushButton(objectName="fila_cancion", checkable=True)
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(piezas.qicono("play", "#7CF5C0", px(40)))
            b.setIconSize(QSize(px(40), px(40)))
            nombre = os.path.splitext(f)[0].lstrip("0123456789 ").capitalize()
            papel = _papel(f)
            b.setText("  %s%s" % (nombre, "   ·   " + papel if papel else ""))
            b.setStyleSheet(
                "QPushButton { text-align: left; padding: 0 %dpx; min-height: %dpx; font-size: %dpx; font-weight: 500; "
                "border-radius: %dpx; border: 1px solid rgba(255,255,255,0.20); background: rgba(255,255,255,0.03); }"
                "QPushButton:hover { background: rgba(255,255,255,0.08); }"
                "QPushButton:checked { background: rgba(34,196,126,0.30); border-color: #22C47E; }"
                % (px(26), px(70), px(30), px(14)))
            ruta = os.path.join(carpeta, f)
            b.clicked.connect(lambda _=False, bb=b, r=ruta: self._tocar(bb, r))
            v.addWidget(b)
            self._filas.append(b)
        if not pistas:
            v.addWidget(QLabel("Este estilo no trae canciones en esta instalación."))
        nota = QLabel("Clic en una canción para oír un trozo.")
        nota.setStyleSheet("color: #9DB0B6; font-size: %dpx;" % px(26))
        nota.setAlignment(Qt.AlignCenter)
        v.addWidget(nota)

    def _tocar(self, boton, ruta):
        for b in self._filas:
            if b is not boton:
                b.setChecked(False)
        if boton.isChecked():
            sonar(ruta, 12.0 if "INTRO" not in os.path.basename(ruta).upper() else 0.0, 25.0)
        else:
            callar()

    def hideEvent(self, e):
        callar()
        super().hideEvent(e)


class VistaIntro(QWidget):
    """El ejemplo de una intro: las 8 fotos entrando con su ritmo (cortes en cuadros a 24 por segundo), el impacto y un
    momento del «video»; se repite. Con su efecto de sonido en cada vuelta si se puede."""
    FPS = 24.0
    PAUSA_S = 1.6                # lo que se queda la ultima imagen (el «video») antes de repetir

    def __init__(self, cortes, fotos, sfx=None, parent=None):
        super().__init__(parent)
        self.cortes = [max(1, int(c)) for c in cortes]
        self.sfx = sfx if sfx and os.path.isfile(sfx) else None
        self.setMinimumSize(px(900), px(590))        # el cuadro 16:9 + la tira del ritmo y sus letras
        self._fotos = []
        for r in list(fotos)[:len(self.cortes) + 1]:
            try:
                lector = QImageReader(r)
                lector.setAutoTransform(True)
                tam = lector.size()
                if tam.isValid() and tam.width() > 1280:
                    lector.setScaledSize(QSize(1280, int(tam.height() * 1280.0 / tam.width())))
                img = lector.read()
                if not img.isNull():
                    self._fotos.append(QPixmap.fromImage(img))
            except Exception:
                pass
        self._t0 = time.monotonic()
        self._vuelta = -1
        self._reloj = QTimer(self, interval=piezas.CUADRO_MS)
        self._reloj.timeout.connect(self._tic)
        self._reloj.start()

    def _dur(self):
        return sum(self.cortes) / self.FPS + self.PAUSA_S

    def _tic(self):
        if not self.isVisible():
            return
        vuelta = int((time.monotonic() - self._t0) / self._dur())
        if vuelta != self._vuelta:
            self._vuelta = vuelta
            if self.sfx:
                sonar(self.sfx, 0.0, self._dur())
        self.update()

    def hideEvent(self, e):
        self._reloj.stop()
        callar()
        super().hideEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect())
        # 16:9 centrado
        w = min(r.width(), r.height() * 16.0 / 9.0)
        cuadro = QRectF(r.center().x() - w / 2, r.center().y() - w * 9 / 32.0, w, w * 9 / 16.0)
        marco = QPainterPath()
        marco.addRoundedRect(cuadro, px(18), px(18))
        p.setClipPath(marco)
        p.fillRect(cuadro, QColor(4, 10, 12))
        t = (time.monotonic() - self._t0) % self._dur()
        f = t * self.FPS
        k, ini = 0, 0.0
        while k < len(self.cortes) and f >= ini + self.cortes[k]:
            ini += self.cortes[k]
            k += 1
        en_video = k >= len(self.cortes)
        u = 0.0 if en_video else (f - ini) / float(self.cortes[k])        # avance dentro de esta foto
        n = len(self._fotos)
        if n:
            pm = self._fotos[min(k, n - 1) if n > len(self.cortes) else k % n]
            z = 1.06 - 0.06 * u if not en_video else 1.0 + 0.03 * min(1.0, (f - ini) / (self.PAUSA_S * self.FPS))
            esc = max(cuadro.width() / pm.width(), cuadro.height() / pm.height()) * z
            tw, th = pm.width() * esc, pm.height() * esc
            p.drawPixmap(QRectF(cuadro.center().x() - tw / 2, cuadro.center().y() - th / 2, tw, th), pm, QRectF(pm.rect()))
        else:
            p.fillRect(cuadro, QColor.fromHsv((k * 37) % 360, 120, 110))
        if not en_video and u < 0.35:                                   # el destello de cada corte
            p.fillRect(cuadro, QColor(255, 255, 255, int(150 * (1.0 - u / 0.35))))
        if en_video and (f - ini) < 5:                                   # el impacto: donde entra la musica
            p.fillRect(cuadro, QColor(255, 255, 255, int(220 * (1.0 - (f - ini) / 5.0))))
        p.setClipping(False)
        p.setPen(QPen(QColor(217, 177, 92, 200), max(1.0, px(3))))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(cuadro, px(18), px(18))
        # la tira del ritmo: una marca por foto, del ancho de lo que dura
        total = float(sum(self.cortes))
        x, y, alto = cuadro.left(), cuadro.bottom() + px(18), px(16)
        if y + alto <= r.bottom():
            for i, c in enumerate(self.cortes):
                ancho = cuadro.width() * 0.72 * c / total
                activo = (i == k) and not en_video
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#22C47E") if activo else QColor(255, 255, 255, 60 if i < k or en_video else 28))
                p.drawRoundedRect(QRectF(x, y, max(2.0, ancho - px(6)), alto), alto / 2, alto / 2)
                x += ancho
            p.setBrush(QColor("#E2B04F") if en_video else QColor(226, 176, 79, 70))
            p.drawRoundedRect(QRectF(x, y, cuadro.right() - x, alto), alto / 2, alto / 2)
            f2 = QFont(self.font())
            f2.setPixelSize(max(9, px(24)))
            p.setFont(f2)
            p.setPen(QColor("#9DB0B6"))
            p.drawText(QRectF(cuadro.left(), y + alto + px(6), cuadro.width(), px(36)), Qt.AlignLeft | Qt.AlignVCenter,
                       "8 fotos")
            p.drawText(QRectF(cuadro.left(), y + alto + px(6), cuadro.width(), px(36)), Qt.AlignRight | Qt.AlignVCenter,
                       "arranca el video")

    def sizeHint(self):
        return QSize(px(1000), px(640))
