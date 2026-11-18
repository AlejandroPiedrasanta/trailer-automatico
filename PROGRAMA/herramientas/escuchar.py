"""ESCUCHAR sin oidos: que suena en una pista o en un video, en una linea (earshot local: CLAP + AST, sin internet).

    python PROGRAMA/herramientas/escuchar.py <archivo o carpeta> [...]      genero, animo, instrumentos, voz, LUFS
    python PROGRAMA/herramientas/escuchar.py <archivo> --es "romantic piano and strings" "sad music"
                                                                            que tanto se parece a cada descripcion (z)
    python PROGRAMA/herramientas/escuchar.py <video> --tramos 0-14 14-37 37-60   lo mismo, por tramos (segundos)

z: >= 3 claro, 2,5-3 probable, 2-2,5 flojo, < 2 no. Los generos y animos son pistas, no certezas (fallan ~1 de 5).
Guarda lo escuchado en datos/analisis/escuchado.json (nombre + tamaño + tramo): no se repite."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nucleo"))
import rutas  # noqa: E402

EXT = (".mp3", ".wav", ".m4a", ".flac", ".mov", ".mp4")
CACHE = os.path.join(rutas.ANALISIS, "escuchado.json")


def _earshot(args):
    exe = shutil.which("earshot")
    if not exe:
        raise SystemExit("earshot no esta instalado (uv tool install earshot).")
    with tempfile.TemporaryDirectory() as d:
        sal = os.path.join(d, "r.json")
        r = subprocess.run([exe] + args + ["--json", "--out", sal], capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if not os.path.exists(sal):
            raise RuntimeError((r.stderr or r.stdout or "sin salida")[-300:])
        with open(sal, encoding="utf-8") as f:
            return json.load(f)


def _cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def describir(ruta, ini=None, fin=None):
    c = _cache()
    # con la carpeta y la fecha: dos pistas de igual duracion pesan lo mismo y se llaman igual en cada estilo
    k = "%s/%s|%d|%d|%s|%s" % (os.path.basename(os.path.dirname(os.path.abspath(ruta))), os.path.basename(ruta),
                               os.path.getsize(ruta), int(os.path.getmtime(ruta)), ini, fin)
    if k not in c:
        args = ["describe", ruta]
        if ini is not None:
            args += ["--start", str(ini), "--end", str(fin)]
        d = _earshot(args)
        t = d.get("tags", {})
        c[k] = {"genero": [(x["term"].replace(" music", ""), x["z"]) for x in t.get("music_genre", [])[:2]],
                "animo": [(x["term"].replace(" music", ""), x["z"]) for x in t.get("music_mood", [])[:2]],
                "instr": [(x["term"], x["z"]) for x in t.get("instruments", [])[:2]],
                "voz": [(x["term"], x["z"]) for x in t.get("voice", [])[:1]],
                "lufs": d.get("measurements", {}).get("lufs"), "lra": d.get("measurements", {}).get("lra_lu"),
                "dur": d.get("duration")}
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False)
    return c[k]


def linea(d):
    def j(xs):
        return ", ".join("%s %+.1f" % (a, z) for a, z in xs)
    voz = [x for x in d["voz"] if x[1] >= 2.5]
    return "%s | %s | %s%s | %s LUFS, rango %s" % (j(d["genero"]), j(d["animo"]), j(d["instr"]),
                                                   " | VOZ: " + j(voz) if voz else "", d["lufs"], d["lra"])


def main():
    a = sys.argv[1:]
    es = a[a.index("--es") + 1:] if "--es" in a else []
    a = a[:a.index("--es")] if "--es" in a else a
    tramos = [x for x in (a[a.index("--tramos") + 1:] if "--tramos" in a else [])]
    a = a[:a.index("--tramos")] if "--tramos" in a else a
    archivos = []
    for p in a:
        if os.path.isdir(p):
            for d, _, fs in os.walk(p):
                archivos += [os.path.join(d, f) for f in sorted(fs) if f.lower().endswith(EXT)]
        else:
            archivos.append(p)
    for r in archivos:
        nombre = os.path.join(os.path.basename(os.path.dirname(r)), os.path.basename(r))
        try:
            if es:
                d = _earshot(["match", r] + es)
                res = d.get("results") or d.get("matches") or d
                print("%s: %s" % (nombre, json.dumps(res, ensure_ascii=False)[:600]))
            elif tramos:
                for t in tramos:
                    ini, fin = (float(x) for x in t.split("-"))
                    print("%s %5.0f-%-5.0f %s" % (nombre[-28:], ini, fin, linea(describir(r, ini, fin))), flush=True)
            else:
                print("%-44s %s" % (nombre[-44:], linea(describir(r))), flush=True)
        except Exception as ex:
            print("%s: no se pudo escuchar (%s)" % (nombre, ex), flush=True)


if __name__ == "__main__":
    main()
