# -*- coding: utf-8 -*-
"""i18n.py - El programa esta en espanol: tr() solo rellena los {campos}."""


def tr(texto, **kw):
    return texto.format(**kw) if kw else texto
