# -*- coding: utf-8 -*-
"""
mapa_codigo.py - Consultar el codigo POR TEMA sin leer archivos enteros (para ahorrar tokens), como en CineCaptions.

  mapa [palabras]     temas que encajan (compacto); mapa id=<tema> da el detalle: archivos, simbolos con su linea, notas
  donde <nombre>      archivo:lineas, tipo y primera linea del docstring de cada funcion/clase que coincide (sin codigo)
  simbolo <nombre> [desde]   el CODIGO de esa funcion/clase/metodo solamente (Clase.metodo tambien vale)
  modulo <archivo>    que es un archivo: su descripcion y sus funciones/clases con linea
  llamadas <nombre>   quien usa esa funcion/clase (archivo:linea: codigo)
  generar             reescribe el mapa de temas de CLAUDE.md desde docs/mapa.json y avisa de simbolos que ya no existen

Uso:  python PROGRAMA/herramientas/mapa_codigo.py mapa color   |   simbolo cdl_para   |   donde texto   |   llamadas armar_todo
"""
import ast
import json
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent             # PROGRAMA (esto esta en PROGRAMA/herramientas)
BASE = RAIZ.parent
MAPA = RAIZ / "docs" / "mapa.json"
CLAUDE = BASE / "CLAUDE.md"
SALTAR = {"datos", "__pycache__", "recursos", "recursos_protegidos"}
INICIO, FIN = "<!-- MAPA:INICIO (lo escribe PROGRAMA/herramientas/mapa_codigo.py generar) -->", "<!-- MAPA:FIN -->"


def _norm(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn")


def _archivos():
    for p in sorted(RAIZ.rglob("*.py")):
        if not SALTAR.intersection(p.relative_to(RAIZ).parts[:-1]):
            yield p


def indice():
    """[(nombre_completo, tipo, ruta_relativa, ini, fin, doc1)] de todas las funciones, clases y metodos."""
    out = []
    for p in _archivos():
        try:
            arbol = ast.parse(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        rel = p.relative_to(BASE).as_posix()

        def visitar(nodos, prefijo):
            for n in nodos:
                if isinstance(n, ast.Assign) and (prefijo == "" or prefijo.endswith(".")):     # CONSTANTES en mayusculas
                    for t in n.targets:
                        if isinstance(t, ast.Name) and t.id.isupper() and len(t.id) > 2:
                            out.append((prefijo + t.id, "constante", rel, n.lineno, n.end_lineno, ""))
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    doc = (ast.get_docstring(n) or "").strip().splitlines()
                    tipo = "clase" if isinstance(n, ast.ClassDef) else ("metodo" if prefijo else "funcion")
                    out.append((prefijo + n.name, tipo, rel, n.lineno, n.end_lineno, doc[0][:110] if doc else ""))
                    if isinstance(n, ast.ClassDef) or prefijo == "":
                        visitar(n.body, prefijo + n.name + ".")
        visitar(arbol.body, "")
    for p in sorted((RAIZ / "compilar").rglob("*.cs")):          # metodos del instalador C#
        rel = p.relative_to(BASE).as_posix()
        for i, l in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            m = re.match(r"\s*(?:public |static |private |override )+[\w<>\[\],]+ (\w+)\(", l)
            if m:
                out.append((m.group(1), "metodo C#", rel, i, i, ""))
    return out


_INDICE = []


def _buscar(nombre):
    if not _INDICE:                 # una sola vez: «generar» busca 400 simbolos y rehacerlo cada vez tardaba 3 min
        _INDICE.extend(indice())
    idx = _INDICE
    n = _norm(nombre)
    exactos = [s for s in idx if _norm(s[0]) == n or _norm(s[0]).endswith("." + n)]
    return exactos or [s for s in idx if n in _norm(s[0])]


def donde(nombre):
    res = _buscar(nombre)
    if not res:
        return "Nada se llama «%s». Prueba: mapa %s" % (nombre, nombre)
    return "\n".join("%s:%d-%d  %s %s%s" % (r, a, b, t, nom, ("  — " + d) if d else "") for nom, t, r, a, b, d in res[:25])


def simbolo(nombre, desde=0, lineas=160):
    res = _buscar(nombre)
    if not res:
        return donde(nombre)
    nom, t, r, a, b, _ = res[0]
    texto = (BASE / r).read_text(encoding="utf-8").splitlines()
    ini = a - 1 + int(desde)
    fin = min(b, ini + lineas)
    cab = "%s:%d-%d  %s %s" % (r, a, b, t, nom) + ("   (otras coincidencias: %s)" % ", ".join(x[0] for x in res[1:6]) if len(res) > 1 else "")
    cola = "\n… sigue: simbolo %s %d" % (nombre, int(desde) + lineas) if fin < b else ""
    return cab + "\n" + "\n".join("%5d %s" % (i + 1, texto[i]) for i in range(ini, fin)) + cola


def modulo(nombre):
    p = next((x for x in _archivos() if x.stem.lower() == nombre.lower().replace(".py", "")), None)
    if p is None:
        return "No hay modulo «%s»." % nombre
    arbol = ast.parse(p.read_text(encoding="utf-8"))
    doc = (ast.get_docstring(arbol) or "").strip().splitlines()
    rel = p.relative_to(BASE).as_posix()
    filas = ["%s (%d lineas)" % (rel, len(p.read_text(encoding="utf-8").splitlines()))] + ["  " + l for l in doc[:8]]
    for nom, t, r, a, b, d in indice():
        if r == rel:
            filas.append("  %5d %s %s%s" % (a, t[:6], nom, ("  — " + d[:80]) if d else ""))
    return "\n".join(filas)


def llamadas(nombre):
    corto = nombre.split(".")[-1]
    patron = re.compile(r"\b%s\s*\(" % re.escape(corto))
    filas = []
    for p in _archivos():
        for i, l in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if patron.search(l) and not re.match(r"\s*(def|class)\s", l):
                filas.append("%s:%d: %s" % (p.relative_to(BASE).as_posix(), i, l.strip()[:120]))
    return "\n".join(filas[:40]) or "Nadie llama a %s." % nombre


def _temas():
    return json.loads(MAPA.read_text(encoding="utf-8"))


def mapa(*palabras, id=None):
    temas = _temas()
    if id:
        t = next((x for x in temas if x["id"] == id), None)
        if t is None:
            return "No hay tema «%s». Temas: %s" % (id, ", ".join(x["id"] for x in temas))
        filas = ["## %s — %s" % (t["id"], t["resumen"]), "archivos: " + ", ".join(t["archivos"])]
        for s in t.get("simbolos", []):
            r = _buscar(s)
            filas.append("  " + ("%s:%d  %s" % (r[0][2], r[0][3], r[0][0]) if r else "%s (NO ENCONTRADO)" % s))
        filas += ["- " + n for n in t.get("notas", [])]
        return "\n".join(filas)
    if not palabras:
        return "\n".join("%-18s %s" % (t["id"], t["resumen"]) for t in temas)
    ws = [_norm(w) for w in palabras]
    puntos = []
    for t in temas:
        texto = _norm(" ".join([t["id"], t["resumen"], " ".join(t.get("claves", [])), " ".join(t.get("simbolos", []))]))
        p = sum(texto.count(w) for w in ws)
        if p:
            puntos.append((p, t))
    puntos.sort(key=lambda x: -x[0])
    return "\n".join("%-18s %s  [%s]" % (t["id"], t["resumen"], ", ".join(t["archivos"][:3])) for _, t in puntos[:6]) \
        or "Ningun tema. Lista: mapa"


def generar():
    temas = _temas()
    avisos = []
    for t in temas:
        for a in t["archivos"]:
            if not (BASE / a).exists():
                avisos.append("%s: no existe el archivo %s" % (t["id"], a))
        for s in t.get("simbolos", []):
            if not _buscar(s):
                avisos.append("%s: no existe el simbolo %s" % (t["id"], s))
    bloque = [INICIO] + ["- **%s**: %s" % (t["id"], t["resumen"]) for t in temas] + [FIN]
    texto = CLAUDE.read_text(encoding="utf-8")
    i, j = texto.find(INICIO), texto.find(FIN)
    if i >= 0 and j > i:
        texto = texto[:i] + "\n".join(bloque) + texto[j + len(FIN):]
        with open(CLAUDE, "r+", encoding="utf-8", newline="") as f:     # r+: CLAUDE.md esta oculto (Windows no deja
            f.write(texto)                                               # abrirlo con "w")
            f.truncate()
    return "Mapa de CLAUDE.md: %d temas.%s" % (len(temas), ("\nAVISOS:\n" + "\n".join(avisos)) if avisos else " Todo existe.")


def main(args):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not args:
        print(__doc__)
        return
    orden, resto = args[0], args[1:]
    if orden == "mapa":
        ids = [a[3:] for a in resto if a.startswith("id=")]
        print(mapa(*[a for a in resto if not a.startswith("id=")], id=ids[0] if ids else None))
    elif orden == "donde":
        print(donde(" ".join(resto)))
    elif orden == "simbolo":
        print(simbolo(resto[0], resto[1] if len(resto) > 1 else 0))
    elif orden == "modulo":
        print(modulo(resto[0]))
    elif orden == "llamadas":
        print(llamadas(resto[0]))
    elif orden == "generar":
        print(generar())
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
