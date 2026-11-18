"""Como va el armado, en pocas lineas (para no leer el registro entero).

    python PROGRAMA/herramientas/avance.py            etapa, ultima linea, hace cuanto, avisos y errores
    python PROGRAMA/herramientas/avance.py tiempos    cuanto tardo cada etapa de la ultima corrida
    python PROGRAMA/herramientas/avance.py error      el ultimo error con su traza

Lee datos/registro/registro.log desde el ultimo «== Analizando material ==»."""
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nucleo"))
import rutas  # noqa: E402

LINEA = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s+(\w+)\s+(.*)$")
INICIO = "== Analizando material =="
# etapas que no llevan «== ==» en el registro: (nombre, como empieza la linea)
MARCAS = (("IA: primera vista", "La IA local mira"), ("IA: cuadro por cuadro", "La IA local revisa cada toma"),
          ("Oido", "El oído (earshot) escucha"), ("Media pool", "Media pool:"),
          ("Personas (DaVinci)", "Reconociendo a las personas"))


def corrida():
    """[(fecha, nivel, texto)] de la ultima corrida."""
    ruta = os.path.join(rutas.DATOS, "registro", "registro.log")
    out = []
    with open(ruta, encoding="utf-8", errors="replace") as f:
        for l in f:
            m = LINEA.match(l.rstrip("\n"))
            if not m:
                continue
            if INICIO in m.group(3):
                out = []
            out.append((datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"), m.group(2), m.group(3)))
    return out


def ultimo_error():
    """Las lineas del ultimo «Error no atrapado» (con su traza), recortadas."""
    ruta = os.path.join(rutas.DATOS, "registro", "registro.log")
    with open(ruta, encoding="utf-8", errors="replace") as f:
        ls = f.read().splitlines()
    for n in range(len(ls) - 1, -1, -1):
        m = LINEA.match(ls[n])
        if m and m.group(2) == "ERROR":
            return [l[:220] for l in ls[n:n + 40]]
    return []


def etapa_de(texto):
    m = re.match(r"^== (.+?) ==$", texto.strip())
    if m:
        return m.group(1)
    for nombre, empieza in MARCAS:
        if texto.strip().startswith(empieza):
            return nombre
    return None


def main():
    if "error" in sys.argv[1:]:
        print("\n".join(ultimo_error()) or "Sin errores.")
        return
    ls = corrida()
    if not ls:
        print("Sin corridas en el registro.")
        return
    etapas = [(f, etapa_de(t)) for f, _, t in ls if etapa_de(t)]
    if "tiempos" in sys.argv[1:]:
        fin = ls[-1][0]
        for (f, n), sig in zip(etapas, etapas[1:] + [(fin, None)]):
            print("%6.1f min  %s" % ((sig[0] - f).total_seconds() / 60.0, n))
        print("%6.1f min  TOTAL" % ((fin - ls[0][0]).total_seconds() / 60.0))
        return
    ahora = datetime.datetime.now()
    print("Etapa: %s (empezo hace %.0f min; la corrida, hace %.0f)" % (
        etapas[-1][1], (ahora - etapas[-1][0]).total_seconds() / 60.0, (ahora - ls[0][0]).total_seconds() / 60.0))
    print("Ultimo (hace %.0f min): %s" % ((ahora - ls[-1][0]).total_seconds() / 60.0, ls[-1][2][:160]))
    errores = [t for _, n, t in ls if n == "ERROR"]
    avisos = [t for _, n, t in ls if n != "ERROR" and re.match(r"^\s*(AVISO|Aviso)\b", t)]
    print("Errores: %d%s | Avisos: %d" % (len(errores), " -> " + errores[-1][:160] if errores else "", len(avisos)))
    for t in sorted(set(avisos))[:6]:
        print("  - " + t[:150])


if __name__ == "__main__":
    main()
