# -*- coding: utf-8 -*-
"""
indexar.py - Deja el material del evento listo para buscar y editar a mano en DaVinci Resolve.

Para cada foto y video del media pool (carpetas por momento que crea build_trailers.py):
  - Metadatos: Escena = momento, Toma = fuente (CAMARA / CELULAR / DRON), palabras clave y calidad.
  - Marcadores verdes "MEJOR TOMA" en los mejores tramos de cada video (segun la calidad medida).
  - Bandera verde en los videos con mejor calidad media.
  - IntelliSearch (opcional): analisis por contenido con reconocimiento de rostros, para buscar en el
    media pool por "pastel", "iglesia", una persona, etc. Es lento: se hace de un video a la vez.

Uso:  python indexar.py [--sin-intellisearch]
No modifica las timelines. Conviene correrlo cuando no haya un render en curso.
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motor  # noqa: E402

PASO = 0.5                # segundos por muestra de calidad
VENTANA = 2.0             # largo de cada "mejor toma" marcada
SEPARACION = 6.0          # minimo entre dos marcadores del mismo video
MARCADORES_POR_VIDEO = 3
BANDERA_MIN = 0.62        # calidad media para bandera verde
NOMBRE_MARCADOR = "MEJOR TOMA"


def fuente(i):
    if i["tipo"] == "dron" or i.get("origen_hora") == "dji":
        return "DRON"
    return "CELULAR" if i.get("origen_hora") == "iphone" else "CAMARA"


def mejores(cal, n=MARCADORES_POR_VIDEO):
    """[(inicio_s, puntaje)] de las mejores ventanas, separadas entre si."""
    w = max(1, int(VENTANA / PASO))
    if len(cal) < w:
        return []
    pref = [0.0]
    for x in cal:
        pref.append(pref[-1] + x)
    cand = sorted(((pref[i + w] - pref[i]) / w, i * PASO) for i in range(len(cal) - w + 1))[::-1]
    elegidos = []
    for sc, t in cand:
        if sc < 0.35:
            break
        if all(abs(t - e) >= SEPARACION for e, _ in elegidos):
            elegidos.append((t, sc))
        if len(elegidos) >= n:
            break
    return sorted(elegidos)


def indexar(log=print, intellisearch=True):
    with motor.CANDADO:
        with open(os.path.join(motor.rutas.ANALISIS, "material.json"), encoding="utf-8") as f:
            items = {os.path.normcase(i["ruta"]): i for i in json.load(f).get("items", [])}
        r = motor.conectar_resolve(log)
        p = r.GetProjectManager().GetCurrentProject()
        if p.IsRenderingInProgress():
            log("AVISO: hay un render en curso; vuelve a indexar cuando termine.")
            return None
        mp = p.GetMediaPool()
        clips = []

        def recorrer(carpeta):
            for c in carpeta.GetClipList() or []:
                ruta = os.path.normcase(c.GetClipProperty("File Path") or "")
                if ruta in items:
                    clips.append((c, items[ruta]))
            for s in carpeta.GetSubFolderList() or []:
                recorrer(s)
        for top in mp.GetRootFolder().GetSubFolderList() or []:
            if top.GetName().split(" ", 1)[-1] in ("FOTOS", "VIDEO"):      # "04 FOTOS" o "FOTOS"
                recorrer(top)
        log("Indexando %d archivos del media pool..." % len(clips))
        n_meta = n_marc = n_band = 0
        for c, i in clips:
            mom = "DESCARTADO" if i.get("descartar") else i.get("momento", "")
            meta = {"Scene": mom.capitalize(), "Keywords": ", ".join(x for x in ("XV", mom.capitalize(),
                    "Foto" if i["tipo"] == "foto" else fuente(i).capitalize()) if x)}
            if i["tipo"] != "foto":
                cal = i.get("calidad") or []
                media = sum(cal) / len(cal) if cal else 0.0
                meta.update({"Shot": fuente(i).capitalize(), "Description": "Calidad media %.2f" % media})
                fps = float(i.get("fps") or 24)
                existentes = {m.get("name") for m in (c.GetMarkers() or {}).values()}
                lista = mejores(cal)
                if lista and NOMBRE_MARCADOR + " 1" not in existentes:
                    for k, (t, sc) in enumerate(lista, 1):
                        if c.AddMarker(int(t * fps), "Green", "%s %d" % (NOMBRE_MARCADOR, k),
                                       "Calidad %.2f (nitidez, luz y estabilidad)" % sc, int(VENTANA * fps)):
                            n_marc += 1
                    meta["Comments"] = "Mejores tomas en: " + ", ".join("%.0f s" % t for t, _ in lista)
                if media >= BANDERA_MIN and "Green" not in (c.GetFlagList() or []):
                    if c.AddFlag("Green"):
                        n_band += 1
            if c.SetMetadata(meta):
                n_meta += 1
        log("Metadatos en %d archivos, %d marcadores MEJOR TOMA, %d banderas verdes." % (n_meta, n_marc, n_band))
        r.GetProjectManager().SaveProject()
        if intellisearch:
            videos = [(c, i) for c, i in clips if i["tipo"] != "foto" and not i.get("descartar")]
            log("IntelliSearch: analizando %d videos con reconocimiento de rostros (lento)..." % len(videos))
            hechos = 0
            for k, (c, i) in enumerate(videos, 1):
                t0 = time.time()
                try:
                    ok = c.AnalyzeForIntellisearch(True, False)
                except Exception as ex:
                    ok = False
                    log("  error en %s: %s" % (i["nombre"], ex))
                hechos += bool(ok)
                log("  %d/%d %s %s (%.0f s)" % (k, len(videos), i["nombre"], "ok" if ok else "fallo", time.time() - t0))
            r.GetProjectManager().SaveProject()
            log("IntelliSearch listo en %d videos. Busca en el media pool por contenido o por persona." % hechos)
        return {"metadatos": n_meta, "marcadores": n_marc, "banderas": n_band}


if __name__ == "__main__":
    indexar(intellisearch="--sin-intellisearch" not in sys.argv)
