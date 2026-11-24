# -*- coding: utf-8 -*-
"""
mapa_codigo.py - Consultar el codigo POR TEMA sin leer archivos enteros (para ahorrar tokens), como en CineCaptions.

  mapa [palabras]     temas que encajan (compacto); mapa id=<tema> da el detalle: archivos, simbolos por archivo con su
                      linea, temas conectados y el TITULO de cada nota numerada (1.9.2: antes, las notas enteras)
  mapa id=<tema> nota 3 [7 ...]   esa(s) nota(s) entera(s)  ·  notas: todas  ·  buscar <palabras>: las que las dicen
  conexiones [modulo|tema]   que modulos usa y quien lo usa (sacado del codigo) y sus temas; sin nada, los centrales
  donde <nombre>      archivo:lineas, tipo y primera linea del docstring de cada funcion/clase que coincide (sin codigo)
  simbolo <nombre> [desde]   el CODIGO de esa funcion/clase/metodo solamente (Clase.metodo tambien vale)
  modulo <archivo>    que es un archivo: su descripcion y sus funciones/clases con linea
  llamadas <nombre>   quien usa esa funcion/clase (archivo:linea: codigo)
  generar             reescribe el mapa de temas de CLAUDE.md desde docs/mapa.json y avisa de simbolos que ya no existen

Uso:  python PROGRAMA/herramientas/mapa_codigo.py mapa color   |   mapa id=color buscar guardian   |   conexiones vertical
      |   simbolo cdl_para   |   donde texto   |   llamadas armar_todo
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
    # (1.9.2) «modulo.nombre» (vertical.medir, caras._grupos): el de ESE archivo (hay medir() en varios)
    pre, _, resto = nombre.partition(".")
    if resto and any(Path(s[2]).stem.lower() == pre.lower() for s in idx):
        en = [s for s in idx if Path(s[2]).stem.lower() == pre.lower()]
        n = _norm(resto)
        return [s for s in en if _norm(s[0]) == n or _norm(s[0]).endswith("." + n)] or \
            [s for s in en if n in _norm(s[0])]
    n = _norm(nombre)
    # el nombre tal cual antes que un metodo con ese nombre (medir() del modulo antes que _medir_temblor.medir)
    exactos = [s for s in idx if _norm(s[0]) == n] + [s for s in idx if _norm(s[0]).endswith("." + n)]
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


# (1.9.2, la persona: «mejora las conexiones») quien usa a quien, sacado del CODIGO (no se escribe a mano): import y
# from (tambien dentro de funciones, como se hace aqui para abrir rapido) y las cargas por nombre del programa
REFERENCIAS = (re.compile(r"_modulo\(\s*[\"'](\w+)[\"']"), re.compile(r"codigo\(\s*[\"'](\w+)\.py[\"']"),
               re.compile(r"spec_from_file_location\(\s*[\"'](\w+)[\"']"),
               re.compile(r"import_module\(\s*[\"'](\w+)[\"']"))
_GRAFO = {}


def grafo():
    """{modulo: (ruta dentro de PROGRAMA, {modulos del programa que usa})}."""
    if _GRAFO:
        return _GRAFO
    archivos = {p.stem: p for p in _archivos()}
    for stem, p in archivos.items():
        texto = p.read_text(encoding="utf-8")
        usa = set()
        try:
            for n in ast.walk(ast.parse(texto)):
                if isinstance(n, ast.Import):
                    usa.update(a.name.split(".")[0] for a in n.names)
                elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                    usa.add(n.module.split(".")[0])
        except SyntaxError:
            pass
        for patron in REFERENCIAS:
            usa.update(patron.findall(texto))
        _GRAFO[stem] = (p.relative_to(RAIZ).as_posix(), {u for u in usa if u in archivos and u != stem})
    return _GRAFO


def conexiones(nombre=""):
    """Un modulo: que modulos usa, quien lo usa (por carpeta) y en que temas sale. Un tema: con que temas comparte
    archivos y que usan sus archivos. Sin nada: los modulos de los que mas depende el programa."""
    g = grafo()
    temas = _temas()
    lo_usan = {s: sorted(o for o, (_r, u) in g.items() if s in u) for s in g}
    carpeta = lambda m: g[m][0].split("/")[0]
    agrupa = lambda ms: "; ".join("%s: %s" % (c, ", ".join(sorted(m for m in ms if carpeta(m) == c)))
                                  for c in sorted({carpeta(m) for m in ms})) or "-"
    if not nombre:
        filas = ["Los modulos de los que mas depende el programa («conexiones <modulo o tema>» da el detalle):"]
        for s in sorted(g, key=lambda s: (-len(lo_usan[s]), s))[:16]:
            filas.append("  %-20s lo usan %2d · usa %2d   %s" % (s, len(lo_usan[s]), len(g[s][1]), g[s][0]))
        return "\n".join(filas)
    t = next((x for x in temas if x["id"] == nombre), None)
    if t is not None:
        mios = set(t.get("archivos", []))
        filas = ["## %s — temas conectados (archivos en comun):" % t["id"]]
        for i, _c in _relacionados(t, temas, 12):
            otros = set(next(x for x in temas if x["id"] == i).get("archivos", []))
            filas.append("  %-16s %s" % (i, ", ".join(Path(a).name for a in sorted(mios & otros))))
        stems = {Path(a).stem for a in mios if a.endswith(".py")}
        filas.append("sus archivos usan: " + agrupa(sorted({u for s in stems if s in g for u in g[s][1]} - stems)))
        return "\n".join(filas)
    s = nombre.lower().replace(".py", "")
    if s not in g:
        return "No hay modulo ni tema «%s». Prueba «conexiones» (sin nada) o «mapa %s»." % (nombre, nombre)
    ts = [x["id"] for x in temas if any(Path(a).stem == s for a in x.get("archivos", []))]
    return "\n".join([g[s][0],
                      "  usa (%d):     %s" % (len(g[s][1]), agrupa(sorted(g[s][1]))),
                      "  lo usan (%d): %s" % (len(lo_usan[s]), agrupa(lo_usan[s])),
                      "  temas:       %s" % (", ".join(ts) or "-")])


TITULO_NOTA = 115                  # (1.9.2) caracteres del titulo de cada nota en «mapa id=»


def _titulo(nota):
    """El comienzo de una nota, cortado en una palabra: lo que se lista en «mapa id=» (la nota entera, a pedido)."""
    t = " ".join(str(nota).split())
    if len(t) <= TITULO_NOTA:
        return t
    corte = t.rfind(" ", 0, TITULO_NOTA)
    return t[:corte if corte > 60 else TITULO_NOTA] + "…"


def _simbolos_por_archivo(t):
    """Los simbolos del tema agrupados por archivo, con su linea: «armado/vertical.py: medir 160, camino 252»."""
    por, faltan = {}, []
    mios = set(t.get("archivos", []))
    for s in t.get("simbolos", []):
        r = _buscar(s)
        if not r:
            faltan.append(s)
            continue
        r = [x for x in r if x[2] in mios] or r        # con el mismo nombre en varios archivos: el del tema
        ruta = r[0][2].replace("PROGRAMA/", "", 1)
        por.setdefault(ruta, []).append("%s %d" % (r[0][0], r[0][3]))
    filas = ["  %s: %s" % (ruta, ", ".join(xs)) for ruta, xs in por.items()]
    if faltan:
        filas.append("  (NO ENCONTRADOS: %s)" % ", ".join(faltan))
    return filas


def _relacionados(t, temas, n=6):
    """Los temas que comparten archivos con este, de mas a menos: [(id, cuantos)]."""
    mios = set(t.get("archivos", []))
    out = [(len(mios & set(x.get("archivos", []))), x["id"]) for x in temas if x["id"] != t["id"]]
    return [(i, c) for c, i in sorted(out, key=lambda z: (-z[0], z[1])) if c][:n]


def mapa(*palabras, id=None, notas=None, buscar=None):
    """(1.9.2, la persona: «crea el mapa para ahorrar tokens sin que se relea todo, mejora las conexiones») «mapa
    id=<tema>» da el resumen, los archivos, los simbolos por archivo, los temas conectados y SOLO el titulo de cada
    nota numerada (antes imprimia las notas enteras: «tiempos» eran ~6.800 tokens). notas = [numeros] o "todas" la(s)
    imprime enteras; buscar = palabras: las notas del tema que las tienen, enteras."""
    temas = _temas()
    if id:
        t = next((x for x in temas if x["id"] == id), None)
        if t is None:
            return "No hay tema «%s». Temas: %s" % (id, ", ".join(x["id"] for x in temas))
        todas = t.get("notas", [])
        if notas == "todas":
            return "\n".join("%d. %s" % (i, n) for i, n in enumerate(todas, 1))
        if notas:
            return "\n".join("%d. %s" % (k, todas[k - 1]) if 1 <= k <= len(todas) else "%d. (no hay: son %d)" % (
                k, len(todas)) for k in notas)
        if buscar:
            ws = [_norm(w) for w in buscar]
            hay = [(i, n) for i, n in enumerate(todas, 1) if all(w in _norm(n) for w in ws)]
            return "\n".join("%d. %s" % x for x in hay) or "Ninguna nota de «%s» dice %s." % (id, " ".join(buscar))
        filas = ["## %s — %s" % (t["id"], t["resumen"]), "archivos: " + ", ".join(
            a.replace("PROGRAMA/", "", 1) for a in t["archivos"])]
        filas += _simbolos_por_archivo(t)
        rel = _relacionados(t, temas)
        if rel:
            filas.append("conectado con: " + ", ".join("%s (%d)" % x for x in rel))
        filas.append("notas (%d; entera: «mapa id=%s nota N», todas: «notas», por palabra: «buscar <palabras>»):" % (
            len(todas), t["id"]))
        filas += ["  %d. %s" % (i, _titulo(n)) for i, n in enumerate(todas, 1)]
        return "\n".join(filas)
    if not palabras:
        return "\n".join("%-18s %s" % (t["id"], t["resumen"]) for t in temas)
    ws = [_norm(w) for w in palabras]
    puntos = []
    for t in temas:
        texto = _norm(" ".join([t["id"], t["resumen"], t.get("detalle", ""), " ".join(t.get("claves", [])),
                                " ".join(t.get("simbolos", []))]))         # (1.9.2) detalle: el resumen largo de antes
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
        otras = [a for a in resto if not a.startswith("id=")]
        if ids and otras and otras[0] in ("nota", "notas", "buscar"):
            if otras[0] == "buscar":
                print(mapa(id=ids[0], buscar=otras[1:]))
            elif otras[0] == "notas" or len(otras) == 1:
                print(mapa(id=ids[0], notas="todas"))
            else:
                print(mapa(id=ids[0], notas=[int(x) for x in otras[1:] if x.isdigit()]))
        else:
            print(mapa(*otras, id=ids[0] if ids else None))
    elif orden == "conexiones":
        print(conexiones(resto[0] if resto else ""))
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
