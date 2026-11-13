# -*- coding: utf-8 -*-
"""
firmar_manifiesto.py - Firma el version.json de las actualizaciones (Ed25519), como CineCaptions: el programa no instala nada
sin una firma valida de Cinema Productions, aunque alguien entrara en la cuenta de GitHub.

  python PROGRAMA/herramientas/firmar_manifiesto.py <version.json>     firma (publicar_version.ps1 lo llama solo)
  python PROGRAMA/herramientas/firmar_manifiesto.py --claves-nuevas    crea la principal y la de reserva (no pisa las que hay) e
                                                                       imprime sus claves publicas para actualizaciones.CLAVES_FIRMA

Las privadas viven FUERA del repositorio, en ~/TrailerAutomatico_claves (o la variable TRAILER_CLAVE_FIRMA = ruta de una). La de
reserva se guarda aparte (USB o nube): si se pierde la principal se firma con ella; sin ninguna, los programas instalados ya no se
actualizan. Antes de escribir comprueba la firma con las claves publicas que lleva el programa.
"""
import os
import sys
import json
import base64
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "nucleo"))
import rutas  # noqa: E402,F401  (pone las carpetas del codigo en sys.path)
import actualizaciones  # noqa: E402
import firma_ed25519  # noqa: E402

CARPETA = Path.home() / "TrailerAutomatico_claves"


def id_clave(publica):
    return hashlib.sha256(publica).hexdigest()[:8]


def claves_nuevas():
    CARPETA.mkdir(parents=True, exist_ok=True)
    for nombre in ("principal", "reserva"):
        ruta = CARPETA / ("firma_%s.txt" % nombre)
        if not ruta.exists():
            ruta.write_text(firma_ed25519.nueva_privada().hex(), encoding="utf-8")
        publica = firma_ed25519.publica(bytes.fromhex(ruta.read_text(encoding="utf-8").strip()))
        print("    '%s': '%s',   # %s" % (id_clave(publica), publica.hex(), nombre))


def leer_privada():
    v = os.environ.get("TRAILER_CLAVE_FIRMA")
    candidatos = [Path(v)] if v else [CARPETA / "firma_principal.txt", CARPETA / "firma_reserva.txt"]
    for r in candidatos:
        if r.exists():
            return bytes.fromhex(r.read_text(encoding="utf-8").strip()), r
    raise SystemExit("No encuentro la clave privada de firma en %s (ni en TRAILER_CLAVE_FIRMA): sin ella no se publica." % CARPETA)


def firmar(ruta_json):
    ruta = Path(ruta_json)
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    privada, origen = leer_privada()
    publica = firma_ed25519.publica(privada)
    valor = firma_ed25519.firmar(privada, actualizaciones.bytes_firmados(datos))
    datos["firma"] = {"alg": "ed25519", "clave": id_clave(publica), "valor": base64.b64encode(valor).decode("ascii")}
    if not actualizaciones.firma_valida(datos):
        raise SystemExit("La clave %s no es ninguna de actualizaciones.CLAVES_FIRMA: los programas la rechazarian. No se firma."
                         % origen.name)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print("    firmado con %s (%s)" % (origen.name, id_clave(publica)))


if __name__ == "__main__":
    if sys.argv[1:] == ["--claves-nuevas"]:
        claves_nuevas()
    elif len(sys.argv) == 2:
        firmar(sys.argv[1])
    else:
        print(__doc__)
