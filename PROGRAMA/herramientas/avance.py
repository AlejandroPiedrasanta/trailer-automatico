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


def ruta_registro():
    """(18-nov) El registro MAS RECIENTE: el del codigo (PROGRAMA/datos o TRAILER_DATOS) o el del programa instalado
    (%LOCALAPPDATA%/TrailerAutomatico, Mac: ~/Library/Application Support/TrailerAutomatico). Antes solo leia el del
    codigo y daba como actual una corrida de hace 13 horas mientras el instalado armaba."""
    casa = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "TrailerAutomatico")
    if sys.platform == "darwin":
        casa = os.path.expanduser("~/Library/Application Support/TrailerAutomatico")
    rutas_ = [os.path.join(d, "registro", "registro.log") for d in (rutas.DATOS, casa)]
    hay = [r for r in rutas_ if os.path.exists(r)]
    return max(hay, key=os.path.getmtime) if hay else rutas_[0]


def corrida():
    """[(fecha, nivel, texto)] de la ultima corrida."""
    ruta = ruta_registro()
    out = []
    with open(ruta, encoding="utf-8", errors="replace") as f:
        for l in f:
            m = LINEA.match(l.rstrip("\n"))
            if not m:
                continue
            f = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            # (18-nov) el pase vertical vuelve a decir «== Analizando material ==»: solo es corrida nueva si la
            # anterior ya acabo (Terminado / No se pudo terminar) o tras 2 min sin lineas
            if INICIO in m.group(3) and (not out or (f - out[-1][0]).total_seconds() > 120 or
                                         out[-1][2].startswith(("== Terminado", "No se pudo terminar"))
                                         or any(t.startswith(("== Terminado", "No se pudo terminar"))
                                                for _, _, t in out[-8:])):
                out = []
            elif m.group(3).startswith("=== Trailer automatico"):    # el programa se abrio de nuevo
                out = []
                continue
            out.append((f, m.group(2), m.group(3)))
    return out


def ultimo_error():
    """Las lineas del ultimo «Error no atrapado» (con su traza), recortadas."""
    with open(ruta_registro(), encoding="utf-8", errors="replace") as f:
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
    if re.match(r"^\d+ s\s+\S+ (Rendering|Ready|Complete)", texto.strip()):    # las lineas de la cola de render
        return "Render"
    return None


def main():
    if "error" in sys.argv[1:]:
        print("\n".join(ultimo_error()) or "Sin errores.")
        return
    ls = corrida()
    if not ls:
        print("Sin corridas en el registro.")
        return
    etapas = []
    for f, _, t in ls:                                       # sin repetir la misma etapa seguida (Render, linea a linea)
        n = etapa_de(t)
        if n and (not etapas or etapas[-1][1] != n):
            etapas.append((f, n))
    if "tiempos" in sys.argv[1:]:
        fin = ls[-1][0]
        for (f, n), sig in zip(etapas, etapas[1:] + [(fin, None)]):
            print("%6.1f min  %s" % ((sig[0] - f).total_seconds() / 60.0, n))
        print("%6.1f min  TOTAL" % ((fin - ls[0][0]).total_seconds() / 60.0))
        return
    ahora = datetime.datetime.now()
    quieto = (ahora - ls[-1][0]).total_seconds() / 60.0
    textos = [t for _, _, t in ls]
    if any(t.startswith("No se pudo terminar") for t in textos):
        estado = "FALLO"
    elif any(t.startswith("== Terminado") for t in textos):     # («Listo en N s.» llega ANTES del render)
        estado = "TERMINADO"
    elif any(re.match(r"^\d+ s\s+\S+ (Rendering|Ready|Complete)", t) for t in textos):
        estado = "renderizando" + (" (sin lineas nuevas hace %.0f min: ¿colgado?)" % quieto if quieto > 10 else "")
    else:
        estado = "en curso" + (" (sin lineas nuevas hace %.0f min: ¿colgado?)" % quieto if quieto > 10 else "")
    print("Estado: %s · %s" % (estado, ruta_registro()))
    print("Etapa: %s (empezo hace %.0f min; la corrida, hace %.0f)" % (
        etapas[-1][1] if etapas else "?", (ahora - etapas[-1][0]).total_seconds() / 60.0 if etapas else 0,
        (ahora - ls[0][0]).total_seconds() / 60.0))
    for f, _, t in ls[-3:]:                                 # las 3 ultimas, no solo una
        print("  %s  %s" % (f.strftime("%H:%M:%S"), t[:170]))
    errores = [t for _, n, t in ls if n == "ERROR"]
    avisos = [t for _, n, t in ls if n != "ERROR" and re.match(r"^\s*(AVISO|Aviso)\b", t)]
    print("Errores: %d | Avisos: %d" % (len(errores), len(avisos)))
    for t in errores[-3:]:                                  # cada error con su ultima linea de traza (archivo:linea)
        print("  ERROR " + t[:170])
    if errores:
        traza = [l for l in ultimo_error() if l.strip().startswith("File ")]
        if traza:
            print("        en " + traza[-1].strip()[:170])
    for t in sorted(set(avisos))[:6]:
        print("  - " + t[:150])


if __name__ == "__main__":
    main()
