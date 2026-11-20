// (1.7, parte 4) Pagina Tráilers: «Elige el estilo». (1.7.9, la persona eligio la propuesta B) La musica en PORTADAS
// en carrusel: la del centro es la elegida (clic en una de los lados, arrastrar o la rueda del raton), con su ▶ para
// oirla; un disco gira despacio solo en la elegida. La intro, en pastillas con sus 8 fotos latiendo a su ritmo.
// Python (PaginaQML) pone d = {estilos, estilo, intros, intro} y hace accion("estilo"|"oir"|"intro"|"ver_intro", i).
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
        carrusel.alDato()
    }
    function px(v) { return Math.round(v * escala) }
    function entrar(dx) { opacity = 0; baja.x = (dx || 0) * px(60); baja.y = dx ? 0 : px(14); entra.restart() }   // (1.7.8) dx: +1 entra desde la derecha (pestaña de mas adelante), -1 desde la izquierda
    transform: Translate { id: baja }
    ParallelAnimation { id: entra
        NumberAnimation { target: raiz; property: "opacity"; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { target: baja; property: "y"; to: 0; duration: 280; easing.type: Easing.OutQuint }
        NumberAnimation { target: baja; property: "x"; to: 0; duration: 300; easing.type: Easing.OutQuint } }

    implicitHeight: col.implicitHeight + px(60)

    // icono, descripcion y los dos colores de la portada de cada estilo
    readonly property var info: ({
        "auto": ["brillo", "El que le va al tipo de evento", "#2BD08C", "#0B4A3B"],
        "cine latino": ["pelicula", "Épica y cálida, de película", "#E2B04F", "#6B3410"],
        "juvenil": ["fiesta", "Ritmo y energía para bailar", "#D4537E", "#3C3489"],
        "clásico": ["nota", "Cuerdas y piano, elegante", "#85B7EB", "#173C6E"],
        "emotivo": ["corazon", "Suave, para emocionar", "#F0997B", "#7A2E16"],
        "plantilla": ["claqueta", "Las canciones de la plantilla", "#8C8A82", "#2E2E2C"]
    })
    readonly property var ritmos: ({ "rampa": [5, 5, 5, 5, 5, 5, 5, 5], "acelera": [9, 7, 6, 5, 4, 4, 3, 2],
                                     "frena": [2, 3, 4, 4, 5, 6, 7, 9], "latido": [7, 3, 7, 3, 7, 3, 7, 3] })
    readonly property var textosIntro: ({ "rampa": "Una foto cada 5 cuadros", "acelera": "De lenta a rápida",
                                          "frena": "Ráfaga que se frena", "latido": "De dos en dos" })

    Column {
        id: col
        width: Math.min(parent.width - px(120), px(1700))
        anchors.horizontalCenter: parent.horizontalCenter
        y: px(36)
        spacing: px(14)

        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Elige el estilo"; color: "white"
            font.family: raiz.familia; font.pixelSize: px(72); font.weight: Font.Bold }
        Text { anchors.horizontalCenter: parent.horizontalCenter; color: "#9DB0B6"
            text: "La portada del centro es la elegida: haz clic en otra, arrástralas o usa la rueda. Con ▶ la escuchas."
            font.family: raiz.familia; font.pixelSize: px(30) }
        Item { width: 1; height: px(4) }

        Item { width: col.width; height: px(84)      // (1.7.9) misma altura que «TUS PLANTILLAS»
            Seccion { anchors.verticalCenter: parent.verticalCenter; texto: "Música"; icono: "nota" } }

        // ---------------------------------------------------------------- el carrusel de portadas
        PathView {
            id: carrusel
            width: col.width; height: px(530)
            model: raiz.estilosL
            pathItemCount: Math.min(5, Math.max(1, count))
            preferredHighlightBegin: 0.5; preferredHighlightEnd: 0.5
            highlightRangeMode: PathView.StrictlyEnforceRange
            highlightMoveDuration: 320
            interactive: count > 1
            clip: false
            property bool _sync: false
            // Python manda la elegida: el carrusel va a ella (sin volver a avisar)
            function alDato() {
                var e = raiz.d.estilo
                if (e === undefined || e < 0 || e >= count || moving || e === currentIndex) return
                _sync = true; currentIndex = e; _sync = false
            }
            function elegir(i) {
                if (i < 0 || i >= count) return
                if (i !== currentIndex) currentIndex = i
                if (i !== raiz.d.estilo) raiz.accion("estilo", i)
            }
            onCountChanged: alDato()
            onMovementEnded: elegir(currentIndex)          // al soltar un arrastre: la que quedo al centro
            Keys.onLeftPressed: elegir((currentIndex - 1 + count) % count)
            Keys.onRightPressed: elegir((currentIndex + 1) % count)

            path: Path {
                startX: 0; startY: carrusel.height / 2
                PathAttribute { name: "esc"; value: 0.62 }
                PathAttribute { name: "opa"; value: 0.30 }
                PathAttribute { name: "capa"; value: 0 }
                PathLine { x: carrusel.width / 2; y: carrusel.height / 2 }
                PathAttribute { name: "esc"; value: 1.0 }
                PathAttribute { name: "opa"; value: 1.0 }
                PathAttribute { name: "capa"; value: 10 }
                PathLine { x: carrusel.width; y: carrusel.height / 2 }
                PathAttribute { name: "esc"; value: 0.62 }
                PathAttribute { name: "opa"; value: 0.30 }
                PathAttribute { name: "capa"; value: 0 }
            }
            delegate: Portada {
                nombre: modelData
                lado: { var n = carrusel.count; var d = (index - carrusel.currentIndex + n) % n; return d === 0 ? 0 : (d <= n / 2 ? 1 : -1) }
                elegida: PathView.isCurrentItem
                scale: PathView.esc === undefined ? 1 : PathView.esc
                opacity: PathView.opa === undefined ? 1 : PathView.opa
                z: PathView.capa === undefined ? 0 : PathView.capa
                onTocar: carrusel.elegir(index)
                onOir: { carrusel.elegir(index); raiz.accion("oir", index) }
            }
        }
        // los puntos: donde esta la elegida
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: px(12)
            Repeater {
                model: carrusel.count
                Rectangle {
                    height: px(12); radius: height / 2
                    width: index === carrusel.currentIndex ? px(44) : px(12)
                    color: index === carrusel.currentIndex ? "#3BEE9F" : Qt.rgba(1, 1, 1, 0.25)
                    Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                    Behavior on color { ColorAnimation { duration: 220 } }
                    MouseArea { anchors.fill: parent; anchors.margins: -px(8); cursorShape: Qt.PointingHandCursor
                        onClicked: carrusel.elegir(index) }
                }
            }
        }
        Item { width: 1; height: px(10) }

        // ---------------------------------------------------------------- la intro, en pastillas
        Seccion { texto: "Intro"; icono: "brillo" }
        Row {
            id: filaIntros
            spacing: px(22)
            readonly property real ancho: (col.width - spacing * 3) / 4
            Repeater {
                model: raiz.introsL
                Pastilla {
                    width: filaIntros.ancho; height: px(176)
                    readonly property string clave: modelData.toLowerCase()
                    titulo: modelData; descripcion: raiz.textosIntro[clave] || ""
                    elegida: raiz.d.intro === index
                    ritmo: raiz.ritmos[clave] || [5, 5, 5, 5, 5, 5, 5, 5]
                    retraso: 200 + Math.min(index, 6) * 40
                    onElegir: raiz.accion("intro", index)
                    onVer: raiz.accion("ver_intro", index)
                }
            }
        }
    }

    // la rueda, sobre todo el carrusel (solo la rueda: el arrastre y los clics siguen llegando a las portadas)
    MouseArea {
        x: col.x + carrusel.x; y: col.y + carrusel.y
        width: carrusel.width; height: carrusel.height
        acceptedButtons: Qt.NoButton
        property real _acum: 0
        onWheel: function(ev) {
            _acum += ev.angleDelta.y !== 0 ? ev.angleDelta.y : -ev.angleDelta.x
            if (Math.abs(_acum) < 120) return
            var paso = _acum > 0 ? -1 : 1
            _acum = 0
            carrusel.elegir((carrusel.currentIndex + paso + carrusel.count) % carrusel.count)
        }
    }

    component Seccion: Row {
        property string texto: ""
        property string icono: ""
        spacing: px(18)
        // (1.7.8, auditoria) rotulo de seccion: mas chico que los titulos, en versalitas doradas
        Image { anchors.verticalCenter: parent.verticalCenter; width: px(34); height: width
            source: "image://icono/" + parent.icono + "/E2B04F/" + width; sourceSize: Qt.size(width * 4, height * 4) }
        Text { anchors.verticalCenter: parent.verticalCenter; text: parent.texto; color: "#E2B04F"
            font.family: raiz.familia; font.pixelSize: px(30); font.weight: Font.DemiBold
            font.capitalization: Font.AllUppercase; font.letterSpacing: px(4) }
    }

    // ------------------------------------------------------------------ una portada de disco
    component Portada: Item {
        id: p
        property string nombre: ""
        property int lado: 0              // (1.7.9) -1 a la izquierda del centro, 1 a la derecha
        property bool elegida: false
        signal tocar()
        signal oir()
        readonly property var dato: raiz.info[p.nombre.toLowerCase()] || ["nota", "", "#2BD08C", "#0B4A3B"]
        width: px(400); height: px(500)
        HoverHandler { id: hvP }

        Item {
            id: cuerpo
            anchors.fill: parent
            // (1.7.8) se inclina hacia el raton (perspectiva) y vuelve suave al salir
            property real _ry: hvP.hovered && !_quieto ? (hvP.point.position.x / Math.max(1, width) - 0.5) * -14 : 0
            property real _rx: hvP.hovered && !_quieto ? (hvP.point.position.y / Math.max(1, height) - 0.5) * 10 : 0
            readonly property bool _quieto: typeof quieto !== "undefined" && quieto
            Behavior on _ry { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
            Behavior on _rx { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
            transform: [
                Rotation { origin.x: width / 2; origin.y: height / 2; axis { x: 0; y: 1; z: 0 } angle: _ry },
                Rotation { origin.x: width / 2; origin.y: height / 2; axis { x: 1; y: 0; z: 0 } angle: _rx }
            ]
            y: zona.containsMouse && !p.elegida ? -px(8) : 0
            Behavior on y { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
            scale: zona.pressed ? 0.98 : 1
            Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

            // el halo verde de la elegida
            Rectangle { anchors.fill: parent; anchors.margins: -px(14); radius: px(46); color: "transparent"
                border.width: px(14); border.color: "#22C47E"
                opacity: p.elegida ? 0.20 : 0; Behavior on opacity { NumberAnimation { duration: 240 } } }

            Rectangle {
                id: tapa
                anchors.fill: parent
                radius: px(32)
                clip: true
                border.width: p.elegida ? px(4) : 1
                border.color: p.elegida ? "#3BEE9F" : Qt.rgba(1, 1, 1, 0.18)
                Behavior on border.color { ColorAnimation { duration: 200 } }
                gradient: Gradient {
                    GradientStop { position: 0.0; color: p.dato[2] }
                    GradientStop { position: 1.0; color: p.dato[3] }
                }
                // el disco de vinilo que asoma: gira despacio solo en la elegida
                Item {
                    x: parent.width * 0.38; y: parent.height * 0.30
                    width: parent.width * 0.95; height: width
                    opacity: 0.22
                    Rectangle { anchors.fill: parent; radius: width / 2; color: "#0A0A0A" }
                    Repeater { model: 4
                        Rectangle { anchors.centerIn: parent; width: parent.width * (0.86 - index * 0.14); height: width
                            radius: width / 2; color: "transparent"; border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.35) } }
                    Rectangle { anchors.centerIn: parent; width: parent.width * 0.30; height: width; radius: width / 2
                        color: p.dato[2] }
                    Rectangle { x: parent.width * 0.5 - width / 2; y: parent.height * 0.18; width: px(10); height: parent.height * 0.12
                        radius: width / 2; color: Qt.rgba(1, 1, 1, 0.6) }
                    RotationAnimation on rotation { running: (p.elegida && p.visible) && (typeof quieto === "undefined" || !quieto); loops: Animation.Infinite
                        from: 0; to: 360; duration: 14000 }
                }
                // el icono grande del estilo
                Image {
                    x: px(40); y: px(40); width: px(120); height: width
                    source: "image://icono/" + p.dato[0] + "/FFFFFF/" + width
                    sourceSize: Qt.size(width * 4, height * 4)
                    opacity: 0.95
                }
                // (1.7.8) el reflejo que cruza la portada siguiendo al cursor
                Rectangle {
                    width: parent.width * 0.5; height: parent.height * 2
                    y: -parent.height * 0.5; rotation: 22
                    x: (hvP.hovered ? hvP.point.position.x : -parent.width) - width / 2
                    Behavior on x { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
                    opacity: hvP.hovered ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: 220 } }
                    gradient: Gradient { orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0) }
                        GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.16) }
                        GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) } }
                }
                // sombra abajo para que el titulo se lea sobre cualquier color
                Rectangle {
                    anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                    height: parent.height * 0.55
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, 0) }
                        GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0.62) }
                    }
                }
                Text {
                    x: px(40); width: parent.width - px(80)
                    anchors.bottom: desc.top; anchors.bottomMargin: px(6)
                    text: p.nombre; color: "white"; elide: Text.ElideRight
                    horizontalAlignment: p.lado > 0 ? Text.AlignRight : Text.AlignLeft   // (1.7.9) lejos de la del centro
                    font.family: raiz.familia; font.pixelSize: px(52); font.weight: Font.Bold
                }
                Text {
                    id: desc
                    x: px(40); width: parent.width - px(80) - (p.elegida ? px(96) : 0)
                    anchors.bottom: parent.bottom; anchors.bottomMargin: px(40)
                    text: p.dato[1]; color: "#F2F2F2"; elide: Text.ElideRight; wrapMode: Text.WordWrap; maximumLineCount: 2
                    font.family: raiz.familia; font.pixelSize: px(28)
                    opacity: p.elegida ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: 200 } }
                }
            }
            // la palomita de la elegida
            Rectangle {
                x: parent.width - width - px(24); y: px(24)
                width: px(52); height: width; radius: width / 2      // (1.7.9) blanca: verde sobre verde no se veia
                color: "#FFFFFF"; border.width: 0
                scale: p.elegida ? 1 : 0.6; opacity: p.elegida ? 1 : 0
                Behavior on scale { NumberAnimation { duration: 220; easing.type: Easing.OutBack; easing.overshoot: 1.6 } }
                Behavior on opacity { NumberAnimation { duration: 120 } }
                Image { anchors.centerIn: parent; width: px(30); height: width
                    source: "image://icono/palomita/04150D/" + width; sourceSize: Qt.size(width * 4, height * 4) }
            }
        }
        MouseArea {
            id: zona
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: p.tocar()
            onDoubleClicked: p.oir()
        }
        // ▶ oir (solo en la elegida)
        Rectangle {
            id: oirB
            x: parent.width - width - px(28); y: parent.height - height - px(28)
            width: px(80); height: width; radius: width / 2
            color: "transparent"      // (1.7.8) vidrio liquido verde
            Vidrio { anchors.fill: parent; radio: parent.radius; tinte: "#22C47E"; tinteA: 0.85; brillo: "#22C47E"; brilloA: 0.55; filo: 1.0; encima: zonaOir.containsMouse; apretado: zonaOir.pressed }
            visible: opacity > 0
            opacity: p.elegida ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 200 } }
            scale: zonaOir.pressed ? 0.9 : 1
            Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
            Image { anchors.centerIn: parent; anchors.horizontalCenterOffset: px(3); width: px(36); height: width
                source: "image://icono/play/04150D/" + width; sourceSize: Qt.size(width * 4, height * 4) }
            MouseArea { id: zonaOir; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                onClicked: p.oir() }
        }
    }

    // ------------------------------------------------------------------ una pastilla de intro
    component Pastilla: Item {
        id: o
        property string titulo: ""
        property string descripcion: ""
        property bool elegida: false
        property int retraso: 0
        property var ritmo: []
        signal elegir()
        signal ver()

        opacity: 0
        Component.onCompleted: aparece.start()
        SequentialAnimation { id: aparece
            PauseAnimation { duration: o.retraso }
            NumberAnimation { target: o; property: "opacity"; to: 1; duration: 240; easing.type: Easing.OutCubic } }

        Rectangle {
            id: caja
            anchors.fill: parent
            radius: px(28)
            scale: zona.pressed ? 0.98 : 1
            Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
            border.width: o.elegida ? px(4) : 1
            border.color: o.elegida ? "#3BEE9F" : (zona.containsMouse ? Qt.rgba(226 / 255, 176 / 255, 79 / 255, 0.6) : Qt.rgba(1, 1, 1, 0.12))
            Behavior on border.color { ColorAnimation { duration: 200 } }
            color: o.elegida ? Qt.rgba(24 / 255, 84 / 255, 66 / 255, 0.92) : Qt.rgba(14 / 255, 34 / 255, 40 / 255, 0.88)
            Behavior on color { ColorAnimation { duration: 200 } }

            // las 8 fotos latiendo a su ritmo (en la elegida o al pasar el raton)
            Row {
                id: fotos
                x: px(30); y: px(30)
                spacing: px(6)
                property int foco: 0
                Repeater {
                    model: 8
                    Rectangle {
                        width: px(20); height: px(36); radius: px(5)
                        color: index === fotos.foco ? (o.elegida ? "#3BEE9F" : "#E2B04F") : Qt.rgba(1, 1, 1, 0.14)
                        scale: index === fotos.foco ? 1.18 : 1
                        Behavior on scale { NumberAnimation { duration: 90 } }
                    }
                }
                Timer {
                    running: o.ritmo.length > 0 && o.visible && (o.elegida || zona.containsMouse)
                    repeat: true
                    interval: Math.max(60, (o.ritmo[fotos.foco] || 5) * 1000 / 24 * 2)
                    onTriggered: fotos.foco = (fotos.foco + 1) % 8
                }
            }
            Text {
                x: px(30); y: px(80)
                width: parent.width - px(60) - (oirI.opacity > 0 ? px(70) : 0)
                text: o.titulo; color: "white"; elide: Text.ElideRight
                font.family: raiz.familia; font.pixelSize: px(38); font.weight: Font.Bold
            }
            Text {
                x: px(30); y: px(80) + px(44)
                width: parent.width - px(60) - (oirI.opacity > 0 ? px(70) : 0)
                text: o.descripcion; color: "#9DB0B6"; elide: Text.ElideRight
                font.family: raiz.familia; font.pixelSize: px(24)
            }
        }
        MouseArea {
            id: zona
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: o.elegir()
            onDoubleClicked: o.ver()
        }
        // ▶ ver la intro
        Rectangle {
            id: oirI
            x: parent.width - width - px(24); y: (parent.height - height) / 2
            width: px(58); height: width; radius: width / 2
            color: "transparent"      // (1.7.8) vidrio liquido
            Vidrio { anchors.fill: parent; radio: parent.radius; tinte: zonaVer.containsMouse ? "#22C47E" : "white"; tinteA: zonaVer.containsMouse ? 0.85 : 0.08; brillo: "#22C47E"; brilloA: zonaVer.containsMouse ? 0.45 : 0; encima: zonaVer.containsMouse; apretado: zonaVer.pressed }
            opacity: zona.containsMouse || zonaVer.containsMouse || o.elegida ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 200 } }
            Behavior on color { ColorAnimation { duration: 150 } }
            scale: zonaVer.pressed ? 0.9 : 1
            Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
            Image { anchors.centerIn: parent; anchors.horizontalCenterOffset: px(2); width: px(26); height: width
                source: "image://icono/play/FFFFFF/" + width; sourceSize: Qt.size(width * 4, height * 4) }
            MouseArea { id: zonaVer; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                onClicked: o.ver() }
        }
    }
}
