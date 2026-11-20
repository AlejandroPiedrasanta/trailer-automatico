# -*- coding: utf-8 -*-
"""
animacion.py - (1.6.0) Lo que se mueve en la ventana.

  Pelicula(al_cuadro, al_terminar)  un video de recursos/animaciones (Higgsfield) cuadro a cuadro, en bucle o una vez.
        ffmpeg lo decodifica Y LO ESCALA en su propio proceso y lo pasa por un tubo a un hilo; el hilo deja el ultimo
        cuadro listo (QImage) y avisa a la ventana (nunca se juntan cuadros: si la ventana va atrasada, salta). Los
        videos con la mascara abajo (alfa=True: color arriba, alfa abajo) salen con transparencia. En pausa (pagina
        oculta, ventana minimizada) ffmpeg queda quieto: 0 % de CPU; con la ventana atras, a media velocidad.
  Fundido(pagina)  al cambiar de pestaña la pagina de antes se desvanece (y se aleja un poco) sobre la nueva.
  brillo_al_pasar(boton)  un borde de luz que aparece suave al pasar el raton (sin tocar el estilo del boton).
  aparecer(widget)        aparece desvaneciendose; contar(etiqueta, n): el numero sube contando.
  ruta(nombre)     el video en recursos/animaciones, o None (sin el, cada pieza usa su imagen quieta).
  Los videos se hacen con herramientas/preparar_animaciones.py (Higgsfield / Kling 3.0, sobre negro puro).

Nada de esto corre antes de que se vea la ventana (regla de arranque): las piezas lo arrancan un rato despues.
"""
import atexit
import os
import shutil
import subprocess
import threading
import time
import weakref

from PySide6.QtCore import QObject, Qt, Signal, Slot, QVariantAnimation, QEasingCurve, QPointF, QRectF, QEvent, QTimer
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QLinearGradient
from PySide6.QtWidgets import QWidget

import rutas

CARPETA = os.path.join(rutas.RECURSOS, "animaciones")
_VIVAS = set()


def ruta(nombre):
    r = os.path.join(CARPETA, nombre)
    return r if os.path.isfile(r) else None


_CERRANDO = False


@atexit.register
def _cerrar_todas():
    global _CERRANDO
    _CERRANDO = True                    # los hilos ya no avisan a una ventana que se esta destruyendo
    for p in list(_VIVAS):
        try:
            p.kill()
        except Exception:
            pass


def _abrir(cmd):
    """ffmpeg con su salida por un tubo -> (proceso, archivo para leer) o None. En Windows el tubo es de 4 MB: con el
    de siempre (4 KB) cada cuadro del cielo eran miles de lecturas (la mitad de la CPU del lector, medido)."""
    if rutas.ES_WIN:
        try:
            import _winapi
            import msvcrt
            leer, escribir = _winapi.CreatePipe(None, 4 << 20)
            try:
                fd = msvcrt.open_osfhandle(escribir, 0)
            except Exception:
                _winapi.CloseHandle(escribir)
                _winapi.CloseHandle(leer)
                raise
            try:
                p = subprocess.Popen(cmd, stdout=fd, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                     creationflags=rutas.SIN_VENTANA)
            except Exception:
                _winapi.CloseHandle(leer)
                raise
            finally:
                os.close(fd)                              # nuestra punta de escritura: sin ella llega el fin
            return p, open(msvcrt.open_osfhandle(leer, 0), "rb", buffering=0)
        except Exception:
            pass
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                             bufsize=0, creationflags=rutas.SIN_VENTANA)
        return p, p.stdout
    except Exception:
        return None


def _leer(tubo, buf, n):
    """Llena buf con un cuadro entero; False al terminar el video (o si se corto)."""
    mv = memoryview(buf)
    hecho = 0
    try:
        while hecho < n:
            m = tubo.readinto(mv[hecho:])
            if not m:
                return False
            hecho += m
    except (OSError, ValueError):
        return False
    return True


_PELIS = weakref.WeakSet()


def detener_todas():
    """(1.6.0) Al cerrar la ventana: para cada video (ffmpeg fuera) antes de que se destruyan sus piezas."""
    global _CERRANDO
    _CERRANDO = True
    for peli in list(_PELIS):
        try:
            peli.detener()
        except RuntimeError:
            pass
    _cerrar_todas()


def _avisar(senal, *args):
    """Emite desde el hilo; False si la ventana ya se destruyo (al cerrar: «Signal source has been deleted»)."""
    if _CERRANDO:
        return False
    try:
        senal.emit(*args)
        return True
    except RuntimeError:
        return False


class Pelicula(QObject):
    _nuevo = Signal()
    _acabo = Signal(int)

    def __init__(self, al_cuadro, al_terminar=None, parent=None):
        super().__init__(parent)
        self._al_cuadro, self._al_terminar = al_cuadro, al_terminar
        self._gen = 0
        self._candado = threading.Lock()
        self._ultimo = None                     # (gen, QImage, bytes): los bytes mantienen viva la memoria del QImage
        self._avisado = False
        self._corre = threading.Event()
        self._corre.set()
        self._factor = 1.0                      # 0,5 con la ventana en segundo plano: a media velocidad, media CPU
        self._proc = None
        self.ruta = None
        self.tam = (0, 0)
        self._nuevo.connect(self._tomar, Qt.QueuedConnection)
        self._acabo.connect(self._fin, Qt.QueuedConnection)
        _PELIS.add(self)

    # ---- desde la ventana
    def reproducir(self, ruta, ancho, alto, fps=24.0, bucle=True, alfa=False):
        """True si arranco (hace falta ffmpeg y el video)."""
        self.detener()
        exe = shutil.which("ffmpeg")
        ancho, alto = int(ancho) // 2 * 2, int(alto) // 2 * 2      # pares: el escalador de yuv420 los pide
        if not exe or not ruta or not os.path.isfile(ruta) or ancho < 16 or alto < 16:
            return False
        self.ruta, self.tam = ruta, (ancho, alto)
        gen = self._gen
        threading.Thread(target=self._correr, args=(gen, exe, ruta, ancho, alto, float(fps), bucle, alfa),
                         daemon=True, name="pelicula").start()
        return True

    def pausar(self, si):
        if si:
            self._corre.clear()
        else:
            self._corre.set()

    def lento(self, si):
        self._factor = 0.5 if si else 1.0

    def en_pausa(self):
        return not self._corre.is_set()

    def detener(self):
        with self._candado:
            self._gen += 1
            p, self._proc = self._proc, None
            self._ultimo = None
        self.ruta = None
        if p is not None:
            _VIVAS.discard(p)
            try:
                p.kill()
            except Exception:
                pass

    # ---- en el hilo de la ventana
    @Slot()
    def _tomar(self):
        with self._candado:
            u, self._ultimo, self._avisado = self._ultimo, None, False
        if u is not None and u[0] == self._gen:
            self._al_cuadro(u[1], u[2])

    @Slot(int)
    def _fin(self, gen):
        if gen == self._gen and self._al_terminar is not None:
            self.ruta = None
            self._al_terminar()

    # ---- en su hilo
    def _correr(self, gen, exe, ruta, w, h, fps, bucle, alfa):
        if alfa:        # color arriba y mascara abajo: se escalan juntos y se unen (Qt premultiplica al pintar)
            vf = ("[0:v]scale=%d:%d:flags=bilinear,split[a][b];[a]crop=%d:%d:0:0[c];[b]crop=%d:%d:0:%d[m];"
                  "[c][m]alphamerge,format=bgra[o]" % (w, 2 * h, w, h, w, h, h))
            fmt = QImage.Format_ARGB32
        else:           # opaco, cubriendo el tamaño pedido (se recorta lo que sobra)
            vf = ("[0:v]scale=%d:%d:force_original_aspect_ratio=increase:flags=bilinear,crop=%d:%d,format=bgra[o]"
                  % (w, h, w, h))
            fmt = QImage.Format_RGB32
        cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin", "-threads", "1"]
        if bucle:
            cmd += ["-stream_loop", "-1"]
        cmd += ["-i", ruta, "-an", "-filter_complex", vf, "-map", "[o]", "-f", "rawvideo", "-pix_fmt", "bgra",
                "pipe:1"]
        n = w * h * 4
        abierto = _abrir(cmd)
        if abierto is None:
            return
        p, tubo = abierto
        with self._candado:
            if gen != self._gen:
                p.kill()
                tubo.close()
                return
            self._proc = p
        _VIVAS.add(p)
        # memoria reusada (un cuadro nuevo no pide memoria nueva): ~200 ms de cuadros, para que el que se esta
        # pintando no se sobrescriba aunque la ventana se demore
        anillo = [bytearray(n) for _ in range(max(3, int(fps * 0.2) + 2))]
        k = 0
        siguiente = time.perf_counter()
        terminado = False
        try:
            while gen == self._gen:
                if not self._corre.is_set():
                    while not self._corre.wait(0.25):
                        if gen != self._gen:
                            return
                    siguiente = time.perf_counter()
                buf = anillo[k % len(anillo)]
                k += 1
                if not _leer(tubo, buf, n):
                    terminado = True
                    break
                img = QImage(buf, w, h, w * 4, fmt)
                with self._candado:
                    if gen != self._gen:
                        break
                    self._ultimo = (gen, img, buf)
                    avisar, self._avisado = not self._avisado, True
                if avisar and not _avisar(self._nuevo):
                    break
                siguiente += 1.0 / max(1.0, fps * self._factor)
                espera = siguiente - time.perf_counter()
                if espera > 0:
                    time.sleep(espera)
                elif espera < -0.3:                 # se atraso mucho (ventana ocupada): sigue sin correr
                    siguiente = time.perf_counter()
        except Exception:
            pass
        finally:
            _VIVAS.discard(p)
            try:
                p.kill()
            except Exception:
                pass
            try:
                tubo.close()
            except Exception:
                pass
            if terminado and gen == self._gen and not _CERRANDO:
                _avisar(self._acabo, gen)


class _Brillo(QWidget):
    """El brillo al pasar el raton: un borde de luz y un reflejo arriba que aparecen y se van suaves (220 ms)."""

    def __init__(self, boton, color, radio):
        super().__init__(boton)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._color, self._radio, self._v = QColor(color), radio, 0.0
        self._anim = QVariantAnimation(self, duration=220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._paso)
        boton.installEventFilter(self)
        self.resize(boton.size())
        self.hide()

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Enter and obj.isEnabled():
            self._ir(1.0)
        elif t in (QEvent.Leave, QEvent.Hide, QEvent.EnabledChange):
            self._ir(0.0)
        elif t == QEvent.Resize:
            self.resize(obj.size())
        return False

    def _ir(self, meta):
        if abs(meta - self._v) < 0.01:
            return
        self._anim.stop()
        self._anim.setStartValue(self._v)
        self._anim.setEndValue(meta)
        self._anim.start()
        self.show()
        self.raise_()

    def _paso(self, v):
        self._v = float(v)
        if self._v <= 0.01:
            self.hide()
        self.update()

    def paintEvent(self, _):
        # (18-nov, captura de la persona: dos botones con el filo dorado a la vez) si el raton ya no esta encima y no
        # llego el aviso de salida (pasa al abrir un popup o al mover rapido), el brillo se apaga solo
        padre = self.parentWidget()
        if padre is not None and not padre.underMouse() and self._anim.state() != QVariantAnimation.Running \
                and self._v > 0.01:
            QTimer.singleShot(0, lambda: self._ir(0.0))
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        rad = min(r.height() / 2.0, self._radio if self._radio is not None else r.height() / 2.0)
        abierto = getattr(self, "abierto", "")   # (19-nov) en la barra del Inicio: el lado pegado al vecino, sin esquina
        if abierto:
            p.setClipRect(QRectF(self.rect()))
            r = r.adjusted(-rad - 2 if abierto in ("izq", "ambos") else 0, 0,
                           rad + 2 if abierto in ("der", "ambos") else 0, 0)
        c = QColor(self._color)
        c.setAlpha(int(210 * self._v))
        p.setPen(QPen(c, 1.6))
        luz = QLinearGradient(r.topLeft(), r.bottomLeft())
        luz.setColorAt(0.0, QColor(255, 255, 255, int(34 * self._v)))
        luz.setColorAt(0.6, QColor(255, 255, 255, 0))
        p.setBrush(luz)
        p.drawRoundedRect(r, rad, rad)


def brillo_al_pasar(boton, color="#E2B04F", radio=None, abierto=""):
    """(1.6.0) Que un boton brille suave al pasar el raton (sin tocar su estilo). abierto: "izq", "der" o "ambos",
    los lados que siguen en el boton vecino (las partes de una barra): por ahi el brillo no cierra ni redondea."""
    if getattr(boton, "_brillo", None) is None:
        boton._brillo = _Brillo(boton, color, radio)
    boton._brillo._radio = radio                 # (si la ventana cambio de escala, el radio del estilo tambien)
    boton._brillo.abierto = abierto
    return boton._brillo


def aparecer(widget, ms=380):
    """(1.6.0) El widget aparece desvaneciendose (y sin efecto despues: no queda pintando de mas)."""
    from PySide6.QtWidgets import QGraphicsOpacityEffect
    if widget.graphicsEffect() is not None:          # ya tiene uno (una sombra): no se le quita
        return None
    ef = QGraphicsOpacityEffect(widget)
    ef.setOpacity(0.0)
    widget.setGraphicsEffect(ef)
    anim = QVariantAnimation(widget, startValue=0.0, endValue=1.0, duration=ms)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.valueChanged.connect(lambda v: ef.setOpacity(float(v)))

    def fin():
        if widget.graphicsEffect() is ef:
            widget.setGraphicsEffect(None)
    anim.finished.connect(fin)
    anim.start(QVariantAnimation.DeleteWhenStopped)
    return anim


def contar(etiqueta, hasta, formato="{}", ms=700):
    """(1.6.0) Un numero que sube contando hasta su valor (las tarjetas de Material)."""
    try:
        desde = int(getattr(etiqueta, "_cuenta", 0))
    except (TypeError, ValueError):
        desde = 0
    hasta = int(hasta)
    etiqueta._cuenta = hasta
    viejo = getattr(etiqueta, "_anim_cuenta", None)
    if viejo is not None:
        viejo.stop()
    if desde == hasta or not etiqueta.isVisible():
        etiqueta.setText(formato.format(hasta))
        return
    anim = QVariantAnimation(etiqueta, startValue=float(desde), endValue=float(hasta), duration=ms)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.valueChanged.connect(lambda v: etiqueta.setText(formato.format(int(round(float(v))))))
    etiqueta._anim_cuenta = anim
    anim.start()


class Fundido(QWidget):
    """Encima de las paginas: la de antes (una foto) se desvanece y se aleja un poco mientras la nueva ya esta."""

    def __init__(self, sobre):
        super().__init__(sobre)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()
        self._pm, self._v = None, 0.0
        self._anim = QVariantAnimation(self, startValue=1.0, endValue=0.0, duration=280)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._paso)
        self._anim.finished.connect(self._listo)

    def empezar(self, pm):
        if pm is None or pm.isNull():
            return
        self._pm = pm
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()
        self._anim.stop()
        self._anim.start()

    def _paso(self, v):
        self._v = float(v)
        self.update()

    def _listo(self):
        self.hide()
        self._pm = None

    def paintEvent(self, _):
        if self._pm is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setOpacity(max(0.0, self._v))
        k = 0.97 + 0.03 * self._v                     # se aleja: de 100 % a 97 %
        c = QPointF(self.width() / 2.0, self.height() / 2.0)
        p.translate(c)
        p.scale(k, k)
        p.translate(-c)
        p.drawPixmap(0, 0, self._pm)
