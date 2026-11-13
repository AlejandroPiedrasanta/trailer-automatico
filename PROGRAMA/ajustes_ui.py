# -*- coding: utf-8 -*-
"""ajustes_ui.py - Preferencias que lee la escena de Inicio: estilo del astrolabio y sonidos (desde estado_programa.json)."""


def leer_prefs():
    try:
        import motor
        e = motor.leer_estado()
    except Exception:
        e = {}
    return {"go_estilo": e.get("go_estilo", "astrolabio"), "go_sonidos": False, "go_modo": e.get("go_modo", "completo")}
