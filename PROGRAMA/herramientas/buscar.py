"""BUSCAR en todo lo grabado: el archivo de eventos (datos/archivo/<evento>.json, lo deja el analisis de cada evento).

    python PROGRAMA/herramientas/buscar.py dron iglesia            tomas que tengan TODAS las palabras
    python PROGRAMA/herramientas/buscar.py pastel bonita           «bonita» = belleza 8 o mas
    python PROGRAMA/herramientas/buscar.py vertical fiesta sonrisa
    python PROGRAMA/herramientas/buscar.py                          que eventos hay y cuantas tomas

Busca en el nombre, el momento, lo que vio la IA (escena, etiquetas, momentos clave como sonrisa, pastel, brindis), el
tipo (video, foto, dron) y el evento. Sin acentos ni mayusculas. Las mas bonitas primero."""
import json
import os
import sys
import unicodedata

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nucleo"))
import rutas  # noqa: E402


def _plano(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn")


def eventos():
    d = os.path.join(rutas.DATOS, "archivo")
    out = []
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if f.endswith(".json"):
            try:
                with open(os.path.join(d, f), encoding="utf-8") as h:
                    out.append(json.load(h))
            except Exception:
                pass
    return out


def buscar(palabras):
    palabras = [_plano(p) for p in palabras]
    res = []
    for ev in eventos():
        for t in ev.get("tomas") or []:
            texto = _plano(" ".join([ev.get("evento", ""), t.get("nombre") or "", t.get("momento") or "",
                                     t.get("tipo") or "", t.get("escena") or "", " ".join(t.get("etiquetas") or []),
                                     " ".join(t.get("clave") or []), "vertical" if t.get("vertical") else "horizontal",
                                     "bonita" if (t.get("belleza") or 0) >= 8 else ""]))
            if all(p in texto for p in palabras):
                res.append((ev.get("evento", ""), t))
    return sorted(res, key=lambda r: -(r[1].get("belleza") or 0))


def main():
    a = sys.argv[1:]
    if not a:
        for ev in eventos():
            print("%-30s %4d tomas" % (ev.get("evento", "?"), len(ev.get("tomas") or [])))
        return
    res = buscar(a)
    print("%d tomas" % len(res))
    for ev, t in res[:40]:
        print("%s | %s | %s %s | belleza %s | %s | %s" % (ev, t.get("nombre"), t.get("tipo"), t.get("momento") or "",
                                                         t.get("belleza") or "-", t.get("escena") or "", t.get("ruta")))


if __name__ == "__main__":
    main()
