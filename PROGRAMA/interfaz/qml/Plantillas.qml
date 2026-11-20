// (1.7, parte 4) Pagina Plantillas: las plantillas de video (Reels, TikTok, CapCut) en tarjetas 9:16 con su portada;
// clic = usarla o dejarla; soltar un video encima = convertirlo en plantilla. Python (PaginaQML) pone d = {lista:
// [{nombre, portada, dur, planos}], marcadas, opciones: [{clave, texto, si}]} y hace accion("marcar"|"opcion"|"agregar").
import QtQuick

Item {
    id: raiz
    property real escala: 0.6
    property string familia: "Segoe UI"
    property var d: ({})
    signal accion(string nombre, var valor)
    signal soltado(var urls)
    // las listas solo se renuevan si cambian (si no, el Repeater rehace las tarjetas y repite su entrada)
    property var listaL: []
    property var opcionesL: []
    onDChanged: {
        if (JSON.stringify(d.lista || []) !== JSON.stringify(listaL)) listaL = d.lista || []
        if (JSON.stringify(d.opciones || []) !== JSON.stringify(opcionesL)) opcionesL = d.opciones || []
    }
    function px(v) { return Math.round(v * escala) }
    function entrar() { opacity = 0; baja.y = px(30); entra.restart() }
    transform: Translate { id: baja }
    ParallelAnimation { id: entra
        NumberAnimation { target: raiz; property: "opacity"; to: 1; duration: 420; easing.type: Easing.OutCubic }
        NumberAnimation { target: baja; property: "y"; to: 0; duration: 560; easing.type: Easing.OutBack; easing.overshoot: 1.05 } }

    readonly property var lista: listaL
    readonly property var marcadas: d.marcadas || []
    implicitHeight: tarjeta.height + px(100)

    Tarjeta {
        id: tarjeta
        escala: raiz.escala; familia: raiz.familia
        titulo: "Plantillas de video"; icono: "pelicula"
        x: px(60); y: px(50)
        width: raiz.width - px(120)
        height: implicitHeight

        // lo que hace y «Agregar plantilla»
        Item {
            width: parent.width; height: agregar.height
            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - agregar.width - px(40)
                wrapMode: Text.WordWrap
                text: "Opcional: cada una sale como un video más, con sus cortes y su música."
                color: "#9DB0B6"; font.family: raiz.familia; font.pixelSize: px(32)
            }
            Boton {
                id: agregar
                anchors.right: parent.right
                escala: raiz.escala; familia: raiz.familia
                texto: "Agregar plantilla"; icono: "carpeta"; principal: true
                onClic: raiz.accion("agregar", 0)
            }
        }
        // las opciones
        Flow {
            width: parent.width
            spacing: px(40)
            Repeater {
                model: raiz.opcionesL
                Row {
                    spacing: px(18)
                    Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.texto; color: "#F1F5F6"
                        font.family: raiz.familia; font.pixelSize: px(34) }
                    Interruptor { anchors.verticalCenter: parent.verticalCenter; escala: raiz.escala; si: modelData.si
                        onCambiado: (si) => raiz.accion("opcion", { "clave": modelData.clave, "si": si }) }
                }
            }
            Text { text: "Todo apagado: la plantilla tal cual, con sus cortes y su música."; color: "#9DB0B6"
                font.family: raiz.familia; font.pixelSize: px(28); height: px(52); verticalAlignment: Text.AlignVCenter }
        }
        Item { width: 1; height: px(6) }
        // las tarjetas 9:16 (o la invitacion a soltar un video)
        Item {
            width: parent.width
            // el alto, calculado (el de la Flow no se actualizaba al llegar las tarjetas)
            readonly property int porFila: Math.max(1, Math.floor((width + px(26)) / (px(250) + px(26))))
            readonly property int filas: Math.ceil(raiz.lista.length / porFila)
            height: raiz.lista.length ? filas * px(540) + (filas - 1) * px(26) : px(380)
            Rectangle {
                visible: raiz.lista.length === 0
                anchors.fill: parent
                radius: px(28); color: Qt.rgba(1, 1, 1, 0.02)
                border.width: px(3); border.color: soltar.containsDrag ? "#3BEE9F" : Qt.rgba(1, 1, 1, 0.14)
                Column {
                    anchors.centerIn: parent
                    spacing: px(20)
                    Image { anchors.horizontalCenter: parent.horizontalCenter; width: px(90); height: width
                        source: "image://icono/pelicula/9DB0B6/" + width; sourceSize: Qt.size(width * 4, height * 4)
                        SequentialAnimation on y { loops: Animation.Infinite
                            NumberAnimation { to: -px(8); duration: 1400; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 0; duration: 1400; easing.type: Easing.InOutSine } } }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; color: "#9DB0B6"
                        text: "Suelta aquí un video (Reel, TikTok, CapCut) para convertirlo en plantilla: sus cortes y su música."
                        font.family: raiz.familia; font.pixelSize: px(32) }
                }
            }
            Flow {
                id: rejilla
                objectName: "rejilla"
                width: parent.width
                height: parent.height
                spacing: px(26)
                Repeater {
                    model: raiz.lista
                    Portada {
                        dato: modelData
                        elegida: raiz.marcadas.indexOf(modelData.nombre) >= 0
                        retraso: index * 70
                        onClic: raiz.accion("marcar", modelData.nombre)
                    }
                }
            }
        }
    }

    // soltar videos en cualquier parte de la pagina: se convierten en plantillas
    DropArea {
        id: soltar
        anchors.fill: parent
        onDropped: (drop) => { if (drop.hasUrls) { raiz.soltado(drop.urls); drop.accept() } }
    }
    Rectangle {
        anchors.fill: parent; anchors.margins: px(30)
        radius: px(40); color: Qt.rgba(34 / 255, 196 / 255, 126 / 255, 0.10)
        border.width: px(4); border.color: "#3BEE9F"
        opacity: soltar.containsDrag ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
        Text { anchors.centerIn: parent; text: "Suelta para convertirlo en plantilla"; color: "white"
            font.family: raiz.familia; font.pixelSize: px(48); font.weight: Font.Bold }
    }

    // una plantilla: portada 9:16, nombre y planos; la elegida con filo verde y palomita
    component Portada: Item {
        id: c
        property var dato: ({})
        property bool elegida: false
        property int retraso: 0
        signal clic()
        width: px(250); height: px(444) + px(96)
        opacity: 0
        Component.onCompleted: aparece.start()
        SequentialAnimation { id: aparece
            PauseAnimation { duration: c.retraso }
            ParallelAnimation {
                NumberAnimation { target: c; property: "opacity"; to: 1; duration: 380 }
                NumberAnimation { target: sube; property: "y"; from: px(30); to: 0; duration: 480; easing.type: Easing.OutBack } } }
        transform: Translate { id: sube }

        Rectangle {
            id: marco
            width: parent.width; height: px(444)
            y: zona.containsMouse ? -px(8) : 0
            Behavior on y { SpringAnimation { spring: 4; damping: 0.3 } }
            radius: px(24)
            color: "#0B1A1F"
            border.width: c.elegida ? px(5) : 1
            border.color: c.elegida ? "#3BEE9F" : (zona.containsMouse ? "#E2B04F" : Qt.rgba(1, 1, 1, 0.14))
            Behavior on border.color { ColorAnimation { duration: 200 } }
            clip: true
            Image {
                anchors.fill: parent; anchors.margins: parent.border.width
                source: c.dato.portada || ""
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                scale: zona.containsMouse ? 1.05 : 1
                Behavior on scale { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
            }
            Rectangle {
                anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                height: parent.height * 0.4
                gradient: Gradient { GradientStop { position: 0; color: "transparent" } GradientStop { position: 1; color: Qt.rgba(0, 0, 0, 0.75) } }
            }
            Rectangle {
                x: parent.width - width - px(16); y: px(16)
                width: px(52); height: width; radius: width / 2
                color: "#22C47E"
                scale: c.elegida ? 1 : 0
                Behavior on scale { SpringAnimation { spring: 3.5; damping: 0.24 } }
                Image { anchors.centerIn: parent; width: px(32); height: width
                    source: "image://icono/palomita/FFFFFF/" + width; sourceSize: Qt.size(width * 4, height * 4) }
            }
        }
        Text {
            y: px(444) + px(18); width: parent.width
            text: (c.dato.nombre || "").replace(/_/g, " ")
            elide: Text.ElideRight; color: "white"
            font.family: raiz.familia; font.pixelSize: px(32); font.weight: Font.DemiBold; font.capitalization: Font.Capitalize
        }
        Text {
            y: px(444) + px(60); width: parent.width
            text: (c.dato.planos || 0) + " planos · " + Math.round(c.dato.dur || 0) + " s"
            color: "#9DB0B6"; font.family: raiz.familia; font.pixelSize: px(26)
        }
        MouseArea { id: zona; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: c.clic() }
    }
}
