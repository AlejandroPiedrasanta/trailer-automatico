# -*- coding: utf-8 -*-
"""
motor.py - Motor del programa "Trailer XV automatico" (sin interfaz).

  armar(log, ...)        analiza el material y lo arma en las plantillas de DaVinci Resolve
  estado_davinci()       (conectado, proyecto) sin cambiar nada en Resolve
  resumen_carpetas()     cuantos archivos hay en cada carpeta
  abrir_timeline(nombre) muestra una timeline en Resolve
  huella()               firma del material (cambia al subir o terminar de copiar archivos)

Habla con DaVinci por su API de scripting (la misma que usa el MCP de Resolve), todo en local.
"""
import os
import re
import sys
import json
import time
import threading
import subprocess

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # PROGRAMA (motor esta en nucleo/)
if os.path.join(SKILL_DIR, "nucleo") not in sys.path:
    sys.path.insert(0, os.path.join(SKILL_DIR, "nucleo"))
import rutas  # noqa: E402
import analizar_material as am  # noqa: E402

BASE = rutas.BASE
BASE_DATOS = "EVENTOS"          # base de datos de Resolve donde vive el proyecto (si existe en esta compu)
PROYECTO = "EVENTOS CINEMA"     # proyecto con las plantillas universales
PROYECTOS_ANTERIORES = ["TRAILER DE XV"]   # nombre viejo: se sigue encontrando si no se ha renombrado
VERSIONES = ["1min", "3min", "15min", "30min"]
SEGUNDOS = {"1min": 60, "3min": 180, "15min": 900, "30min": 1800}      # lo que dura cada version
ETIQUETA_VERTICAL = "VERTICAL"      # las lineas del formato vertical: «XV 2026-11-08 - VERTICAL 1min»
SIN_VERTICALES = ("El formato vertical solo usa videos grabados en vertical (celular parado) y no alcanzan los que hay "
                  "en el material. Suelta más videos verticales o arma el formato horizontal.")
# Voz original (pastor, brindis, discursos) sobre la musica: como viene cada version en Ajustes. En la de 30 min va
# siempre y no se pregunta (igual que VOZ_DEFECTO / VOZ_SIEMPRE de build_trailers.py).
VOZ_DEFECTO = {"1min": False, "3min": False, "15min": True, "30min": True}    # (18-nov) la de 30 tambien se puede apagar
CARPETAS = am.CARPETAS          # {"foto": .../1 MATERIAL/FOTOS, "video": .../VIDEOS, "dron": .../DRON}
ESPERA_ESTABLE = 30             # segundos sin cambios antes de armar (copia terminada)
ESTADO = rutas.ESTADO
CANDADO = threading.Lock()      # una sola conversacion con Resolve a la vez


def leer_estado():
    try:
        with open(ESTADO, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def guardar_estado(d):
    am._guardar_json(ESTADO, d)            # escritura segura: si se corta la luz, el estado anterior queda entero


def marcar_terminado(evento, videos):
    """El evento ya tiene su EVENTO TERMINADO con al menos un video bueno: lo siguiente que se suelte empieza un evento
    nuevo (la persona, 2026-11-16: «al terminar el anterior»). videos = [(linea, ok, ruta)] de renderizar."""
    if evento and any(ok for _, ok, _ in videos or []):
        est = leer_estado()
        est["terminado"] = evento
        guardar_estado(est)


def evento_terminado():
    """El nombre del evento que hay en 1 MATERIAL si ya quedo terminado (con sus videos), o ''."""
    est = leer_estado()
    terminado = est.get("terminado") or ""
    return terminado if terminado == est.get("evento") else ""


# ------------------------------------------------------------------ prevenir errores
class SinDormir:
    """Mientras arma y renderiza, que la PC no se suspenda NI se apague la pantalla: con la pantalla apagada DaVinci
    entra en su «modo de suspension» y un analisis de IntelliSearch se quedo atascado para siempre (2026-11-14).
    Va en el hilo que trabaja: en Windows el pedido vale mientras ese hilo lo mantenga; en Mac lo sostiene
    `caffeinate`."""
    def __enter__(self):
        self.proc = None
        try:
            if rutas.ES_WIN:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)   # CONTINUOUS | SYSTEM | DISPLAY
            elif sys.platform == "darwin":
                self.proc = subprocess.Popen(["caffeinate", "-d", "-i", "-w", str(os.getpid())])
        except Exception:
            pass
        return self

    def __exit__(self, *_):
        try:
            if rutas.ES_WIN:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            elif self.proc is not None:
                self.proc.terminate()
        except Exception:
            pass


GB_POR_VERSION = {"1min": 0.1, "3min": 0.25, "15min": 1.1, "30min": 2.2}     # MOV H.265 medido: ~71 MB por minuto


def espacio_para_render(versiones):
    """(libre_gb, necesita_gb) en el disco donde quedan los EVENTO TERMINADO (con margen para el masterizado)."""
    import shutil
    d = rutas.TERMINADOS
    while d and not os.path.isdir(d):
        d = os.path.dirname(d)
    libre = shutil.disk_usage(d or rutas.BASE).free / 1e9
    return libre, sum(GB_POR_VERSION.get(v, 2.2) for v in versiones or VERSIONES) * 2 + 1.0


def esperar_copias(log, max_s=180):
    """Si algo de 1 MATERIAL se esta copiando todavia (el Explorador / Finder), espera a que termine: un video a medio
    copiar se leeria cortado."""
    limite = time.time() + max_s
    avisado = False
    while time.time() < limite:
        rutas.revisar_parada()                    # (1.8.0) «Cancelar» corta tambien esta espera (hasta 3 min)
        ahora = time.time()
        recientes = []
        for _, ruta in am.listar(BASE):
            try:
                if ahora - os.path.getmtime(ruta) < 15:
                    recientes.append(ruta)
            except OSError:
                pass
        if not recientes:
            return True
        tam = {r: os.path.getsize(r) for r in recientes if os.path.exists(r)}
        time.sleep(3)
        if all(os.path.exists(r) and os.path.getsize(r) == t for r, t in tam.items()) and \
                all(time.time() - os.path.getmtime(r) >= 6 for r in tam if os.path.exists(r)):
            return True
        if not avisado:
            log("Esperando a que termine de copiarse el material (%s…)." % os.path.basename(recientes[0]))
            avisado = True
    log("Aviso: hay archivos que siguen cambiando; sigo con lo que hay.")
    return False


def huella():
    return am.huella(BASE)


def resumen_carpetas():
    cuenta = {t: 0 for t in CARPETAS}
    for tipo, _ in am.listar(BASE):
        cuenta[tipo] += 1
    return cuenta


# Lo minimo para armar: al menos un video. Las 8 fotos de la intro (y la del final) salen de capturas del video si no hay
# fotos JPG (1.5.7, la persona: «si no hay fotos para la intro tomas capturas del video»). El dron es opcional.
MINIMOS = {"foto": 0, "video": 1, "dron": 0}
FOTOS_INTRO = 9                                   # 8 en la intro y 1 al final
NOMBRE_CARPETA = {"foto": "FOTOS", "video": "VIDEOS", "dron": "DRON"}


def revisar_material():
    """{"cuenta": {tipo: n}, "faltan": [(tipo, cuantos_faltan)], "ok": bool}"""
    cuenta = resumen_carpetas()
    faltan = [(t, m - cuenta[t]) for t, m in MINIMOS.items() if cuenta[t] < m]
    return {"cuenta": cuenta, "faltan": faltan, "ok": not faltan}


RAW = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2", ".srw"}
CARPETAS_DRON = am.CARPETAS_DRON
tipo_de_archivo = am.tipo_de_archivo        # solo JPG como foto (1.5.7); dron por nombre o carpeta


class Cancelado(Exception):
    pass


def _fecha_rapida(ruta, tipo):
    """El dia de un archivo sin analizarlo entero: EXIF de la foto, nombre (DJI, Pixel, Samsung) o fecha del archivo."""
    import datetime
    try:
        if tipo == "foto" and am.Image is not None:
            with am.Image.open(ruta) as im:
                ex = im.getexif()
                try:
                    sub = ex.get_ifd(0x8769)
                except Exception:
                    sub = {}
                d = am._fecha(sub.get(36867) or sub.get(36868) or ex.get(306))
                if d:
                    return am._jornada(d)
        d = am._hora_de_nombre(os.path.basename(ruta))
        if d:
            return am._jornada(d)
        return am._jornada(datetime.datetime.fromtimestamp(os.path.getmtime(ruta)))
    except Exception:
        return None


def examinar_origen(rutas_origen, forzar_tipo=None):
    """Mira lo que se quiere agregar SIN copiar nada: {"pares": [(ruta, tipo)], "cuenta": {tipo: n}, "bytes": total,
    "otros": {".ext": n} (lo que no se usa: RAW, documentos...), "fecha": "AAAA-MM-DD" | None, "nombre": carpeta soltada}."""
    from collections import Counter
    archivos = []
    for r in rutas_origen:
        if os.path.isdir(r):
            for d, dirs, fs in os.walk(r):
                dirs[:] = sorted(x for x in dirs if not x.startswith((".", "$")) and x.lower() != "anteriores")
                archivos += [os.path.join(d, f) for f in sorted(fs)]
        elif os.path.isfile(r):
            archivos.append(r)
    pares, otros, total = [], Counter(), 0
    for a in archivos:
        nombre = os.path.basename(a)
        if nombre.startswith((".", "~")) or nombre.lower() in ("thumbs.db", "desktop.ini"):
            continue                          # "._DSC0001.JPG" de la Mac en discos externos, temporales
        t = tipo_de_archivo(a)
        if t is not None:
            try:
                tam = os.path.getsize(a)
            except OSError:
                continue
            if tam == 0:
                otros["vacíos"] += 1
                continue
        if t is None:
            otros[os.path.splitext(a)[1].lower() or "sin extensión"] += 1
            continue
        if forzar_tipo:                       # "Agregar" de una carpeta concreta: fotos con fotos, videos con videos
            if (forzar_tipo == "foto") != (t == "foto"):
                continue
            t = forzar_tipo
        pares.append((a, t))
        total += tam
    cuenta = {t: sum(1 for _, x in pares if x == t) for t in CARPETAS}
    votos = Counter()
    for tipo, cuantos in (("foto", 16), ("video", 8), ("dron", 4)):
        grupo = [a for a, t in pares if t == tipo]
        paso = max(1, len(grupo) // cuantos)
        for a in grupo[::paso][:cuantos]:
            d = _fecha_rapida(a, tipo)
            if d:
                votos[d] += 2 if tipo == "foto" else 1
    fecha = votos.most_common(1)[0][0].isoformat() if votos else None
    primero = rutas_origen[0] if rutas_origen else ""
    nombre = os.path.basename(primero.rstrip("\\/")) if os.path.isdir(primero) else ""
    return {"pares": pares, "cuenta": cuenta, "bytes": total, "otros": dict(otros), "fecha": fecha, "nombre": nombre}


def texto_otros(otros):
    """'12 RAW (.nef) · 3 .txt' para avisar de lo que no se uso."""
    if not otros:
        return ""
    raw = sum(n for e, n in otros.items() if e in RAW)
    partes = []
    if raw:
        partes.append("%d RAW (%s): usa los JPG" % (raw, ", ".join(sorted(e for e in otros if e in RAW))))
    resto = sorted(((n, e) for e, n in otros.items() if e not in RAW), reverse=True)
    partes += [("%d vacío%s" % (n, "s" if n > 1 else "")) if e == "vacíos" else "%d %s" % (n, e) for n, e in resto[:4]]
    return " · ".join(partes)


def evento_actual():
    """(nombre, fecha) del material que hay ahora en 1 MATERIAL, segun el ultimo analisis; (None, None) si esta vacio."""
    if not any(resumen_carpetas().values()):
        return None, None
    fecha = None
    try:
        with open(os.path.join(rutas.ANALISIS, "material.json"), encoding="utf-8") as f:
            fecha = json.load(f).get("fecha")
    except Exception:
        pass
    if not fecha:                             # sin analizar todavia: una mirada rapida a lo que hay
        from collections import Counter
        votos = Counter()
        lista = am.listar(BASE)
        for tipo, ruta in lista[::max(1, len(lista) // 20)][:20]:
            d = _fecha_rapida(ruta, tipo)
            if d:
                votos[d] += 1
        fecha = votos.most_common(1)[0][0].isoformat() if votos else None
    return leer_estado().get("evento") or fecha or "evento anterior", fecha


def es_evento_nuevo():
    """(1.5.7) Lo que se suelta se une al evento que hay; solo si ese ya quedo terminado (con su EVENTO TERMINADO y sus
    videos) lo soltado empieza un evento nuevo. Devuelve el nombre del terminado o ''."""
    if not any(resumen_carpetas().values()):
        return ""
    return evento_terminado()


def es_otro_evento(fecha_nueva, fecha_actual):
    """True si lo que se suelta es de otro dia (mas de un dia de diferencia: la fiesta pasa de medianoche)."""
    import datetime
    if not fecha_nueva or not fecha_actual:
        return False
    try:
        a, b = datetime.date.fromisoformat(fecha_nueva), datetime.date.fromisoformat(fecha_actual)
    except ValueError:
        return False
    return abs((a - b).days) > 1


def archivar_material(nombre):
    """Evento nuevo: lo que hay en FOTOS / VIDEOS / DRON pasa a 1 MATERIAL/ANTERIORES/<nombre>/ (no se borra nada) y los
    textos del evento (nombres, frase, fecha) quedan en blanco. Devuelve (carpeta, cuantos)."""
    import re
    import shutil
    limpio = re.sub(r'[\\/:*?"<>|]+', " ", str(nombre or "evento anterior")).strip() or "evento anterior"
    destino = os.path.join(rutas.MATERIAL, "ANTERIORES", limpio)
    k = 2
    while os.path.exists(destino) and os.listdir(destino):
        destino = os.path.join(rutas.MATERIAL, "ANTERIORES", "%s (%d)" % (limpio, k))
        k += 1
    n = 0
    for t, carpeta in CARPETAS.items():
        if not os.path.isdir(carpeta):
            continue
        for f in os.listdir(carpeta):
            sub = os.path.join(destino, NOMBRE_CARPETA[t])
            os.makedirs(sub, exist_ok=True)
            shutil.move(os.path.join(carpeta, f), os.path.join(sub, f))
            n += 1
    if os.path.exists(rutas.CLASIFICACION):               # las correcciones a mano eran de ESE evento
        os.makedirs(destino, exist_ok=True)
        shutil.move(rutas.CLASIFICACION, os.path.join(destino, os.path.basename(rutas.CLASIFICACION)))
    if os.path.isdir(rutas.CAPTURAS):                     # las capturas de la intro eran de ESE evento
        os.makedirs(destino, exist_ok=True)
        shutil.move(rutas.CAPTURAS, os.path.join(destino, "CAPTURAS"))
    est = leer_estado()
    for clave in ("nombre_xv", "frase", "fecha_lugar", "evento_manual", "evento", "huella", "timelines", "resumen_versiones",
                  "terminado", "carpetas", "sin_renombrar"):
        est.pop(clave, None)
    guardar_estado(est)
    return destino, n


def usar_carpeta(carpeta, anterior=None):
    """(1.5.7, la persona: «si te arrastran la carpeta, es la ruta donde está») La carpeta soltada se usa DONDE ESTA: no
    se copia nada. Se une a las del evento; si el anterior ya estaba terminado (anterior = su nombre) empieza un evento
    nuevo (sus textos quedan en blanco y lo suyo se guarda en ANTERIORES). Nada se borra. Devuelve las carpetas."""
    if anterior:
        archivar_material(anterior)
    est = leer_estado()
    lista = [c for c in est.get("carpetas") or [] if os.path.isdir(c)]
    nueva = os.path.abspath(carpeta)
    if os.path.normcase(nueva) not in [os.path.normcase(os.path.abspath(c)) for c in lista]:
        lista.append(nueva)
    est["carpetas"] = lista
    guardar_estado(est)
    return lista


MOMENTO_NOMBRE = {"MAQUILLAJE": "MAQUILLAJE", "IGLESIA": "CEREMONIA", "FIESTA": "FIESTA"}


def _de_carpetas_evento(ruta):
    r = os.path.normcase(os.path.abspath(ruta))
    caps = os.path.normcase(os.path.abspath(rutas.CAPTURAS))
    return any(r.startswith(c + os.sep) for c in (os.path.normcase(os.path.abspath(x)) for x in rutas.fuentes())
               if c != caps)


def renombrar_material(analisis, log=print):
    """(1.5.7, la persona: «simplemente renombras todos los archivos: si son dron, dron; si es video vertical, video
    vertical; si es horizontal también; y entre paréntesis si es maquillaje, ceremonia o fiesta; nunca borres ningún
    archivo») Cada archivo del evento se renombra EN SU SITIO (misma carpeta: nada se mueve ni se borra), numerado por hora
    dentro de su tipo: «VIDEO HORIZONTAL 001 (CEREMONIA).MP4», «VIDEO VERTICAL 004 (FIESTA).MOV», «DRON 001 (FIESTA).MP4»,
    «FOTO 003 (MAQUILLAJE).JPG». Lo ya medido sigue valiendo (am.renombrar_cache) y los nombres de antes quedan en
    datos/analisis/nombres.json, para poder deshacerlo. Devuelve [(ruta_vieja, ruta_nueva)]."""
    if leer_estado().get("sin_renombrar"):     # la persona restauro los nombres originales: no se vuelve a renombrar
        return []
    items = [i for i in analisis.get("items") or [] if _de_carpetas_evento(i["ruta"]) and os.path.exists(i["ruta"])]
    grupos = {}
    for i in items:
        if i["tipo"] == "foto":
            t = "FOTO"
        elif i["tipo"] == "dron":
            t = "DRON"
        else:
            t = "VIDEO HORIZONTAL" if i.get("horizontal", True) else "VIDEO VERTICAL"
        grupos.setdefault(t, []).append(i)
    plan = []
    # (1.8.2, MEDIDO en la XV del 8-nov) antes se numeraba de nuevo por hora en CADA armado: al entrar material o
    # cambiar una hora, dos archivos INTERCAMBIABAN su numero. DaVinci sigue cada clip por su ruta, asi que una linea ya
    # armada mostraba OTRO video sin avisar (la «061» paso de una toma de 205 MB a una de 1,1 GB y salio oscura: el
    # color era el de la otra). Ahora un archivo que ya tiene su nombre CONSERVA su numero (solo se le corrige el
    # momento) y los nuevos siguen despues del ultimo numero de su tipo.
    patron = re.compile(r"^(FOTO|DRON|VIDEO HORIZONTAL|VIDEO VERTICAL) (\d{3,})(?: \([^)]*\))?$", re.I)
    for t, lista in grupos.items():
        lista.sort(key=lambda i: (str(i.get("hora") or ""), i["nombre"]))
        usados, numero = set(), {}
        for i in lista:                       # los que ya tienen nombre del programa: su numero es suyo
            m = patron.match(os.path.splitext(os.path.basename(i["ruta"]))[0])
            if m and m.group(1).upper() == t and int(m.group(2)) not in usados:
                numero[id(i)] = int(m.group(2))
                usados.add(int(m.group(2)))
        siguiente = max(usados) + 1 if usados else 1
        for i in lista:                       # los nuevos, por hora, despues del ultimo
            if id(i) not in numero:
                while siguiente in usados:
                    siguiente += 1
                numero[id(i)] = siguiente
                usados.add(siguiente)
        for i in lista:
            k = numero[id(i)]
            mom = MOMENTO_NOMBRE.get(i.get("momento"))
            ext = os.path.splitext(i["ruta"])[1]
            nombre = "%s %03d%s%s" % (t, k, " (%s)" % mom if mom else "", ext)
            nuevo = os.path.join(os.path.dirname(i["ruta"]), nombre)
            if os.path.normcase(nuevo) != os.path.normcase(i["ruta"]):
                plan.append((i["ruta"], nuevo))
    if not plan:
        return []
    origenes = {os.path.normcase(a) for a, _ in plan}
    final = []
    for a, b in plan:                         # un archivo ajeno que ya se llame asi no se pisa: «... (2)»
        base, ext = os.path.splitext(b)
        k = 2
        while os.path.exists(b) and os.path.normcase(b) not in origenes:
            b = "%s (%d)%s" % (base, k, ext)
            k += 1
        final.append((a, b))
    registro = os.path.join(rutas.ANALISIS, "nombres.json")       # primero la lista: si algo se corta, se sabe que era
    try:
        with open(registro, encoding="utf-8") as f:
            hist = json.load(f)
    except Exception:
        hist = []
    hist.append({"fecha": time.strftime("%Y-%m-%d %H:%M:%S"), "cambios": final})
    am._guardar_json(registro, hist)
    # en dos pasos (a un nombre de paso y luego al final): asi dos archivos pueden intercambiar su numero sin pisarse
    pasos, hechos = [], []
    for n, (a, b) in enumerate(final):
        tmp = os.path.join(os.path.dirname(a), "~renombrando %d%s" % (n, os.path.splitext(a)[1]))
        try:
            os.rename(a, tmp)
            pasos.append((a, tmp, b))
        except OSError as ex:
            log("Aviso: no pude renombrar %s (%s)" % (os.path.basename(a), ex))
    for a, tmp, b in pasos:
        try:
            os.rename(tmp, b)
            hechos.append((a, b))
        except OSError as ex:
            try:
                os.rename(tmp, a)
            except OSError:
                pass
            log("Aviso: no pude renombrar %s (%s)" % (os.path.basename(a), ex))
    am.renombrar_cache(hechos)
    try:
        import editable
        editable.seguir_renombrado(hechos)       # los proxies ya hechos siguen a su video
    except Exception:
        pass
    try:
        n = migrar_claves(hechos)
        if n:
            log("Lo que DaVinci ya había reconocido (personas, voces) sigue a los archivos renombrados: %d datos." % n)
    except Exception as ex:
        log("Aviso: no pude pasar los datos guardados a los nombres nuevos (%s)" % ex)
    log("Renombrados en su carpeta: %d archivos (nombres de antes en %s)" % (len(hechos), registro))
    return hechos


def migrar_claves(hechos):
    """(18-nov) Al renombrar, lo guardado por «nombre|tamaño» FUERA del cache del analisis se quedaba con el nombre
    viejo: personas y voces de DaVinci, ruido, volumen, estabilizador... y DaVinci volvia a reconocer todo (20 min con
    un solo nucleo; la persona: «debería usar el 100 % de CPU o GPU y no lo está haciendo»). Pasa cada clave vieja a
    la nueva en los .json de datos/analisis y en los que viajan con el material (.trailer). Devuelve cuantas paso."""
    mapa = {}
    for a, b in hechos:
        try:
            t = os.path.getsize(b)
        except OSError:
            continue
        mapa["%s|%d" % (os.path.basename(a), t)] = "%s|%d" % (os.path.basename(b), t)
    if not mapa:
        return 0
    total = [0]

    def pasar(x):
        if isinstance(x, dict):
            nuevo = {}
            for k, v in x.items():
                k2 = k
                if isinstance(k, str) and "|" in k:
                    partes = k.split("|")
                    base = "|".join(partes[:2])
                    if base in mapa:              # «nombre|tamaño» o «nombre|tamaño|mas cosas» (estabilizador)
                        k2 = "|".join([mapa[base]] + partes[2:])
                        total[0] += 1
                nuevo[k2] = pasar(v)
            return nuevo
        if isinstance(x, list):
            return [pasar(v) for v in x]
        return x
    archivos = []
    try:
        archivos += [os.path.join(rutas.ANALISIS, f) for f in os.listdir(rutas.ANALISIS)
                     if f.endswith(".json") and f not in ("nombres.json", "material.json", "material_parcial.json",
                                                          "material_ventana.json", "material_ventana2.json",
                                                          "estado_programa.json", "plan_previo.json")]
    except OSError:
        pass
    vistas = set()
    for raiz in rutas.fuentes():
        d = os.path.abspath(raiz)
        for _ in range(4):
            if os.path.normcase(d) not in vistas:
                vistas.add(os.path.normcase(d))
                for f in ("personas.json", "voces.json"):
                    archivos.append(os.path.join(d, ".trailer", f))
            arriba = os.path.dirname(d)
            if not arriba or arriba == d or len(arriba) <= 3:
                break
            d = arriba
    for ruta in archivos:
        try:
            with open(ruta, encoding="utf-8") as f:
                j = json.load(f)
        except Exception:
            continue
        antes = total[0]
        j2 = pasar(j)
        if total[0] != antes:
            try:
                am._guardar_json(ruta, j2)
            except Exception:
                pass
    return total[0]


def _historial_nombres():
    try:
        with open(os.path.join(rutas.ANALISIS, "nombres.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def nombres_de_hoy():
    """{ruta de cualquier nombre de antes (normcase): ruta de hoy}, siguiendo todos los renombrados (nombres.json) en orden.
    Lo usa reenlazar: un archivo importado en DaVinci y renombrado despues se vuelve a encontrar."""
    hoy = {}
    for vez in _historial_nombres():
        cambios = {os.path.normcase(os.path.abspath(a)): b for a, b in vez.get("cambios") or []}
        for k, v in list(hoy.items()):
            nuevo = cambios.get(os.path.normcase(os.path.abspath(v)))
            if nuevo:
                hoy[k] = nuevo
        hoy.update(cambios)
    return hoy


def restaurar_nombres(log=print):
    """(1.5.7) Deshace el renombrado: cada archivo vuelve a su nombre ORIGINAL (el que traia antes del primer renombrado),
    en su misma carpeta; si ese nombre ya lo usa otro archivo, se queda como esta. Lo deja anotado (asi DaVinci lo vuelve
    a encontrar) y el evento ya no se renombra solo (estado.sin_renombrar). Devuelve cuantos restauro."""
    hoy = nombres_de_hoy()
    originales = {}                             # ruta de hoy (normcase) -> nombre original
    vistos = set()
    for vez in _historial_nombres():
        for a, _ in vez.get("cambios") or []:
            k = os.path.normcase(os.path.abspath(a))
            if k in vistos:
                continue
            vistos.add(k)
            if k in hoy and not any(k == os.path.normcase(os.path.abspath(b)) for b in hoy.values() if b):
                originales.setdefault(os.path.normcase(os.path.abspath(hoy[k])), a)
    plan = [(hoy_r, orig) for hoy_r, orig in originales.items() if os.path.exists(hoy_r)
            and os.path.normcase(hoy_r) != os.path.normcase(orig)]
    pasos, hechos = [], []
    for n, (a, b) in enumerate(plan):
        tmp = os.path.join(os.path.dirname(a), "~restaurando %d%s" % (n, os.path.splitext(a)[1]))
        try:
            os.rename(a, tmp)
            pasos.append((a, tmp, b))
        except OSError:
            pass
    for a, tmp, b in pasos:
        destino = b if not os.path.exists(b) else a
        try:
            os.rename(tmp, destino)
            if destino == b:
                hechos.append((a, b))
        except OSError:
            try:
                os.rename(tmp, a)
            except OSError:
                pass
    if hechos:
        hist = _historial_nombres()
        hist.append({"fecha": time.strftime("%Y-%m-%d %H:%M:%S"), "cambios": hechos, "restaurado": True})
        am._guardar_json(os.path.join(rutas.ANALISIS, "nombres.json"), hist)
        am.renombrar_cache(hechos)
    est = leer_estado()
    est["sin_renombrar"] = True
    guardar_estado(est)
    log("Nombres originales restaurados: %d archivos" % len(hechos))
    return len(hechos)


def capturas_intro(analisis, cuantas, log=print):
    """(1.5.7, la persona: «si no hay fotos para la intro tomas capturas del video») Cuadros nitidos de los videos (sin
    quemar, sin barrido, camara firme), uno por video, repartidos entre maquillaje, ceremonia y fiesta. Se guardan POR
    DENTRO (rutas.CAPTURAS) como «CAPTURA 001 (CEREMONIA).jpg», con la hora del momento en EXIF (asi caen en su momento
    al analizarlas). Devuelve cuantas hizo."""
    import math
    import subprocess
    import datetime
    from collections import defaultdict
    vids = [i for i in analisis.get("items") or [] if i["tipo"] == "video" and not i.get("descartar")
            and (i.get("ia") or {}).get("util") is not False
            and (i.get("vista") or {}).get("nit") and i.get("hora") and i.get("dur", 0) > 3]
    horizontales = [i for i in vids if i.get("horizontal", True)]
    vids = horizontales if len(horizontales) >= cuantas else vids
    if not vids:
        return 0
    refs = defaultdict(list)
    for v in vids:
        refs[(v.get("camara"), v.get("ancho"))] += v["vista"]["nit"]
    refs = {k: sorted(x)[len(x) // 2] for k, x in refs.items() if x}
    cand = []
    for v in vids:
        vi = v["vista"]
        nit, quem, pan = vi.get("nit") or [], vi.get("quem") or [], vi.get("pan") or []
        tem, col = v.get("temblor") or [], v.get("color") or []
        ref = refs.get((v.get("camara"), v.get("ancho"))) or 1.0
        oscuros = v.get("oscuros") or []
        # lo que vio la IA local: los novios / la festejada y los momentos clave dan las mejores fotos de intro
        et = set((v.get("ia") or {}).get("etiquetas") or [])
        ia_peso = (1.5 if et & {"beso", "anillos", "primer_baile", "pastel", "brindis"} else 1.0) * \
            (1.3 if et & {"novia", "novio", "festejada"} else 1.0)
        mejor = None
        # (16-nov) donde la IA vio que no sirve (techo, de cabeza, gente sin cara o sin cabeza...), ninguna captura
        malos_ia = [x[0] for x in (v.get("ia") or {}).get("instantes") or [] if len(x) > 2 and x[2] is False]
        for k in range(1, len(nit) - 1):
            t = k * 0.5 + 0.25
            if t < 1.0 or t > v["dur"] - 1.0 or any(a - 1 <= t <= b + 1 for a, b in oscuros) \
                    or any(abs(t - m) <= 1.6 for m in malos_ia):
                continue
            q = quem[k] if k < len(quem) else 0.0
            p = max((math.hypot(*pan[j]) if j < len(pan) else 0.0) for j in (k - 1, k, k + 1))
            tb = tem[k] if k < len(tem) else 0.0
            luz = col[k][0] if k < len(col) else 0.3
            if q > 0.06 or p > 2.5 or tb > 3.0 or not 0.18 <= luz <= 0.85:
                continue
            puntos = min(nit[k] / ref, 2.0) * (1 - 4 * q) * (1 - 0.15 * p) * ia_peso
            if mejor is None or puntos > mejor[0]:
                mejor = (puntos, t)
        if mejor:
            cand.append((mejor[0], v, mejor[1]))
    if not cand:
        return 0
    por_momento = defaultdict(list)
    for c in sorted(cand, key=lambda c: -c[0]):
        por_momento[c[1].get("momento") or "FIESTA"].append(c)
    elegidas = []
    objetivo = cuantas * 2                     # el doble: luego la IA local mira cada una y se quedan las mejores
    while len(elegidas) < objetivo and any(por_momento.values()):   # por turnos: maquillaje, ceremonia, fiesta...
        for m in ("MAQUILLAJE", "IGLESIA", "FIESTA") + tuple(k for k in por_momento if k not in MOMENTO_NOMBRE):
            if por_momento.get(m) and len(elegidas) < objetivo:
                elegidas.append(por_momento[m].pop(0))
    hechas_rutas = []
    os.makedirs(rutas.CAPTURAS, exist_ok=True)
    hechas = 0
    previas = len([f for f in os.listdir(rutas.CAPTURAS) if f.lower().endswith(".jpg")])
    for n, (_, v, t) in enumerate(sorted(elegidas, key=lambda c: (str(c[1]["hora"]), c[2])), previas + 1):
        mom = MOMENTO_NOMBRE.get(v.get("momento"), "FIESTA")
        salida = os.path.join(rutas.CAPTURAS, "CAPTURA %03d (%s).jpg" % (n, mom))
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.2f" % t, "-i", v["ruta"],
                            "-frames:v", "1", "-q:v", "2", salida], capture_output=True, creationflags=rutas.SIN_VENTANA)
        if r.returncode != 0 or not os.path.exists(salida):
            log("Aviso: no pude sacar la captura de %s" % v["nombre"])
            continue
        try:                                   # la hora del cuadro en EXIF: cae en su momento al analizarla
            from PIL import Image
            hora = datetime.datetime.fromisoformat(str(v["hora"])) + datetime.timedelta(seconds=t)
            with Image.open(salida) as im:
                im.load()
                ex = Image.Exif()
                ex[306] = hora.strftime("%Y:%m:%d %H:%M:%S")
                ex[271] = "CAPTURA DE VIDEO"
                im.save(salida, quality=95, exif=ex)
            os.utime(salida, (hora.timestamp(), hora.timestamp()))
        except Exception as ex:
            log("Aviso: captura sin hora (%s)" % ex)
        hechas += 1
        hechas_rutas.append((salida, v))
    hechas -= _quedarse_con_las_mejores(hechas_rutas, cuantas, log)
    log("Sin fotos JPG suficientes para la intro: %d capturas de los videos (por dentro, en %s)" % (hechas, rutas.CAPTURAS))
    return hechas


def _quedarse_con_las_mejores(capturas, cuantas, log=print):
    """La IA local mira cada captura y se quedan las `cuantas` mejores: los novios / la festejada y los momentos clave
    (beso, anillos, votos, primer baile, pastel, brindis), al menos 2 de cada momento si hay; las demas pasan a
    CAPTURAS/.descartadas (no se borran; la carpeta con punto no se usa). Sin IA local, se quedan todas. Devuelve cuantas
    aparto."""
    if len(capturas) <= cuantas:
        return 0
    try:
        import vision_ia
        if not vision_ia.modelo(log):
            return 0
    except Exception:
        return 0
    puntos = []
    for salida, v in capturas:
        ia = vision_ia.describir("foto", salida, 0.0, log) or {}
        et = set(ia.get("etiquetas") or [])
        p = 0.0 if ia.get("util") is False else 1.0 + 1.0 * bool(et & {"novia", "novio", "festejada"}) + \
            0.8 * bool(et & {"beso", "anillos", "votos", "primer_baile", "pastel", "brindis"}) + \
            0.2 * bool(et & {"familia", "grupo"})
        puntos.append((p, salida, v.get("momento")))
    puntos.sort(key=lambda x: -x[0])
    quedan = []
    for m in ("MAQUILLAJE", "IGLESIA", "FIESTA"):                # primero las 2 mejores de cada momento
        quedan += [x for x in puntos if x[2] == m][:2]
    quedan = quedan[:cuantas]
    for x in puntos:
        if len(quedan) >= cuantas:
            break
        if x not in quedan:
            quedan.append(x)
    aparte = os.path.join(rutas.CAPTURAS, ".descartadas")
    n = 0
    for x in puntos:
        if x not in quedan:
            os.makedirs(aparte, exist_ok=True)
            try:
                os.replace(x[1], os.path.join(aparte, os.path.basename(x[1])))
                n += 1
            except OSError:
                pass
    log("La IA local eligio las %d mejores capturas para la intro (de %d)." % (len(quedan), len(puntos)))
    return n


def _huella_rapida(ruta, tam):
    """Huella de un archivo sin leerlo entero (tamano + primer y ultimo trozo): para no copiar dos veces lo mismo."""
    import hashlib
    h = hashlib.sha1(str(tam).encode())
    with open(ruta, "rb") as f:
        h.update(f.read(262144))
        if tam > 524288:
            f.seek(-262144, 2)
            h.update(f.read(262144))
    return h.hexdigest()


def copiar_material(rutas_origen, avance=None, forzar_tipo=None, cancelado=None, examen=None):
    """Copia archivos (o carpetas completas, con subcarpetas) a 1 MATERIAL/FOTOS|VIDEOS|DRON segun su tipo.
    avance(bytes_hechos, bytes_total, nombre, i, n). No pisa nada: el mismo archivo (aunque tenga otro nombre) se omite, y
    otro distinto con el mismo nombre (dos camaras con DSC_0001.JPG) queda como «DSC_0001 (2).JPG».
    Devuelve {"copiados": {tipo: n}, "ya_estaban": n, "otros": {".ext": n}, "bytes": copiados}."""
    import shutil
    examen = examen or examinar_origen(rutas_origen, forzar_tipo)
    pares, total = examen["pares"], max(1, examen["bytes"])
    libre = shutil.disk_usage(rutas.MATERIAL if os.path.isdir(rutas.MATERIAL) else BASE).free
    if examen["bytes"] > libre - 500e6:
        raise RuntimeError("No hay espacio en el disco para el material: hacen falta %.1f GB y quedan %.1f GB."
                           % (examen["bytes"] / 1e9, libre / 1e9))
    hechos = {t: 0 for t in CARPETAS}
    ya, hecho_b, copiado_b = 0, 0, 0
    indice = {}                                # tipo -> {tamano: [rutas ya en la carpeta]}

    def tamanos(t):
        if t not in indice:
            d = {}
            os.makedirs(CARPETAS[t], exist_ok=True)
            for e in os.scandir(CARPETAS[t]):
                if e.is_file():
                    d.setdefault(e.stat().st_size, []).append(e.path)
            indice[t] = d
        return indice[t]

    for i, (a, t) in enumerate(pares, 1):
        if cancelado and cancelado():
            raise Cancelado()
        tam = os.path.getsize(a)
        nombre = os.path.basename(a)
        if avance:
            avance(hecho_b, total, nombre, i, len(pares))
        iguales = tamanos(t).get(tam) or []
        if iguales:                            # mismo tamano: ¿es el mismo archivo con otro nombre?
            h = _huella_rapida(a, tam)
            if any(os.path.exists(x) and (os.path.samefile(x, a) or _huella_rapida(x, tam) == h) for x in iguales):
                ya += 1
                hecho_b += tam
                continue
        base, ext = os.path.splitext(nombre)
        destino, k = os.path.join(CARPETAS[t], nombre), 2
        while os.path.exists(destino):
            destino = os.path.join(CARPETAS[t], "%s (%d)%s" % (base, k, ext))
            k += 1
        parcial = destino + ".copiando"        # si se corta (disco lleno, se desconecta), no queda un video a medias
        try:
            with open(a, "rb") as fo, open(parcial, "wb") as fd:
                while True:
                    if cancelado and cancelado():
                        raise Cancelado()
                    buf = fo.read(8 << 20)
                    if not buf:
                        break
                    fd.write(buf)
                    hecho_b += len(buf)
                    if avance:
                        avance(hecho_b, total, nombre, i, len(pares))
            shutil.copystat(a, parcial)        # la fecha del archivo se conserva: el analizador la usa
            os.replace(parcial, destino)
        except BaseException:
            try:
                os.remove(parcial)
            except OSError:
                pass
            raise
        tamanos(t).setdefault(tam, []).append(destino)
        hechos[t] += 1
        copiado_b += tam
    if avance:
        avance(total, total, "", len(pares), len(pares))
    return {"copiados": hechos, "ya_estaban": ya, "otros": examen["otros"], "bytes": copiado_b}


# ------------------------------------------------------------------ plan sin DaVinci
class _PlantillaFalsa:
    def __init__(self, nombre, d):
        self.nombre, self.d = nombre, d

    def GetName(self):
        return self.nombre

    def GetSetting(self, clave):
        return self.d.get("fps", 24.0) if clave == "timelineFrameRate" else None

    def GetMarkers(self):
        return {int(f): m for f, m in (self.d.get("marcadores") or {}).items()}


class _ResolveFalso:
    """Lo minimo de la API para PLANIFICAR sin DaVinci abierto: las 4 plantillas con sus marcadores (los que trae el
    programa en recursos/plantillas_marcadores.json)."""
    def __init__(self, plantillas):
        self.tls = [_PlantillaFalsa(n, d) for n, d in plantillas.items()]

    def GetProjectManager(self):
        return self

    def GetCurrentProject(self):
        return self

    def GetTimelineCount(self):
        return len(self.tls)

    def GetTimelineByIndex(self, i):
        return self.tls[i - 1]


def guardar_plan(rep):
    """El ultimo plan previo queda en datos/analisis/plan_previo.json (lo lee la ventana y las pruebas)."""
    if rep:
        am._guardar_json(os.path.join(rutas.ANALISIS, "plan_previo.json"),
                         {"evento": rep.get("evento"), "versiones": rep.get("versiones", [])})


def plan_previo(analisis, log=print, solo=None, tipo_evento="xv", evento="", verticales=True,
                formato="horizontal", **_):
    """El plan de cada version (cuantos planos por zona, camara lenta, estabilizar) SIN conectar con DaVinci: usa los
    marcadores de las plantillas que trae el programa. Devuelve el reporte de build_trailers o None."""
    try:
        with open(os.path.join(rutas.RECURSOS, "plantillas_marcadores.json"), encoding="utf-8") as f:
            plantillas = json.load(f)
    except Exception:
        return None
    import re
    repiten = {}                                # version -> planos que repiten video (un solo aviso al final, no uno por zona)

    def decir(*a, **k):
        t = " ".join(str(x) for x in a)
        m = re.match(r"AVISO: (\S+) .*?: (\d+) planos repiten video", t)
        if m:
            repiten[m.group(1)] = repiten.get(m.group(1), 0) + int(m.group(2))
        else:
            log(t.replace(" | 0 cortes al ritmo", ""))      # el ritmo se mide despues, ya con la musica en DaVinci

    ruta = rutas.codigo("build_trailers.py")
    g = {"__name__": "build_trailers", "resolve": _ResolveFalso(plantillas), "BASE": BASE, "ANALISIS": analisis,
         "EVENTO": evento or None, "SOLO": solo or None, "REHACER": True, "DRY_RUN": True, "SIN_RESOLVE": True,
         "TIPO_EVENTO": tipo_evento, "VERTICALES": bool(verticales), "FORMATO": formato, "print": decir}
    with open(ruta, encoding="utf-8") as f:
        exec(compile(f.read(), ruta, "exec"), g)
    if repiten:
        claves = sorted(repiten, key=lambda v: int(re.sub(r"\D", "", v) or 0))
        vs = [re.sub(r"(\d+)", r"\1 ", v) for v in claves]              # «15min» -> «15 min»
        lista = vs[0] if len(vs) == 1 else ", ".join(vs[:-1]) + " y " + vs[-1]
        if len(vs) == 1:
            log("Con el video que hay, la versión de %s repite %d tomas: con más video queda mejor." % (lista, repiten[claves[0]]))
        else:
            log("Con el video que hay, las versiones de %s repiten tomas (%s): con más video quedan mejor."
                % (lista, " · ".join("%s: %d" % (v, repiten[k]) for v, k in zip(vs, claves))))
    res = g.get("result")
    if isinstance(res, dict):
        res["repiten"] = repiten
    return res


def chequeo():
    """Chequeo de arranque: [(nombre, ok, detalle)]. No toca DaVinci."""
    import shutil
    res = []
    rutas.crear_carpetas()
    m = revisar_material()
    c = m["cuenta"]
    res.append(("Fotos de la intro", c["foto"] >= MINIMOS["foto"],
                "%d fotos" % c["foto"] if c["foto"] >= MINIMOS["foto"] else
                "faltan %d fotos" % (MINIMOS["foto"] - c["foto"])))
    res.append(("Videos", c["video"] >= MINIMOS["video"],
                "%d videos" % c["video"] if c["video"] else "no hay videos"))
    res.append(("Dron", True, "%d tomas" % c["dron"] if c["dron"] else "sin tomas de dron (opcional)"))
    ff = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
    res.append(("ffmpeg", ff, "listo" if ff else "falta ffmpeg"))
    dv = os.path.exists(rutas.SCRIPT_LIB) and os.path.isdir(rutas.SCRIPT_API)
    res.append(("DaVinci Resolve", dv, "instalado" if dv else "no encuentro DaVinci Resolve Studio"))
    pl = os.path.exists(rutas.PLANTILLAS_DRP)
    res.append(("Plantillas", pl, "listas" if pl else "falta %s" % os.path.basename(rutas.PLANTILLAS_DRP)))
    try:
        os.makedirs(rutas.DIR_LUT_MCP, exist_ok=True)
        lut = os.access(rutas.DIR_LUT_MCP, os.W_OK)
    except Exception:
        lut = False
    res.append(("Color y ruido", lut, "carpeta de LUT lista" if lut else "sin permiso en la carpeta de LUT"))
    try:
        import numpy  # noqa: F401
        lib = True
    except Exception:
        lib = False
    res.append(("Ritmo de la musica", lib, "listo" if lib else "falta numpy"))
    return res


def _resumen(items):
    res = {}
    for it in items:
        if it.get("descartar") or not it.get("momento"):
            continue
        r = res.setdefault(it["momento"], {"fotos": 0, "videos": 0, "dron": 0, "min": 0.0})
        r["fotos" if it["tipo"] == "foto" else "videos"] += 1
        r["dron"] += it["tipo"] == "dron"
        r["min"] += it.get("dur", 0) / 60.0 if it["tipo"] != "foto" else 0
    return res


def resumen_material():
    """Fotos/videos por momento segun el ultimo analisis guardado (sin volver a analizar)."""
    try:
        with open(os.path.join(rutas.ANALISIS, "material.json"), encoding="utf-8") as f:
            return _resumen(json.load(f).get("items", []))
    except Exception:
        return {}


def _dvr():
    api = os.environ.get("RESOLVE_SCRIPT_API") or rutas.SCRIPT_API
    lib = os.environ.get("RESOLVE_SCRIPT_LIB") or rutas.SCRIPT_LIB
    os.environ["RESOLVE_SCRIPT_API"], os.environ["RESOLVE_SCRIPT_LIB"] = api, lib
    if rutas.CONGELADO:
        # Desde el .exe: fusionscript busca python3.dll en PYTHON3HOME y sus DLL en la carpeta de Resolve
        os.environ.setdefault("PYTHON3HOME", rutas.PROGRAMA)
        if rutas.ES_WIN and os.path.isdir(os.path.dirname(lib)):
            try:
                os.add_dll_directory(os.path.dirname(lib))
            except Exception:
                pass
    mods = os.path.join(api, "Modules")
    if not os.path.exists(lib) or not os.path.isdir(mods):
        raise RuntimeError("No encuentro DaVinci Resolve Studio en esta computadora. Instálalo (la versión Studio: la "
                           "gratuita no deja que otros programas la controlen), ábrelo una vez y vuelve a pulsar ▶.")
    if mods not in sys.path:
        sys.path.append(mods)
    try:
        import DaVinciResolveScript
    except ImportError as ex:
        raise RuntimeError("DaVinci Resolve está instalado pero no se pudo cargar su conexión (%s). Reinstala DaVinci "
                           "Resolve Studio o actualízalo." % ex)
    return DaVinciResolveScript


def _sin_titulo(nombre):
    n = (nombre or "").strip().lower()
    return not n or n.startswith(("untitled project", "proyecto sin t", "sin titulo", "sin título"))


def resolve_abierto():
    """True si el proceso de DaVinci Resolve esta corriendo (sin tocar su API: nunca se cuelga)."""
    try:
        if rutas.ES_WIN:
            # (17-nov) en bytes: tasklist responde en la pagina de codigos de la consola (Windows en espanol: acentos
            # en cp850) y leerlo como texto UTF-8 rompia la lectura («DaVinci cerrado» aunque estuviera abierto)
            r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Resolve.exe", "/NH"], capture_output=True,
                               timeout=5, creationflags=rutas.SIN_VENTANA)
            return b"resolve.exe" in (r.stdout or b"").lower()
        r = subprocess.run(["pgrep", "-x", "Resolve"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def estado_davinci():
    """(abierto, proyecto). Sin usar la API de Resolve ni el candado, para no frenar nunca al boton Play:
    el nombre del proyecto se lee del titulo de la ventana en Windows."""
    if not resolve_abierto():
        return False, ""
    proyecto = ""
    for t in _titulos_resolve(todos=True):
        if t.startswith("DaVinci Resolve") and " - " in t:
            proyecto = t.split(" - ", 1)[1].strip()
    return True, proyecto


def dialogos_resolve(exe="resolve.exe"):
    """Titulos de ventanas de Resolve que no son la principal (p. ej. 'Crear proyecto', 'Organizador de
    proyectos'). Con un cuadro asi abierto, la API se bloquea o no responde."""
    return _titulos_resolve(False, exe)


def _titulos_resolve(todos=False, exe="resolve.exe"):
    """Titulos de las ventanas visibles de Resolve (Windows). todos=False: sin la ventana principal."""
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    titulos = []

    def es_resolve(pid):
        h = k32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            buf = ctypes.create_unicode_buffer(520)
            n = wintypes.DWORD(520)
            return bool(k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))) and \
                buf.value.lower().endswith("\\" + exe)
        finally:
            k32.CloseHandle(h)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cada(hwnd, _):
        if u32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            buf = ctypes.create_unicode_buffer(256)
            u32.GetWindowTextW(hwnd, buf, 256)
            if buf.value and es_resolve(pid.value):
                titulos.append(buf.value)
        return True
    try:
        u32.EnumWindows(cada, 0)
    except Exception:
        return []
    return titulos if todos else [t for t in titulos if not t.startswith("DaVinci Resolve")]


ORGANIZADOR = ("organizador de proyectos", "project manager")   # se cierra solo al abrir el proyecto


def _bloqueos(incluir_organizador):
    return [t for t in dialogos_resolve()
            if incluir_organizador or not t.lower().startswith(ORGANIZADOR)]


CUADROS_NUESTROS = ("crear proyecto", "create project", "guardar proyecto", "save project")


def _cerrar_cuadros(titulos):
    """Cierra (= Cancelar) ventanas de Resolve con esos titulos. Solo Windows."""
    if os.name != "nt":
        return 0
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.windll.user32
    hechas = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cada(h, _):
        buf = ctypes.create_unicode_buffer(256)
        u32.GetWindowTextW(h, buf, 256)
        if u32.IsWindowVisible(h) and buf.value.lower().startswith(titulos):
            u32.PostMessageW(h, 0x0010, 0, 0)          # WM_CLOSE
            hechas.append(buf.value)
        return True
    u32.EnumWindows(cada, 0)
    return len(hechas)


class _Vigilante:
    """Mientras se abre el proyecto: si Resolve saca un cuadro que bloquea la API ("Crear proyecto"...),
    lo cancela para que la llamada no se quede esperando para siempre."""
    def __init__(self, log):
        self.log, self.fin = log, threading.Event()

    def __enter__(self):
        def vigilar():
            while not self.fin.wait(2.0):
                if _cerrar_cuadros(CUADROS_NUESTROS):
                    self.log("AVISO: DaVinci abrio un cuadro que bloqueaba la conexion; se cancelo solo.")
        threading.Thread(target=vigilar, daemon=True).start()
        return self

    def __exit__(self, *_):
        self.fin.set()


def conectar_resolve(log, quedarse=False):
    """quedarse: (19-nov) lo que corre en segundo plano (IntelliSearch, leer el ruido) acepta el proyecto de un video
    que la persona tenga abierto: antes la sacaba de ahi y le cargaba EVENTOS CINEMA mientras editaba."""
    with _Vigilante(log):
        return _conectar_resolve(log, quedarse)


_CONEXION = {"r": None}


def _conexion_viva():
    """(1.8.2, la persona: «pule la rapidez de respuesta con DaVinci») La conexion de la vez anterior, si DaVinci
    sigue contestando por ella (una llamada barata); si DaVinci se cerro o se reinicio, None y se conecta de nuevo.
    Antes cada accion (Editar, Renderizar lo editado, el ruido, IntelliSearch) volvia a llamar a scriptapp."""
    r = _CONEXION.get("r")
    if r is None:
        return None
    try:
        if r.GetProjectManager() is not None:
            return r
    except Exception:
        pass
    _CONEXION["r"] = None
    return None


def _conectar_resolve(log, quedarse=False):
    abiertos = _bloqueos(False)
    t0 = time.time()
    while abiertos and time.time() - t0 < 15:     # (18-nov) una ventana «Resolve» de paso (progreso) no es un cuadro:
        time.sleep(1.0)                            # se espera a que se vaya antes de rendirse
        abiertos = _bloqueos(False)
    if abiertos:
        raise RuntimeError("DaVinci tiene abierto: %s. Cierralo y vuelve a intentar."
                           % ", ".join("«%s»" % t for t in abiertos))
    dvr = _dvr()
    r = _conexion_viva()
    if r is None:
        r = dvr.scriptapp("Resolve")
    if r is None and any(" - " in t for t in _titulos_resolve(True)):
        # (1.8.2, MEDIDO el 20-nov) DaVinci YA abierto con un proyecto (ya cargo) y aun asi no contesta: antes se
        # esperaban 75 s mas. Dos intentos mas (~8 s) y se dice que hacer.
        for _ in range(2):
            rutas.revisar_parada()
            r = dvr.scriptapp("Resolve")
            if r is not None:
                break
        if r is None:
            raise RuntimeError("DaVinci está abierto pero no deja que el programa lo controle. Ciérralo y ábrelo otra "
                               "vez; si sigue igual, en DaVinci: Preferencias > Sistema > General > Scripting externo "
                               "= Local.")
    if r is None and rutas.abrir_resolve():
        log("Abriendo DaVinci Resolve...")

        import vigia_davinci

        def esperar(segundos):
            # (18-nov, medido) contesta a los 15-37 s; tras una caida se quedo 273 s sin contestar (la espera era de 40
            # VUELTAS y cada scriptapp sin respuesta tarda ~4 s) y al reabrirlo contesto en 15 s: se cuenta en segundos
            r, t0, sin_proceso, dicho = None, time.time(), 0, 0
            while time.time() - t0 < segundos:
                time.sleep(3)
                # (1.8.0, auditoria) «Cancelar» cortaba recien al terminar la espera (hasta 3-4 min) y la ventana decia
                # lo mismo todo el rato: ahora corta enseguida y cada 15 s dice cuanto lleva
                rutas.revisar_parada()
                if time.time() - t0 >= dicho + 15:
                    dicho += 15
                    log("Esperando a DaVinci… %d s (suele contestar en 15-40 s)" % dicho)
                r = dvr.scriptapp("Resolve")
                if r is not None and r.GetProjectManager() is not None:
                    log("DaVinci contestó en %.0f s." % (time.time() - t0))
                    break
                # (18-nov) se caia a los 10 s (Python de Fusion sin arrancar) y aqui se esperaban 2 + 3 min a ciegas:
                # sin proceso dos veces seguidas = se cerro solo; se abre otra vez enseguida (hasta 2 veces)
                sin_proceso = 0 if vigia_davinci.abierto() else sin_proceso + 1
                if sin_proceso >= 2:
                    if _relanzados["n"] >= 2:
                        log("DaVinci se cerró solo al abrir, tres veces: no sigo.")
                        break
                    _relanzados["n"] += 1
                    log("DaVinci se cerró solo al abrir (a los %.0f s): lo abro otra vez..." % (time.time() - t0))
                    rutas.abrir_resolve()
                    sin_proceso = 0
            return r
        _relanzados = {"n": 0}
        r = esperar(75)
        if r is None or r.GetProjectManager() is None:
            log("DaVinci no contestó en 75 s; ventanas abiertas: %s" % (", ".join(
                "«%s»" % t for t in _titulos_resolve(True)) or "ninguna"))
        if (r is None or r.GetProjectManager() is None) and os.name == "nt" and \
                not any(t.startswith("DaVinci Resolve") for t in _titulos_resolve(True)):
            # (17-nov, dos veces en un dia) DaVinci abrio pero se quedo sin contestar: colgado en la portada «Cargando
            # proyectos» o parado en el Organizador de proyectos. No hay ningun proyecto abierto (su ventana se llamaria
            # «DaVinci Resolve - ...»), asi que no se pierde nada: se cierra y se abre otra vez, una sola vez.
            log("DaVinci no contesta (portada u Organizador de proyectos): lo cierro y lo abro otra vez...")
            try:
                import subprocess
                subprocess.run(["taskkill", "/IM", "Resolve.exe", "/F"], capture_output=True, timeout=30,
                               creationflags=rutas.SIN_VENTANA)
                time.sleep(4)
                if rutas.abrir_resolve():
                    r = esperar(120)
            except Exception as ex:
                log("  no se pudo reabrir DaVinci (%s)" % ex)
        time.sleep(5)                     # que termine de arrancar antes de pedirle el proyecto
    if r is None or r.GetProjectManager() is None:       # a veces scriptapp devuelve un objeto "hueco"
        raise RuntimeError("No pude conectar con DaVinci Resolve. Abrelo y revisa Preferencias > Sistema > "
                           "General > Scripting externo = Local.")
    pm = r.GetProjectManager()
    actual = pm.GetCurrentProject()
    nombres = [PROYECTO] + PROYECTOS_ANTERIORES + ([_PROYECTO_VIDEO["nombre"]] if _PROYECTO_VIDEO["nombre"] else [])
    if quedarse and leer_estado().get("proyecto_video"):
        nombres.append(leer_estado()["proyecto_video"])
    try:
        base_actual = (pm.GetCurrentDatabase() or {}).get("DbName")
    except Exception:
        base_actual = None
    bases = [d.get("DbName") for d in (pm.GetDatabaseList() or [])]
    # (18-nov) DaVinci abrio en la base «REDES SOCIALES», que TAMBIEN tiene un «EVENTOS CINEMA»: como el nombre
    # coincidia no se cambiaba de base, se armo todo ahi y al hacer los .drp por video DaVinci perdio esa base
    # («Driver not loaded») y se colgo. Ahora la base tiene que ser EVENTOS aunque el proyecto se llame igual.
    otra_base = BASE_DATOS in bases and base_actual not in (None, BASE_DATOS)
    if otra_base:
        log("DaVinci estaba en la base «%s»: paso a «%s»." % (base_actual, BASE_DATOS))
    if actual is None or actual.GetName() not in nombres or otra_base:
        log("Abriendo el proyecto %s..." % PROYECTO)
        # Solo se guarda un proyecto con nombre de verdad. Guardar el "Untitled Project" que Resolve abre al
        # arrancar hace salir el cuadro "Crear proyecto" y la API se queda esperando para siempre.
        if actual is not None and not _sin_titulo(actual.GetName()):
            pm.SaveProject()
        if BASE_DATOS in bases:
            if not pm.SetCurrentDatabase({"DbType": "Disk", "DbName": BASE_DATOS}):
                log("AVISO: DaVinci no quiso pasar a la base «%s» (sigue en «%s»)." % (
                    BASE_DATOS, (pm.GetCurrentDatabase() or {}).get("DbName")))
        cargado = None
        if _PROYECTO_VIDEO["nombre"] and _PROYECTO_VIDEO.get("carpeta"):
            # (19-nov) DaVinci se reinicio a mitad del render de un video: se vuelve a SU proyecto (en la carpeta
            # del evento), no a EVENTOS CINEMA (si no, se exportaba EVENTOS CINEMA entero como el .drp del video)
            pm.GotoRootFolder()
            pm.OpenFolder(_PROYECTO_VIDEO["carpeta"])
            cargado = pm.LoadProject(_PROYECTO_VIDEO["nombre"])
        pm.GotoRootFolder()
        if not cargado:
            cargado = any(pm.LoadProject(n) for n in nombres)
        if not cargado:
            # (20-nov, MEDIDO) DaVinci recien abierto seguia cargando su ultimo proyecto (el de un video, 11 s): el
            # LoadProject de EVENTOS CINEMA devolvio None aunque estaba en la raiz, y se intento instalar las plantillas
            # otra vez (falla: ese nombre ya existe). Si el proyecto esta ahi, se espera y se pide otra vez.
            hay = [n for n in nombres if n in (pm.GetProjectListInCurrentFolder() or [])]
            for vuelta in range(8 if hay else 0):
                log("DaVinci todavia esta cargando; pido el proyecto otra vez (%d)..." % (vuelta + 1))
                time.sleep(6)
                pm.GotoRootFolder()
                if any(pm.LoadProject(n) for n in hay):
                    cargado = True
                    break
            if hay and not cargado:
                raise RuntimeError("DaVinci no quiso abrir el proyecto %s. Cierralo, abrelo otra vez y vuelve a "
                                   "intentar." % hay[0])
        if not cargado:
            if not os.path.exists(rutas.PLANTILLAS_DRP):
                raise RuntimeError("No encontre el proyecto '%s' en DaVinci ni las plantillas en %s."
                                   % (PROYECTO, rutas.PLANTILLAS_DRP))
            log("Primera vez en esta computadora: instalando las plantillas en DaVinci...")
            if not (pm.ImportProject(rutas.PLANTILLAS_DRP, PROYECTO) and pm.LoadProject(PROYECTO)):
                raise RuntimeError("DaVinci no pudo importar las plantillas (%s)." % rutas.PLANTILLAS_DRP)
        time.sleep(2)
    abiertos = _bloqueos(True)
    if abiertos:
        raise RuntimeError("DaVinci sigue con %s abierto. Cierralo y vuelve a intentar."
                           % ", ".join("«%s»" % t for t in abiertos))
    _CONEXION["r"] = r
    return r


def carpetas_movidas(perdidas):
    """{carpeta que ya no esta: donde esta hoy}. (19-nov, XV 8-nov) La persona mueve el evento terminado
    (D:\\XV 8 NOV -> D:\\TERMIANDO\\XV 8 NOV) y su proyecto de DaVinci queda todo en rojo: se busca la misma ruta uno o
    dos niveles mas adentro en su disco, o en otro disco (C: no). Solo se listan carpetas, nunca se recorre el disco."""
    import string
    perdidas = [d for d in perdidas if d and not os.path.isdir(d)]
    if not perdidas:
        return {}
    niveles = {}

    def bajo(r):                                # r y sus carpetas a uno y dos niveles
        if r not in niveles:
            out = [r]
            try:
                hijos = [os.path.join(r, x) for x in os.listdir(r)
                         if not x.startswith(("$", ".")) and x != "System Volume Information"]
            except OSError:
                hijos = []
            for h in hijos:
                if os.path.isdir(h):
                    out.append(h)
                    try:
                        out += [os.path.join(h, y) for y in os.listdir(h) if os.path.isdir(os.path.join(h, y))]
                    except OSError:
                        pass
            niveles[r] = out
        return niveles[r]
    if os.name == "nt":
        discos = [l + ":\\" for l in string.ascii_uppercase if l != "C" and os.path.isdir(l + ":\\")]
    else:
        discos = [os.path.join("/Volumes", v) for v in (os.listdir("/Volumes") if os.path.isdir("/Volumes") else [])]
    out = {}
    for d in perdidas:
        unidad, resto = os.path.splitdrive(d)
        if unidad:
            raiz = unidad + "\\"
        elif d.startswith("/Volumes/") and d.count("/") > 3:
            raiz = "/".join(d.split("/")[:3])
            resto = d[len(raiz):]
        else:
            continue
        resto = resto.strip("\\/")
        if not resto:
            continue
        for r in [raiz] + [x for x in discos if os.path.normcase(x) != os.path.normcase(raiz)]:
            b = next((b for b in bajo(r) if os.path.isdir(os.path.join(b, resto))), None)
            if b:
                out[d] = os.path.join(b, resto)
                break
    return out


def _carpetas_al_dia(movidas, log=print):
    """Las carpetas soltadas del estado que se movieron quedan apuntando a su sitio nuevo (rutas.fuentes)."""
    est = leer_estado()
    cambio = False
    nuevas = []
    for c in est.get("carpetas") or []:
        if isinstance(c, str) and not os.path.isdir(c):
            for viejo, nuevo in movidas.items():
                if os.path.normcase(viejo + os.sep).startswith(os.path.normcase(c.rstrip("\\/") + os.sep)):
                    cola = viejo[len(c.rstrip("\\/")):]
                    if nuevo.endswith(cola):
                        log("La carpeta del evento se movió: %s -> %s" % (c, nuevo[:len(nuevo) - len(cola)] or nuevo))
                        c, cambio = nuevo[:len(nuevo) - len(cola)] or nuevo, True
                        break
        nuevas.append(c)
    if cambio:
        est["carpetas"] = nuevas
        guardar_estado(est)


def reenlazar(project, log=print):
    """Vuelve a enlazar los clips del media pool cuyo archivo ya no esta en esa ruta (carpetas movidas o
    proyecto abierto en otra computadora / Mac). Los busca por nombre en 1 MATERIAL y PROGRAMA/recursos."""
    import re
    mp = project.GetMediaPool()
    perdidos = []

    # (17-nov, XV 8-nov) El material de OTRO evento no se reenlaza por nombre: los archivos se llaman igual en todos
    # («VIDEO VERTICAL 029 (FIESTA).MOV»), y los clips de la boda del 7-nov (su carpeta ya no estaba) quedaron
    # enlazados a los videos del XV: lineas de la boda con imagenes del XV, clips con el largo cambiado (huecos en
    # negro) y DaVinci colgado invalidando la cache. Solo se reenlaza lo del evento de ahora y lo que no es de ningun
    # evento (plantillas, musica, efectos).
    evento = str(leer_estado().get("evento") or "").strip().upper()
    de_eventos = ("VIDEO", "FOTOS", "DRON", "EVENTOS", "SECUENCIAS")

    def recorrer(f, camino=()):
        ajeno = len(camino) >= 2 and re.sub(r"^\d+\s+", "", camino[0]).upper() in de_eventos \
            and bool(evento) and camino[1].strip().upper() != evento
        if not ajeno:
            for c in f.GetClipList() or []:
                r = c.GetClipProperty("File Path") or ""
                if r and not os.path.exists(r):
                    perdidos.append((c, re.split(r"[\\/]", r)[-1]))
        for s in f.GetSubFolderList() or []:
            recorrer(s, camino + (s.GetName() or "",))
    recorrer(mp.GetRootFolder())
    if not perdidos:
        return 0
    n, total = 0, len(perdidos)
    # (1.5.7) archivos que se renombraron en su carpeta despues de importarlos: su nombre de hoy, por la lista de nombres
    renombres = nombres_de_hoy()
    quedan = []
    for c, nombre in perdidos:
        hoy = renombres.get(os.path.normcase(os.path.abspath(c.GetClipProperty("File Path") or "")))
        if hoy and os.path.exists(hoy):
            try:
                if c.ReplaceClip(hoy):
                    n += 1
                    continue
            except Exception:
                pass
        quedan.append((c, nombre))
    perdidos = quedan
    movidas = carpetas_movidas({os.path.dirname(c.GetClipProperty("File Path") or "") for c, _ in perdidos})
    if movidas:                                 # (19-nov) el evento se movio de carpeta: cada clip en su sitio nuevo
        quedan, por_carpeta = [], {}
        for c, nombre in perdidos:
            nueva = movidas.get(os.path.dirname(c.GetClipProperty("File Path") or ""))
            if nueva and os.path.exists(os.path.join(nueva, nombre)):
                por_carpeta.setdefault(nueva, []).append((c, nombre))
            else:
                quedan.append((c, nombre))
        for d, grupo in por_carpeta.items():
            for c, nombre in grupo:
                try:
                    n += bool(c.ReplaceClip(os.path.join(d, nombre)))
                except Exception:
                    pass
        perdidos = quedan
        _carpetas_al_dia(movidas, log)
    hay = {}
    for raiz in [rutas.MATERIAL, rutas.RECURSOS, rutas.AUDIO] + rutas.fuentes():
        for d, _, fs in os.walk(raiz):
            for x in fs:
                hay.setdefault(x.lower(), d)
    por_carpeta = {}
    for c, nombre in perdidos:
        if nombre.lower() in hay:
            por_carpeta.setdefault(hay[nombre.lower()], []).append((c, nombre))
    for d, grupo in por_carpeta.items():
        if mp.RelinkClips([c for c, _ in grupo], d):
            n += len(grupo)
            continue
        for c, nombre in grupo:                       # uno por uno si la carpeta completa no se pudo
            try:
                n += bool(c.ReplaceClip(os.path.join(d, nombre)))
            except Exception:
                pass
    log("Archivos reenlazados en DaVinci: %d%s" % (n, (" (faltan %d que no estan en las carpetas)" % (total - n))
                                                         if n < total else ""))
    return n


def instalar_fuentes(log=print):
    """Instala para el usuario (sin administrador) las fuentes de los titulos que falten:
    Windows: %LOCALAPPDATA%\\Microsoft\\Windows\\Fonts + registro HKCU. Mac: ~/Library/Fonts."""
    import shutil
    origen = {}                                  # nombre -> carpeta (las del programa y la con licencia guardada aparte)
    for d in rutas.carpetas_fuentes():
        for f in os.listdir(d):
            if f.lower().endswith((".ttf", ".otf")):
                origen.setdefault(f, d)
    if not origen:
        return 0
    archivos = sorted(origen)
    n = 0
    if rutas.ES_MAC:
        destino = os.path.expanduser("~/Library/Fonts")
        os.makedirs(destino, exist_ok=True)
        for f in archivos:
            if not os.path.exists(os.path.join(destino, f)):
                shutil.copy2(os.path.join(origen[f], f), os.path.join(destino, f))
                n += 1
    elif rutas.ES_WIN:
        import winreg
        sistema = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        destino = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")
        os.makedirs(destino, exist_ok=True)
        clave = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts")
        try:
            for f in archivos:
                if os.path.exists(os.path.join(sistema, f)) or os.path.exists(os.path.join(destino, f)):
                    continue
                shutil.copy2(os.path.join(origen[f], f), os.path.join(destino, f))
                nombre = os.path.splitext(f)[0].replace("-", " ")
                winreg.SetValueEx(clave, "%s (%s)" % (nombre, "OpenType" if f.lower().endswith(".otf") else "TrueType"),
                                  0, winreg.REG_SZ, os.path.join(destino, f))
                n += 1
        finally:
            winreg.CloseKey(clave)
        if n:
            try:
                import ctypes
                ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 0x0002, 1000, None)   # WM_FONTCHANGE
            except Exception:
                pass
    if n:
        log("Instale %d fuentes de los titulos. Si DaVinci estaba abierto, cierralo y vuelve a pulsar Play." % n)
    return n


def abrir_timeline(nombre):
    with CANDADO:
        r = _conexion_viva() or _dvr().scriptapp("Resolve")
        p = r.GetProjectManager().GetCurrentProject() if r else None
        if p is None:
            return False
        for i in range(1, p.GetTimelineCount() + 1):
            t = p.GetTimelineByIndex(i)
            if t.GetName() == nombre:
                r.OpenPage("edit")
                return bool(p.SetCurrentTimeline(t))
    return False


def cargar_perfiles():
    """{clave: perfil} de perfiles_evento.json (boda, xv, bautizo, graduacion, cumpleanos)."""
    try:
        with open(rutas.perfiles(), encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    except Exception:
        return {"xv": {"nombre": "XV años", "momentos": {"MAQUILLAJE": "Maquillaje", "IGLESIA": "Iglesia",
                                                        "FIESTA": "Fiesta"}}}


def aplicar_ruido(log, intensidad):
    """Cambia la intensidad de la reduccion de ruido en TODAS las timelines de eventos (no en las plantillas)."""
    import ruido
    if ruido.drx_activo(intensidad):                 # el ruido lo quita DaVinci con el ajuste guardado por la persona
        log("El ruido lo quita DaVinci con tu ajuste guardado: el cambio se aplica al volver a armar.")
        return {"tipo": "ruido", "clips": 0, "timelines": 0}
    with CANDADO:
        ruido.escribir(intensidad, os.path.join(rutas.DATOS, "dctl"))
        r = conectar_resolve(log)
        p = r.GetProjectManager().GetCurrentProject()
        if p.IsRenderingInProgress():
            log("AVISO: hay un render en curso; aplica la intensidad cuando termine.")
            return None
        p.RefreshLUTList()
        n_tl = n = 0
        clips = []                                   # (item, ruta del video): primero se juntan, luego se mide lo que falte
        for i in range(1, p.GetTimelineCount() + 1):
            t = p.GetTimelineByIndex(i)
            if t.GetName().startswith(("TRAILER XV", "CC ")):
                continue
            n_tl += 1
            for tr in range(1, t.GetTrackCount("video") + 1):
                for it in t.GetItemListInTrack("video", tr) or []:
                    if ruido.es_video(it):
                        clips.append((it, it.GetMediaPoolItem().GetClipProperty("File Path") or ""))
        medidas = {}
        if int(intensidad) > 0:                      # cada toma con el nivel que pide SU ruido (el mismo proceso para todas)
            try:
                import ruido_tomas
                medidas = ruido_tomas.medir_varios(sorted({(ruta, None) for _, ruta in clips if ruta}), log)
            except Exception as ex:
                log("Aviso: no pude medir el ruido de los videos (%s); van con el nivel normal." % ex)
        cuenta = {}
        for it, ruta in clips:
            medida = medidas.get(os.path.normcase(ruta))
            if ruido.aplicar_a_item(it, intensidad, medida):
                n += 1
                nv = ruido.nivel_para(medida, intensidad)
                cuenta[nv] = cuenta.get(nv, 0) + 1
        r.GetProjectManager().SaveProject()
        log("Reduccion de ruido %d (%s) aplicada a %d clips en %d timelines: %s." % (
            int(intensidad), ruido.nivel(intensidad), n, n_tl,
            ", ".join("%d %s" % (cuenta[k], ruido.NOMBRES[k]) for k in sorted(cuenta)) or "sin clips"))
        return {"tipo": "ruido", "clips": n, "timelines": n_tl}


def estado_ruido_davinci():
    """El ajuste de ruido de DaVinci guardado: {"hay", "fecha", "clip", "linea", "herramientas", "de_ruido"}."""
    import ruido
    return ruido.estado_davinci()


def capturar_ruido_davinci(log):
    """Guarda el grado del clip que DaVinci tiene bajo el cursor: ahi dejo la persona el ruido a su gusto (pagina
    Color). Al armar se aplica a todas las tomas. Devuelve lo mismo que estado_ruido_davinci()."""
    import ruido
    with CANDADO:
        if not resolve_abierto():
            raise RuntimeError("Abre DaVinci Resolve en el clip donde dejaste el ruido a tu gusto.")
        r = conectar_resolve(log, quedarse=True)     # (19-nov) el clip que la persona ajusto, en el proyecto donde esta
        p = r.GetProjectManager().GetCurrentProject()
        if p is not None and p.IsRenderingInProgress():
            raise RuntimeError("Hay un render en curso: guarda el ajuste cuando termine.")
        return ruido.capturar_de_resolve(r, log)


def quitar_ruido_davinci():
    import ruido
    ruido.quitar_davinci()
    return ruido.estado_davinci()


LEEME_EDITABLE = """PLANTILLAS DE LOS VIDEOS - %(evento)s

Cada archivo de esta carpeta es la plantilla de DaVinci de UN video, con el mismo nombre que el video
(VIDEO FINAL 1 MIN.drp es la de VIDEO FINAL 1 MIN.mov), tal como la armo el programa (cortes, color, textos,
musica, efectos de sonido y voz). Sirve para corregir lo que no te guste.
Doble clic en el .drp (o en DaVinci: Archivo > Importar proyecto): se abre un proyecto con SOLO esa linea de
tiempo y sus clips, ya con proxies (reproduce fluido) y la cache de render automatica.
Los videos estan al lado, en la carpeta VIDEO TERMINADO.

LO MAS RAPIDO: en el programa, boton "Editar en DaVinci" y elige el video.
  DaVinci cierra lo que tenga abierto y abre SOLO el proyecto de ese video, con su unica linea en Edicion.
  Cambia lo que quieras y pulsa "Renderizar lo editado" en el programa: saca el video de nuevo, con el
  audio a -14 LUFS, SIN volver a armarlo (tus cambios se conservan).
  Sale con la duracion de siempre (1, 3, 15 o 30 min). Si lo alargas o quieres otro tramo, pon marcas de
  entrada y salida (teclas I y O) en la linea: se renderiza lo que quede entre ellas.
  Ojo: el boton grande de play vuelve a armar desde cero y reemplaza lo que hayas cambiado a mano.

TAMBIEN EN DAVINCI: en el Administrador de proyectos, carpeta %(evento)s, hay un proyecto por video
  («%(evento)s - VIDEO FINAL 1 MIN»...), el mismo que el .drp de aqui.

EN OTRA COMPUTADORA: importa el .drp. Necesita el mismo material y los recursos del programa; si salen
  sin conexion, clic derecho > Volver a enlazar.
"""


def _etiqueta(nombre_linea):
    """«XV 2026-11-08 - VERTICAL 1min» o «... - VIDEO FINAL VERTICAL 1 MIN» (1.5.7) -> «VERTICAL 1min»."""
    return rutas.etiqueta_de(nombre_linea)


def lineas_del_evento(project, evento):
    """Las lineas armadas de un evento que siguen en DaVinci, en el orden 1, 3, 15, 30 min (primero las horizontales
    y luego las verticales). Solo las que arma el programa: una copia hecha a mano («... copia») no entra."""
    orden = {v: k for k, v in enumerate(VERSIONES)}
    orden.update({"%s %s" % (ETIQUETA_VERTICAL, v): k + len(VERSIONES) for k, v in enumerate(VERSIONES)})
    res = []
    for i in range(1, project.GetTimelineCount() + 1):
        t = project.GetTimelineByIndex(i)
        n = t.GetName() or ""
        if evento and n.startswith(evento + " - ") and _etiqueta(n) in orden:
            res.append((orden[_etiqueta(n)], t))
        elif evento and n.startswith(evento + " - PLANTILLA "):     # (18-nov) las de plantilla de referencia, al final
            res.append((100 + len(res), t))
    return [t for _, t in sorted(res, key=lambda x: x[0])]


def leeme_editable(evento):
    """El LEEME de la carpeta de plantillas del evento (EVENTO TERMINADO - <EVENTO>/PLANTILLAS DE LOS VIDEOS), si ya existe."""
    try:
        carpeta = rutas.plantillas_evento(evento)
        leeme = os.path.join(carpeta, "LEEME.txt")
        if os.path.isdir(carpeta):                       # (1.5.7) siempre el texto de hoy (.drp por video)
            with open(leeme, "w", encoding="utf-8") as f:
                f.write(LEEME_EDITABLE % {"evento": evento})
    except OSError:
        pass


def guardar_editable(resolve, tl, evento, log=None):
    """Deja la linea de ese video junto a el: EVENTO TERMINADO - <EVENTO>/PLANTILLAS DE LOS VIDEOS/VIDEO FINAL 1 MIN.drt,
    con un LEEME de como usarla. Devuelve la ruta o None."""
    try:
        carpeta = rutas.plantillas_evento(evento)
        os.makedirs(carpeta, exist_ok=True)
        ruta = os.path.join(carpeta, rutas.nombre_video(tl.GetName()) + ".drt")
        if not tl.Export(ruta, resolve.EXPORT_DRT):
            return None
        leeme_editable(evento)
        return ruta
    except Exception as ex:
        if log:
            log("Aviso: no se pudo guardar la plantilla editable de %s (%s)" % (tl.GetName(), ex))
        return None


def dejar_editable(resolve, project, evento, etiquetas=None):
    """Al terminar, DaVinci queda en la pagina Edicion con la linea del evento abierta (la mas corta de las que se
    acaban de hacer): lista para retocar. Devuelve su nombre o None."""
    try:
        lineas = lineas_del_evento(project, evento)
        if etiquetas:
            lineas = [t for t in lineas if _etiqueta(t.GetName()) in etiquetas] or lineas
        if not lineas or project.IsRenderingInProgress():
            return None
        project.SetCurrentTimeline(lineas[0])
        resolve.OpenPage("edit")
        return lineas[0].GetName()
    except Exception:
        return None


def traer_davinci_al_frente():
    """La ventana de DaVinci, delante (cuando la persona pide «Editar en DaVinci»)."""
    try:
        if rutas.ES_MAC:
            rutas.abrir_resolve()
            return
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        hallada = []

        def ver(h, _):
            if u.IsWindowVisible(h):
                t = ctypes.create_unicode_buffer(200)
                u.GetWindowTextW(h, t, 200)
                if t.value.startswith("DaVinci Resolve"):
                    hallada.append(h)
            return True
        u.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(ver), 0)
        if hallada:
            if u.IsIconic(hallada[0]):
                u.ShowWindow(hallada[0], 9)            # SW_RESTORE
            u.SetForegroundWindow(hallada[0])
    except Exception:
        pass


def abrir_editable(log, evento=None):
    """«Editar en DaVinci»: abre DaVinci (si hace falta) en la pagina Edicion con la linea del evento. Devuelve el
    nombre de la linea."""
    with CANDADO:
        evento = evento or leer_estado().get("evento")
        if not evento:
            raise RuntimeError("Todavía no hay ningún evento armado: pulsa ▶ primero.")
        resolve = conectar_resolve(log)
        project = resolve.GetProjectManager().GetCurrentProject()
        if project.IsRenderingInProgress():
            raise RuntimeError("DaVinci está renderizando: espera a que termine.")
        nombre = dejar_editable(resolve, project, evento)
        if not nombre:
            raise RuntimeError("No encuentro las líneas de %s en DaVinci: pulsa ▶ para armarlo." % evento)
    traer_davinci_al_frente()
    return nombre


def encolar_render(project, tl, evento):
    """Pone en la cola de render la linea TAL COMO ESTA ahora, quitando antes su trabajo anterior. Tramo: el que la
    persona haya marcado con entrada y salida (I / O) en la linea; sin marcas (lo normal: tras un render DaVinci no
    las conserva), la duracion de siempre de esa version (1, 3, 15 o 30 min) o hasta donde llegue la linea si la
    acorto. Las verticales salen del tamano de la linea. Devuelve True/False."""
    nombre = tl.GetName()
    salida = rutas.videos_terminados(evento)
    os.makedirs(salida, exist_ok=True)
    for job in project.GetRenderJobList() or []:
        if job.get("TimelineName") == nombre:
            project.DeleteRenderJob(job.get("JobId"))
    project.SetCurrentTimeline(tl)
    time.sleep(0.5)
    ajustes = {"SelectAllFrames": True, "TargetDir": salida, "CustomName": rutas.nombre_video(nombre)}
    try:
        marcas = (tl.GetMarkInOut() or {}).get("video") or {}
        ini, fin = tl.GetStartFrame(), tl.GetEndFrame() - 1
        if marcas.get("in") is not None and marcas.get("out") is not None and marcas["out"] > marcas["in"]:
            ajustes.update({"SelectAllFrames": False, "MarkIn": int(marcas["in"]), "MarkOut": int(marcas["out"])})
        else:
            seg = SEGUNDOS.get(_etiqueta(nombre).split(" ")[-1])
            if seg:
                fps = int(round(float(tl.GetSetting("timelineFrameRate") or 24)))
                ajustes.update({"SelectAllFrames": False, "MarkIn": ini, "MarkOut": min(fin, ini + seg * fps - 1)})
    except Exception:
        pass
    try:
        w, h = int(tl.GetSetting("timelineResolutionWidth")), int(tl.GetSetting("timelineResolutionHeight"))
    except Exception:
        w, h = 1920, 1080
    if h > w:
        ajustes.update({"FormatWidth": w, "FormatHeight": h})
    project.SetRenderSettings(ajustes)
    ok = bool(project.AddRenderJob())
    if h > w:                                    # la pagina Entrega vuelve al tamano horizontal de siempre
        project.SetRenderSettings({"FormatWidth": h, "FormatHeight": w})
    return ok


# (19-nov, la persona: «no me des tantas líneas de tiempo abiertas porque estresa... si yo abro una plantilla, tienes
# que cerrarme DaVinci y abrirme solo la plantilla con la que estoy trabajando para editar ese mismo video») Cada video
# tiene su PROPIO proyecto en DaVinci (carpeta <evento>, «<evento> - VIDEO FINAL 1 MIN», solo esa linea y sus clips: el
# mismo del .drp). «Editar en DaVinci» abre ese y nada mas; «Renderizar lo editado» saca el video desde ahi.
_PROYECTO_VIDEO = {"nombre": None}        # mientras se trabaja en el proyecto de un video, conectar_resolve lo acepta


def eventos_con_plantillas():
    """(19-nov, la persona: «debe de tirarme las plantillas que ya hay») [(evento, [videos])] de TODOS los eventos con
    plantillas (.drp en EVENTO TERMINADO - <evento>/PLANTILLAS DE LOS VIDEOS), aunque el de ahora no este terminado:
    primero el evento actual y luego los demas, del mas nuevo al mas viejo."""
    salida = []
    vistos = set()
    actual = leer_estado().get("evento")
    carpetas = []
    try:
        for f in os.listdir(rutas.SALIDA):
            p = os.path.join(rutas.SALIDA, f)
            if f.startswith(rutas.PREFIJO_TERMINADO) and os.path.isdir(os.path.join(p, rutas.PLANTILLAS_EVENTO)):
                carpetas.append((os.path.getmtime(p), f[len(rutas.PREFIJO_TERMINADO):]))
    except OSError:
        pass
    eventos = ([actual] if actual else []) + [e for _, e in sorted(carpetas, reverse=True)]
    for ev in eventos:
        clave = rutas.limpiar_nombre(ev).upper()
        if clave in vistos:
            continue
        vistos.add(clave)
        try:
            vids = videos_editables(ev)
        except Exception:
            vids = []
        if vids:
            salida.append((ev, vids))
    return salida


def videos_editables(evento):
    """Los videos del evento con su proyecto editable (.drp en PLANTILLAS DE LOS VIDEOS), en orden: horizontales por
    duracion, verticales y luego las plantillas."""
    import re
    carpeta = rutas.plantillas_evento(evento) if evento else ""
    por_video = {}
    try:
        # (19-nov) el mismo video con el nombre de antes («VIDEO FINAL 1 MIN») y el de hoy («... HORIZONTAL 1 MIN»):
        # queda solo el .drp mas nuevo (si no, el popup ponia dos «1 min» y uno era viejo)
        for f in os.listdir(carpeta):
            if f.lower().endswith(".drp") and not f.lower().endswith((" (nuevo).drp", ".nuevo.drp")):   # temporales
                n = os.path.splitext(f)[0]
                # (19-nov) solo los tráileres «VIDEO FINAL ...» se juntan por nombre viejo/nuevo; las plantillas
                # («PLANTILLA 1 VERTICAL - 2026-11-08») llevan « - » adentro y salian todas como una sola
                clave = rutas.nombre_video("%s - %s" % (evento, n)) if n.upper().startswith("VIDEO FINAL") else n
                t = os.path.getmtime(os.path.join(carpeta, f))
                if clave not in por_video or t > por_video[clave][0]:
                    por_video[clave] = (t, n)
    except OSError:
        pass
    nombres = [n for _, n in por_video.values()]
    est = leer_estado()                # (19-nov) + las lineas armadas del evento que aun no tienen .drp (se hace al abrir)
    if evento and est.get("evento") == evento:
        for t in est.get("timelines") or []:
            if t.startswith(evento + " - ") and rutas.nombre_video(t) not in por_video:
                por_video[rutas.nombre_video(t)] = (0, rutas.nombre_video(t))
                nombres.append(rutas.nombre_video(t))

    def orden(n):
        m = re.search(r"(\d+)", n)
        k = int(m.group(1)) if m else 0
        return (2 if n.upper().startswith("PLANTILLA") else 1 if "VERTICAL" in n.upper() else 0, k, n)
    return sorted(nombres, key=orden)


def _exportar_drp(pm, nombre, drp):
    """Exporta el proyecto encima de su .drp sin dejarlo a medias: primero a un temporal y luego lo cambia.
    (19-nov) DaVinci agrega «.drp» si el nombre no termina asi: «x.drp.nuevo» quedaba «x.drp.nuevo.drp» y el .drp
    nunca se actualizaba. Devuelve True/False."""
    tmp = os.path.splitext(drp)[0] + " (nuevo).drp"
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
        if pm.ExportProject(nombre, tmp, True) and os.path.exists(tmp):
            os.replace(tmp, drp)
            return True
    except OSError:
        pass
    return False


def _proyecto_de_video(pm, evento, video):
    """Nombre del proyecto del video en la carpeta del evento (el ultimo, si quedo uno con la hora detras)."""
    nombre = "%s - %s" % (rutas.limpiar_nombre(evento), video)
    lista = pm.GetProjectListInCurrentFolder() or []
    # (19-nov) el de la hora detras se hizo PORQUE el de siempre no se pudo borrar: ese es el nuevo
    otros = sorted(n for n in lista if n.startswith(nombre + " ("))
    return otros[-1] if otros else nombre


def abrir_proyecto_video(resolve, evento, video, log=print, marcar=True):
    """Guarda y cierra lo que haya abierto en DaVinci y abre SOLO el proyecto de ese video (si no esta en la base, se
    importa su .drp), con su linea en Edicion. marcar: queda apuntado para «Renderizar lo editado».
    Devuelve (proyecto, linea)."""
    pm = resolve.GetProjectManager()
    actual = pm.GetCurrentProject()
    if actual is not None and actual.IsRenderingInProgress():
        raise RuntimeError("DaVinci está renderizando: espera a que termine.")
    carpeta = rutas.limpiar_nombre(evento)
    if actual is not None and not _sin_titulo(actual.GetName()):
        pm.SaveProject()
    pm.GotoRootFolder()
    if carpeta not in (pm.GetFolderListInCurrentFolder() or []):
        pm.CreateFolder(carpeta)
    pm.OpenFolder(carpeta)
    nombre = _proyecto_de_video(pm, evento, video)
    p = actual if actual is not None and actual.GetName() == nombre else pm.LoadProject(nombre)
    vacio = p is not None and not p.GetTimelineCount()
    if vacio:                                # (19-nov, XV 8-nov) quedo a medias (DaVinci colgado): sin linea, se rehace
        log("El proyecto de %s quedó sin su línea: lo vuelvo a hacer." % video)
        p = None
    if p is None:
        drp = os.path.join(rutas.plantillas_evento(evento), video + ".drp")
        if vacio or not os.path.exists(drp):  # (19-nov) se hace ahora desde la linea de EVENTOS CINEMA
            pm.GotoRootFolder()
            todo = pm.LoadProject(PROYECTO)
            if not todo:
                raise RuntimeError("No encuentro el proyecto de «%s» ni el proyecto %s." % (video, PROYECTO))
            import editable
            linea = next((t.GetName() for t in lineas_del_evento(todo, evento)
                          if rutas.nombre_video(t.GetName()) == video), None)
            log("Haciendo el proyecto propio de %s..." % video)
            if not linea or not editable.proyecto_por_video(resolve, evento, [linea], log):
                raise RuntimeError("No encuentro la línea de «%s» en DaVinci: pulsa ▶ para armarlo." % video)
            pm.GotoRootFolder()
            pm.OpenFolder(carpeta)
            nombre = _proyecto_de_video(pm, evento, video)
        else:
            log("Importando el proyecto de %s en DaVinci..." % video)
            if not pm.ImportProject(drp, nombre):
                raise RuntimeError("DaVinci no pudo abrir el proyecto de «%s»." % video)
        p = pm.LoadProject(nombre)
        if p is None:
            raise RuntimeError("DaVinci no pudo abrir el proyecto de «%s»." % video)
    _PROYECTO_VIDEO.update({"nombre": p.GetName(), "carpeta": carpeta})
    try:                                        # (19-nov) material movido o renombrado: que no se abra en rojo
        cambio = reenlazar(p, log)
        try:                                    # (19-nov) y sus proxies, desde Videos/PROXIES TRAILER AUTOMATICO
            import editable
            cambio = editable.enlazar_proxies(p, log) or cambio
        except Exception as ex:
            log("Aviso: no se pudieron enlazar los proxies de %s (%s)" % (video, ex))
        if cambio:
            pm.SaveProject()
            drp = os.path.join(rutas.plantillas_evento(evento), video + ".drp")
            if os.path.exists(drp):
                _exportar_drp(pm, p.GetName(), drp)
    except Exception as ex:
        log("Aviso: no se pudieron volver a enlazar los archivos de %s (%s)" % (video, ex))
    lineas = [p.GetTimelineByIndex(i) for i in range(1, p.GetTimelineCount() + 1)]
    tl = next((t for t in lineas if rutas.nombre_video(t.GetName()) == video), lineas[0] if lineas else None)
    if tl is not None:
        if not (tl.GetName() or "").startswith(evento + " - "):   # (19-nov) los hechos antes del arreglo: «00»
            tl.SetName("%s - %s" % (evento, video))           # sin el nombre, el render no la encuentra
        p.SetCurrentTimeline(tl)
    resolve.OpenPage("edit")
    est = leer_estado()
    marcas = (est.get("marcas_ia") or {}).pop(tl.GetName(), None) if tl is not None else None
    if marcas:                                # (19-nov) los rojos «REVISAR (IA)» llegaron despues de hacer el proyecto
        try:
            import revision_ia
            n = revision_ia.marcar(tl, marcas[1], marcas[0])
            pm.SaveProject()
            drp = os.path.join(rutas.plantillas_evento(evento), video + ".drp")
            if os.path.exists(drp):
                _exportar_drp(pm, p.GetName(), drp)    # el .drp tambien los lleva
            log("%s: %d marcadores rojos «REVISAR (IA)»." % (video, n))
        except Exception as ex:
            log("Aviso: no se pudieron poner los marcadores de IA en %s (%s)" % (video, ex))
    est["proyecto_video"] = p.GetName()       # lo de segundo plano no la saca de aqui (conectar_resolve quedarse)
    if marcar:
        previos = est.get("editando") or [] if est.get("editando_evento") == evento else []
        est["editando"] = [v for v in previos if v != video] + [video]
        est["editando_evento"] = evento
    guardar_estado(est)
    return p, tl


def abrir_al_terminar(evento, log=print):
    """(19-nov) Al entregar, DaVinci NO queda en EVENTOS CINEMA con las lineas de todos los eventos: queda en el
    proyecto propio del primer video (el mas corto), con su unica linea en Edicion. Nunca rompe la entrega."""
    videos = videos_editables(evento)
    if not videos or not os.path.exists(os.path.join(rutas.plantillas_evento(evento), videos[0] + ".drp")):
        return None                           # sin su .drp (fallo hacerlo): no se rehace aqui, se queda como esta
    try:
        with CANDADO:
            abrir_proyecto_video(conectar_resolve(log, quedarse=True), evento, videos[0], log)
        log("DaVinci quedó en el proyecto de %s (solo esa línea)." % videos[0])
        return videos[0]
    except Exception as ex:
        log("Aviso: no pude dejar abierto el proyecto de %s (%s)" % (videos[0], ex))
        return None
    finally:
        _PROYECTO_VIDEO["nombre"] = None      # el proximo ▶ vuelve a EVENTOS CINEMA


def abrir_video_editable(log, video, evento=None):
    """«Editar en DaVinci» con un video elegido: solo su proyecto, nada mas abierto. Devuelve el nombre del video."""
    with CANDADO:
        evento = evento or leer_estado().get("evento")
        if not evento:
            raise RuntimeError("Todavía no hay ningún evento armado: pulsa ▶ primero.")
        try:
            abrir_proyecto_video(conectar_resolve(log, quedarse=True), evento, video, log)
        finally:
            _PROYECTO_VIDEO["nombre"] = None  # si no, el proximo ▶ armaria dentro del proyecto del video
    traer_davinci_al_frente()
    return video


def renderizar_videos_editados(log, evento, videos, paso=lambda pct, texto: None):
    """Saca cada video desde SU proyecto (lo retocado ahi) a VIDEO TERMINADO, lo termina como siempre (audio a -14
    LUFS, revision, MP4 las plantillas) y actualiza su .drp. Devuelve [(linea, ok, ruta)]."""
    import renderizar
    hechos = []
    try:
        for k, video in enumerate(videos):
            rutas.revisar_parada()
            with CANDADO:
                resolve = conectar_resolve(log, quedarse=True)
                p, tl = abrir_proyecto_video(resolve, evento, video, log)
                if tl is None or not encolar_render(p, tl, evento):
                    log("AVISO: %s no se pudo poner en la cola de render." % video)
                    continue
                etiqueta = _etiqueta(tl.GetName())
                resolve.GetProjectManager().SaveProject()
            base = 45 + int(50.0 * k / max(1, len(videos)))
            res = renderizar.renderizar(log, evento, lambda pct, texto: paso(base + int(pct * 0.5 / len(videos)), texto),
                                        [etiqueta])
            res = plantillas_a_mp4(res, log)
            hechos += res
            renderizar.poner_revision_ia(log)    # (19-nov) los rojos de ESTE video, en su linea (antes se pisaban)
            with CANDADO:
                resolve = conectar_resolve(log)
                pm = resolve.GetProjectManager()
                drp = os.path.join(rutas.plantillas_evento(evento), video + ".drp")
                if pm.GetCurrentProject().GetName() != _PROYECTO_VIDEO["nombre"]:   # nunca EVENTOS CINEMA entero
                    log("Aviso: DaVinci no quedó en el proyecto de %s: su .drp no se actualiza." % video)
                    continue
                pm.SaveProject()
                if _exportar_drp(pm, pm.GetCurrentProject().GetName(), drp):
                    log("Proyecto editable de %s actualizado." % video)
    finally:
        _PROYECTO_VIDEO["nombre"] = None
    return hechos


def renderizar_editado(log, avance=None, evento=None, videos=None):
    """«Renderizar lo editado»: saca de nuevo los videos del evento con las lineas TAL COMO ESTAN en DaVinci (lo que
    la persona haya retocado a mano), SIN volver a armar; masteriza el audio y actualiza la plantilla editable.
    videos: (19-nov) los que la persona eligio en la ventana, cada uno desde su proyecto (None = los apuntados).
    Devuelve lo mismo que armar_todo."""
    def paso(pct, texto):
        if avance:
            avance(pct, texto)
    with SinDormir():
        paso(5, "Abriendo DaVinci Resolve")
        log("== Conectando con DaVinci Resolve ==")
        with CANDADO:
            evento = evento or leer_estado().get("evento")
            if not evento:
                raise RuntimeError("Todavía no hay ningún evento armado: pulsa ▶ primero.")
            resolve = conectar_resolve(log, quedarse=True)     # (19-nov) sin cargar EVENTOS CINEMA para nada
            project = resolve.GetProjectManager().GetCurrentProject()
            if project.IsRenderingInProgress():
                raise RuntimeError("DaVinci ya está renderizando: espera a que termine.")
            est = leer_estado()
            hay = videos_editables(evento)
            if videos is not None:
                editando = [v for v in videos if v in hay]
            else:
                editando = [v for v in est.get("editando") or [] if v in hay
                            and est.get("editando_evento") in (None, evento)]
            lineas = []
            if not editando:
                if project.GetName() != PROYECTO:
                    resolve = conectar_resolve(log)
                    project = resolve.GetProjectManager().GetCurrentProject()
                lineas = lineas_del_evento(project, evento)
            if not lineas and not editando:
                raise RuntimeError("No encuentro las líneas de %s en DaVinci: pulsa ▶ para armarlo." % evento)
        if editando:                         # (19-nov) cada video desde su propio proyecto, el que la persona retoco
            libre, necesita = espacio_para_render([_etiqueta("%s - %s" % (evento, v)).split(" ")[-1] for v in editando])
            if libre < necesita:
                raise RuntimeError("No hay espacio para renderizar: quedan %.1f GB libres y hacen falta unos %.1f GB."
                                   % (libre, necesita))
            log("== Renderizando lo editado en su proyecto: %s ==" % ", ".join(editando))
            paso(45, "Renderizando")
            videos = renderizar_videos_editados(log, evento, editando, paso)
            paso(100, "Listo")
            marcar_terminado(evento, videos)
            return {"evento": evento, "videos": videos, "carpeta": rutas.carpeta_terminado(evento), "avisos": [],
                    "editado": True}
        with CANDADO:
            resolve = conectar_resolve(log)
            project = resolve.GetProjectManager().GetCurrentProject()
            libre, necesita = espacio_para_render([_etiqueta(t.GetName()).split(" ")[-1] for t in lineas])
            if libre < necesita:
                raise RuntimeError("No hay espacio para renderizar: quedan %.1f GB libres y hacen falta unos %.1f GB."
                                   % (libre, necesita))
            log("== Renderizando lo editado (sin volver a armar) ==")
            etiquetas = []
            for tl in lineas:
                if encolar_render(project, tl, evento):
                    etiquetas.append(_etiqueta(tl.GetName()))
                    guardar_editable(resolve, tl, evento, log)
                else:
                    log("AVISO: %s no se pudo poner en la cola de render." % tl.GetName())
            if "untitled" not in (project.GetName() or "").lower():      # guardar «Untitled Project» cuelga la API
                resolve.GetProjectManager().SaveProject()
        if not etiquetas:
            raise RuntimeError("DaVinci no aceptó ningún trabajo de render.")
        rutas.revisar_parada()               # (1.6.0) «Cancelar»
        paso(45, "Renderizando")
        import renderizar
        videos = renderizar.renderizar(log, evento, lambda pct, texto: paso(45 + int(pct * 0.5), texto), etiquetas)
        paso(100, "Listo")
        marcar_terminado(evento, videos)
        preparar_edicion(evento, log)
        renderizar.poner_revision_ia(log)             # (18-nov) la IA reviso mientras se hacian las plantillas
        abrir_al_terminar(evento, log)
        return {"evento": evento, "videos": videos, "carpeta": rutas.carpeta_terminado(evento), "avisos": [],
                "editado": True}


def estimar_segundos(n_videos, gb, versiones=None, verticales=None, render=True, nuevos=None):
    """(1.5.7, la persona: «que me diga en cuánto tiempo va a estar listo») Cuanto tarda TODO, aproximado, medido en la
    boda del 7-nov (73 videos, 29 GB, las 4 versiones y el vertical de 1 min: analisis 7 min, IA 5, armado 9, render 25,
    masterizado y revision 6, proxies y plantillas 6): ~60 min. nuevos = videos sin analizar todavia."""
    versiones = list(VERSIONES) if versiones is None else list(versiones)
    verticales = ["1min"] if verticales is None else list(verticales)
    nuevos = n_videos if nuevos is None else nuevos
    parte_nueva = nuevos / float(max(1, n_videos))
    s = 30.0 + nuevos * 3.0 + gb * 8.0 * parte_nueva                     # analisis (lo ya medido no se repite)
    s += nuevos * 2.5                             # la IA local mira cada toma (18-nov, XV 8-nov: 129 tomas en 258 s)
    s += gb * 20.0 * parte_nueva                  # y la revisa cuadro por cuadro, uno cada 3 s (18-nov, XV 8-nov, 45 GB:
    #                                               14 min con 4 preguntas a la vez y sin lo ya descartado; antes 29)
    # (18-nov) medido con el estabilizador en la GPU: 1 min + 15 min = 186 s la primera vez (antes 328)
    armado = {"1min": 35, "3min": 45, "15min": 120, "30min": 220}
    s += sum(armado.get(v, 60) for v in versiones) + 35 * len(verticales) + n_videos * 0.3
    if render:
        dur = sum(SEGUNDOS.get(v, 60) for v in versiones) + sum(SEGUNDOS.get(v, 60) for v in verticales)
        n = len(versiones) + len(verticales)
        s += dur * 0.5 + n * 40 + dur * 0.05                              # render, masterizado y revision con IA
        s += gb * 8.0 * parte_nueva + n * 30                              # proxies y una plantilla por video
    return s


def texto_tiempo(segundos):
    """«unos 45 min (listo a las 17:40)»."""
    m = max(1, int(round(segundos / 60.0)))
    hora = time.strftime("%H:%M", time.localtime(time.time() + segundos))
    return ("unos %d min" % m if m < 90 else "unas %.1f h" % (m / 60.0)) + " (listo a las %s)" % hora


def preparar_edicion(evento, log=print, solo=None):
    """(1.5.7) Con los videos ya entregados: proxies de todo el material y cache de render (editar con fluidez) y una
    plantilla por video (.drp con SOLO esa linea) en EVENTO TERMINADO/PLANTILLAS DE LOS VIDEOS, en lugar del .drt. Al
    final DaVinci queda otra vez en EVENTOS CINEMA, en Edicion, con la linea del evento abierta. Nunca rompe la entrega.
    solo: (19-nov) las lineas que se acaban de renderizar: el proyecto de las demas NO se rehace (ahi puede haber
    retoques de la persona, que ahora viven solo en el proyecto de cada video)."""
    if not evento:
        return
    import editable
    import vigia_davinci
    desde = time.time()

    def hacer():
        with CANDADO:
            resolve = conectar_resolve(log)
            project = resolve.GetProjectManager().GetCurrentProject()
            editable.proxies_y_cache(project, log)
            lineas = [t.GetName() for t in lineas_del_evento(project, evento)
                      if solo is None or t.GetName() in solo]
            for drp in editable.proyecto_por_video(resolve, evento, lineas, log, desde=desde):
                drt = os.path.splitext(drp)[0] + ".drt"          # la plantilla es el .drp: no quedan dos
                if os.path.exists(drt):
                    os.remove(drt)
            est = leer_estado()                  # proyectos por video recien hechos: nada retocado todavia
            est.update({"editando": [], "editando_evento": evento})
            guardar_estado(est)
            project = resolve.GetProjectManager().GetCurrentProject()
            dejar_editable(resolve, project, evento)
    try:                    # (18-nov) aqui DaVinci se colgo 10 min: el vigia lo cierra y se intenta otra vez
        vigia_davinci.reintentar(hacer, "plantillas por video", veces=3, log=log, tope=None)
    except Exception as ex:
        log("Aviso: no se pudieron preparar los proxies y las plantillas por video (%s)" % ex)


def calentar_ia():
    """(1.8.2) Carga ya el modelo de la IA local en la tarjeta (y el servidor rapido de Ollama) en otro hilo, mientras
    se miden los videos: cuando el analisis llega a la IA, no espera a que el modelo se cargue."""
    def correr():
        try:
            import vision_ia
            vision_ia.en_gpu()
        except Exception:
            pass
    threading.Thread(target=correr, name="calentar_ia", daemon=True).start()


def preanalizar(log=print):
    """(1.8.2, la persona: «aplica todo»: analizar mientras se espera) El analisis entero (medidas, IA local, oido,
    personas) en cuanto se suelta la carpeta, mientras la persona escribe el nombre y elige las versiones. Toma el
    mismo CANDADO que el armado: si pulsa «Empezar» antes de que termine, el armado espera y despues no repite nada
    (todo queda guardado). Devuelve el analisis, o None si el motor estaba ocupado o no hay material."""
    if os.environ.get("TRAILER_PREANALISIS") == "0":
        return None
    if not CANDADO.acquire(timeout=1):
        return None
    try:
        calentar_ia()
        esperar_copias(log)
        return am.analizar(BASE, log=log)
    finally:
        CANDADO.release()


def armar(log, evento="", solo=None, seco=False, nombre_xv="", fecha_lugar="", frase="", tipo_evento="xv",
          ruido=None, igualar=True, voz=None, verticales=True, formato="horizontal", solo_analisis=False):
    """Analiza el material y lo arma en las plantillas. Devuelve el reporte.
    voz: {"1min": bool, "3min": bool, "15min": bool} = en que versiones va la voz original (None = lo de siempre:
    activada en la de 15 min; en la de 30 min va siempre).
    formato: "horizontal" (16:9; entran los videos horizontales y, con verticales=True, tambien los verticales) o
    "vertical" (9:16 para celular, con las mismas duraciones: SOLO los videos grabados en vertical)."""
    vertical = str(formato or "").lower().startswith("v")
    with CANDADO:
        t0 = time.time()
        log("== Analizando material ==")
        if not seco:
            calentar_ia()                     # (1.8.2) el modelo se carga mientras se mide
        esperar_copias(log)
        analisis = am.analizar(BASE, log=log)
        if not analisis.get("items"):
            log("No hay material para armar.")
            return None
        if not seco:                          # (1.5.7) nombres con tipo y momento, en su carpeta; capturas si no hay fotos
            if renombrar_material(analisis, log):
                analisis = am.analizar(BASE, log=log)      # ya medido: solo se ordena de nuevo, con los nombres nuevos
            fotos = sum(1 for i in analisis["items"] if i["tipo"] == "foto" and not i.get("descartar"))
            if fotos < FOTOS_INTRO and capturas_intro(analisis, FOTOS_INTRO - fotos, log):
                analisis = am.analizar(BASE, log=log)      # solo se miden las capturas nuevas
        usables = [i for i in analisis["items"] if i["tipo"] != "foto" and not i.get("descartar")
                   and i.get("dur", 0) - sum(b - a for a, b in i.get("oscuros") or []) > 3]
        if not usables:                       # todos dañados, en negro o de menos de 3 s: el trailer saldria en negro
            raise RuntimeError("No hay videos que se puedan usar (dañados, en negro o muy cortos). Revisa los videos que soltaste: "
                               + "; ".join(a for a in analisis.get("avisos", [])[:2]))
        if vertical and all(i.get("horizontal", True) for i in usables):
            raise RuntimeError(SIN_VERTICALES)
        if sum(1 for i in analisis["items"] if i["tipo"] == "foto" and not i.get("descartar")) < MINIMOS["foto"]:
            log("Aviso: hay menos de %d fotos que se puedan leer: la intro repetira fotos." % MINIMOS["foto"])
        resumen = _resumen(analisis["items"])
        if not seco and (ruido is None or int(ruido) > 0):
            try:                              # (1.8.1) el ruido de cada video se mide en segundo plano desde ya
                import ruido_tomas
                # primero las que el armado prefiere (las de la festejada y las mas bonitas segun la IA)
                orden = sorted(usables, key=lambda i: (not i.get("prota"),
                                                       -float(((i.get("ia") or {}).get("belleza")) or 0)))
                n_r = ruido_tomas.adelantar([(i["ruta"], i.get("dur")) for i in orden
                                             if vertical is False or not i.get("horizontal", True)])
                if n_r:
                    log("Midiendo en segundo plano el ruido de %d videos (para la reducción de ruido)." % n_r)
            except Exception as ex:
                log("Aviso: no se pudo adelantar la medida del ruido (%s)" % ex)
        previo = None
        try:                                  # el plan se ve ya, antes de abrir DaVinci (y aunque DaVinci falle)
            log("== Plan previo ==")
            previo = plan_previo(analisis, log, solo=solo, tipo_evento=tipo_evento, evento=evento,
                                 verticales=verticales, formato=formato)
            if not vertical:
                guardar_plan(previo)
            elif previo is not None and not previo.get("versiones"):   # no alcanza el video vertical: ni se abre DaVinci
                return None
        except Exception as ex:
            log("Aviso: no pude calcular el plan previo (%s)" % ex)
        if solo_analisis:
            # (1.8.2, la persona: «solo plantillas 1, 2, 3, 4») sin versiones del programa: el analisis, los nombres y
            # el evento quedan listos; las plantillas de referencia se arman despues (armar_plantillas_ref)
            ev = evento or (previo or {}).get("evento")
            if not ev:                        # sin plan: el mismo nombre que le pondria build_trailers
                pf = (cargar_perfiles() or {}).get(tipo_evento) or {}
                ev = "%s %s" % (pf.get("prefijo") or tipo_evento.upper(), analisis.get("fecha") or time.strftime("%Y-%m-%d"))
            est = leer_estado()
            est.update({"huella": analisis["huella"], "evento": ev, "armado": time.strftime("%Y-%m-%d %H:%M"),
                        "timelines": [], "resumen_versiones": []})
            guardar_estado(est)
            log("Material analizado y ordenado para las plantillas (%.0f s)." % (time.time() - t0))
            return {"evento": ev, "versiones": [], "material": resumen, "seco": False}
        log("== Conectando con DaVinci Resolve ==")
        instalar_fuentes(log)
        resolve = conectar_resolve(log)
        reenlazar(resolve.GetProjectManager().GetCurrentProject(), log)
        log("== %s ==" % ("Plan (prueba en seco)" if seco else "Armando timelines"))
        ruta = rutas.codigo("build_trailers.py")
        g = {"__name__": "build_trailers", "resolve": resolve, "BASE": BASE, "ANALISIS": analisis,
             "EVENTO": evento or None, "SOLO": solo or None, "REHACER": True, "DRY_RUN": seco,
             "NOMBRE_XV": nombre_xv, "FECHA_LUGAR": fecha_lugar, "FRASE": frase, "TIPO_EVENTO": tipo_evento,
             "RUIDO": ruido, "IGUALAR": bool(igualar), "VOZ": voz if isinstance(voz, dict) else None,
             "VERTICALES": bool(verticales), "FORMATO": "vertical" if vertical else "horizontal",
             "print": lambda *a, **k: log(" ".join(str(x) for x in a))}
        with open(ruta, encoding="utf-8") as f:
            exec(compile(f.read(), ruta, "exec"), g)
        rep = g.get("result") or {}
        rep["material"] = resumen
        rep["seco"] = seco
        if not seco:
            est = leer_estado()
            lineas = [v["timeline"] for v in rep.get("versiones", [])]
            if vertical:                      # se suman a las horizontales de este mismo evento
                otras = [t for t in est.get("timelines") or [] if est.get("evento") == rep.get("evento")
                         and not _etiqueta(t).startswith(ETIQUETA_VERTICAL)]
                est.update({"huella": analisis["huella"], "evento": rep.get("evento"),
                            "armado": time.strftime("%Y-%m-%d %H:%M"), "timelines": otras + lineas,
                            "resumen_versiones_vertical": rep.get("versiones", [])})
            else:
                est.update({"huella": analisis["huella"], "evento": rep.get("evento"),
                            "armado": time.strftime("%Y-%m-%d %H:%M"), "timelines": lineas,
                            "resumen_versiones": rep.get("versiones", [])})
            guardar_estado(est)
            leeme_editable(rep.get("evento") or "")
            if rep.get("versiones"):          # DaVinci queda en Edicion con el evento abierto: listo para retocar
                dejar_editable(resolve, resolve.GetProjectManager().GetCurrentProject(), rep.get("evento"),
                               [_etiqueta(v["timeline"]) for v in rep["versiones"]])
        log("Listo en %.0f s." % (time.time() - t0))
        return rep


def plantillas_a_mp4(videos, log=print):
    """(19-nov, la persona: «entrégame las 4 plantillas en MP4») Los videos de plantilla («PLANTILLA 1 VERTICAL - ...») pasan
    de .mov a .mp4 SIN volver a comprimir (solo video y audio: la pista de codigo de tiempo de DaVinci no entra en MP4 y
    con ella salia un archivo vacio). Devuelve la lista con las rutas nuevas."""
    import subprocess
    out = []
    for n, ok, r in videos:
        if ok and r and r.lower().endswith(".mov") and os.path.basename(r).upper().startswith("PLANTILLA "):
            mp4 = os.path.splitext(r)[0] + ".mp4"
            # (19-nov, visto) al rearmar, el MP4 de antes podia estar abierto (reproductor, revision): se escribe
            # aparte y se cambia al final, con reintentos
            tmp = os.path.splitext(r)[0] + ".nuevo.mp4"
            p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", r, "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy",
                                "-tag:v", "hvc1", "-movflags", "+faststart", tmp], capture_output=True, timeout=600,
                               creationflags=rutas.SIN_VENTANA)
            listo = p.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 1024 * 1024
            for _i in range(10 if listo else 0):
                try:
                    os.replace(tmp, mp4)
                    break
                except OSError:
                    time.sleep(1)
            else:
                listo = False
            if listo:
                try:
                    os.remove(r)                 # el .mov lo hizo el programa: queda solo el MP4
                except OSError:
                    pass
                log("En MP4: %s" % mp4)
                r = mp4
            else:
                log("Aviso: no se pudo pasar a MP4 %s (queda el .mov; %s)" % (
                    os.path.basename(r), (p.stderr or b"").decode("utf-8", "replace").strip()[-200:] or "el MP4 de antes está abierto"))
        out.append((n, ok, r))
    return out


def armar_plantillas_ref(evento, tipo_evento, log=print):
    """(18-nov) Las plantillas de referencia elegidas en Material (estado plantillas_ref): una linea por cada una
    (armar_ref.armar), con su render en cola. Devuelve sus etiquetas («PLANTILLA 1»...) para renderizar."""
    est_ = leer_estado()
    elegidas = [n for n in est_.get("plantillas_ref") or []]
    if not elegidas or not evento:
        return []
    import plantilla_ref
    import armar_ref
    try:                                     # (1.8.7) cada plantilla con tomas distintas a las otras
        armar_ref.reiniciar_variedad()
    except Exception:
        pass
    infos = {p["nombre"]: p for p in plantilla_ref.lista()}
    # (19-nov, visto en la Plantilla 1: un plano de suelo y sillas) am.leer_ultimo() es el RESUMEN de la ventana: sin la
    # «vista» de cada medio segundo el planificador no aplicaba NINGUN filtro por tramo (enfoque, temblor, lo que vio
    # la IA): las 45 tomas de la boda salian sin medidas. El analisis completo, como el resto del armado.
    try:
        with open(am._cache_ruta(), encoding="utf-8") as f:
            j = json.load(f)
        analisis = {"items": j.get("items") or [], "fecha": j.get("fecha")}
    except (OSError, ValueError):
        analisis = am.leer_ultimo()
    log("== Plantillas: %s ==" % ", ".join(elegidas))
    etiquetas = []
    with CANDADO:
        r = conectar_resolve(log)
        p = r.GetProjectManager().GetCurrentProject()
        for n in elegidas:
            if n not in infos:
                log("AVISO: la plantilla «%s» ya no está; se salta." % n)
                continue
            try:
                # (19-nov, la persona: «todas las plantillas tienen que estar en esa misma carpeta para no perder el
                # orden... plantilla 1, plantilla 2... con las fechas»): junto a los demas videos del evento,
                # EVENTO TERMINADO - <evento>/VIDEO TERMINADO/PLANTILLA 1 VERTICAL - 2026-11-15.mp4 (y su .drp en
                # PLANTILLAS DE LOS VIDEOS, como los demas: preparar_edicion)
                destino = rutas.videos_terminados(evento)
                etiquetas.append(rutas.etiqueta_de(armar_ref.armar(
                    r, p, infos[n], evento, analisis, destino, tipo_evento, log,
                    nombre_xv=est_.get("nombre_xv") or "", frase=est_.get("frase") or "",
                    con_texto=est_.get("plantillas_texto", True) is not False,
                    con_destellos=est_.get("plantillas_destellos", True) is not False,
                    con_fundidos=est_.get("plantillas_fundidos", True) is not False)))
            except Exception as ex:
                log("AVISO: no se pudo armar la plantilla «%s» (%s)" % (n, ex))
    return etiquetas


def armar_todo(log, avance=None, render=True, vertical=None, horizontal=True, **op):
    """(18-nov) _armar_todo con el vigia de DaVinci: si DaVinci se congela (no responde y no hace nada 15 s) el vigia
    lo cierra y se arma otra vez desde el principio (el analisis ya esta guardado: solo se repite lo de DaVinci)."""
    import vigia_davinci
    try:                                    # (18-nov) programas pesados fuera (con la X, nunca a la fuerza): la IA y el
        import liberar                      # render iban hasta 4 veces mas lentos con la memoria de video llena
        liberar.cerrar(log)
    except Exception as ex:
        log("Aviso: no se pudieron cerrar los programas pesados (%s)" % ex)
    return vigia_davinci.reintentar(
        lambda: _armar_todo(log, avance, render, vertical, horizontal, **dict(op)), "armado", veces=2, log=log,
        tope=None)


def _armar_todo(log, avance=None, render=True, vertical=None, horizontal=True, **op):
    """El boton Play: analiza, arma las versiones en DaVinci, renderiza, masteriza el audio y mide la imagen.
    op["solo"] = versiones del formato horizontal (None = todas); horizontal=False = ninguna.
    vertical = ["1min", ...] versiones del formato vertical (9:16, solo videos verticales); None o [] = ninguna.
    avance(pct, texto). Devuelve {"evento", "videos": [(nombre, ok, ruta)], "carpeta", "avisos": [lo que el formato
    vertical no pudo armar]}. Las lineas quedan en DaVinci, editables (ver renderizar_editado y guardar_editable)."""
    def paso(pct, texto):
        if avance:
            avance(pct, texto)
    # (1.8.2, la persona: «solo plantillas 1, 2, 3, 4») ni versiones horizontales ni verticales y si plantillas de
    # referencia elegidas: solo se arman esas (antes salian tambien las 4 versiones del programa)
    solo_ref = not horizontal and not vertical and bool(leer_estado().get("plantillas_ref"))
    pases = [] if solo_ref else ([("horizontal", op.get("solo"))] if horizontal or not vertical else [])
    if vertical:
        pases.append(("vertical", [v for v in VERSIONES if v in vertical]))
    auto_vertical = op.pop("auto_vertical", True)
    est = leer_estado()                      # (19-nov) se rearma: las lineas cambian y los proyectos por video viejos
    est.update({"editando": [], "editando_evento": None, "proyecto_video": None,      # ya no valen hasta el render
                "marcas_ia": {}})
    if est.get("terminado") and est.get("terminado") == est.get("evento"):
        est["terminado"] = ""                # «Editar» / «Renderizar lo editado» vuelven cuando salgan los videos
    guardar_estado(est)
    with SinDormir():                        # una suspension a media render deja el trabajo colgado
        paso(3, "Revisando el material")
        evento, etiquetas, pedidas, avisos = None, [], [], []
        for n, (formato, solo) in enumerate(pases):
            rutas.revisar_parada()               # (1.6.0) «Cancelar»
            if formato == "vertical":
                log("== Formato vertical (9:16): solo videos verticales ==")
                if n:
                    paso(30, "Armando el formato vertical")
            try:
                rep = armar(log, **dict(op, solo=solo, formato=formato))
            except RuntimeError as ex:
                if formato == "vertical" and etiquetas:      # lo horizontal ya quedo armado: no se pierde
                    log("AVISO: %s" % ex)
                    avisos.append(str(ex))
                    continue
                raise
            if not rep or not rep.get("versiones"):
                if formato == "vertical":
                    if etiquetas:
                        log("AVISO: el formato vertical no se armo: falta video grabado en vertical.")
                        avisos.append(SIN_VERTICALES)
                        continue
                    raise RuntimeError(SIN_VERTICALES)
                raise RuntimeError("No se armo ninguna version (revisa que haya fotos y videos en el material).")
            evento = evento or rep.get("evento")
            etiquetas += [_etiqueta(v["timeline"]) for v in rep["versiones"]]
            pedidas += [_etiqueta(v["timeline"]).split(" ")[-1] for v in rep["versiones"]]
            if formato == "vertical":            # versiones que se quedaron sin armar por falta de video vertical
                avisos += [a for a in rep.get("avisos") or [] if "no se arma" in a]
            # (1.5.7, la persona: «si hay videos verticales, automáticamente activas las plantillas verticales de un
            # minuto») aunque no se haya pedido el formato vertical
            if formato == "horizontal" and auto_vertical and not any(f == "vertical" and "1min" in (s or [])
                                                                     for f, s in pases):
                verticales = [i for i in (am.leer_ultimo().get("items") or []) if i.get("tipo") == "video"
                              and not i.get("horizontal", True) and not i.get("descartar")]
                if verticales:
                    log("Hay %d videos verticales: se arma tambien el VERTICAL 1 min." % len(verticales))
                    pases.append(("vertical", ["1min"]))
        if solo_ref:                             # (1.8.2) solo plantillas: el analisis y el evento, sin versiones
            rep = armar(log, **dict(op, solo=None, formato="horizontal", solo_analisis=True))
            if not rep:
                raise RuntimeError("No hay material para armar las plantillas.")
            evento = rep.get("evento")
            paso(20, "Armando las plantillas")
        etiquetas += armar_plantillas_ref(evento, op.get("tipo_evento", "xv"), log)      # (18-nov) las de Material
        salida = {"evento": evento, "videos": [], "carpeta": rutas.carpeta_terminado(evento) if evento else rutas.SALIDA,
                  "avisos": avisos}
        if not render:
            paso(100, "Armado en DaVinci")
            log("== Terminado: armado en DaVinci, sin renderizar ==")     # (18-nov) el fin de verdad, para avance.py
            return salida
        libre, necesita = espacio_para_render(pedidas)
        if libre < necesita:
            raise RuntimeError("No hay espacio para renderizar: quedan %.1f GB libres y hacen falta unos %.1f GB. "
                               "Las timelines ya quedaron armadas en DaVinci." % (libre, necesita))
        rutas.revisar_parada()               # (1.6.0) «Cancelar»
        paso(45, "Renderizando")
        import renderizar
        salida["videos"] = renderizar.renderizar(
            log, evento, lambda pct, texto: paso(45 + int(pct * 0.5), texto), etiquetas)
        salida["videos"] = plantillas_a_mp4(salida["videos"], log)      # (19-nov) las de plantilla, en MP4
        marcar_terminado(evento, salida["videos"])
        paso(97, "Proxies y plantillas para editar")
        preparar_edicion(evento, log, solo=[v[0] for v in salida["videos"] or []])
        renderizar.poner_revision_ia(log, paso)      # (18-nov) la IA reviso mientras se hacian las plantillas
        abrir_al_terminar(evento, log)               # (19-nov) solo el proyecto del primer video, nada mas abierto
        paso(100, "Listo")
        ok = [v for v in salida["videos"] if v[1]]
        log("== Terminado: %d de %d videos ==" % (len(ok), len(salida["videos"])))
        for v in salida["videos"]:
            log("  %s %s" % ("OK   " if v[1] else "FALLO", v[2] if len(v) > 2 and v[2] else v[0]))
        return salida
