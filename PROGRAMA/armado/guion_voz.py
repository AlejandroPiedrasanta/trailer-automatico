# -*- coding: utf-8 -*-
"""
guion_voz.py - (1.8.7) La IA local como EDITORA de la voz original de los videos largos (15 y 30 min).

La persona (20-nov): «pule más la IA y el armado final para entregar videos largos más profesionales, ya con la voz del
audio original, pasando tomas encima de la voz, algo bonito junto la música y SFX»; «arma una historia bonita».

Lo que dijeron en el evento (la transcripcion de DaVinci: el pastor, los votos, los brindis, los discursos) llega aqui
ya partido en trozos que se pueden oir solos (cortados en limites de oracion, build_trailers._trozos). La IA local
(la misma de vision_ia: Qwen3-VL en Ollama, que tambien lee texto) califica CADA trozo como lo haria un editor de bodas:
  - se_entiende: la frase tiene sentido completo (la transcripcion automatica se equivoca mucho con musica de fondo:
    en el XV del 8-nov casi todo eran palabras sin sentido, y sin esto entraban a la pelicula);
  - emocion 0-10 (votos, promesas, un papa agradeciendo por su hija: 10; avisos, platica: 0);
  - cierre: si sirve para despedir el video (gracias, bendiciones, felicidades).
Con eso: la APERTURA es la mas emotiva y corta (va al empezar el primer capitulo, como adelanto), la HISTORIA las demas
buenas (en el momento en que se dijeron) y el CIERRE la mas calida para despedir (sobre la imagen final).
MEDIDO (20-nov): pedirle a la IA que elija o califique la lista entera de una vez daba todo 0 o notas cruzadas; una
frase por pregunta es estable (~2 s cada una con la tarjeta ocupada, 4 a la vez).

Sin IA local devuelve None y build_trailers elige como siempre (puntaje + palabras de emocion). Lo calificado queda en
datos/analisis/guion_voz.json por frase: el siguiente armado no vuelve a preguntar.
"""
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import rutas

CACHE = os.path.join(rutas.ANALISIS, "guion_voz.json")
VERSION = 5                    # 5: preguntas concretas (que tipo de frase, cuantas palabras raras) y la nota la calcula
#                                el programa: con «nota 0-10» la IA daba 0 a todo (v3) o 7-8 a todo, hasta a «guarden
#                                silencio» (v4). 3: una frase por pregunta. 2: lista entera (todo 0). 1: «elige» (ninguna)
TIEMPO_MAX = 120.0             # s que se espera cada respuesta (con DaVinci abierto la tarjeta va mas lenta)
TEXTO_MAX = 360                # letras de cada trozo que lee la IA
A_LA_VEZ = 4                   # preguntas a la vez (el servidor propio de vision_ia atiende 4)
NOTA_HISTORIA = 5              # nota (0-10) desde la que una frase que se entiende entra a la historia (1.8.7: 6 -> 5,
#                                la persona: «la voz más presente»)
NOTA_APERTURA = 8              # y desde la que puede abrir el video (ademas: corta)
NOTA_CIERRE = 7                # y desde la que puede cerrarlo (ademas: la IA dijo que sirve para despedir)
APERTURA_MAX_S = 15.0
# la nota de cada tipo de frase (la IA dice el tipo; el programa pone la nota)
NOTA_TIPO = {"voto_promesa": 10, "bendicion_familia": 9, "bendicion_oracion": 8, "agradecimiento": 8, "brindis": 8,
             "consejo_deseo": 7, "platica": 3, "otro": 4, "aviso_instruccion": 0, "letra_cancion": 0}
RESTA_RARAS = {"ninguna": 0, "pocas": 1, "muchas": 3}          # «casi_todas» = no se entiende
TIPOS_CIERRE = ("bendicion_familia", "bendicion_oracion", "agradecimiento", "brindis", "consejo_deseo")

FORMATO = {"type": "object", "properties": {
    "tipo": {"type": "string", "enum": list(NOTA_TIPO)},
    "palabras_raras": {"type": "string", "enum": ["ninguna", "pocas", "muchas", "casi_todas"]},
    "habla_de_los_novios": {"type": "boolean"},
    "cierre": {"type": "boolean"}},
    "required": ["tipo", "palabras_raras", "habla_de_los_novios", "cierre"]}

PROMPT = """Esta frase se dijo en {evento} ({quien}). Es la transcripción automática del audio de una cámara (puede \
tener palabras mal escritas; en la película se escucha la voz real):

«{texto}»

Responde con estas etiquetas:
- "tipo": "voto_promesa" (votos, "te prometo", "te acepto", "te amo"), "bendicion_familia" (un papá, una mamá, un
  abuelo o un padrino bendice o habla con cariño a los novios), "bendicion_oracion" (una oración o bendición para los
  novios o su matrimonio), "agradecimiento" (gracias a Dios, a la familia, a los invitados), "brindis", "consejo_deseo"
  (un consejo o buenos deseos para los novios), "aviso_instruccion" (avisos u órdenes: "guarden silencio", "un
  aplauso", "pónganse de pie", "pasen a la mesa", "vamos a recibir"), "letra_cancion", "platica" (conversación sin
  importancia) u "otro".
- "palabras_raras": cuántas palabras parecen inventadas o no tienen sentido: "ninguna", "pocas", "muchas" o
  "casi_todas".
- "habla_de_los_novios": true si la frase es para los novios o sobre ellos.
- "cierre": true si sirve para despedir la película (agradecimiento final, bendición, felicitación, "para siempre").
Responde solo el JSON."""

NOMBRE_EVENTO = {"boda": "una boda", "xv": "unos quince años", "bautizo": "un bautizo", "graduacion": "una graduación",
                 "cumpleanos": "un cumpleaños"}
QUIEN = {"PASTOR": "lo dijo el pastor o sacerdote en la ceremonia", "VOTOS": "son los votos en la ceremonia",
         "DECLARACION": "en la ceremonia", "BRINDIS": "es un brindis en la fiesta", "AMOR": "en el evento"}


def _leer():
    try:
        with open(CACHE, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("v") == VERSION and isinstance(d.get("frases"), dict):
            return d
    except (OSError, ValueError):
        pass
    return {"v": VERSION, "frases": {}}


def _guardar(d):
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        tmp = CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, CACHE)
    except OSError:
        pass


def _texto(t):
    return " ".join(str(t.get("texto") or "").split())[:TEXTO_MAX]


def _clave(t, tipo_evento, modelo):
    base = "|".join((tipo_evento, str(t.get("tipo")), str(t.get("momento")), modelo, _texto(t)))
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def nota_de(c):
    """La nota (0-10) de una frase con las etiquetas de la IA."""
    if not c or c.get("palabras_raras") == "casi_todas":
        return 0
    base = NOTA_TIPO.get(c.get("tipo"), 4)
    if base <= 0:
        return 0
    return max(0, min(10, base + (1 if c.get("habla_de_los_novios") else 0) - RESTA_RARAS.get(c.get("palabras_raras"), 1)))


def _calificar(t, tipo_evento, modelo):
    import vision_ia
    quien = QUIEN.get(t.get("tipo")) or ("en la ceremonia" if t.get("momento") == "IGLESIA" else "en la fiesta")
    cuerpo = {"model": modelo, "stream": False, "format": FORMATO, "keep_alive": "10m",
              "options": {"temperature": 0, "num_predict": 80, "num_ctx": 4096},
              "messages": [{"role": "user", "content": PROMPT.format(
                  evento=NOMBRE_EVENTO.get(tipo_evento, "un evento"), quien=quien, texto=_texto(t))}]}
    d = json.loads(vision_ia._pedir("/api/chat", cuerpo, timeout=TIEMPO_MAX)["message"]["content"])
    c = {"tipo": str(d.get("tipo") or "otro"), "palabras_raras": str(d.get("palabras_raras") or "pocas"),
         "habla_de_los_novios": d.get("habla_de_los_novios") is True or str(d.get("habla_de_los_novios")).lower() == "true",
         "cierre": d.get("cierre") is True or str(d.get("cierre")).lower() == "true"}
    c["emocion"] = nota_de(c)
    c["se_entiende"] = c["palabras_raras"] != "casi_todas"
    return c


def repartir(trozos, califs, n):
    """Con la calificacion de cada trozo: apertura, historia (de la mejor a la peor, a lo sumo n) y cierre."""
    notas = [(c["emocion"] if c and c.get("se_entiende") else 0) for c in califs]
    total = len(trozos)
    ap = max((i for i in range(total) if notas[i] >= NOTA_APERTURA and trozos[i]["dur"] <= APERTURA_MAX_S),
             key=lambda i: (notas[i], -i), default=None)
    # el cierre: una bendicion, un agradecimiento, un brindis o buenos deseos (MEDIDO con la boda: la IA no marco
    # «cierre» en ninguna de 62 frases, asi que lo decide el tipo), mejor de la fiesta (lo ultimo que se dijo) y si la
    # IA dijo que despide, luego por nota
    ci = max((i for i in range(total) if i != ap and notas[i] >= NOTA_CIERRE
              and ((califs[i] or {}).get("cierre") or (califs[i] or {}).get("tipo") in TIPOS_CIERRE)),
             key=lambda i: (trozos[i].get("momento") == "FIESTA", bool((califs[i] or {}).get("cierre")), notas[i], i),
             default=None)
    historia = [i for i in sorted(range(total), key=lambda i: (-notas[i], i))
                if notas[i] >= NOTA_HISTORIA and i not in (ap, ci)][:n]
    return {"apertura": ap, "historia": historia, "cierre": ci, "notas": notas}


def elegir(trozos, n, tipo_evento="boda", minutos=15, log=print):
    """trozos: [{"momento", "tipo", "dur", "texto"}] (los candidatos, del mejor puntaje al peor). Devuelve
    {"apertura": i|None, "historia": [i...], "cierre": i|None, "notas": [0-10 por trozo]} con indices de `trozos`, o
    None sin IA local (o si la IA no contesto ninguna)."""
    if not trozos or os.environ.get("TRAILER_GUION_IA") == "0":
        return None
    try:
        import vision_ia
        modelo = vision_ia.modelo()
    except Exception:
        modelo = None
    if not modelo:
        return None
    cache = _leer()
    claves = [_clave(t, tipo_evento, modelo) for t in trozos]
    faltan = [i for i, k in enumerate(claves) if k not in cache["frases"]]
    t0, fallos = time.time(), 0
    if faltan:
        def uno(i):
            try:
                return i, _calificar(trozos[i], tipo_evento, modelo)
            except Exception:
                return i, None
        with ThreadPoolExecutor(A_LA_VEZ) as ex:
            for i, c in ex.map(uno, faltan):
                if c is None:
                    fallos += 1
                    continue
                cache["frases"][claves[i]] = c
        _guardar(cache)
    califs = [cache["frases"].get(k) for k in claves]
    if not any(califs):
        log("Guion de la voz: la IA local no respondió; se elige como siempre.")
        return None
    res = repartir(trozos, califs, n)
    entiende = sum(1 for c in califs if c and c.get("se_entiende"))
    elegidas = len(res["historia"]) + (res["apertura"] is not None) + (res["cierre"] is not None)
    log("Guion de la voz con la IA local (%s): de %d frases se entienden %d y valen %d (%d preguntadas en %.0f s%s)."
        % (modelo, len(trozos), entiende, elegidas, len(faltan) - fallos, time.time() - t0,
           ", %d sin respuesta" % fallos if fallos else ""))
    return res
