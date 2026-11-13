# -*- coding: utf-8 -*-
"""qt_kit.py - Lo minimo del kit de interfaz de CineCaptions que usa la escena de Inicio (escena_go, estilos_inicio,
orbe_mecanica, boton_go): fuentes en pixeles, trabajo en un hilo e iconos de linea."""
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QFont, QFontDatabase, QIcon

_FAMILIA = [None]
PESOS = {None: QFont.Weight.Normal, "medio": QFont.Weight.Medium, "negrita": QFont.Weight.Bold,
         "extra": QFont.Weight.ExtraBold}


def familia_ui():
    if _FAMILIA[0] is None:
        hay = set(QFontDatabase.families())
        _FAMILIA[0] = next((f for f in ("Inter", "Segoe UI Variable Display", "Segoe UI", "SF Pro Display",
                                        "Helvetica Neue", "Arial") if f in hay), "Arial")
    return _FAMILIA[0]


def fuente(tam=13, negrita=False, italica=False, subrayada=False, familia=None, peso=None):
    """QFont en PIXELES. peso: 'medio' | 'negrita' | 'extra'."""
    if peso is None and negrita:
        peso = "negrita"
    f = QFont(familia or familia_ui())
    f.setPixelSize(max(1, int(tam)))
    f.setWeight(PESOS.get(peso, QFont.Weight.Normal))
    f.setItalic(italica)
    f.setUnderline(subrayada)
    return f


class _Mensajero(QObject):
    listo = Signal(object, object)


_VIVOS = set()


def correr_en_hilo(contexto, trabajo, al_terminar, baja=False):
    """Corre trabajo() en un hilo y llama al_terminar(resultado, error) en el hilo de la ventana."""
    m = _Mensajero()
    _VIVOS.add(m)

    def entregar(r, e):
        _VIVOS.discard(m)
        try:
            al_terminar(r, e)
        except Exception:
            pass
    m.listo.connect(entregar)

    def correr():
        try:
            r, e = trabajo(), None
        except BaseException as ex:
            r, e = None, ex
        m.listo.emit(r, e)
    threading.Thread(target=correr, daemon=True).start()


def icono_linea(nombre, color=None, color_activo=None):
    """Iconos Phosphor de qtawesome si estan instalados; si no, un icono vacio (el estilo sigue funcionando)."""
    try:
        import qtawesome
        return qtawesome.icon(nombre, color=color or "#FFFFFF")
    except Exception:
        return QIcon()
