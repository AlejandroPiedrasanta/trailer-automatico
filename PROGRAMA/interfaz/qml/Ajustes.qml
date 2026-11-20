// (1.7, parte 4) Pagina Ajustes: Video, Voz y ruido arriba; Inteligencia, Disco y Programa abajo (como la maqueta).
// Python (PaginaQML) pone d = {interruptores: [{clave, texto, si}], voz: [{clave, texto, si}], ruido, ia: {texto, ok,
// boton}, oido: {...}, cache: {texto, frac}, version, act} y hace accion("interruptor"|"voz"|"ruido"|"instalar_ia"|
// "instalar_oido"|"borrar_cache"|"buscar", valor).
import QtQuick

Item {
    id: raiz
    property real escala: 0.6
    property string familia: "Segoe UI"
    property var d: ({})
    signal accion(string nombre, var valor)
    signal soltado(var urls)
    // las listas solo se renuevan si cambian (si no, el Repeater rehace las tarjetas y repite su entrada)
    property var interruptoresL: []
    property var vozL: []
    onDChanged: {
        if (JSON.stringify(d.interruptores || []) !== JSON.stringify(interruptoresL)) interruptoresL = d.interruptores || []
        if (JSON.stringify(d.voz || []) !== JSON.stringify(vozL)) vozL = d.voz || []
    }
    function px(v) { return Math.round(v * escala) }
    function entrar() { opacity = 0; baja.y = px(30); entra.restart() }
    transform: Translate { id: baja }
    ParallelAnimation { id: entra
        NumberAnimation { target: raiz; property: "opacity"; to: 1; duration: 420; easing.type: Easing.OutCubic }
        NumberAnimation { target: baja; property: "y"; to: 0; duration: 560; easing.type: Easing.OutBack; easing.overshoot: 1.05 } }

    readonly property real sep: px(30)
    readonly property real col6: (width - 5 * sep) / 6
    implicitHeight: fila1.height + sep + fila2.height + px(40)

    Row {
        id: fila1
        spacing: raiz.sep
        height: Math.max(video.implicitHeight, voz.implicitHeight)
        Tarjeta {
            id: video
            escala: raiz.escala; familia: raiz.familia; titulo: "Video"; icono: "video"
            width: raiz.col6 * 3 + raiz.sep * 2; height: fila1.height
            Repeater {
                model: raiz.interruptoresL
                Item {
                    width: video.width - video.px(88); height: px(64)
                    Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.texto; color: "#F1F5F6"
                        font.family: raiz.familia; font.pixelSize: px(34) }
                    Interruptor { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                        escala: raiz.escala; si: modelData.si
                        onCambiado: (si) => raiz.accion("interruptor", { "clave": modelData.clave, "si": si }) }
                }
            }
            // (19-nov) donde van los proxies (con ellos encendidos): un clic abre la carpeta
            Text {
                visible: (raiz.d.proxies_ruta || "") !== ""
                width: video.width - video.px(88)
                elide: Text.ElideMiddle
                text: "Van en Videos › " + (raiz.d.proxies_ruta || "").split(/[\\/]/).pop() + "  (abrir)"
                color: zp.containsMouse ? "#6CF2B4" : "#9DB0B6"
                font.family: raiz.familia; font.pixelSize: px(26); font.underline: zp.containsMouse
                Behavior on color { ColorAnimation { duration: 150 } }
                MouseArea { id: zp; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: raiz.accion("abrir_proxies", 0) }
            }
        }
        Tarjeta {
            id: voz
            escala: raiz.escala; familia: raiz.familia; titulo: "Voz y ruido"; icono: "onda"
            width: raiz.col6 * 3 + raiz.sep * 2; height: fila1.height
            Item { width: 1; height: px(8) }
            Row {
                spacing: px(24)
                Text { anchors.verticalCenter: parent.verticalCenter; text: "Voz original"; color: "#F1F5F6"; width: px(200)
                    font.family: raiz.familia; font.pixelSize: px(34) }
                Row {
                    spacing: px(6)
                    Repeater {
                        model: raiz.vozL
                        Rectangle {
                            id: pv
                            property bool v: modelData.si
                            width: (voz.width - voz.px(88) - px(200) - px(24) - px(18)) / 4; height: px(72); radius: px(14)
                            color: v ? "#22C47E" : (zv.containsMouse ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(1, 1, 1, 0.03))
                            border.width: 1; border.color: v ? "#44D894" : Qt.rgba(1, 1, 1, 0.18)
                            Behavior on color { ColorAnimation { duration: 180 } }
                            scale: zv.pressed ? 0.95 : 1
                            Behavior on scale { SpringAnimation { spring: 5; damping: 0.3 } }
                            Text { id: tv; anchors.centerIn: parent; text: modelData.texto; color: "white"
                                font.family: raiz.familia; font.pixelSize: px(32); font.weight: pv.v ? Font.DemiBold : Font.Normal }
                            MouseArea { id: zv; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: { pv.v = !pv.v; raiz.accion("voz", { "clave": modelData.clave, "si": pv.v }) } }
                        }
                    }
                }
            }
            Rectangle { width: parent.width; height: 1; color: Qt.rgba(1, 1, 1, 0.10) }
            // quitar ruido: deslizador verde
            Row {
                spacing: px(24)
                Text { anchors.verticalCenter: parent.verticalCenter; text: "Quitar ruido"; color: "#F1F5F6"; width: px(220)
                    font.family: raiz.familia; font.pixelSize: px(34) }
                Item {
                    id: desl
                    anchors.verticalCenter: parent.verticalCenter
                    width: voz.width - voz.px(88) - px(220) - px(24) * 2 - px(70); height: px(52)
                    property real valor: (raiz.d.ruido !== undefined ? raiz.d.ruido : 60)
                    property real visto: valor
                    Connections { target: raiz; function onDChanged() { if (!arrastre.pressed) desl.visto = desl.valor } }
                    Rectangle { anchors.verticalCenter: parent.verticalCenter; width: parent.width; height: px(10); radius: height / 2
                        color: Qt.rgba(140 / 255, 160 / 255, 170 / 255, 0.35) }
                    Rectangle { anchors.verticalCenter: parent.verticalCenter; width: parent.width * desl.visto / 100; height: px(10)
                        radius: height / 2; color: "#22C47E" }
                    Rectangle {
                        width: px(36); height: width; radius: width / 2
                        anchors.verticalCenter: parent.verticalCenter
                        x: (parent.width - width) * desl.visto / 100
                        color: "white"; border.width: px(4); border.color: "#22C47E"
                        scale: arrastre.pressed ? 1.2 : 1
                        Behavior on scale { NumberAnimation { duration: 120 } }
                    }
                    MouseArea {
                        id: arrastre
                        anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                        function poner(x) { desl.visto = Math.max(0, Math.min(100, Math.round(x / width * 100))) }
                        onPressed: (m) => poner(m.x)
                        onPositionChanged: (m) => poner(m.x)
                        onReleased: raiz.accion("ruido", desl.visto)
                    }
                }
                Text { anchors.verticalCenter: parent.verticalCenter; text: Math.round(desl.visto); color: "#F1F5F6"; width: px(70)
                    horizontalAlignment: Text.AlignRight; font.family: raiz.familia; font.pixelSize: px(34) }
            }
            // (19-nov) el ruido de DaVinci (temporal: el que mas limpia): se deja a gusto en un clip y se guarda aqui
            Rectangle { width: parent.width; height: 1; color: Qt.rgba(1, 1, 1, 0.10) }
            Text {
                width: parent.width; wrapMode: Text.WordWrap
                text: ((raiz.d.ruido_dv || {}).texto || "") + ((raiz.d.ruido_dv || {}).hay ? "" :
                      "  ·  Para limpiar más, deja la reducción de ruido a tu gusto en un clip de DaVinci (página Color) y guárdala:")
                color: "#9DB0B6"; font.family: raiz.familia; font.pixelSize: px(28)
            }
            Row {
                spacing: px(16)
                Boton { escala: raiz.escala; familia: raiz.familia; texto: "Guardar el del clip actual"; icono: "onda"
                    activo: !(raiz.d.ruido_dv || {}).ocupado; onClic: raiz.accion("ruido_dv_guardar", 0) }
                Boton { visible: (raiz.d.ruido_dv || {}).hay === true; escala: raiz.escala; familia: raiz.familia
                    texto: "Quitar"; onClic: raiz.accion("ruido_dv_quitar", 0) }
            }
        }
    }

    Row {
        id: fila2
        y: fila1.height + raiz.sep
        spacing: raiz.sep
        height: Math.max(intel.implicitHeight, disco.implicitHeight, prog.implicitHeight)
        Tarjeta {
            id: intel
            escala: raiz.escala; familia: raiz.familia; titulo: "Inteligencia"; icono: "chip"
            width: raiz.col6 * 2 + raiz.sep; height: fila2.height
            Estado { dato: raiz.d.ia || ({}); accionBoton: "instalar_ia" }
            Estado { dato: raiz.d.oido || ({}); accionBoton: "instalar_oido" }
        }
        Tarjeta {
            id: disco
            escala: raiz.escala; familia: raiz.familia; titulo: "Disco"; icono: "disco"
            width: raiz.col6 * 2 + raiz.sep; height: fila2.height
            Text { text: (raiz.d.cache || {}).texto || "Midiendo la caché…"; color: "#F1F5F6"
                font.family: raiz.familia; font.pixelSize: px(34) }
            Rectangle {
                width: parent.width; height: px(26); radius: height / 2
                color: Qt.rgba(1, 1, 1, 0.08); clip: true
                Rectangle {
                    height: parent.height; radius: height / 2
                    width: Math.max(height, parent.width * Math.min(1, ((raiz.d.cache || {}).frac || 0)))
                    Behavior on width { NumberAnimation { duration: 900; easing.type: Easing.OutCubic } }
                    gradient: Gradient { orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: "#E2B04F" } GradientStop { position: 1; color: "#F6D27A" } }
                    Rectangle { width: parent.height * 3; height: parent.height
                        gradient: Gradient { orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: Qt.rgba(1, 1, 1, 0) }
                            GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.45) }
                            GradientStop { position: 1; color: Qt.rgba(1, 1, 1, 0) } }
                        NumberAnimation on x { loops: Animation.Infinite; from: -px(80); to: px(400); duration: 2400 } }
                }
            }
            Boton { width: parent.width; escala: raiz.escala; familia: raiz.familia; texto: "Borrar caché"; icono: "papelera"
                onClic: raiz.accion("borrar_cache", 0) }
        }
        Tarjeta {
            id: prog
            escala: raiz.escala; familia: raiz.familia; titulo: "Programa"; icono: "engrane"
            width: raiz.col6 * 2 + raiz.sep; height: fila2.height
            Text { text: raiz.d.version || ""; color: "#F1F5F6"; font.family: raiz.familia; font.pixelSize: px(34) }
            Text { visible: (raiz.d.act || "") !== ""; width: parent.width; wrapMode: Text.WordWrap
                text: raiz.d.act || ""; color: "#9DB0B6"; font.family: raiz.familia; font.pixelSize: px(28) }
            Boton { width: parent.width; escala: raiz.escala; familia: raiz.familia; texto: "Buscar actualizaciones"
                icono: "refrescar"; girar: true; onClic: raiz.accion("buscar", 0) }
        }
    }

    // una fila de Inteligencia: el punto (verde listo, ambar falta) que late, el texto y el enlace para instalar
    component Estado: Rectangle {
        id: e
        property var dato: ({})
        property string accionBoton: ""
        width: intel.width - intel.px(88); height: Math.max(px(84), colEst.implicitHeight + px(28))
        radius: px(16); color: Qt.rgba(1, 1, 1, 0.03)
        border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.10)
        Rectangle {
            id: punto
            x: px(26); anchors.verticalCenter: parent.verticalCenter
            width: px(18); height: width; radius: width / 2
            color: e.dato.ok ? "#22C47E" : "#F2B84B"
            SequentialAnimation on opacity { loops: Animation.Infinite
                NumberAnimation { to: 0.45; duration: 900; easing.type: Easing.InOutSine }
                NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutSine } }
        }
        Column {
            id: colEst
            x: px(66); anchors.verticalCenter: parent.verticalCenter
            width: parent.width - px(66) - px(24)
            spacing: px(6)
        Text { width: parent.width; elide: Text.ElideRight
            text: e.dato.texto || ""; color: "#F1F5F6"; font.family: raiz.familia; font.pixelSize: px(32) }
        Text {
            id: enlace
            visible: (e.dato.boton || "") !== ""
            text: e.dato.boton || ""; color: zl.containsMouse ? "#6CF2B4" : "#3BEE9F"
            font.family: raiz.familia; font.pixelSize: px(28); font.weight: Font.Bold
            font.underline: zl.containsMouse
            MouseArea { id: zl; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                onClicked: raiz.accion(e.accionBoton, 0) }
        }
        }
    }
}
