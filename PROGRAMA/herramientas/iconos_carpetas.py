# -*- coding: utf-8 -*-
"""
iconos_carpetas.py - Pone a las carpetas del proyecto el icono negro de CINEMA PRODUCTIONS con su nombre (igual que
en CINESLIDE): la raiz, PROGRAMA, 3 INSTALADORES y las carpetas de dentro de esas dos. Solo Windows.

  python PROGRAMA/herramientas/iconos_carpetas.py            pone (o rehace) los iconos
  python PROGRAMA/herramientas/iconos_carpetas.py --quitar   los quita

Cada carpeta lleva, ocultos, `.cf/icono.ico` y `desktop.ini`. Git, el compilador y el paquete de Mac los saltan.
La carpeta en blanco (sin nombre) es PROGRAMA/compilar/icono/carpeta_base.png.
"""
import ctypes
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

PROGRAMA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.dirname(PROGRAMA)
BASE = os.path.join(PROGRAMA, "compilar", "icono", "carpeta_base.png")
FUENTE = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeuib.ttf")
TAMANOS = [16, 24, 32, 48, 64, 128, 256]
ANCHO, CENTRO_Y, K = 208, 148, 4                   # ancho util y centro del cuerpo de la carpeta (en 256 px); K: sobremuestreo


def carpetas():
    """La raiz, sus carpetas a la vista y las de dentro de cada una (dos niveles, como CINESLIDE)."""
    visibles = lambda d: sorted(os.path.join(d, x) for x in os.listdir(d)                      # noqa: E731
                                if os.path.isdir(os.path.join(d, x)) and not x.startswith((".", "__")))
    lista = [RAIZ]
    for c in visibles(RAIZ):
        lista += [c] + visibles(c)
    return lista


def rotulo(carpeta):
    """`3 INSTALADORES` -> INSTALADORES, `recursos_protegidos` -> RECURSOS PROTEGIDOS."""
    palabras = os.path.basename(carpeta).replace("_", " ").upper().split()
    if len(palabras) > 1 and palabras[0].isdigit():
        palabras = palabras[1:]
    return palabras


def _lineas(palabras, dibujo):
    """El reparto (una o dos lineas) que deja la letra mas grande."""
    opciones = [[" ".join(palabras)]] + [[" ".join(palabras[:i]), " ".join(palabras[i:])] for i in range(1, len(palabras))]
    mejor = None
    for lineas in opciones:
        for t in range(46 if len(lineas) == 1 else 40, 9, -1):
            f = ImageFont.truetype(FUENTE, t * K)
            if max(dibujo.textlength(x, font=f) for x in lineas) <= ANCHO * K:
                break
        if mejor is None or t > mejor[0] + (4 if len(lineas) == 2 else 0):      # dos lineas solo si ganan de verdad
            mejor = (t, lineas, f)
    return mejor


def dibujar(palabras):
    base = Image.open(BASE).convert("RGBA")
    capa = Image.new("RGBA", (256 * K, 256 * K), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    t, lineas, f = _lineas(palabras, d)
    alto_linea = int(t * K * 1.08)
    mayus = f.getbbox("H")                                     # alto real de las mayusculas
    alto_texto = alto_linea * (len(lineas) - 1) + (mayus[3] - mayus[1])
    hueco, barra = 13 * K, 5 * K
    y = CENTRO_Y * K - (alto_texto + hueco + barra) // 2
    for i, linea in enumerate(lineas):
        x = (256 * K - d.textlength(linea, font=f)) / 2
        d.text((x, y + i * alto_linea - mayus[1]), linea, font=f, fill=(255, 255, 255, 255))
    yb = y + alto_texto + hueco
    d.rounded_rectangle((128 * K - 23 * K, yb, 128 * K + 23 * K, yb + barra), radius=barra // 2, fill=(255, 255, 255, 255))
    base.alpha_composite(capa.resize((256, 256), Image.LANCZOS))
    return base


def _attrib(*args):
    subprocess.run(["attrib", *args], capture_output=True)


def poner(carpeta):
    cf, ini = os.path.join(carpeta, ".cf"), os.path.join(carpeta, "desktop.ini")
    os.makedirs(cf, exist_ok=True)
    ico = os.path.join(cf, "icono.ico")
    dibujar(rotulo(carpeta)).save(ico, sizes=[(s, s) for s in TAMANOS])
    if os.path.exists(ini):
        _attrib("-h", "-s", ini)
    with open(ini, "w", encoding="utf-8") as f:
        f.write("[.ShellClassInfo]\nIconResource=.cf\\icono.ico,0\n")
    _attrib("+h", "+s", ini)
    _attrib("+h", cf)
    _attrib("+r", carpeta)                           # sin esto Windows no lee el desktop.ini de la carpeta


def quitar(carpeta):
    cf, ini = os.path.join(carpeta, ".cf"), os.path.join(carpeta, "desktop.ini")
    if os.path.exists(ini):
        _attrib("-h", "-s", ini)
        os.remove(ini)
    if os.path.exists(os.path.join(cf, "icono.ico")):
        os.remove(os.path.join(cf, "icono.ico"))
        os.rmdir(cf)
    _attrib("-r", carpeta)


def main():
    if sys.platform != "win32":
        raise SystemExit("Los iconos de carpeta son solo de Windows.")
    accion = quitar if "--quitar" in sys.argv else poner
    lista = carpetas()
    for c in lista:
        accion(c)
        ctypes.windll.shell32.SHChangeNotify(0x00001000, 0x0005, ctypes.c_wchar_p(c), None)      # SHCNE_UPDATEDIR
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)                              # SHCNE_ASSOCCHANGED
    print("%s el icono de %d carpetas" % ("Quitado" if accion is quitar else "Puesto", len(lista)))


if __name__ == "__main__":
    main()
