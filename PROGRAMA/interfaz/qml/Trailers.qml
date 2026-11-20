// (1.7, parte 4) Pagina Tráilers: «Elige el estilo». La musica en tarjetas grandes (un clic y listo; el boton redondo o doble
// clic: oir sus canciones) y la intro con sus 8 fotos latiendo al ritmo de cada tipo. Python (PaginaQML) pone d =
// {estilos, estilo, intros, intro} y hace accion("estilo"|"oir"|"intro"|"ver_intro", i).
import QtQuick

Item {
    id: raiz
    property real escala: 0.6
    property string familia: "Segoe UI"
    property var d: ({})
    signal accion(string nombre, var valor)
    signal soltado(var urls)
    // las listas solo se renuevan si cambian (si no, el Repeater rehace las tarjetas y repite su entrada)
    property var estilosL: []
    property var introsL: []
    onDChanged: {
        if (JSON.stringify(d.estilos || []) !== JSON.stringify(estilosL)) estilosL = d.estilos || []
        if (JSON.stringify(d.intros || []) !== JSON.stringify(introsL)) introsL = d.intros || []
    }
    function px(v) { return Math.round(v * escala) }
    function entrar() { opacity = 0; baja.y = px(30); entra.restart() }
    transform: Translate { id: baja }
    ParallelAnimation { id: entra
        NumberAnimation { target: raiz; property: "opacity"; to: 1; duration: 420; easing.type: Easing.OutCubic }
        NumberAnimation { target: baja; property: "y"; to: 0; duration: 560; easing.type: Easing.OutBack; easing.overshoot: 1.05 } }

    implicitHeight: col.implicitHeight + px(120)

    readonly property var info: ({
        "auto": ["brillo", "El que le va al tipo de evento"],
        "cine latino": ["pelicula", "Épica y cálida, de película"],
        "juvenil": ["fiesta", "Ritmo y energía para bailar"],
        "clásico": ["nota", "Cuerdas y piano, elegante"],
        "emotivo": ["corazon", "Suave, para emocionar"],
        "plantilla": ["claqueta", "Las canciones de la plantilla"]
    })
    readonly property var ritmos: ({ "rampa": [5, 5, 5, 5, 5, 5, 5, 5], "acelera": [9, 7, 6, 5, 4, 4, 3, 2],
                                     "frena": [2, 3, 4, 4, 5, 6, 7, 9], "latido": [7, 3, 7, 3, 7, 3, 7, 3] })
    readonly property var textosIntro: ({ "rampa": "Una foto cada 5 cuadros", "acelera": "De lenta a rápida",
                                          "frena": "Ráfaga que se frena", "latido": "De dos en dos" })

    Column {
        id: col
        width: Math.min(parent.width - px(120), px(1700))
        anchors.horizontalCenter: parent.horizontalCenter
        y: px(60)
        spacing: px(22)

        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Elige el estilo"; color: "white"
            font.family: raiz.familia; font.pixelSize: px(72); font.weight: Font.Bold }
        Text { anchors.horizontalCenter: parent.horizontalCenter; color: "#9DB0B6"
            text: "Un clic y listo: se guarda solo. Con el botón redondo o doble clic oyes sus canciones o ves la intro."
            font.family: raiz.familia; font.pixelSize: px(30) }
        Item { width: 1; height: px(26) }

        Seccion { texto: "Música"; icono: "nota" }
        Grid {
            id: rejilla
            columns: 3
            spacing: px(26)
            readonly property real ancho: (col.width - spacing * (columns - 1)) / columns
            Repeater {
                model: raiz.estilosL
                Opcion {
                    width: rejilla.ancho; height: px(210)
                    readonly property var dato: raiz.info[modelData.toLowerCase()] || ["nota", ""]
                    titulo: modelData; descripcion: dato[1]; icono: dato[0]
                    elegida: raiz.d.estilo === index
                    retraso: index * 60
                    onElegir: raiz.accion("estilo", index)
                    onOir: raiz.accion("oir", index)
                }
            }
        }
        Item { width: 1; height: px(20) }
        Seccion { texto: "Intro"; icono: "brillo" }
        Row {
            id: filaIntros
            spacing: px(26)
            readonly property real ancho: (col.width - spacing * 3) / 4
            Repeater {
                model: raiz.introsL
                Opcion {
                    width: filaIntros.ancho; height: px(250)
                    readonly property string clave: modelData.toLowerCase()
                    titulo: modelData; descripcion: raiz.textosIntro[clave] || ""
                    elegida: raiz.d.intro === index
                    retraso: 360 + index * 60
                    ritmo: raiz.ritmos[clave] || []
                    onElegir: raiz.accion("intro", index)
                    onOir: raiz.accion("ver_intro", index)
                }
            }
        }
    }

    component Seccion: Row {
        property string texto: ""
        property string icono: ""
        spacing: px(18)
        Image { anchors.verticalCenter: parent.verticalCenter; width: px(46); height: width
            source: "image://icono/" + parent.icono + "/E2B04F/" + width; sourceSize: Qt.size(width * 4, height * 4) }
        Text { anchors.verticalCenter: parent.verticalCenter; text: parent.texto; color: "#EBCB8F"
            font.family: raiz.familia; font.pixelSize: px(40); font.weight: Font.DemiBold }
    }

    // una tarjeta para elegir: se eleva al pasar el raton, la elegida brilla en verde con su palomita
    component Opcion: Item {
        id: o
        property string titulo: ""
        property string descripcion: ""
        property string icono: ""
        property bool elegida: false
        property int retraso: 0
        property var ritmo: []
        signal elegir()
        signal oir()

        opacity: 0
        Component.onCompleted: aparece.start()
        SequentialAnimation { id: aparece
            PauseAnimation { duration: o.retraso }
            NumberAnimation { target: o; property: "opacity"; to: 1; duration: 380; easing.type: Easing.OutCubic } }

        Rectangle {
            id: caja
            width: parent.width; height: parent.height
            y: zona.containsMouse ? -px(6) : 0
            Behavior on y { SpringAnimation { spring: 4; damping: 0.3 } }
            radius: px(30)
            border.width: o.elegida ? px(4) : 1
            border.color: o.elegida ? "#3BEE9F" : (zona.containsMouse ? Qt.rgba(226 / 255, 176 / 255, 79 / 255, 0.6) : Qt.rgba(1, 1, 1, 0.12))
            Behavior on border.color { ColorAnimation { duration: 200 } }
            gradient: Gradient {
                GradientStop { position: 0; color: o.elegida ? Qt.rgba(24 / 255, 84 / 255, 66 / 255, 0.92) : Qt.rgba(20 / 255, 44 / 255, 50 / 255, 0.86) }
                GradientStop { position: 1; color: o.elegida ? Qt.rgba(10 / 255, 46 / 255, 36 / 255, 0.94) : Qt.rgba(8 / 255, 22 / 255, 28 / 255, 0.90) }
            }
            // el halo verde de la elegida
            Rectangle { anchors.fill: parent; anchors.margins: -px(10); radius: parent.radius + px(10); z: -1
                color: "transparent"; border.width: px(10); border.color: "#22C47E"
                opacity: o.elegida ? 0.18 : 0; Behavior on opacity { NumberAnimation { duration: 300 } } }

            // icono o, en las intros, las 8 fotos latiendo a su ritmo
            Image {
                visible: o.ritmo.length === 0
                x: px(36); y: px(36); width: px(64); height: width
                source: o.icono ? "image://icono/" + o.icono + "/" + (o.elegida ? "3BEE9F" : "E2B04F") + "/" + width : ""
                sourceSize: Qt.size(width * 4, height * 4)
            }
            Row {
                visible: o.ritmo.length > 0
                x: px(36); y: px(40)
                spacing: px(10)
                property int foco: 0
                id: fotos
                Repeater {
                    model: 8
                    Rectangle {
                        width: px(30); height: px(44); radius: px(6)
                        color: index === fotos.foco ? (o.elegida ? "#3BEE9F" : "#E2B04F") : Qt.rgba(1, 1, 1, 0.14)
                        scale: index === fotos.foco ? 1.18 : 1
                        Behavior on scale { NumberAnimation { duration: 90 } }
                    }
                }
                Timer {
                    running: o.ritmo.length > 0 && o.visible
                    repeat: true
                    interval: Math.max(60, (o.ritmo[fotos.foco] || 5) * 1000 / 24 * 2)
                    onTriggered: fotos.foco = (fotos.foco + 1) % 8
                }
            }
            Text {
                x: px(36); y: o.ritmo.length > 0 ? px(116) : px(118)
                width: parent.width - px(72)
                text: o.titulo; color: "white"; elide: Text.ElideRight
                font.family: raiz.familia; font.pixelSize: px(42); font.weight: Font.Bold
            }
            Text {
                x: px(36); y: (o.ritmo.length > 0 ? px(116) : px(118)) + px(56)
                width: parent.width - px(72) - px(70)
                text: o.descripcion; color: "#9DB0B6"; elide: Text.ElideRight
                font.family: raiz.familia; font.pixelSize: px(28)
            }
            // la palomita de la elegida
            Rectangle {
                x: parent.width - width - px(26); y: px(26)
                width: px(46); height: width; radius: width / 2
                color: "#22C47E"
                scale: o.elegida ? 1 : 0
                Behavior on scale { SpringAnimation { spring: 3.5; damping: 0.24 } }
                Image { anchors.centerIn: parent; width: px(30); height: width
                    source: "image://icono/palomita/FFFFFF/" + width; sourceSize: Qt.size(width * 4, height * 4) }
            }
            // ▶ oir / ver
            Rectangle {
                id: oirB
                x: parent.width - width - px(26); y: parent.height - height - px(26)
                width: px(64); height: width; radius: width / 2
                color: zonaOir.containsMouse ? "#22C47E" : Qt.rgba(1, 1, 1, 0.08)
                border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.2)
                opacity: zona.containsMouse || zonaOir.containsMouse || o.elegida ? 1 : 0.0
                Behavior on opacity { NumberAnimation { duration: 200 } }
                Behavior on color { ColorAnimation { duration: 150 } }
                scale: zonaOir.pressed ? 0.9 : 1
                Image { anchors.centerIn: parent; anchors.horizontalCenterOffset: px(3); width: px(30); height: width
                    source: "image://icono/play/FFFFFF/" + width; sourceSize: Qt.size(width * 4, height * 4) }
            }
        }
        MouseArea {
            id: zona
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: o.elegir()
            onDoubleClicked: o.oir()
        }
        MouseArea {
            id: zonaOir
            x: oirB.x; y: oirB.y; width: oirB.width; height: oirB.height
            hoverEnabled: true; cursorShape: Qt.PointingHandCursor
            onClicked: o.oir()
        }
    }
}
