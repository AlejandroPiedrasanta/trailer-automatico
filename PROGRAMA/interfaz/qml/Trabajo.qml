// (1.7, la persona: «QML por partes: pantalla de trabajo») Mientras trabaja: la fila de pasos (hecho / activo /
// pendiente / error) y el avance de cada version (armando, renderizando con %, lista, error), la hora en que termina
// y «Cancelar». Python (barra_qml.TrabajoQML) pone `pasos`, `versiones`, `eta`, `cancelarTexto`, `cancelarActivo` y
// escucha `cancelarClic`. Todo se mueve por tiempo en la tarjeta grafica (60 por segundo, sin repintar la ventana).
import QtQuick
import QtQuick.Shapes

Item {
    id: raiz
    property real escala: 0.6
    property string familia: "Segoe UI"
    property var pasos: []            // [{clave, nombre, estado}]
    property var versiones: []        // [{etq, estado, texto, pct, detalle}]
    property string eta: ""
    property string cancelarTexto: "Cancelar"
    property bool cancelarActivo: true
    signal cancelarClic()
    function px(v) { return Math.round(v * escala) }

    readonly property color oro: "#E2B04F"
    readonly property color verde: "#22C47E"
    readonly property color tenue: "#9DB0B6"
    implicitHeight: filaPasos.height + px(40) + tarjeta.height

    // al empezar a trabajar: los pasos y las versiones aparecen subiendo (Python llama entrar())
    function entrar() { raiz.opacity = 0; baja.y = px(30); entra.restart() }
    transform: Translate { id: baja; y: 0 }
    ParallelAnimation {
        id: entra
        NumberAnimation { target: raiz; property: "opacity"; to: 1; duration: 450; easing.type: Easing.OutCubic }
        NumberAnimation { target: baja; property: "y"; to: 0; duration: 600; easing.type: Easing.OutBack; easing.overshoot: 1.05 }
    }

    // ------------------------------------------------------------------ la fila de pasos
    Item {
        id: filaPasos
        width: parent.width
        height: px(118)
        readonly property int n: raiz.pasos.length
        readonly property real margen: px(80)
        readonly property real r: px(25)
        function xDe(i) { return margen + (width - 2 * margen) * i / Math.max(1, n - 1) }

        // las lineas entre pasos
        Repeater {
            model: Math.max(0, filaPasos.n - 1)
            Item {
                readonly property string a: raiz.pasos[index].estado
                readonly property string b: raiz.pasos[index + 1].estado
                x: filaPasos.xDe(index) + filaPasos.r
                y: filaPasos.r + px(4) - height / 2
                width: filaPasos.xDe(index + 1) - filaPasos.xDe(index) - 2 * filaPasos.r
                height: px(4)
                Rectangle {
                    anchors.fill: parent
                    radius: height / 2
                    color: a === "hecho" ? raiz.verde : Qt.rgba(150 / 255, 165 / 255, 175 / 255, 0.43)
                    gradient: (a === "hecho" && b === "activo") ? haciaOro : null
                    Behavior on color { ColorAnimation { duration: 400 } }
                }
                Gradient {
                    id: haciaOro
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: raiz.verde }
                    GradientStop { position: 1; color: raiz.oro }
                }
                // una luz corre por la linea hacia el paso activo
                Rectangle {
                    visible: a === "hecho" && b === "activo"
                    width: px(30); height: width; radius: width / 2
                    y: (parent.height - height) / 2
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Qt.rgba(1, 0.95, 0.8, 0) }
                        GradientStop { position: 0.5; color: Qt.rgba(1, 0.95, 0.8, 0.95) }
                        GradientStop { position: 1; color: Qt.rgba(1, 0.95, 0.8, 0) }
                    }
                    NumberAnimation on x {
                        running: visible; loops: Animation.Infinite
                        from: -px(15); to: parent.width - px(15); duration: 1400; easing.type: Easing.InOutSine
                    }
                }
            }
        }

        // los circulos
        Repeater {
            model: raiz.pasos
            Item {
                id: paso
                readonly property string e: modelData.estado
                x: filaPasos.xDe(index) - width / 2
                y: 0
                width: px(200); height: filaPasos.height

                // halo
                Rectangle {
                    id: halo
                    width: filaPasos.r * 3.4; height: width; radius: width / 2
                    x: (paso.width - width) / 2; y: filaPasos.r + px(4) - height / 2
                    color: paso.e === "activo" ? raiz.oro : paso.e === "hecho" ? raiz.verde : "transparent"
                    opacity: paso.e === "activo" ? 0.22 : paso.e === "hecho" ? 0.14 : 0
                    SequentialAnimation on scale {
                        running: paso.e === "activo"; loops: Animation.Infinite
                        NumberAnimation { to: 1.15; duration: 780; easing.type: Easing.InOutSine }
                        NumberAnimation { to: 0.92; duration: 780; easing.type: Easing.InOutSine }
                    }
                }
                // la onda verde al quedar hecho
                Rectangle {
                    id: onda
                    width: filaPasos.r * 2; height: width; radius: width / 2
                    x: (paso.width - width) / 2; y: filaPasos.r + px(4) - height / 2
                    color: "transparent"; border.color: "#36F0A0"; border.width: px(4)
                    opacity: 0
                    ParallelAnimation {
                        id: ondaAnim
                        NumberAnimation { target: onda; property: "scale"; from: 1; to: 2.3; duration: 700; easing.type: Easing.OutCubic }
                        NumberAnimation { target: onda; property: "opacity"; from: 0.85; to: 0; duration: 700 }
                    }
                }
                onEChanged: if (e === "hecho") { ondaAnim.restart(); pop.restart() }

                // el circulo
                Rectangle {
                    id: circulo
                    width: filaPasos.r * 2; height: width; radius: width / 2
                    x: (paso.width - width) / 2; y: px(4)
                    color: paso.e === "hecho" ? raiz.verde : paso.e === "activo" ? "#1C180C"
                         : paso.e === "error" ? "#3A1414" : "transparent"
                    border.width: paso.e === "hecho" ? 0 : px(4)
                    border.color: paso.e === "activo" ? raiz.oro : paso.e === "error" ? "#E5534B"
                                : Qt.rgba(150 / 255, 165 / 255, 175 / 255, paso.e === "saltado" ? 0.25 : 0.55)
                    Behavior on color { ColorAnimation { duration: 300 } }
                    SequentialAnimation on scale {
                        id: pop; running: false
                        NumberAnimation { to: 1.25; duration: 160; easing.type: Easing.OutQuad }
                        SpringAnimation { to: 1.0; spring: 4; damping: 0.25 }
                    }
                    Image {
                        anchors.centerIn: parent
                        visible: paso.e === "hecho"
                        width: parent.width * 0.62; height: width
                        source: "image://icono/check/FFFFFF/" + Math.round(width)
                        sourceSize: Qt.size(width * 4, height * 4)
                    }
                    Text {
                        anchors.centerIn: parent
                        visible: paso.e === "error"
                        text: "!"; color: "#FF8A80"; font.family: raiz.familia; font.pixelSize: px(30); font.bold: true
                    }
                }
                // el arco que gira alrededor del activo
                Shape {
                    visible: paso.e === "activo"
                    width: filaPasos.r * 2.8; height: width
                    x: (paso.width - width) / 2; y: filaPasos.r + px(4) - height / 2
                    RotationAnimation on rotation { running: paso.e === "activo"; loops: Animation.Infinite; from: 0; to: 360; duration: 1600 }
                    ShapePath {
                        strokeColor: Qt.rgba(1, 0.92, 0.7, 0.9); strokeWidth: px(3); fillColor: "transparent"
                        capStyle: ShapePath.RoundCap
                        PathAngleArc { centerX: filaPasos.r * 1.4; centerY: filaPasos.r * 1.4
                            radiusX: filaPasos.r * 1.36; radiusY: filaPasos.r * 1.36; startAngle: 0; sweepAngle: 80 }
                    }
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: filaPasos.r * 2 + px(22)
                    text: modelData.nombre
                    font.family: raiz.familia; font.pixelSize: px(32); font.weight: Font.Medium
                    color: paso.e === "activo" ? "#F3D58C" : paso.e === "hecho" ? "#E6EEF0"
                         : paso.e === "error" ? "#FF8A80" : raiz.tenue
                    Behavior on color { ColorAnimation { duration: 300 } }
                }
            }
        }
    }

    // ------------------------------------------------------------------ las versiones
    Rectangle {
        id: tarjeta
        y: filaPasos.height + px(40)
        width: parent.width
        height: columna.height + px(16) + px(26)
        radius: px(28)
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, 0.12)
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.rgba(20 / 255, 44 / 255, 50 / 255, 0.88) }
            GradientStop { position: 1; color: Qt.rgba(8 / 255, 22 / 255, 28 / 255, 0.90) }
        }
        Column {
            id: columna
            x: px(44); y: px(16)
            width: parent.width - px(84)
            Repeater {
                model: raiz.versiones
                Fila { width: columna.width; dato: modelData; ultima: index === raiz.versiones.length - 1 }
            }
            Rectangle { width: parent.width; height: 1; color: Qt.rgba(1, 1, 1, 0.10) }
            Item {
                width: parent.width; height: px(24) + pie.height
                Row {
                    id: pie
                    y: px(24); spacing: px(20)
                    width: parent.width
                    Image {
                        anchors.verticalCenter: parent.verticalCenter
                        width: px(46); height: width
                        source: "image://icono/reloj/E2B04F/" + width
                        sourceSize: Qt.size(width * 4, height * 4)
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        width: pie.width - px(46) - botonCancelar.width - px(60)
                        text: raiz.eta; textFormat: Text.RichText
                        color: "#F1F5F6"; font.family: raiz.familia; font.pixelSize: px(36)
                    }
                    Rectangle {
                        id: botonCancelar
                        anchors.verticalCenter: parent.verticalCenter
                        width: textoCancelar.implicitWidth + px(80); height: px(84)
                        radius: px(14)
                        color: zonaC.containsMouse && raiz.cancelarActivo ? Qt.rgba(226 / 255, 176 / 255, 79 / 255, 0.16) : Qt.rgba(1, 1, 1, 0.04)
                        border.width: 1
                        border.color: Qt.rgba(226 / 255, 176 / 255, 79 / 255, raiz.cancelarActivo ? 0.75 : 0.25)
                        opacity: raiz.cancelarActivo ? 1 : 0.55
                        scale: zonaC.pressed ? 0.96 : 1
                        Behavior on scale { SpringAnimation { spring: 5; damping: 0.3 } }
                        Behavior on color { ColorAnimation { duration: 180 } }
                        Text { id: textoCancelar; anchors.centerIn: parent; text: raiz.cancelarTexto
                            color: "#F1F5F6"; font.family: raiz.familia; font.pixelSize: px(32); font.weight: Font.DemiBold }
                        MouseArea { id: zonaC; anchors.fill: parent; hoverEnabled: true
                            enabled: raiz.cancelarActivo; cursorShape: Qt.PointingHandCursor
                            onClicked: raiz.cancelarClic() }
                    }
                }
            }
        }
    }

    // una version: claqueta, «15 min · 62% · plano 87 de 140», barra y palomita
    component Fila: Item {
        id: fila
        property var dato: ({})
        property bool ultima: false
        readonly property string e: dato.estado || "cola"
        readonly property real meta: (e === "listo" || e === "armada") ? 1.0 : (e === "render" || e === "armando") ? (dato.pct || 0) : 0
        property real visto: meta
        Behavior on visto { NumberAnimation { duration: 900; easing.type: Easing.OutCubic } }
        height: raiz.versiones.length > 4 ? px(66) : px(82)     // (19-nov) con muchas (tráileres + plantillas) caben

        Image {
            x: px(26 - 44 + 26); anchors.verticalCenter: parent.verticalCenter
            width: px(50); height: width
            source: "image://icono/claqueta/C9D6DA/" + width
            sourceSize: Qt.size(width * 4, height * 4)
        }
        Text {
            x: px(110 - 44); anchors.verticalCenter: parent.verticalCenter
            width: fila.width * 0.40 - x - px(10)
            elide: Text.ElideRight
            textFormat: Text.StyledText
            font.family: raiz.familia; font.pixelSize: px(34); font.weight: Font.Medium
            color: "#F1F5F6"
            readonly property string nombre: /\dmin$/.test(dato.etq || "") ? (dato.etq || "").replace("min", " min").replace("VERTICAL", "Vertical") : (dato.etq || "").charAt(0) + (dato.etq || "").slice(1).toLowerCase()
            readonly property string colorEstado: (e === "listo" || e === "armada") ? "#4ADE9A" : e === "error" ? "#FF8A80"
                                                  : e === "armando" ? "#E2B04F" : e === "render" ? "#FFFFFF" : "#8FB3C4"
            text: nombre + "  ·  <font color='" + colorEstado + "'>" + (e === "render" ? "<b>" + dato.texto + "</b>" : dato.texto)
                  + "</font>" + (e === "render" && dato.detalle ? "  ·  <font color='#8FB3C4'>" + dato.detalle + "</font>" : "")
        }
        // la barra
        Rectangle {
            id: barra
            x: fila.width * 0.40; anchors.verticalCenter: parent.verticalCenter
            width: fila.width * 0.50; height: px(16); radius: height / 2
            color: Qt.rgba(120 / 255, 140 / 255, 150 / 255, 0.27)
            clip: true
            Rectangle {               // lo hecho, en verde, con un brillo que lo recorre
                id: llena
                visible: fila.visto > 0.001
                height: parent.height; radius: height / 2
                width: Math.max(height, parent.width * fila.visto)
                gradient: Gradient {
                    GradientStop { position: 0; color: "#3BEE9F" }
                    GradientStop { position: 1; color: "#16B06E" }
                }
                Rectangle {
                    visible: fila.e === "render" || fila.e === "armando"
                    width: Math.max(parent.height * 4, parent.width * 0.25); height: parent.height
                    gradient: Gradient { orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Qt.rgba(1, 1, 1, 0) }
                        GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.47) }
                        GradientStop { position: 1; color: Qt.rgba(1, 1, 1, 0) } }
                    NumberAnimation on x { running: parent.visible; loops: Animation.Infinite
                        from: -width; to: llena.width + width; duration: 1800 }
                }
            }
            Rectangle {               // «Armando…» sin porcentaje: una luz dorada que va y viene
                visible: fila.e === "armando" && (fila.dato.pct || 0) <= 0.001
                width: parent.width * 0.22; height: parent.height; radius: height / 2
                gradient: Gradient { orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Qt.rgba(226 / 255, 176 / 255, 79 / 255, 0) }
                    GradientStop { position: 0.5; color: Qt.rgba(246 / 255, 210 / 255, 122 / 255, 0.9) }
                    GradientStop { position: 1; color: Qt.rgba(226 / 255, 176 / 255, 79 / 255, 0) } }
                SequentialAnimation on x { running: parent.visible; loops: Animation.Infinite
                    NumberAnimation { from: 0; to: barra.width * 0.78; duration: 1300; easing.type: Easing.InOutSine }
                    NumberAnimation { from: barra.width * 0.78; to: 0; duration: 1300; easing.type: Easing.InOutSine } }
            }
        }
        // la palomita aparece con un rebote; el error, una cruz roja
        Image {
            id: palomita
            x: fila.width - px(80 - 40); anchors.verticalCenter: parent.verticalCenter
            width: px(44); height: width
            source: fila.e === "error" ? "image://icono/x/FF8A80/" + width : "image://icono/check/2FD98F/" + width
            sourceSize: Qt.size(width * 4, height * 4)
            scale: (fila.e === "listo" || fila.e === "error") ? 1 : 0
            Behavior on scale { SpringAnimation { spring: 3.5; damping: 0.22 } }
        }
        Rectangle {
            visible: !fila.ultima
            anchors.bottom: parent.bottom; width: parent.width; height: 1
            color: Qt.rgba(1, 1, 1, 0.10)
        }
    }
}
