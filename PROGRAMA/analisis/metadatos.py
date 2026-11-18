# -*- coding: utf-8 -*-
"""
metadatos.py - Los METADATOS VISIBLES de cada video analizado, DENTRO del archivo original (MP4 / MOV).

(18-nov, la persona: «no hay metadatos en los videos y deberían estar») El analisis ya viajaba con cada archivo en un
flujo oculto de NTFS («video.mp4:trailer», analizar_material._incrustar), pero eso no se ve en Windows ni en ningun
programa. Aqui se escribe lo que se entiende de la toma como etiquetas normales del contenedor (iTunes / QuickTime
«udta/meta/ilst»): titulo (que pasa), comentario (momento · escena · belleza · si sirve) y palabras clave. Se ven en
Propiedades > Detalles del Explorador, en DaVinci, VLC, MediaInfo o ffprobe.

COMO, para no arriesgar el original:
  - Solo se toca la CABECERA («moov»), que en los videos de camara, celular y dron va DESPUES de la imagen («mdat»):
    la imagen y el sonido no se mueven ni se reescriben (ni un byte), y los indices siguen valiendo.
  - Antes de escribir se guarda la cola original del archivo (desde «moov») en «.trailer/original/» de su carpeta:
    restaurar(ruta) lo deja exactamente como estaba.
  - Si la cabecera va ANTES de la imagen (videos exportados, «faststart») no se toca: devolveria False.
  - La fecha del archivo (la hora de la camara) se conserva.
El archivo crece unos cientos de bytes: quien lo llama (analizar_material) cambia su clave nombre|tamaño.

    python PROGRAMA/analisis/metadatos.py leer <video>
    python PROGRAMA/analisis/metadatos.py restaurar <video>
"""
import os
import struct
import sys

MARCA = "Tráiler automático"
RESPALDO = os.path.join(".trailer", "original")
CLAVES = {"titulo": b"\xa9nam", "comentario": b"\xa9cmt", "descripcion": b"desc", "etiquetas": b"keyw"}
EXT = (".mp4", ".mov", ".m4v")


def campos_de(item):
    """Lo que se escribe de una toma analizada (item del analisis): titulo, comentario, descripcion y etiquetas."""
    ia = item.get("ia") or {}
    momento = str(item.get("momento") or "").strip()
    escena = str(ia.get("escena") or "").strip()
    etiquetas = [str(e) for e in ia.get("etiquetas") or []]
    clave = sorted({str(e) for x in ia.get("instantes") or [] if len(x) > 1 for e in (x[1] or [])})
    partes = [p for p in (momento, escena) if p]
    if etiquetas:
        partes.append("se ve: " + ", ".join(etiquetas))
    if clave:
        partes.append("momentos: " + ", ".join(clave))
    if ia.get("belleza"):
        partes.append("belleza %s de 10" % ia["belleza"])
    if item.get("prota"):
        partes.append("sale la persona festejada")
    partes.append("no sirve" if (ia.get("util") is False or item.get("descartar")) else "sirve")
    partes.append(MARCA)
    todas = ([momento] if momento else []) + etiquetas + clave
    return {"titulo": escena or momento, "comentario": " · ".join(partes), "descripcion": momento,
            "etiquetas": "; ".join(dict.fromkeys(todas))}


def _atomos(b, ini, fin):
    """[(tipo, inicio, tamaño, cabecera)] de los atomos de b[ini:fin]."""
    out, pos = [], ini
    while pos + 8 <= fin:
        n, t = struct.unpack(">I4s", b[pos:pos + 8])
        cab = 8
        if n == 1:
            n, cab = struct.unpack(">Q", b[pos + 8:pos + 16])[0], 16
        elif n == 0:
            n = fin - pos
        if n < cab or pos + n > fin:
            raise ValueError("atomo roto en %d" % pos)
        out.append((t, pos, n, cab))
        pos += n
    return out


def _atomo(tipo, cuerpo):
    return struct.pack(">I4s", 8 + len(cuerpo), tipo) + cuerpo


def _dato(clave, texto):
    return _atomo(clave, _atomo(b"data", struct.pack(">II", 1, 0) + texto.encode("utf-8")))


def _arriba(ruta):
    """Los atomos de primer nivel: [(tipo, inicio, tamaño)], sin leer el archivo entero."""
    out, pos, fin = [], 0, os.path.getsize(ruta)
    with open(ruta, "rb") as f:
        while pos + 8 <= fin:
            f.seek(pos)
            h = f.read(16)
            n, t = struct.unpack(">I4s", h[:8])
            if n == 1:
                n = struct.unpack(">Q", h[8:16])[0]
            elif n == 0:
                n = fin - pos
            if n < 8 or pos + n > fin:
                raise ValueError("archivo con estructura rara")
            out.append((t, pos, n))
            pos += n
    return out


def _moov_nuevo(moov, campos):
    """La cabecera con nuestras etiquetas en udta/meta/ilst (lo que ya hubiera ahi de otros se conserva)."""
    nuestras = {CLAVES[k]: v for k, v in campos.items() if k in CLAVES and v}
    hijos = _atomos(moov, 8, len(moov))
    udta = next((h for h in hijos if h[0] == b"udta"), None)
    otros_udta, items_viejos, hdlr = b"", b"", None
    if udta is not None:
        for t, p, n, cab in _atomos(moov, udta[1] + udta[3], udta[1] + udta[2]):
            if t != b"meta":
                otros_udta += moov[p:p + n]
                continue
            try:
                for t2, p2, n2, cab2 in _atomos(moov, p + cab + 4, p + n):
                    if t2 == b"hdlr":
                        hdlr = moov[p2:p2 + n2]
                    elif t2 == b"ilst":
                        for t3, p3, n3, _ in _atomos(moov, p2 + cab2, p2 + n2):
                            if t3 not in CLAVES.values():
                                items_viejos += moov[p3:p3 + n3]
            except ValueError:
                otros_udta += moov[p:p + n]          # un «meta» que no es de etiquetas: se deja tal cual
    hdlr = hdlr or _atomo(b"hdlr", struct.pack(">II4s4sIIH", 0, 0, b"mdir", b"appl", 0, 0, 0)[:25])
    ilst = _atomo(b"ilst", items_viejos + b"".join(_dato(k, v) for k, v in nuestras.items()))
    udta_n = _atomo(b"udta", otros_udta + _atomo(b"meta", struct.pack(">I", 0) + hdlr + ilst))
    cuerpo = b"".join(udta_n if h is udta else moov[h[1]:h[1] + h[2]] for h in hijos)
    if udta is None:
        cuerpo += udta_n
    return _atomo(b"moov", cuerpo)


def _carpeta_respaldo(ruta):
    return os.path.join(os.path.dirname(ruta), RESPALDO)


def leer(ruta):
    """{"titulo", "comentario", "descripcion", "etiquetas"} que haya en el archivo (los que haya)."""
    out = {}
    try:
        arriba = _arriba(ruta)
        t, p, n = next(a for a in arriba if a[0] == b"moov")
        with open(ruta, "rb") as f:
            f.seek(p)
            moov = f.read(n)
        udta = next(h for h in _atomos(moov, 8, len(moov)) if h[0] == b"udta")
        meta = next(h for h in _atomos(moov, udta[1] + udta[3], udta[1] + udta[2]) if h[0] == b"meta")
        ilst = next(h for h in _atomos(moov, meta[1] + meta[3] + 4, meta[1] + meta[2]) if h[0] == b"ilst")
        al_reves = {v: k for k, v in CLAVES.items()}
        for t3, p3, n3, cab3 in _atomos(moov, ilst[1] + ilst[3], ilst[1] + ilst[2]):
            if t3 in al_reves:
                d = next(h for h in _atomos(moov, p3 + cab3, p3 + n3) if h[0] == b"data")
                out[al_reves[t3]] = moov[d[1] + d[3] + 8:d[1] + d[2]].decode("utf-8", "replace")
    except (StopIteration, ValueError, OSError):
        pass
    return out


def escribir(ruta, campos):
    """Pone las etiquetas en el archivo. campos: {"titulo", "comentario", "descripcion", "etiquetas"} (textos).
    True si quedaron escritas (o ya estaban iguales); False si el archivo no es de los que se pueden tocar sin riesgo."""
    if not ruta.lower().endswith(EXT):
        return False
    campos = {k: str(v) for k, v in campos.items() if k in CLAVES and v}
    if leer(ruta) == campos:
        return True
    arriba = _arriba(ruta)
    tipos = [a[0] for a in arriba]
    if b"moov" not in tipos or b"mdat" not in tipos:
        return False
    i_moov = tipos.index(b"moov")
    if any(t == b"mdat" for t in tipos[i_moov + 1:]):          # cabecera antes de la imagen: no se toca
        return False
    ini = arriba[i_moov][1]
    st = os.stat(ruta)
    with open(ruta, "rb") as f:
        f.seek(ini)
        cola = f.read()
    moov = cola[:arriba[i_moov][2]]
    nueva = _moov_nuevo(moov, campos) + cola[len(moov):]
    _atomos(nueva, 0, len(nueva))                              # que lo nuevo se pueda leer entero antes de escribir
    resp = os.path.join(_carpeta_respaldo(ruta), "%s.%d.cola" % (os.path.basename(ruta), st.st_size))
    if not any(f.startswith(os.path.basename(ruta) + ".") for f in
               (os.listdir(_carpeta_respaldo(ruta)) if os.path.isdir(_carpeta_respaldo(ruta)) else [])):
        os.makedirs(os.path.dirname(resp), exist_ok=True)       # la primera cola es la ORIGINAL: no se pisa nunca
        with open(resp, "wb") as f:
            f.write(struct.pack(">Q", ini) + cola)
    with open(ruta, "r+b") as f:
        f.seek(ini)
        f.write(nueva)
        f.truncate()
        f.flush()
        os.fsync(f.fileno())
    os.utime(ruta, ns=(st.st_atime_ns, st.st_mtime_ns))
    return leer(ruta) == campos


def restaurar(ruta):
    """Deja el archivo exactamente como antes de la primera escritura. True si habia que restaurar y se pudo."""
    d = _carpeta_respaldo(ruta)
    try:
        resp = next(os.path.join(d, f) for f in os.listdir(d) if f.startswith(os.path.basename(ruta) + ".")
                    and f.endswith(".cola"))
    except (OSError, StopIteration):
        return False
    st = os.stat(ruta)
    with open(resp, "rb") as f:
        b = f.read()
    ini, cola = struct.unpack(">Q", b[:8])[0], b[8:]
    with open(ruta, "r+b") as f:
        f.seek(ini)
        f.write(cola)
        f.truncate()
    os.utime(ruta, ns=(st.st_atime_ns, st.st_mtime_ns))
    return True


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "leer":
        print(leer(sys.argv[2]))
    elif len(sys.argv) > 2 and sys.argv[1] == "restaurar":
        print(restaurar(sys.argv[2]))
    else:
        print(__doc__)
