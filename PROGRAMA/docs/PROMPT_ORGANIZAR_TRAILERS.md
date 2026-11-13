# PROMPT PARA QUE LA IA ORGANICE EL TRÁILER DE XV

Copia todo lo que está debajo de la línea y pégalo en Claude (con DaVinci Resolve conectado). Cambia lo que está entre [CORCHETES].

---

Eres editor de video profesional de tráilers de XV años. Trabaja en DaVinci Resolve Studio, proyecto **EVENTOS CINEMA**, usando la plantilla ya armada (timeline "TRAILER XV 4 - Dua Lipa": 1920x1080, 24 fps) y la skill **trailer-xv-auto**. Cada versión usa estas pistas: V1 VIDEOS, V2 FOTOS INTRO, V3 TEXTOS, V4 AJUSTE, V5 TITULOS, V6 EFECTOS · A1 VOZ NATURAL, A2–A3 MUSICA, A4 MUSICA INTRO, A5–A9 SFX.

## Datos del evento
- Quinceañera: [NOMBRE]
- Fecha y lugar: [FECHA] en [LUGAR]
- Estilo: [elegante / romántico / fiesta / cinematográfico]
- Título que debe aparecer: "MIS XV" + [NOMBRE]

## Material
- Fotos de intro: `Escritorio\TRAILER XV AUTOMATICO\1_FOTOS_INTRO`
- Videos: `Escritorio\TRAILER XV AUTOMATICO\2_VIDEOS`
- Música y efectos: ya están en el media pool (carpetas MUSICA y EFECTOS).

## Lo que debes hacer, en este orden
1. **Inventario.** Lista todas las fotos y videos con nombre, duración y resolución. Avisa si algo está dañado, vertical o con otro fps.
2. **Clasificación.** Agrupa cada video por momento del evento: preparativos, llegada, ceremonia o misa, entrada, vals, momentos con familia, fiesta y baile, cierre. Si no puedes ver el contenido, usa el nombre del archivo, la fecha de creación y la duración; dime qué no pudiste clasificar y cómo lo trataste.
3. **Plan de cada versión** (muéstramelo en una tabla antes de armar y espera mi OK):
   - **1 minuto**: ritmo medio, cortes de 1.2 a 2.5 s, un pequeño arco en 3 actos (intro, romántica, fiesta). Look cine teal orange.
   - **3 minutos**: historia con 4 actos (intro, épica y ceremonia, romántica, fiesta), cortes de 2 a 4.5 s con pausas largas en los momentos románticos. Look romántico cálido.
   - **15 minutos**: recuerdo resumido en orden cronológico (intro, épica y llegada, ceremonia y romántica, fiesta), cortes de 3 a 7 s. Look film Kodak 2383.
   - **30 minutos**: versión larga tipo recuerdo completo, mismos actos que la de 15 min, cortes de 4 a 10 s, dejando respirar los momentos importantes. Look natural suave.
4. **Reglas obligatorias.**
   - Los **primeros 5 segundos** de cada versión son la **intro hecha solo con fotos** (5 fotos de 1 s, con el título de entrada de la plantilla).
   - Cada versión debe ser **completamente diferente**: otra música, otro look, otras fotos de intro, otros planos y otro orden. No repitas el mismo trozo de video entre versiones; si falta material, dime cuántos planos tendrías que repetir (en las de 15 y 30 minutos se acepta repetir si no alcanza, pero avísame).
   - Los mejores planos (primer baile, abrazos, entrada) van en la versión que más los aproveche, no en todas.
   - Termina cada versión con el texto final (fecha y lugar) y un cierre de audio limpio.
   - Respeta la plantilla: no borres títulos ni efectos, y usa cada pista según su nombre.
   - Música por actos (ya definida en la skill; cámbiala si quieres): 1 min con "Perfect" y el "Mix variado"; 3 min con "Forza", "Yo te extrañaré" y el "Mix variado"; 15 y 30 min con "Forza", "No crezcas", "Un pacto", "Yo te extrañaré", "Perfect" y el "Mix variado".
5. **Armado.** Con mi OK, usa la skill **trailer-xv-auto**: el programa `trailer_xv.py` (`--seco` y luego `--una-vez`) duplica mis 4 plantillas y llena las zonas de los marcadores FOTOS, MAQUILLAJE, IGLESIA y FIESTA. Si algo cae en el momento equivocado, corrige `CLASIFICACION_EVENTO.json`. Ajusta a mano lo que el programa no pueda (clips de la plantilla que pasan de la duración, mezcla de audio, SFX en los golpes de música).
6. **Revisión.** Revisa que cada timeline dure exactamente lo pedido, que la intro sean fotos en V2 en los primeros 5 s, que no haya clips offline y que la música no se corte de golpe. Dame un resumen por versión con la lista de planos usados.

## Entrega
- Timelines dentro del proyecto EVENTOS CINEMA, con nombre "TRAILER XV - 1min", "TRAILER XV - 3min", "TRAILER XV - 15min" y "TRAILER XV - 30min".
- Renders en cola hacia `Escritorio\TRAILER XV AUTOMATICO\5_SALIDA`.
- Un resumen corto con lo que quedó pendiente.
