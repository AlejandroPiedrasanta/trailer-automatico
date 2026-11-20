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


def _davinci_abierto():
    import subprocess
    try:
        if os.name == "nt":
            r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Resolve.exe", "/NH"], capture_output=True, text=True,
                               timeout=20, creationflags=motor.rutas.SIN_VENTANA)
            return "Resolve.exe" in r.stdout
        return subprocess.run(["pgrep", "-x", "Resolve"], capture_output=True, timeout=20).returncode == 0
    except Exception:
        return False


def _reiniciar_davinci(resolve, project, log=print, espera_s=120):
    """Guarda el proyecto (nunca «Untitled Project»: saca un cuadro y la API se cuelga), cierra DaVinci y espera a que
    salga. Abrirlo de nuevo es de motor.conectar_resolve."""
    try:
        if project is not None and project.GetName() != "Untitled Project":
            resolve.GetProjectManager().SaveProject()
    except Exception:
        pass
    try:
        resolve.Quit()
    except Exception:
        pass
    t0 = time.time()
    while _davinci_abierto() and time.time() - t0 < espera_s:
        time.sleep(3)
    if _davinci_abierto():
        raise RuntimeError("DaVinci no se cerró")
    time.sleep(3)


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
        # (19-nov, visto) dos trabajos de la misma linea (uno viejo, con su carpeta ya borrada por la persona) y DaVinci
        # no empezaba ninguno: queda solo el ultimo de cada linea y su carpeta se crea si falta
        ultimo = {}
        for j in jobs:
            ultimo[j.get("TimelineName")] = j
        for j in jobs:
            if ultimo.get(j.get("TimelineName")) is not j:
                try:
                    p.DeleteRenderJob(j["JobId"])
                except Exception:
                    pass
        jobs = list(ultimo.values())
        for j in jobs:
            try:
                if j.get("TargetDir"):
                    os.makedirs(j["TargetDir"], exist_ok=True)
            except OSError:
                pass
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
        # (18-nov, la persona: «necesito procesos más rápidos o en segundo plano») Cada video se TERMINA (audio a
        # -14 LUFS, medida de la imagen, cuadros negros, oido) en cuanto sale del render, en un hilo, mientras DaVinci
        # renderiza el siguiente: el de 1 min queda listo en su carpeta sin esperar a los largos y el final ya no suma
        # el masterizado de todos. La revision con la IA de vista va despues del render (usa la tarjeta).
        import masterizar
        from concurrent.futures import ThreadPoolExecutor
        revisar, revisar_audio, revisar_imagen = {}, {}, {}
        post, en_post = ThreadPoolExecutor(1), {}

        def terminar(nombre, ruta):
            masterizar.masterizar(ruta, log)
            masterizar.verificar_imagen(ruta, log)       # mide saturacion y luz del video final
            try:                                         # (1.6.0) cuadros negros o congelados
                cortes = masterizar.revisar_cortes(ruta, log)
                if cortes:
                    revisar_imagen[nombre] = [s for s, _, _ in cortes]
            except Exception as ex:
                log("Aviso: no se pudo revisar la imagen de %s (%s)" % (os.path.basename(ruta), ex))
            try:                                         # (1.5.9) el oido: clics sueltos, huecos y saturacion
                import oido
                seg = oido.revisar_audio(ruta, log)
                if seg:
                    revisar_audio[nombre] = seg
            except Exception as ex:
                log("Aviso: no se pudo revisar el audio de %s (%s)" % (os.path.basename(ruta), ex))
            log("LISTO: %s ya está terminado en su carpeta." % os.path.basename(ruta))

        def recoger():
            """Manda a terminar los videos que ya salieron del render."""
            for j in jobs:
                if j["TimelineName"] in en_post:
                    continue
                if (p.GetRenderJobStatus(j["JobId"]) or {}).get("JobStatus") != "Complete":
                    continue
                ruta = os.path.join(j.get("TargetDir", ""), j.get("OutputFilename", ""))
                if os.path.exists(ruta) and os.path.getsize(ruta) > 0:
                    en_post[j["TimelineName"]] = post.submit(terminar, j["TimelineName"], ruta)

        def correr(cuales):
            """Renderiza esos trabajos y espera. False si DaVinci no pudo ni empezar."""
            if not p.StartRendering(cuales, False):
                return False
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
                recoger()
                time.sleep(5)
            recoger()
            return True

        def fallados():
            return [j for j in jobs if (p.GetRenderJobStatus(j["JobId"]) or {}).get("JobStatus") != "Complete"]
        if not correr(ids):
            log("ERROR: Resolve no pudo iniciar el render.")
            return []
        # (18-nov, la persona: «hay un error, no me está dando los videos renderizados») Los 4 trabajos dieron «Failed»
        # en 16 s y el programa siguio como si nada, sin videos. En el registro de DaVinci: «NVENC ... Internal Error,
        # Nvidia codec cannot be initialized». MEDIDO: dentro de una sesion de DaVinci, despues de renderizar UNA vez
        # con un codificador del procesador (H265), el de la tarjeta (H265_NVIDIA / H264_NVIDIA) ya no abre mas, con
        # ningun ajuste; cerrando y abriendo DaVinci vuelve a funcionar. Por eso: NUNCA se cambia de codificador desde
        # el programa; si el render falla se reintenta y, si sigue, se reinicia DaVinci y se renderiza otra vez.
        mal = fallados()
        if mal:
            log("El render falló en %d de %d (%s): reintento en unos segundos…" % (
                len(mal), len(jobs), ", ".join(motor.rutas.etiqueta_de(j["TimelineName"]) for j in mal)))
            time.sleep(10)
            correr([j["JobId"] for j in mal])
            mal = fallados()
        if mal:
            log("El codificador de video de DaVinci no responde: cierro y abro DaVinci y renderizo otra vez "
                "(el proyecto queda guardado)…")
            nombres = {j["TimelineName"] for j in mal}
            try:
                _reiniciar_davinci(r, p, log)
                r = motor.conectar_resolve(log)
                p = r.GetProjectManager().GetCurrentProject()
                cola = {j.get("TimelineName"): j for j in p.GetRenderJobList() or []}
                for j in jobs:                           # los trabajos siguen en la cola del proyecto guardado
                    if j["TimelineName"] in cola:
                        j.update(cola[j["TimelineName"]])
                r.OpenPage("deliver")
                correr([j["JobId"] for j in jobs if j["TimelineName"] in nombres])
            except motor.rutas.Detenido:
                raise
            except Exception as ex:
                log("Aviso: no pude reiniciar DaVinci para renderizar (%s). Ciérralo, ábrelo y pulsa «Renderizar lo "
                    "editado»." % ex)
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
    # lo que faltara por terminar (el ultimo video suele estar en eso) y, ya sin render, la IA de vista mira cada uno
    for k, (nombre, ok, ruta) in enumerate(res, 1):
        if not ok:
            continue
        if progreso:
            progreso(100, "Terminando el audio %d de %d" % (k, len(res)))
        try:
            if nombre not in en_post:
                en_post[nombre] = post.submit(terminar, nombre, ruta)
            en_post[nombre].result()
        except Exception as ex:
            log("Aviso: no se pudo terminar %s (%s)" % (os.path.basename(ruta), ex))
    post.shutdown(wait=True)
    hechos = [(nombre, ruta) for nombre, ok, ruta in res if ok]
    if hechos:
        # (1.5.7) la IA local mira los videos finales. (18-nov, medido en la boda: 4 min 13 s, y despues 4 min 56 s de
        # plantillas .drp, una detras de otra) Ahora va EN SEGUNDO PLANO: la IA usa la GPU y las plantillas DaVinci y
        # el disco; sus marcadores rojos los pone poner_revision_ia() cuando termina (motor lo llama al final).
        # (19-nov) lo que la IA ya vio bien al analizar no se vuelve a preguntar (se lee de la linea aqui, con DaVinci)
        vistos = {}
        try:
            import revision_ia
            ini = {j["TimelineName"]: int(j.get("MarkIn") or 0) for j in jobs}
            por_nombre = dict(hechos)
            with motor.CANDADO:
                pv = motor.conectar_resolve(log, quedarse=True).GetProjectManager().GetCurrentProject()
                for i in range(1, pv.GetTimelineCount() + 1):
                    tl = pv.GetTimelineByIndex(i)
                    if tl.GetName() in por_nombre:
                        vistos[por_nombre[tl.GetName()]] = revision_ia.tramos_vistos(tl, ini.get(tl.GetName()) or None)
        except Exception as ex:
            log("Aviso: la revision con IA mirara todo (%s)" % ex)

        def revisar_ia(lista=list(hechos)):
            import revision_ia
            malos = revision_ia.revisar_varios([r for _, r in lista], log, vistos)
            return {nombre: malos[ruta] for nombre, ruta in lista if malos.get(ruta)}
        from concurrent.futures import ThreadPoolExecutor as _TP
        _ia = _TP(1, thread_name_prefix="revision_ia")
        _PENDIENTE["revision"] = (_ia.submit(revisar_ia), {j["TimelineName"]: int(j.get("MarkIn") or 0) for j in jobs})
        _ia.shutdown(wait=False)
        log("Revisando con IA los %d videos en segundo plano (mientras se hacen los proxies y las plantillas)." % len(hechos))
    if revisar or revisar_audio or revisar_imagen:       # marcadores en la linea de DaVinci, para corregir a mano
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
                    if tl.GetName() in revisar_imagen:
                        n = revision_ia.marcar(tl, revisar_imagen[tl.GetName()], inicio - tl.GetStartFrame(),
                                               revision_ia.COLOR_IMAGEN, revision_ia.MARCA_IMAGEN, revision_ia.NOTA_IMAGEN)
                        log("%s: %d marcadores morados «REVISAR (IMAGEN)» en la linea." % (tl.GetName(), n))
        except Exception as ex:
            log("Aviso: no se pudieron poner los marcadores de revision (%s)" % ex)
    hechos = {nombre: ruta for nombre, ok, ruta in res if ok}
    if hechos:                                           # (1.6.0) capitulos para YouTube junto a cada video
        try:
            import capitulos
            with motor.CANDADO:
                p = motor.conectar_resolve(log).GetProjectManager().GetCurrentProject()
                desde = {j["TimelineName"]: int(j.get("MarkIn") or 0) for j in jobs}
                for i in range(1, p.GetTimelineCount() + 1):
                    tl = p.GetTimelineByIndex(i)
                    if tl.GetName() in hechos:
                        capitulos.escribir(tl, desde.get(tl.GetName()) or tl.GetStartFrame(), hechos[tl.GetName()], log)
        except Exception as ex:
            log("Aviso: no se pudieron escribir los capítulos para YouTube (%s)" % ex)
    return res


_PENDIENTE = {}


def poner_revision_ia(log=print, progreso=None):
    """Espera la revision con IA que dejo en marcha renderizar() y pone sus marcadores rojos «REVISAR (IA)» en las
    lineas. Devuelve cuantas lineas marco (0 si no habia nada pendiente)."""
    pend = _PENDIENTE.pop("revision", None)
    if not pend:
        return 0
    fut, desde = pend
    if progreso and not fut.done():
        progreso(99, "Terminando la revisión con IA")
    try:
        revisar = fut.result()
    except Exception as ex:
        log("Aviso: no se pudo revisar con IA (%s)" % ex)
        return 0
    if not revisar:
        return 0
    try:
        import revision_ia
        with motor.CANDADO:
            # quedarse: tras «Renderizar lo editado» se marca la linea del proyecto del video, sin cambiar de proyecto
            p = motor.conectar_resolve(log, quedarse=True).GetProjectManager().GetCurrentProject()
            pendientes = {}
            for i in range(1, p.GetTimelineCount() + 1):
                tl = p.GetTimelineByIndex(i)
                if tl.GetName() in revisar:
                    inicio = desde.get(tl.GetName()) or tl.GetStartFrame()
                    n = revision_ia.marcar(tl, revisar[tl.GetName()], inicio - tl.GetStartFrame())
                    log("%s: %d marcadores rojos «REVISAR (IA)» en la linea." % (tl.GetName(), n))
                    pendientes[tl.GetName()] = [inicio - tl.GetStartFrame(), list(revisar[tl.GetName()])]
            if p.GetName() == motor.PROYECTO and pendientes:
                # (19-nov) los proyectos por video ya estaban hechos: cada uno los recibe al abrirse
                # (motor.abrir_proyecto_video)
                est = motor.leer_estado()
                est["marcas_ia"] = dict(est.get("marcas_ia") or {}, **pendientes)
                motor.guardar_estado(est)
    except Exception as ex:
        log("Aviso: no se pudieron poner los marcadores de la revision con IA (%s)" % ex)
    return len(revisar)


if __name__ == "__main__":
    def _log(m):
        print(time.strftime("%H:%M:%S  ") + str(m), flush=True)
    res = renderizar(_log, sys.argv[1] if len(sys.argv) > 1 else None)
    sys.exit(0 if res and all(ok for _, ok, _ in res) else 1)
