# -*- coding: utf-8 -*-
"""
probar_arrastre.py - Lanza la prueba «suelta la carpeta y listo» en ESTE equipo (Windows o Mac), sin tocar tu material:
crea un evento de mentira, abre el programa con una carpeta de trabajo y unos datos aparte, suelta la carpeta en la ventana
y comprueba que se ordene, se organice y empiece a armar. Todo en local (sin internet).

  python PROGRAMA/herramientas/probar_arrastre.py                      prueba el codigo
  python PROGRAMA/herramientas/probar_arrastre.py --programa <exe>     prueba el programa instalado o compilado
     Windows: %LOCALAPPDATA%\\Programs\\TrailerAutomatico\\TrailerAutomatico.exe
     Mac:     /Applications/TrailerAutomatico.app/Contents/MacOS/TrailerAutomatico
  --salida <carpeta>     donde dejar resultado.txt y las capturas (por defecto, una carpeta temporal)
  --con-davinci          deja que conecte con DaVinci Resolve y arme de verdad (crea «BODA 2026-10-17 - 1min»)
  --dos-eventos          antes deja OTRO evento ya terminado: lo soltado empieza uno nuevo sin preguntar y el anterior
                         queda en ANTERIORES (1.5.7: si no estuviera terminado, se uniria al mismo evento)
Sin --con-davinci la prueba hace como si DaVinci no estuviera: llega hasta el plan de las plantillas y el aviso claro.
"""
import os
import sys
import json
import shutil
import tempfile
import subprocess

PROG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(args):
    programa = os.path.abspath(args[args.index("--programa") + 1]) if "--programa" in args else None
    salida = os.path.abspath(args[args.index("--salida") + 1]) if "--salida" in args else None
    zona = tempfile.mkdtemp(prefix="trailer_prueba_")
    salida = salida or os.path.join(zona, "resultado")
    os.makedirs(salida, exist_ok=True)
    orden = [programa] if programa else [sys.executable, os.path.join(PROG, "interfaz", "trailer_xv.py")]
    env = dict(os.environ)
    env.update({"TRAILER_BASE": os.path.join(zona, "trabajo"), "TRAILER_DATOS": os.path.join(zona, "datos"),
                "PYTHONIOENCODING": "utf-8"})
    env.pop("TRAILER_PRUEBA_ARRASTRE", None)
    estado = {"renderizar": False}                      # la prueba nunca renderiza
    if "--con-davinci" in args:
        env["TRAILER_PRUEBA_ESPERA"] = "armado"
        estado["versiones"] = ["1min"]                  # con DaVinci de verdad: solo la de 1 min
    os.makedirs(os.path.join(zona, "datos", "analisis"), exist_ok=True)
    with open(os.path.join(zona, "datos", "analisis", "estado_programa.json"), "w", encoding="utf-8") as f:
        json.dump(estado, f)
    if "--con-davinci" not in args:                     # como si DaVinci no estuviera instalado: no se toca tu proyecto
        env["RESOLVE_SCRIPT_LIB"] = os.path.join(zona, "no_hay", "fusionscript")
        env["RESOLVE_SCRIPT_API"] = os.path.join(zona, "no_hay")
    material = os.path.join(zona, "para soltar")
    os.makedirs(material)
    r = subprocess.run(orden + ["--tarea", "material_prueba", material], env=env)
    evento = os.path.join(material, "Boda Ana y José (prueba)")
    if r.returncode != 0 or not os.path.isdir(evento):
        err = os.path.join(material, "error.txt")
        print("FALLA  no se pudo crear el material de prueba: %s" % (open(err, encoding="utf-8").read()[:600]
                                                                     if os.path.exists(err) else r.returncode))
        return 1
    if "--dos-eventos" in args:                         # otro evento ya en 1 MATERIAL, YA TERMINADO (con sus videos):
        estado.update({"evento": "EVENTO VIEJO", "terminado": "EVENTO VIEJO"})       # lo soltado empieza uno nuevo
        with open(os.path.join(zona, "datos", "analisis", "estado_programa.json"), "w", encoding="utf-8") as f:
            json.dump(estado, f)
        viejo = os.path.join(env["TRAILER_BASE"], "1 MATERIAL")
        os.makedirs(os.path.join(viejo, "FOTOS"))
        os.makedirs(os.path.join(viejo, "VIDEOS"))
        for k in range(6):                              # sin EXIF: su fecha es la del archivo (junio de 2025)
            for sub, origen in (("FOTOS", os.path.join("Fotos cámara", "foto sin exif.png")),
                                ("VIDEOS", os.path.join("Video cámara", "C000%d.MP4" % (k + 1)))):
                d = os.path.join(viejo, sub, "VIEJO_%d%s" % (k, os.path.splitext(origen)[1]))
                shutil.copy2(os.path.join(evento, origen), d)
                if sub == "FOTOS":                      # que no sean el mismo archivo 6 veces
                    with open(d, "ab") as f:
                        f.write(b"\0" * (k + 1))
                os.utime(d, (1.75e9 + 600 * k, 1.75e9 + 600 * k))
    env["TRAILER_PRUEBA_ARRASTRE"] = evento
    env["TRAILER_PRUEBA_SALIDA"] = salida
    r = subprocess.run(orden, env=env)
    res = os.path.join(salida, "resultado.txt")
    if os.path.exists(res):
        sys.stdout.buffer.write(open(res, "rb").read())
    else:
        print("FALLA  el programa no dejo resultado (codigo %s)" % r.returncode)
    print("capturas y resultado en: %s" % salida)
    if "--dos-eventos" in args:
        ant = os.path.join(env["TRAILER_BASE"], "1 MATERIAL", "ANTERIORES")
        n = sum(len(fs) for _, _, fs in os.walk(ant)) if os.path.isdir(ant) else 0
        print("%s  el evento anterior quedo guardado en ANTERIORES (%d archivos)" % ("OK    " if n >= 12 else "FALLA ", n))
        if n < 12:
            return 1
    return r.returncode if os.path.exists(res) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
