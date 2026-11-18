# -*- mode: python ; coding: utf-8 -*-
# Receta de PyInstaller para la Mac: TrailerAutomatico.app (la usa construir_mac.sh).
import os
import glob

PROG = os.environ["TRAILER_PROGRAMA"]
FFMPEG = os.environ.get("TRAILER_FFMPEG", "")
ICNS = os.environ.get("TRAILER_ICNS") or None
VERSION = os.environ.get("TRAILER_VERSION", "1.0.0")

# el codigo va en carpetas (nucleo, analisis, armado, entrega, interfaz); en el .exe / .app queda todo junto
GRUPOS = ("nucleo", "analisis", "armado", "entrega", "interfaz")
propios = [f for g in GRUPOS for f in glob.glob(os.path.join(PROG, g, "*.py"))]
datas = [(f, ".") for f in propios]
for x in ("perfiles_evento.json", "version.txt", "LEEME.txt"):
    datas.append((os.path.join(PROG, "config", x), "."))
# el desinstalador va DENTRO de la app (el disco solo trae la app y el enlace a Aplicaciones)
datas.append((os.path.join(PROG, "compilar", "mac", "Desinstalar.command"), "."))
for carpeta in ("recursos", "dctl"):
    ruta = os.path.join(PROG, carpeta)
    if not os.path.isdir(ruta):
        raise SystemExit("Falta la carpeta %s" % ruta)
    datas.append((ruta, carpeta))
if FFMPEG:
    for exe in ("ffmpeg", "ffprobe"):
        if os.path.exists(os.path.join(FFMPEG, exe)):
            datas.append((os.path.join(FFMPEG, exe), "ffmpeg"))
modulos = [os.path.splitext(os.path.basename(f))[0] for f in propios if not f.endswith("trailer_xv.py")]

a = Analysis(
    [os.path.join(PROG, "interfaz", "trailer_xv.py")],
    pathex=[os.path.join(PROG, g) for g in GRUPOS],
    datas=datas,
    hiddenimports=modulos + ["PIL.Image", "PIL.ImageOps", "numpy", "logging.handlers", "faulthandler", "onnxruntime"],
    excludes=["torch", "torchvision", "torchaudio", "transformers", "sympy", "onnx", "tensorboard", "tensorflow",
              "onnxruntime.transformers", "onnxruntime.quantization", "onnxruntime.training", "onnxruntime.tools",
              "librosa", "numba", "llvmlite", "scipy", "sklearn", "matplotlib", "pandas", "tkinter", "IPython",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtNetwork", "PySide6.QtOpenGL",
              "PySide6.QtOpenGLWidgets", "PySide6.QtPdf", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.QtMultimedia", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
              "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSvg"],
)
a.datas = [d for d in a.datas if not d[0].replace("\\", "/").lower().startswith("pyside6/translations")]
a.datas = [d for d in a.datas if "/.cf/" not in d[0].replace("\\", "/") and not d[0].lower().endswith("desktop.ini")]
a.datas = [d for d in a.datas if "/musica/xv/" not in d[0].replace("\\", "/").lower()
           and "/musica/_descartadas/" not in d[0].replace("\\", "/").lower()]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TrailerAutomatico", console=False, upx=False,
          argv_emulation=False)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="TrailerAutomatico")
app = BUNDLE(coll, name="TrailerAutomatico.app", icon=ICNS, bundle_identifier="com.cinemaproductions.trailerautomatico",
             info_plist={"CFBundleName": "Tráiler automático", "CFBundleDisplayName": "Tráiler automático",
                         "CFBundleShortVersionString": VERSION, "CFBundleVersion": VERSION,
                         "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "13.0",
                         "NSRequiresAquaSystemAppearance": False})
