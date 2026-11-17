# -*- coding: utf-8 -*-
"""
masterizar.py - Deja el audio de los renders listo para entregar: volumen parejo y sin saturar.

  - Normaliza a -14 LUFS (redes, celular, YouTube) con picos maximos de -1 dBTP (sin saturacion).
  - Dos pasadas de ffmpeg loudnorm (medir y aplicar). El video se copia tal cual (no se recomprime).
  - Todas las versiones quedan al mismo volumen.

Uso:  python masterizar.py "2 VIDEOS TERMINADOS\\BODA 2026-11-07"     (todos los .mov/.mp4 de la carpeta)
"""
import os
import re
import sys
import json
import subprocess

OBJETIVO_LUFS = -14.0
PICO_MAX = -1.5          # se apunta a -1.5 para quedar con margen bajo -1 dBTP
RANGO = 11.0
if __name__ == "__main__":                 # suelto: PROGRAMA/nucleo para encontrar rutas
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nucleo"))
try:
    import rutas
    SIN_VENTANA = rutas.SIN_VENTANA
except ImportError:
    SIN_VENTANA = 0x08000000 if os.name == "nt" else 0


def _ff(args, timeout=3600):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats"] + args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout, creationflags=SIN_VENTANA)


def medir(ruta):
    """(LUFS integrado, pico verdadero dBTP) del audio."""
    r = _ff(["-i", ruta, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)
    return (float(i[-1]) if i else None, float(tp[-1]) if tp else None)


def masterizar(ruta, log=print):
    base = "loudnorm=I=%g:TP=%g:LRA=%g" % (OBJETIVO_LUFS, PICO_MAX, RANGO)
    r = _ff(["-i", ruta, "-vn", "-af", base + ":print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        log("AVISO: no se pudo medir el audio de %s" % os.path.basename(ruta))
        return False
    j = json.loads(m.group(0))
    filtro = (base + ":measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:offset=%s:linear=true"
              % (j["input_i"], j["input_tp"], j["input_lra"], j["input_thresh"], j["target_offset"]))
    tmp = ruta + ".master" + os.path.splitext(ruta)[1]
    # limitador de seguridad a -2 dBFS: en modo lineal loudnorm no limita y el AAC puede pasar de -1 dBTP
    comun = ["-af", filtro + ",alimiter=limit=0.79:attack=5:release=60:level=false,aresample=48000",
             "-c:a", "aac", "-b:a", "320k", "-shortest"]
    r = _ff(["-y", "-i", ruta, "-map", "0", "-c", "copy"] + comun + [tmp])
    if r.returncode != 0:                         # sin la pista de timecode si el contenedor no la acepta
        r = _ff(["-y", "-i", ruta, "-map", "0:v", "-map", "0:a", "-c:v", "copy"] + comun + [tmp])
    if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 1000:
        log("AVISO: no se pudo masterizar %s" % os.path.basename(ruta))
        if os.path.exists(tmp):
            os.remove(tmp)
        return False
    os.replace(tmp, ruta)
    i, tp = medir(ruta)
    log("Audio masterizado: %s  (antes %s LUFS / %s dBTP -> ahora %.1f LUFS / %.1f dBTP)" % (
        os.path.basename(ruta), j["input_i"], j["input_tp"], i if i is not None else 0, tp if tp is not None else 0))
    return True


def verificar_imagen(ruta, log=print):
    """Mide el video final (1 cuadro por segundo): saturacion media, % de cuadros muy saturados,
    luz media y % de cuadros con altas luces quemadas. Valores en escala de 8 bits."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", ruta, "-an", "-vf",
                        "fps=1,scale=480:-2,signalstats,metadata=mode=print:file=-", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600,
                       creationflags=SIN_VENTANA)
    def serie(clave):
        return [float(x) for x in re.findall(r"lavfi\.signalstats\.%s=([\d.]+)" % clave, r.stdout)]
    sat, sat_alta, luz, luz_alta = serie("SATAVG"), serie("SATHIGH"), serie("YAVG"), serie("YHIGH")
    if not sat:
        log("AVISO: no se pudo medir la imagen de %s" % os.path.basename(ruta))
        return None
    res = {"saturacion": round(sum(sat) / len(sat), 1),
           "muy_saturados_pct": round(100.0 * sum(1 for x in sat_alta if x > 115) / len(sat_alta), 1),
           "luz": round(sum(luz) / len(luz), 1),
           "quemados_pct": round(100.0 * sum(1 for x in luz_alta if x >= 240) / len(luz_alta), 1)}
    ok_sat = res["saturacion"] <= 60 and res["muy_saturados_pct"] <= 10
    ok_luz = 60 <= res["luz"] <= 150 and res["quemados_pct"] <= 10
    log("Imagen %s: saturacion media %.0f, muy saturados %.0f%% (%s) | luz media %.0f, quemados %.0f%% (%s)" % (
        os.path.basename(ruta), res["saturacion"], res["muy_saturados_pct"], "ok" if ok_sat else "ALTA",
        res["luz"], res["quemados_pct"], "ok" if ok_luz else "REVISAR"))
    res["ok"] = ok_sat and ok_luz
    return res


# (1.6.0) Control de cuadros NEGROS y CONGELADOS en el video final (la persona eligio esta mejora). Umbrales para no
# confundir lo que es a proposito: los fundidos entre momentos pasan por negro menos de 1 s y las fotos llevan zoom.
NEGRO_MIN_S = 1.0
CONGELADO_MIN_S = 2.0
SIN_REVISAR_INICIO_S, SIN_REVISAR_FINAL_S = 3.0, 12.0     # el fundido de la plantilla; la foto final con su tarjeta


def revisar_cortes(ruta, log=print):
    """Cuadros negros o congelados en el video final (un hueco en la linea, un clip sin su medio, un render trabado).
    Devuelve [(segundo, "negro"|"congelado", duracion)] fuera del principio y del final; renderizar.py pone un marcador
    morado «REVISAR (IMAGEN)» en cada uno."""
    filtro = ("scale=320:-2,blackdetect=d=%.2f:pic_th=0.98:pix_th=0.06,freezedetect=n=0.003:d=%.2f"
              % (NEGRO_MIN_S, CONGELADO_MIN_S))
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", ruta, "-an", "-vf", filtro, "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600,
                       stdin=subprocess.DEVNULL, creationflags=SIN_VENTANA)
    d = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr)
    total = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3)) if d else 0.0
    malos = [(float(a), "negro", float(b) - float(a))
             for a, b in re.findall(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)", r.stderr)]
    ini = [float(x) for x in re.findall(r"freeze_start:\s*([\d.]+)", r.stderr)]
    fin = [float(x) for x in re.findall(r"freeze_end:\s*([\d.]+)", r.stderr)]
    negros = list(malos)
    for k, a in enumerate(ini):
        b = fin[k] if k < len(fin) else total
        if not any(n0 - 0.2 <= a and a + (b - a) <= n0 + dn + 0.2 for n0, _, dn in negros):   # el negro ya esta
            malos.append((a, "congelado", b - a))
    malos = sorted(m for m in malos if m[0] >= SIN_REVISAR_INICIO_S
                   and (not total or m[0] + m[2] <= total - SIN_REVISAR_FINAL_S))
    if malos:
        log("Imagen %s: %s. Quedan marcadores morados «REVISAR (IMAGEN)» en la línea." % (
            os.path.basename(ruta), ", ".join("%s %.1f s en %d:%02d" % (t, dur, int(s) // 60, int(s) % 60)
                                              for s, t, dur in malos[:6])))
    else:
        log("Imagen %s: sin cuadros negros ni congelados." % os.path.basename(ruta))
    return malos


def masterizar_carpeta(carpeta, log=print):
    hechos = 0
    for f in sorted(os.listdir(carpeta)):
        if f.lower().endswith((".mov", ".mp4")) and ".master." not in f:
            hechos += masterizar(os.path.join(carpeta, f), log)
    return hechos


if __name__ == "__main__":
    masterizar_carpeta(sys.argv[1])
