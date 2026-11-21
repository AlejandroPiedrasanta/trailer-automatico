# -*- coding: utf-8 -*-
"""
protegidos.py - La musica, los SFX y las fuentes con licencia van CIFRADOS en el repositorio publico (no se redistribuyen):
AES-256-GCM con una clave que vive solo en tu PC (PROGRAMA/datos/clave_recursos.txt) y en el secreto TRAILER_CLAVE de GitHub.

  python protegidos.py cifrar        recursos/audio/* + fuentes con licencia -> recursos_protegidos/protegidos.bin.parteNN (<90 MB)
  python protegidos.py descifrar     (con TRAILER_CLAVE en el entorno) -> vuelve a dejarlos en PROGRAMA/recursos
"""
import os
import io
import sys
import base64
import zipfile

PROG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECURSOS = os.path.join(PROG, "recursos")
SALIDA = os.path.join(PROG, "recursos_protegidos")
CLAVE_LOCAL = os.path.join(PROG, "datos", "clave_recursos.txt")
FUENTES_CON_LICENCIA = ("FogtwoNo5.ttf",)
TROZO = 90 * 1024 * 1024


def _protegidos():
    out = []
    for f in sorted(os.listdir(os.path.join(RECURSOS, "audio"))):
        out.append(os.path.join("audio", f))
    for f in FUENTES_CON_LICENCIA:
        if os.path.exists(os.path.join(RECURSOS, "fuentes", f)):
            out.append(os.path.join("fuentes", f))
    return out + musica_con_licencia()


def musica_con_licencia():
    """(1.8.7) Las versiones de canciones con derechos que la persona agrego a los estilos de musica (A Thousand Years,
    Perfect, Time...): su nombre lleva « - » y el titulo («02 ROMANTICA C - A THOUSAND YEARS (VIOLIN).mp3»). No van en
    git (.gitignore) ni en las actualizaciones publicas (construir.ps1): van cifradas aqui, como recursos/audio."""
    out = []
    for raiz, carpetas, fs in os.walk(os.path.join(RECURSOS, "musica")):
        carpetas[:] = [c for c in carpetas if c not in ("xv", "_descartadas")]
        out += [os.path.relpath(os.path.join(raiz, f), RECURSOS) for f in fs if f.lower().endswith(".mp3") and " - " in f]
    return sorted(out)


def _clave():
    k = os.environ.get("TRAILER_CLAVE", "").strip()
    if not k and os.path.exists(CLAVE_LOCAL):
        k = open(CLAVE_LOCAL, encoding="utf-8").read().strip()
    return base64.b64decode(k) if k else None


def cifrar():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    clave = _clave()
    if clave is None:
        clave = AESGCM.generate_key(bit_length=256)
        os.makedirs(os.path.dirname(CLAVE_LOCAL), exist_ok=True)
        open(CLAVE_LOCAL, "w", encoding="utf-8").write(base64.b64encode(clave).decode())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for rel in _protegidos():
            z.write(os.path.join(RECURSOS, rel), rel.replace(os.sep, "/"))
    nonce = os.urandom(12)
    datos = nonce + AESGCM(clave).encrypt(nonce, buf.getvalue(), b"trailer-automatico")
    os.makedirs(SALIDA, exist_ok=True)
    for f in os.listdir(SALIDA):
        if f.startswith("protegidos.bin.parte"):
            os.remove(os.path.join(SALIDA, f))
    n = 0
    for i in range(0, len(datos), TROZO):
        n += 1
        open(os.path.join(SALIDA, "protegidos.bin.parte%02d" % n), "wb").write(datos[i:i + TROZO])
    print("cifrados %d archivos (%.0f MB) en %d partes" % (len(_protegidos()), len(datos) / 1e6, n))


def descifrar():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    clave = _clave()
    if clave is None:
        raise SystemExit("Falta la clave (TRAILER_CLAVE)")
    partes = sorted(f for f in os.listdir(SALIDA) if f.startswith("protegidos.bin.parte"))
    datos = b"".join(open(os.path.join(SALIDA, f), "rb").read() for f in partes)
    plano = AESGCM(clave).decrypt(datos[:12], datos[12:], b"trailer-automatico")
    with zipfile.ZipFile(io.BytesIO(plano)) as z:
        z.extractall(RECURSOS)
        print("descifrados %d archivos" % len(z.namelist()))


if __name__ == "__main__":
    {"cifrar": cifrar, "descifrar": descifrar}[sys.argv[1]]()
