# -*- coding: utf-8 -*-
"""
renderizar.py - Renderiza las timelines de un evento que estan en la cola de DaVinci Resolve y espera a que
terminen, mostrando el avance.  Uso:  python renderizar.py ["XV 2026-11-07"]
(sin argumento renderiza el ultimo evento armado).
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nucleo"))   # PROGRAMA/nucleo: rutas pone las demas carpetas
import motor  # noqa: E402


def renderizar(log=print, evento=None, progreso=None, solo=None):
    """Renderiza los trabajos en cola del evento. progreso(pct, texto) es opcional. Devuelve [(timeline, ok, ruta)].
    solo: ["3min", "VERTICAL 1min", ...] = solo esas versiones, por su etiqueta (lo que va tras « - » en el nombre de
    la linea); las demas que sigan en la cola de un armado anterior no se tocan."""
    evento = evento or motor.leer_estado().get("evento")
    with motor.CANDADO:
        r = motor.conectar_resolve(log)
        p = r.GetProjectManager().GetCurrentProject()
        jobs = [j for j in p.GetRenderJobList() or [] if evento and j.get("TimelineName", "").startswith(evento + " - ")]
        if solo:
            jobs = [j for j in jobs if motor.rutas.etiqueta_de(j["TimelineName"]) in solo]
        if not jobs:
            log("No hay trabajos de render para %s en la cola." % evento)
            return []
        tpl = [p.GetTimelineByIndex(i) for i in range(1, p.GetTimelineCount() + 1)
               if p.GetTimelineByIndex(i).GetName().startswith("TRAILER XV")]
        if tpl:                                   # el visor queda en la plantilla, no en el evento
            p.SetCurrentTimeline(tpl[0])
        r.OpenPage("deliver")
        ids = [j["JobId"] for j in jobs]
        log("Renderizando %d timelines: %s" % (len(ids), ", ".join(j["TimelineName"] for j in jobs)))
        t0 = time.time()
        if not p.StartRendering(ids, False):
            log("ERROR: Resolve no pudo iniciar el render.")
            return []
        ultimo = ""
        while p.IsRenderingInProgress():
            if motor.rutas.PARAR.is_set():       # (1.6.0) «Cancelar»: se detiene el render en DaVinci
                p.StopRendering()
                log("Render detenido: lo pidió la persona.")
                raise motor.rutas.Detenido()
            estado, total = [], 0.0
            for j in jobs:
                s = p.GetRenderJobStatus(j["JobId"]) or {}
                pct = float(s.get("CompletionPercentage", 0) or 0)
                total += pct if s.get("JobStatus") != "Complete" else 100.0
                estado.append("%s %s %d%%" % (motor.rutas.etiqueta_de(j["TimelineName"]), s.get("JobStatus", "?"), pct))
            linea = " | ".join(estado)
            if linea != ultimo:
                log("%5.0f s  %s" % (time.time() - t0, linea))
                ultimo = linea
            if progreso:
                progreso(int(total / len(jobs)), "Renderizando")
            time.sleep(15)
        log("Fin del render en %.0f s" % (time.time() - t0))
        res = []
        for j in jobs:
            s = p.GetRenderJobStatus(j["JobId"]) or {}
            ruta = os.path.join(j.get("TargetDir", ""), j.get("OutputFilename", ""))
            tam = os.path.getsize(ruta) / 1e6 if os.path.exists(ruta) else 0
            ok = s.get("JobStatus") == "Complete" and tam > 0
            log("%s: %s  %s (%.0f MB)" % (j["TimelineName"], s.get("JobStatus"), ruta, tam))
            res.append((j["TimelineName"], ok, ruta))
        # DaVinci queda en Edicion con la linea del evento abierta: lista para retocar lo que no guste
        abierta = motor.dejar_editable(r, p, evento, [motor.rutas.etiqueta_de(j["TimelineName"]) for j in jobs])
        if abierta:
            log("En DaVinci queda abierta y editable: %s" % abierta)
    # audio de entrega: -14 LUFS y picos bajo -1 dBTP en todas las versiones (no necesita Resolve)
    import masterizar
    revisar, revisar_audio = {}, {}
    for k, (nombre, ok, ruta) in enumerate(res, 1):
        if ok:
            if progreso:
                progreso(100, "Masterizando audio %d de %d" % (k, len(res)))
            masterizar.masterizar(ruta, log)
            masterizar.verificar_imagen(ruta, log)       # mide saturacion y luz del video final
            try:                                         # (1.5.9) el oido: clics sueltos, huecos y saturacion
                import oido
                if progreso:
                    progreso(100, "Escuchando el audio %d de %d" % (k, len(res)))
                seg = oido.revisar_audio(ruta, log)
                if seg:
                    revisar_audio[nombre] = seg
            except Exception as ex:
                log("Aviso: no se pudo revisar el audio de %s (%s)" % (os.path.basename(ruta), ex))
            try:                                         # (1.5.7) la IA local mira el video final
                import revision_ia
                if progreso:
                    progreso(100, "Revisando con IA %d de %d" % (k, len(res)))
                malos = revision_ia.revisar(ruta, log)
                if malos:
                    revisar[nombre] = malos
            except Exception as ex:
                log("Aviso: no se pudo revisar con IA %s (%s)" % (os.path.basename(ruta), ex))
    if revisar or revisar_audio:                         # marcadores en la linea de DaVinci, para corregir a mano
        try:
            import revision_ia
            with motor.CANDADO:
                p = motor.conectar_resolve(log).GetProjectManager().GetCurrentProject()
                desde = {j["TimelineName"]: int(j.get("MarkIn") or 0) for j in jobs}
                for i in range(1, p.GetTimelineCount() + 1):
                    tl = p.GetTimelineByIndex(i)
                    inicio = desde.get(tl.GetName()) or tl.GetStartFrame()
                    if tl.GetName() in revisar:
                        n = revision_ia.marcar(tl, revisar[tl.GetName()], inicio - tl.GetStartFrame())
                        log("%s: %d marcadores rojos «REVISAR (IA)» en la linea." % (tl.GetName(), n))
                    if tl.GetName() in revisar_audio:
                        n = revision_ia.marcar(tl, revisar_audio[tl.GetName()], inicio - tl.GetStartFrame(),
                                               revision_ia.COLOR_AUDIO, revision_ia.MARCA_AUDIO, revision_ia.NOTA_AUDIO)
                        log("%s: %d marcadores amarillos «REVISAR (AUDIO)» en la linea." % (tl.GetName(), n))
        except Exception as ex:
            log("Aviso: no se pudieron poner los marcadores de revision (%s)" % ex)
    return res


if __name__ == "__main__":
    def _log(m):
        print(time.strftime("%H:%M:%S  ") + str(m), flush=True)
    res = renderizar(_log, sys.argv[1] if len(sys.argv) > 1 else None)
    sys.exit(0 if res and all(ok for _, ok, _ in res) else 1)
