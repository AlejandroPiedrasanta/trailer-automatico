# -*- coding: utf-8 -*-
"""
profundidad.py - (16-nov) «Enfoque de cine» en las tomas protagonistas con la IA de profundidad de DaVinci Studio.

La persona (2026-11-16): «aprovecha todas las funciones que tiene DaVinci Resolve Studio»; «puedes usar Magic Mask v2
para algunas tomas». La Magic Mask necesita puntos puestos A MANO en el visor (la API no deja ponerlos: ver
FusionToolReference, «Points can only be placed… in the viewer»), asi que no se puede hacer sola. El Depth Map (la
misma IA, Neural Engine) no necesita puntos: sabe que esta cerca y que esta lejos. Con eso, en las tomas que mas
importan (camara lenta y el plano final) el fondo se desenfoca un poco y baja apenas de luz, como con un lente de
cine: los novios o la festejada se separan del fondo. Es suave a proposito (nada de recortes falsos).

En el clip: MediaIn -> [ESTABILIZADOR] -> PROFUNDIDAD (Blur limitado por el Depth Map invertido = el fondo) ->
FONDO (Color Corrector con un poco menos de luz, misma mascara) -> MediaOut. Todo se ve y se retoca en Fusion.
"""
DESENFOQUE = 5.0              # Blur Size de Fusion en el fondo (suave: separa sin que se note el efecto)
LUZ_FONDO = 0.93              # el fondo baja apenas de luz


def _ultimo(comp, mo):
    """La herramienta que hoy entra al MediaOut (MediaIn o el ESTABILIZADOR)."""
    try:
        sal = mo.Input.GetConnectedOutput()
        return sal.GetTool() if sal is not None else comp.FindTool("MediaIn1")
    except Exception:
        return comp.FindTool("MediaIn1")


def aplicar(item, log=None):
    """Pone el enfoque de cine en el clip. True si quedo puesto."""
    try:
        comp = item.GetFusionCompByIndex(1) if item.GetFusionCompCount() else None
        comp = comp or item.AddFusionComp()
    except Exception:
        comp = None
    if comp is None:
        return False
    comp.Lock()
    try:
        mo = comp.FindTool("MediaOut1")
        if mo is None or comp.FindTool("PROFUNDIDAD"):
            return bool(comp.FindTool("PROFUNDIDAD"))
        fuente = _ultimo(comp, mo)
        if fuente is None:
            return False
        mapa = comp.AddTool("DepthMap", -32768, -32768)
        mapa.SetAttrs({"TOOLS_Name": "MAPA_PROFUNDIDAD"})
        mapa.ConnectInput("Input", fuente)
        mapa.SetInput("Mode", "Better")
        mapa.SetInput("DepthMapPreview", 0)      # usar el alfa, no la vista previa
        mapa.SetInput("Invert", 1)               # blanco = lo lejano (el fondo)
        mapa.SetInput("Postprocessing", 1)
        mapa.SetInput("Blur", 0.15)              # borde suave entre la persona y el fondo
        blur = comp.AddTool("Blur", -32768, -32768)
        blur.SetAttrs({"TOOLS_Name": "PROFUNDIDAD"})
        blur.ConnectInput("Input", fuente)
        blur.SetInput("Filter", "Gaussian")
        blur.SetInput("XBlurSize", DESENFOQUE)
        blur.ConnectInput("EffectMask", mapa)
        cc = comp.AddTool("ColorCorrector", -32768, -32768)
        cc.SetAttrs({"TOOLS_Name": "FONDO"})
        cc.ConnectInput("Input", blur)
        cc.SetInput("MasterRGBGain", LUZ_FONDO)
        cc.ConnectInput("EffectMask", mapa)
        mo.ConnectInput("Input", cc)
        return True
    except Exception as ex:
        if log:
            log("Aviso: no se pudo poner el enfoque de cine (%s)" % ex)
        return False
    finally:
        comp.Unlock()
