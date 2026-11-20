// (1.7, la persona: «QML por partes: los popups») El popup de la ventana en QML: lo de atras borroso (una foto de la
// ventana que pone Python), la tarjeta de vidrio con filo dorado que respira, el emblema con su aro de luz, el titulo,
// el texto, una forma (trailer / nombre / videos) y los botones en pastilla (verde el principal, con su brillo).
// Python (barra_qml.PopupQML) llama abrir(...) y espera la señal respuesta(boton, json de la forma).
import QtQuick
import QtQuick.Shapes

Item {
    id: raiz
    property real escala: 0.6
    property string familia: "Segoe UI"
    property string fondo: ""
    property string titulo: ""
    property string texto: ""
    property var botones: ["Entendido"]
    property string tipo: "info"
    property int primario: 0
    property int esc: 0
    property string forma: ""
    property var datos: ({})
    property bool cerrando: false
    signal respuesta(int boton, string json)
    function px(v) { return Math.round(v * escala) }

    readonly property var colorTipo: ({ "aviso": "F2B84B", "pregunta": "E2B04F", "info": "22C47E", "error": "E5534B", "ok": "22C47E" })
    readonly property string colorEmblema: colorTipo[tipo] || "22C47E"

    // el resultado de la forma (lo llenan los formularios)
    property var resultado: ({})

    function abrir() {
        cerrando = false
        resultado = JSON.parse(JSON.stringify(datos || {}))
        velo.opacity = 0; tarjeta.opacity = 0; baja.y = px(54)
        entra.restart()
        foco.forceActiveFocus()
    }
    function cerrar(i) {
        if (cerrando) return
        cerrando = true
        elegido = i
        sale.restart()
    }
    property int elegido: -1

    ParallelAnimation {
        id: entra
        NumberAnimation { target: velo; property: "opacity"; to: 1; duration: 240; easing.type: Easing.OutCubic }
        NumberAnimation { target: tarjeta; property: "opacity"; to: 1; duration: 240; easing.type: Easing.OutCubic }
        NumberAnimation { target: baja; property: "y"; to: 0; duration: 320; easing.type: Easing.OutBack; easing.overshoot: 1.2 }
    }
    SequentialAnimation {
        id: sale
        ParallelAnimation {
            NumberAnimation { target: velo; property: "opacity"; to: 0; duration: 160 }
            NumberAnimation { target: tarjeta; property: "opacity"; to: 0; duration: 140 }
            NumberAnimation { target: baja; property: "y"; to: px(24); duration: 160; easing.type: Easing.InCubic }
        }
        ScriptAction { script: raiz.respuesta(raiz.elegido, JSON.stringify(raiz.resultado)) }
    }

    // lo de atras: la ventana borrosa y oscura
    Item {
        id: velo
        anchors.fill: parent
        Image { anchors.fill: parent; source: raiz.fondo; smooth: true; cache: false }
        Rectangle { anchors.fill: parent; color: Qt.rgba(2 / 255, 10 / 255, 12 / 255, 0.65) }
        MouseArea { anchors.fill: parent; hoverEnabled: true }      // lo de atras no recibe clics
    }

    Item {
        id: foco
        anchors.fill: parent
        focus: true
        Keys.onEscapePressed: raiz.cerrar(raiz.esc)
        Keys.onReturnPressed: raiz.cerrar(raiz.primario)
        Keys.onEnterPressed: raiz.cerrar(raiz.primario)
    }

    // ------------------------------------------------------------------ la tarjeta
    Item {
        id: tarjeta
        anchors.centerIn: parent
        transform: Translate { id: baja; y: 0 }
        width: Math.min(raiz.width - px(48), Math.max(px(820), Math.min(px(1180), filaBotones.implicitWidth + px(140))))
        height: contenido.height + px(50) + px(58)

        // el resplandor dorado que respira alrededor
        Repeater {
            model: 5
            Rectangle {
                anchors.fill: parent
                anchors.margins: -(px(6) + index * px(7))
                radius: px(64) + index * px(7)
                color: "transparent"
                border.width: px(6)
                border.color: "#E2B04F"
                opacity: (0.09 - index * 0.016) * respira.v
            }
        }
        QtObject { id: respira; property real v: 1.0
            SequentialAnimation on v { loops: Animation.Infinite
                NumberAnimation { to: 1.6; duration: 1600; easing.type: Easing.InOutSine }
                NumberAnimation { to: 0.8; duration: 1600; easing.type: Easing.InOutSine } } }

        Rectangle {
            anchors.fill: parent
            radius: px(64)
            border.width: Math.max(1, px(3))
            border.color: "#D9B15C"
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(16 / 255, 52 / 255, 48 / 255, 0.97) }
                GradientStop { position: 0.45; color: Qt.rgba(9 / 255, 30 / 255, 32 / 255, 0.98) }
                GradientStop { position: 1.0; color: Qt.rgba(7 / 255, 22 / 255, 26 / 255, 0.99) }
            }
        }

        Column {
            id: contenido
            x: px(70); y: px(50)
            width: tarjeta.width - px(140)
            spacing: px(20)

            // el emblema: circulo con aro dorado y una luz que lo recorre
            Item {
                anchors.horizontalCenter: parent.horizontalCenter
                width: px(150); height: width
                Rectangle {
                    anchors.fill: parent; radius: width / 2
                    color: Qt.rgba(0, 0, 0, 0.35)
                    border.width: px(4); border.color: "#C9A267"
                }
                Shape {
                    anchors.fill: parent
                    RotationAnimation on rotation { loops: Animation.Infinite; from: 0; to: 360; duration: 2600 }
                    ShapePath {
                        strokeColor: Qt.rgba(1, 0.93, 0.75, 0.95); strokeWidth: px(4); fillColor: "transparent"
                        capStyle: ShapePath.RoundCap
                        PathAngleArc { centerX: px(75); centerY: px(75); radiusX: px(73); radiusY: px(73)
                            startAngle: 0; sweepAngle: 70 }
                    }
                }
                // el simbolo (como el emblema de siempre): ! en triangulo, ? , i, cruz o palomita; entra creciendo
                Item {
                    id: simbolo
                    anchors.fill: parent
                    scale: tarjeta.opacity
                    readonly property color col: "#" + raiz.colorEmblema
                    readonly property real s: width
                    Text {
                        anchors.centerIn: parent
                        visible: raiz.tipo === "pregunta" || raiz.tipo === "info"
                        text: raiz.tipo === "pregunta" ? "?" : "i"
                        color: simbolo.col
                        font.family: raiz.familia; font.pixelSize: simbolo.s * 0.56; font.bold: true
                    }
                    Shape {
                        anchors.fill: parent
                        visible: raiz.tipo === "aviso" || raiz.tipo === "error"
                        ShapePath {
                            strokeColor: simbolo.col; strokeWidth: Math.max(2, px(7)); fillColor: "transparent"
                            capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
                            startX: raiz.tipo === "aviso" ? simbolo.s * 0.5 : simbolo.s * 0.35
                            startY: raiz.tipo === "aviso" ? simbolo.s * 0.26 : simbolo.s * 0.35
                            PathLine { x: raiz.tipo === "aviso" ? simbolo.s * 0.76 : simbolo.s * 0.65
                                       y: raiz.tipo === "aviso" ? simbolo.s * 0.69 : simbolo.s * 0.65 }
                            PathMove { x: raiz.tipo === "aviso" ? simbolo.s * 0.76 : simbolo.s * 0.65
                                       y: raiz.tipo === "aviso" ? simbolo.s * 0.69 : simbolo.s * 0.35 }
                            PathLine { x: raiz.tipo === "aviso" ? simbolo.s * 0.24 : simbolo.s * 0.35
                                       y: raiz.tipo === "aviso" ? simbolo.s * 0.69 : simbolo.s * 0.65 }
                            PathLine { x: raiz.tipo === "aviso" ? simbolo.s * 0.5 : simbolo.s * 0.35
                                       y: raiz.tipo === "aviso" ? simbolo.s * 0.26 : simbolo.s * 0.65 }
                            PathMove { x: simbolo.s * 0.5; y: raiz.tipo === "aviso" ? simbolo.s * 0.42 : simbolo.s * 0.5 }
                            PathLine { x: simbolo.s * 0.5; y: raiz.tipo === "aviso" ? simbolo.s * 0.54 : simbolo.s * 0.5 }
                        }
                    }
                    Rectangle {     // el punto del !
                        visible: raiz.tipo === "aviso"
                        width: Math.max(3, px(8)); height: width; radius: width / 2
                        color: simbolo.col
                        x: simbolo.s * 0.5 - width / 2; y: simbolo.s * 0.62 - height / 2
                    }
                    Image {
                        anchors.centerIn: parent
                        visible: raiz.tipo === "ok"
                        width: px(70); height: width
                        source: "image://icono/check/" + raiz.colorEmblema + "/" + width
                        sourceSize: Qt.size(width * 4, height * 4)
                    }
                }
            }
            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: raiz.titulo
                color: "white"
                font.family: raiz.familia; font.pixelSize: px(64); font.weight: Font.ExtraBold
            }
            Text {
                visible: raiz.texto !== ""
                width: parent.width
                horizontalAlignment: raiz.texto.indexOf("•") >= 0 ? Text.AlignLeft : Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: raiz.texto
                color: "#B9C6C9"
                font.family: raiz.familia; font.pixelSize: px(34)
                lineHeight: 1.15
            }

            // la forma (si la hay)
            Loader {
                width: parent.width
                active: raiz.forma !== ""
                visible: active
                sourceComponent: raiz.forma === "trailer" ? formaTrailer : raiz.forma === "nombre" ? formaNombre
                               : raiz.forma === "videos" ? formaVideos : null
            }

            Item { width: 1; height: px(22) }
            Row {
                id: filaBotones
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: px(34)
                Repeater {
                    model: raiz.botones
                    Pastilla {
                        texto: modelData
                        principal: index === raiz.primario
                        onClic: raiz.cerrar(index)
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------------ piezas
    component Pastilla: Rectangle {
        id: p
        property string texto: ""
        property bool principal: false
        property bool marcada: false          // para las pastillas de elegir (formato, duraciones, videos)
        property bool chica: false
        signal clic()
        implicitWidth: Math.max(chica ? px(200) : px(250), t.implicitWidth + px(54) * 2)
        implicitHeight: chica ? px(80) : px(92)
        width: implicitWidth; height: implicitHeight
        radius: chica ? px(30) : px(46)
        scale: zona.pressed ? 0.96 : 1
        Behavior on scale { SpringAnimation { spring: 5; damping: 0.3 } }
        clip: true
        color: (principal || marcada) ? "transparent" : (zona.containsMouse ? Qt.rgba(217 / 255, 177 / 255, 92 / 255, 0.16) : Qt.rgba(1, 1, 1, 0.04))
        Behavior on color { ColorAnimation { duration: 160 } }
        border.width: Math.max(1, px(2))
        border.color: (principal || marcada) ? Qt.rgba(1, 1, 1, 0.28) : (zona.containsMouse ? "#F1CB7A" : Qt.rgba(217 / 255, 177 / 255, 92 / 255, 0.75))
        gradient: (principal || marcada) ? verdeG : null
        Gradient {
            id: verdeG
            GradientStop { position: 0; color: zona.containsMouse ? "#3BE3A0" : "#2BD08C" }
            GradientStop { position: 1; color: zona.containsMouse ? "#16A068" : "#118A57" }
        }
        Rectangle {        // el destello que cruza el boton principal
            visible: p.principal
            width: p.height * 0.9; height: p.height * 2.4; y: -p.height * 0.7; rotation: 20
            gradient: Gradient { orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Qt.rgba(1, 1, 1, 0) }
                GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.32) }
                GradientStop { position: 1; color: Qt.rgba(1, 1, 1, 0) } }
            SequentialAnimation on x { running: p.principal; loops: Animation.Infinite
                PauseAnimation { duration: 900 }
                NumberAnimation { from: -p.height * 1.5; to: p.width + p.height; duration: 1100; easing.type: Easing.InOutQuad }
                PauseAnimation { duration: 1800 } }
        }
        Row {
            anchors.centerIn: parent
            spacing: px(14)
            Image {
                visible: p.marcada && !p.principal
                anchors.verticalCenter: parent.verticalCenter
                width: px(30); height: width
                source: "image://icono/palomita/FFFFFF/" + width
                sourceSize: Qt.size(width * 4, height * 4)
            }
            Text {
                id: t
                anchors.verticalCenter: parent.verticalCenter
                text: p.texto
                color: "white"
                font.family: raiz.familia; font.pixelSize: p.chica ? px(30) : px(34)
                font.weight: (p.principal || p.marcada) ? Font.ExtraBold : Font.DemiBold
            }
        }
        MouseArea { id: zona; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: p.clic() }
    }

    // Tráiler: el formato y sus duraciones (cada formato guarda las suyas)
    Component {
        id: formaTrailer
        Column {
            spacing: px(24)
            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: px(12)
                Repeater {
                    model: ["Horizontal", "Vertical"]
                    Pastilla { chica: true; texto: modelData; marcada: raiz.resultado.formato === index
                        onClic: { var r = Object.assign({}, raiz.resultado)   /* una copia: el mismo objeto no avisa del cambio y la pastilla no se marcaba */; r.formato = index; raiz.resultado = r } }
                }
            }
            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: px(18)
                Repeater {
                    model: raiz.datos.versiones || []
                    Pastilla {
                        chica: true
                        readonly property string lista: raiz.resultado.formato === 1 ? "v" : "h"
                        texto: modelData[1]
                        marcada: (raiz.resultado[lista] || []).indexOf(modelData[0]) >= 0
                        onClic: {
                            var r = Object.assign({}, raiz.resultado)   /* una copia: el mismo objeto no avisa del cambio y la pastilla no se marcaba */
                            var l = (r[lista] || []).slice()
                            var i = l.indexOf(modelData[0])
                            if (i >= 0) { if (l.length + ((r[lista === "h" ? "v" : "h"] || []).length) > 1) l.splice(i, 1) }
                            else l.push(modelData[0])
                            r[lista] = l
                            raiz.resultado = r
                        }
                    }
                }
            }
        }
    }

    // Nombre: el tipo de evento y el nombre
    Component {
        id: formaNombre
        Column {
            spacing: px(26)
            Flow {
                width: parent.width
                spacing: px(12)
                Repeater {
                    model: raiz.datos.tipos || []
                    Pastilla { chica: true; texto: modelData; marcada: raiz.resultado.tipo_i === index
                        onClic: { var r = Object.assign({}, raiz.resultado)   /* una copia: el mismo objeto no avisa del cambio y la pastilla no se marcaba */; r.tipo_i = index; raiz.resultado = r } }
                }
            }
            Rectangle {
                width: parent.width; height: px(96)
                radius: px(28)
                color: Qt.rgba(1, 1, 1, 0.04)
                border.width: Math.max(1, px(2))
                border.color: campo.activeFocus ? "#44D894" : Qt.rgba(1, 1, 1, 0.18)
                Behavior on border.color { ColorAnimation { duration: 180 } }
                TextInput {
                    id: campo
                    anchors.fill: parent; anchors.leftMargin: px(30); anchors.rightMargin: px(30)
                    verticalAlignment: TextInput.AlignVCenter
                    text: raiz.datos.nombre || ""
                    color: "white"; selectionColor: "#1FA971"
                    font.family: raiz.familia; font.pixelSize: px(36)
                    clip: true
                    onTextEdited: { var r = Object.assign({}, raiz.resultado)   /* una copia: el mismo objeto no avisa del cambio y la pastilla no se marcaba */; r.nombre = text; raiz.resultado = r }
                    Keys.onReturnPressed: raiz.cerrar(raiz.primario)
                    Keys.onEscapePressed: raiz.cerrar(raiz.esc)
                    Component.onCompleted: forceActiveFocus()
                    Text { visible: !campo.text; anchors.verticalCenter: parent.verticalCenter
                        text: "Valeria  ·  Ana y Luis"; color: Qt.rgba(1, 1, 1, 0.35)
                        font.family: raiz.familia; font.pixelSize: px(36) }
                }
            }
        }
    }

    // Videos: una pastilla por video (uno o varios)
    Component {
        id: formaVideos
        Flow {
            spacing: px(12)
            Repeater {
                model: raiz.datos.videos || []
                Pastilla {
                    chica: true
                    width: Math.max(implicitWidth, px(250))
                    texto: modelData[1]
                    marcada: (raiz.resultado.elegidos || []).indexOf(modelData[0]) >= 0
                    onClic: {
                        var r = Object.assign({}, raiz.resultado)   /* una copia: el mismo objeto no avisa del cambio y la pastilla no se marcaba */
                        var l = (r.elegidos || []).slice()
                        var i = l.indexOf(modelData[0])
                        if (raiz.datos.varios) { if (i >= 0) l.splice(i, 1); else l.push(modelData[0]) }
                        else l = [modelData[0]]
                        r.elegidos = l
                        raiz.resultado = r
                    }
                }
            }
        }
    }
}
