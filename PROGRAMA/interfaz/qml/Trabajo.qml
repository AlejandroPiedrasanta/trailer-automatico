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
    property var pasos: []            // [{clave, nombre, estado, detalle, tiempo, pct, desde}]
    property var versiones: []        // [{etq, estado, texto, pct, detalle}]
    property string eta: ""
    property string cancelarTexto: "Cancelar"
    property bool cancelarActivo: true
    // (23-nov, la persona: «no sé si está avanzando... que indique el proceso de cada paso») lo que hace ahora, desde
    // cuando trabaja (ms de la epoca; 0 = ya no) y el reloj que cuenta los segundos (aqui: Python no avisa cada segundo)
    property string ahora: ""
    property double inicio: 0
    property double ahoraMs: Date.now()
    signal cancelarClic()
    function px(v) { return Math.round(v * escala) }
    function reloj(ms) {
        var s = Math.max(0, Math.floor(ms / 1000)), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60
        return (h > 0 ? h + ":" + (m < 10 ? "0" : "") + m : "" + m) + ":" + (x < 10 ? "0" : "") + x
    }
    Timer {
        interval: 1000; repeat: true; triggeredOnStart: true
        running: raiz.inicio > 0 && raiz.visible
        onTriggered: raiz.ahoraMs = Date.now()
    }

    // (1.7.8, auditoria de animaciones) Python manda una lista NUEVA en cada aviso: con la lista directa como modelo el Repeater
    // rehacia todas las filas y nada se animaba (la barra saltaba, el brillo y el arco volvian a 0, la palomita no
    // aparecia). Ahora las filas se ACTUALIZAN en su sitio (ListModel.set) y solo se rehacen si cambia cuantas son.
    // Cada fila lleva siempre todos los campos (ListModel guarda el valor viejo si falta uno).
    ListModel { id: mPasos }
    ListModel { id: mVers }
    function _norm(o, campos) { var r = {}; for (var k in campos) r[k] = (o && o[k] !== undefined && o[k] !== null) ? o[k] : campos[k]; return r }
    function _sync(m, l, campos) {
        l = l || []
        if (m.count !== l.length) { m.clear(); for (var i = 0; i < l.length; i++) m.append(_norm(l[i], campos)) }
        else for (var j = 0; j < l.length; j++) m.set(j, _norm(l[j], campos))
    }
    onPasosChanged: _sync(mPasos, pasos, { "clave": "", "nombre": "", "estado": "pendiente", "detalle": "",
                                           "tiempo": "", "pct": -1.0, "desde": 0.0 })
    onVersionesChanged: _sync(mVers, versiones, { "etq": "", "estado": "cola", "texto": "", "pct": 0.0, "detalle": "" })

    readonly property color oro: "#E2B04F"
    readonly property color verde: "#22C47E"
    readonly property color tenue: "#9DB0B6"
    implicitHeight: tarjeta.y + tarjeta.height

    // al empezar a trabajar: los pasos y las versiones aparecen subiendo (Python llama entrar())
    function entrar() { raiz.opacity = 0; baja.y = (typeof quieto !== "undefined" && quieto) ? 0 : px(14); entra.restart() }
    transform: Translate { id: baja; y: 0 }
    ParallelAnimation {
        id: entra
        NumberAnimation { target: raiz; property: "opacity"; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { target: baja; property: "y"; to: 0; duration: 280; easing.type: Easing.OutQuint }
    }

    // ------------------------------------------------------------------ la fila de pasos
    Item {
        id: filaPasos
        width: parent.width
        height: px(200)                   // (23-nov) + el detalle y el tiempo de cada paso
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
                    // (1.7.9) por FRACCION del tramo: con «to: parent.width» el recorrido se fijaba al empezar y, si la
                    // ventana cambiaba de tamaño, la luz se salia de la linea (quedaba una media luna junto a «Listo»)
                    property real f: 0
                    x: -px(15) + f * parent.width
                    NumberAnimation on f {
                        running: (visible) && (typeof quieto === "undefined" || !quieto); loops: Animation.Infinite
                        from: 0; to: 1; duration: 1400; easing.type: Easing.InOutSine
                    }
                }
            }
        }

        // los circulos
        Repeater {
            model: mPasos
            Item {
                id: paso
                readonly property string e: model.estado
                x: filaPasos.xDe(index) - width / 2
                y: 0
                width: px(200); height: filaPasos.height

                // halo
                Rectangle {
                    id: halo
                    width: filaPasos.r * 3.4; height: width; radius: width / 2
                    x: (paso.width - width) / 2; y: filaPasos.r + px(4) - height / 2
                    color: paso.e === "activo" ? raiz.oro : paso.e === "hecho" ? raiz.verde : "transparent"
                    Behavior on color { ColorAnimation { duration: 300; easing.type: Easing.OutCubic } }
                    opacity: paso.e === "activo" ? 0.22 : paso.e === "hecho" ? 0.14 : 0
                    Behavior on opacity { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
                    // (1.8.4, auditoria) el latido va en «pulso»: al dejar de estar activo el halo VUELVE a 1 suave
                    // (antes se quedaba congelado a mitad del latido, p. ej. en 1,13, y el color saltaba de golpe)
                    readonly property bool _quieto: typeof quieto !== "undefined" && quieto
                    property real pulso: 1
                    scale: paso.e === "activo" && !_quieto ? pulso : 1
                    Behavior on scale { enabled: paso.e !== "activo"; NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
                    SequentialAnimation on pulso {
                        running: paso.e === "activo" && !halo._quieto; loops: Animation.Infinite
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
                        NumberAnimation { target: onda; property: "opacity"; from: 0.85; to: 0; duration: 700; easing.type: Easing.OutQuad }
                    }
                }
                onEChanged: if (e === "hecho" && !(typeof quieto !== "undefined" && quieto)) { ondaAnim.restart(); pop.restart() }

                // el circulo
                Rectangle {
                    id: circulo
                    width: filaPasos.r * 2; height: width; radius: width / 2
                    x: (paso.width - width) / 2; y: px(4)
                    color: paso.e === "hecho" ? raiz.verde : paso.e === "activo" ? "#1C180C"
                         : paso.e === "error" ? "#3A1414" : "transparent"
                    border.width: paso.e === "hecho" ? 0 : px(4)
                    // (23-nov) con cuenta, el filo del activo queda tenue y encima se llena el aro de su avance
                    border.color: paso.e === "activo" ? (model.pct >= 0 ? Qt.rgba(0.886, 0.69, 0.31, 0.34) : raiz.oro)
                                : paso.e === "error" ? "#E5534B"
                                : Qt.rgba(150 / 255, 165 / 255, 175 / 255, paso.e === "saltado" ? 0.25 : 0.55)
                    Behavior on color { ColorAnimation { duration: 300 } }
                    SequentialAnimation on scale {
                        id: pop; running: false
                        NumberAnimation { to: 1.25; duration: 160; easing.type: Easing.OutQuad }
                        // (1.8.4) asienta en 260 ms como los botones (el resorte tardaba mas de 1 s)
                        NumberAnimation { to: 1.0; duration: 260; easing.type: Easing.OutBack; easing.overshoot: 1.6 }
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
                    opacity: paso.e === "activo" ? 1 : 0           // (1.8.4) aparece y se va fundiendose
                    Behavior on opacity { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
                    visible: opacity > 0.01
                    width: filaPasos.r * 2.8; height: width
                    x: (paso.width - width) / 2; y: filaPasos.r + px(4) - height / 2
                    RotationAnimation on rotation { running: paso.e === "activo" && !(typeof quieto !== "undefined" && quieto); loops: Animation.Infinite; from: 0; to: 360; duration: 1600 }
                    ShapePath {
                        strokeColor: Qt.rgba(1, 0.92, 0.7, 0.9); strokeWidth: px(3); fillColor: "transparent"
                        capStyle: ShapePath.RoundCap
                        PathAngleArc { centerX: filaPasos.r * 1.4; centerY: filaPasos.r * 1.4
                            radiusX: filaPasos.r * 1.36; radiusY: filaPasos.r * 1.36; startAngle: 0; sweepAngle: 80 }
                    }
                }
                // (23-nov) el avance del paso que corre: un aro que se llena sobre el circulo (solo si hay cuenta)
                Shape {
                    id: aro
                    readonly property real meta: paso.e === "activo" && model.pct >= 0 ? model.pct : 0
                    property real visto: meta
                    Behavior on visto { NumberAnimation { duration: 700; easing.type: Easing.OutCubic } }
                    opacity: paso.e === "activo" && model.pct >= 0 ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
                    visible: opacity > 0.01
                    width: filaPasos.r * 2; height: width
                    x: (paso.width - width) / 2; y: px(4)
                    ShapePath {
                        strokeColor: "#FFE3A0"; strokeWidth: px(4); fillColor: "transparent"
                        capStyle: ShapePath.RoundCap
                        PathAngleArc { centerX: filaPasos.r; centerY: filaPasos.r
                            radiusX: filaPasos.r - px(2); radiusY: filaPasos.r - px(2)
                            startAngle: -90; sweepAngle: 360 * Math.max(0.002, Math.min(1, aro.visto)) }
                    }
                }
                Text {
                    id: nombrePaso
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: filaPasos.r * 2 + px(22)
                    text: model.nombre
                    font.family: raiz.familia; font.pixelSize: px(32); font.weight: Font.Medium
                    color: paso.e === "activo" ? "#F3D58C" : paso.e === "hecho" ? "#E6EEF0"
                         : paso.e === "error" ? "#FF8A80" : raiz.tenue
                    Behavior on color { ColorAnimation { duration: 300 } }
                }
                // (23-nov) debajo: lo que lleva («40 de 57», «62 %», «654 archivos») y su tiempo (el activo cuenta)
                Text {
                    id: detallePaso
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: paso.width - px(8); horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                    y: nombrePaso.y + px(44)
                    text: model.detalle
                    font.family: raiz.familia; font.pixelSize: px(26); font.weight: Font.DemiBold
                    color: paso.e === "activo" ? "#E9C77A" : paso.e === "error" ? "#FF8A80" : "#B9C6C9"
                    opacity: text ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: detallePaso.y + px(34)
                    text: paso.e === "activo" && model.desde > 0 ? raiz.reloj(raiz.ahoraMs - model.desde) : model.tiempo
                    font.family: raiz.familia; font.pixelSize: px(24)
                    color: raiz.tenue
                    opacity: text ? 0.95 : 0
                    Behavior on opacity { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
                }
            }
        }
    }

    // ------------------------------------------------------------------ (23-nov) lo que esta haciendo ahora
    Item {
        id: filaAhora
        y: filaPasos.height + px(4)
        width: parent.width
        height: px(56)
        opacity: raiz.ahora ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
        Row {
            anchors.centerIn: parent
            spacing: px(16)
            Rectangle {                        // late mientras trabaja: esta vivo aunque una linea tarde en llegar
                id: latido
                anchors.verticalCenter: parent.verticalCenter
                width: px(14); height: width; radius: width / 2
                color: raiz.oro
                readonly property bool vivo: raiz.inicio > 0 && raiz.visible && !(typeof quieto !== "undefined" && quieto)
                SequentialAnimation on opacity {
                    running: latido.vivo; loops: Animation.Infinite
                    NumberAnimation { to: 0.25; duration: 700; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 1.0; duration: 700; easing.type: Easing.InOutSine }
                }
            }
            Text {
                id: textoAhora
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(implicitWidth, filaAhora.width - px(220))
                elide: Text.ElideRight
                text: raiz.ahora
                font.family: raiz.familia; font.pixelSize: px(30)
                color: "#DDE6E8"
                // cada cosa nueva entra aclarandose (se nota que cambio)
                onTextChanged: if (!(typeof quieto !== "undefined" && quieto)) entraAhora.restart()
                NumberAnimation on opacity { id: entraAhora; running: false; from: 0.3; to: 1; duration: 260
                                             easing.type: Easing.OutCubic }
            }
        }
    }

    // ------------------------------------------------------------------ las versiones
    Rectangle {
        id: tarjeta
        y: filaAhora.y + filaAhora.height + px(22)
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
                model: mVers
                Fila { width: columna.width; dato: model; ultima: index === mVers.count - 1 }
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
                        width: pie.width - px(46) - botonCancelar.width - px(40)      // (1.7.9) «Cancelar» al mismo borde que las palomitas
                        // (23-nov) «Lleva 12:34 · Listo a las 21:05 · faltan 18 min»: el reloj cuenta cada segundo
                        text: (raiz.inicio > 0 ? "Lleva <b>" + raiz.reloj(raiz.ahoraMs - raiz.inicio) + "</b>"
                               + (raiz.eta ? "  ·  " : "") : "") + raiz.eta
                        textFormat: Text.RichText
                        color: "#F1F5F6"; font.family: raiz.familia; font.pixelSize: px(36)
                    }
                    Rectangle {
                        id: botonCancelar
                        anchors.verticalCenter: parent.verticalCenter
                        width: textoCancelar.implicitWidth + px(80); height: px(84)
                        radius: height / 2
                        color: "transparent"      // (1.7.8) vidrio liquido
                        Vidrio { anchors.fill: parent; radio: parent.radius; tinteA: 0.07; encima: zonaC.containsMouse && raiz.cancelarActivo; apretado: zonaC.pressed }
                        opacity: raiz.cancelarActivo ? 1 : 0.55
                        scale: zonaC.pressed ? 0.96 : 1
                        Behavior on scale { NumberAnimation { duration: zonaC.pressed ? 90 : 300; easing.type: zonaC.pressed || (typeof quieto !== "undefined" && quieto) ? Easing.OutQuad : Easing.OutBack; easing.overshoot: 2.2 } }
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
            x: 0; anchors.verticalCenter: parent.verticalCenter      // (1.7.9) mismo borde que el reloj del pie
            width: px(46); height: width
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
            // (1.7.8) el porcentaje CUENTA con la barra (va con «visto», que se mueve suave) en vez de saltar
            function contar(s) { return (s || "").replace(/(\d+)(\s*%)/, function(m, n, sp) { return Math.round(fila.visto * 100) + sp }) }
            text: nombre + "  ·  <font color='" + colorEstado + "'>" + (e === "render" ? "<b>" + contar(dato.texto) + "</b>" : dato.texto)
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
                // (1.7.9) del color de su estado: dorada mientras arma (como su texto), verde al renderizar y lista
                readonly property bool oro: fila.e === "armando"
                gradient: Gradient {
                    GradientStop { position: 0; color: llena.oro ? "#F6D27A" : "#3BEE9F" }
                    GradientStop { position: 1; color: llena.oro ? "#C9952E" : "#16B06E" }
                }
                Rectangle {
                    visible: fila.e === "render" || fila.e === "armando"
                    width: Math.max(parent.height * 4, parent.width * 0.25); height: parent.height
                    gradient: Gradient { orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Qt.rgba(1, 1, 1, 0) }
                        GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.47) }
                        GradientStop { position: 1; color: Qt.rgba(1, 1, 1, 0) } }
                    // (1.7.9) por fraccion: sigue a la barra aunque crezca (antes el recorrido quedaba fijo al empezar)
                    property real f: 0
                    x: -width + f * (llena.width + 2 * width)
                    NumberAnimation on f { running: parent.visible && (typeof quieto === "undefined" || !quieto); loops: Animation.Infinite; from: 0; to: 1; duration: 1800 }   // (1.8.4) brillo de adorno: fuera con movimiento reducido
                }
            }
            Rectangle {               // «Armando…» sin porcentaje: una luz dorada que va y viene
                visible: fila.e === "armando" && (fila.dato.pct || 0) <= 0.001
                width: parent.width * 0.22; height: parent.height; radius: height / 2
                gradient: Gradient { orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Qt.rgba(226 / 255, 176 / 255, 79 / 255, 0) }
                    GradientStop { position: 0.5; color: Qt.rgba(246 / 255, 210 / 255, 122 / 255, 0.9) }
                    GradientStop { position: 1; color: Qt.rgba(226 / 255, 176 / 255, 79 / 255, 0) } }
                property real f: 0
                x: f * barra.width * 0.78
                SequentialAnimation on f { running: parent.visible; loops: Animation.Infinite
                    NumberAnimation { from: 0; to: 1; duration: 1300; easing.type: Easing.InOutSine }
                    NumberAnimation { from: 1; to: 0; duration: 1300; easing.type: Easing.InOutSine } }
            }
        }
        // la palomita aparece con un rebote; el error, una cruz roja
        Image {
            id: palomita
            x: fila.width - width; anchors.verticalCenter: parent.verticalCenter      // (1.7.9) no se sale de la columna
            width: px(44); height: width
            source: fila.e === "error" ? "image://icono/x/FF8A80/" + width : "image://icono/check/2FD98F/" + width
            sourceSize: Qt.size(width * 4, height * 4)
            scale: (fila.e === "listo" || fila.e === "error") ? 1 : 0
            Behavior on scale { NumberAnimation { duration: 220; easing.type: Easing.OutBack; easing.overshoot: 1.6 } }
        }
        Rectangle {
            visible: !fila.ultima
            anchors.bottom: parent.bottom; width: parent.width; height: 1
            color: Qt.rgba(1, 1, 1, 0.10)
        }
    }
}
