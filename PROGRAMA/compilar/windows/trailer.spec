# -*- mode: python ; coding: utf-8 -*-
# Receta de PyInstaller del "Trailer automatico" (modo carpeta, sin consola). La usa construir.ps1.
import os
import glob

PROG = os.environ["TRAILER_PROGRAMA"]
FFMPEG = os.environ.get("TRAILER_FFMPEG", "")
ICONO = os.path.join(PROG, "compilar", "icono", "icono.ico")

# el codigo va en carpetas (nucleo, analisis, armado, entrega, interfaz); en el .exe / .app queda todo junto
GRUPOS = ("nucleo", "analisis", "armado", "entrega", "interfaz")
propios = [f for g in GRUPOS for f in glob.glob(os.path.join(PROG, g, "*.py"))]
# los modulos tambien van como .py: build_trailers.py se ejecuta desde su archivo y carga los demas por ruta
datas = [(f, ".") for f in propios]
for x in ("perfiles_evento.json", "version.txt", "LEEME.txt"):
    datas.append((os.path.join(PROG, "config", x), "."))
for carpeta in ("recursos", "dctl"):
    ruta = os.path.join(PROG, carpeta)
    if not os.path.isdir(ruta):
        raise SystemExit("Falta la carpeta %s" % ruta)
    datas.append((ruta, carpeta))
if FFMPEG:
    for exe in ("ffmpeg.exe", "ffprobe.exe"):
        datas.append((os.path.join(FFMPEG, exe), "ffmpeg"))

modulos = [os.path.splitext(os.path.basename(f))[0] for f in propios if not f.endswith("trailer_xv.py")]

a = Analysis(
    [os.path.join(PROG, "interfaz", "trailer_xv.py")],
    pathex=[os.path.join(PROG, g) for g in GRUPOS],
    binaries=[],
    datas=datas,
    hiddenimports=modulos + ["PIL.Image", "PIL.ImageOps", "numpy", "winreg", "logging.handlers", "faulthandler"],
    excludes=["librosa", "numba", "llvmlite", "scipy", "sklearn", "matplotlib", "pandas", "tkinter", "IPython",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtNetwork", "PySide6.QtOpenGL",
              "PySide6.QtOpenGLWidgets", "PySide6.QtPdf", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.QtMultimedia", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
              "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSvg"],
    noarchive=False,
)
# lo que no hace falta y pesa (lecciones de CineCaptions): OpenGL por software y traducciones de Qt
a.binaries = [b for b in a.binaries if "opengl32sw" not in b[0].lower()]
a.datas = [d for d in a.datas if not d[0].replace("\\", "/").lower().startswith("pyside6/translations")]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TrailerAutomatico", console=False, upx=False,
          icon=ICONO if os.path.exists(ICONO) else None)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="TrailerAutomatico")
