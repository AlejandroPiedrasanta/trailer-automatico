// =============================================================================================================================
// Tráiler automático · CINEMA PRODUCTIONS
// compilar/mac/instalador/instalador_mac.swift — Contents/MacOS/instalar de «Instalar Trailer automatico.app», la app del disco
// de Mac («Doble clic para instalar», como el de CineSlide 9.62). La ventana es NATIVA (AppKit + SwiftUI): sale al instante.
// Es la misma ventana que el instalador de Windows (compilar/windows/Instalador.cs): banner con el astrolabio que gira, PASOS,
// % y barra. Empieza sola (sin botón INSTALAR) y no pide contraseña:
//   1. Cerrar la versión anterior
//   2. Copiar el programa: Resources/TrailerAutomatico.zip -> /Applications/TrailerAutomatico.app (si no se puede escribir
//      ahí, ~/Applications), con «ditto -x -k» a «.nuevo» y cambio de nombre (nunca queda a medias); sin cuarentena y
//      registrada en Launch Services
//   3. Aplicaciones y Dock: la fija en el Dock (y quita las de otras rutas)
//   4. Fuentes, color y carpetas: TrailerAutomatico --tarea instalar (lo de tareas.instalar: música aparte, fuentes, color de
//      DaVinci, servicio de actualizaciones del usuario); si falla es solo un aviso: el programa lo repite al abrirse
// Al terminar abre el programa, se cierra y expulsa el disco. Si ya está instalada esa versión (o una más nueva), solo lo abre.
// Solo pide la contraseña si la app de Aplicaciones es del sistema (Mac instaladas con el .pkg, hasta la 1.5.1).
// Registro: ~/Library/Application Support/TrailerAutomatico/registro/instalador_mac.log
//   instalar --demo | --demo-error     simula una instalación (para ver el diseño)
// Lo compila construir_mac.sh con swiftc (en una Mac: Windows no puede).
// =============================================================================================================================
import AppKit
import Metal
import SwiftUI

extension Color {
    init(_ r: Double, _ g: Double, _ b: Double, _ a: Double = 1) {
        self.init(.sRGB, red: r / 255, green: g / 255, blue: b / 255, opacity: a)
    }
}

// el Tema del instalador de Windows
let FONDO = Color(8, 12, 20)
let LINEA = Color(30, 42, 66)
let SUAVE = Color(150, 165, 192)
let PENDIENTE = Color(118, 132, 158)
let ACENTO = Color(22, 163, 106)
let CIAN = Color(70, 228, 170)
let EN_CURSO = Color(96, 236, 178)
let OK_C = Color(98, 209, 150)
let AVISO_C = Color(255, 184, 107)
let ERROR_C = Color(255, 107, 107)
let VERDE_T = Color(58, 230, 140)
let FIRMA = Color(78, 96, 126)

let NOMBRE = "Tráiler automático"
let ID_APP = "com.cinemaproductions.trailerautomatico"
let NOMBRE_APP = "TrailerAutomatico.app"
// el programa va en un .zip DENTRO del instalador: el disco es HFS+, que guarda los nombres con tildes («Extrañaré») de otra
// forma (NFD); con el programa suelto en el disco, la firma no verificaba («file missing») y macOS diría «está dañado»
let ZIP_APP = "TrailerAutomatico.zip"
let INSTALADOR = "Instalar Trailer automatico.app"
let HOME = NSHomeDirectory()
let DATOS = HOME + "/Library/Application Support/TrailerAutomatico"
let REGISTRO = DATOS + "/registro/instalador_mac.log"
let LSREGISTER = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
let ANCHO: CGFloat = 880
let ALTO: CGFloat = 580
let ALTO_BANNER: CGFloat = 236

// ---------------------------------------------------------------------------------------------------------------- utilidades
func numeroVersion(_ v: String) -> Int {
    let p = v.split(separator: ".").map { Int($0) ?? 0 }
    return (p.count > 0 ? p[0] : 0) * 1_000_000 + (p.count > 1 ? p[1] : 0) * 1_000 + (p.count > 2 ? p[2] : 0)
}

func versionDe(_ app: String) -> String? {
    guard let d = NSDictionary(contentsOfFile: app + "/Contents/Info.plist") else { return nil }
    return d["CFBundleShortVersionString"] as? String
}

func appInstalada() -> String? {
    for r in ["/Applications/" + NOMBRE_APP, HOME + "/Applications/" + NOMBRE_APP]
    where FileManager.default.isExecutableFile(atPath: r + "/Contents/MacOS/TrailerAutomatico") {
        return r
    }
    return nil
}

func leerTexto(_ ruta: String) -> String {
    return (try? String(contentsOfFile: ruta, encoding: .utf8)) ?? ""
}

/// Corre un programa y espera: (código, salida + errores).
@discardableResult
func ejecutar(_ exe: String, _ args: [String], entrada: Data? = nil) -> (Int32, Data) {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: exe)
    p.arguments = args
    let salida = Pipe()
    p.standardOutput = salida
    p.standardError = salida
    let tubo = Pipe()
    if entrada != nil {
        p.standardInput = tubo
    } else {
        p.standardInput = FileHandle.nullDevice
    }
    do {
        try p.run()
    } catch {
        return (-1, Data(error.localizedDescription.utf8))
    }
    if let e = entrada {
        tubo.fileHandleForWriting.write(e)
        try? tubo.fileHandleForWriting.close()
    }
    let datos = salida.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return (p.terminationStatus, datos)
}

/// Bytes de los archivos de una carpeta (para el avance de la copia).
func tamano(_ ruta: String) -> Int64 {
    let claves: [URLResourceKey] = [.fileSizeKey, .isRegularFileKey]
    guard let en = FileManager.default.enumerator(at: URL(fileURLWithPath: ruta), includingPropertiesForKeys: claves,
                                                  options: [], errorHandler: { _, _ in true }) else { return 0 }
    var total: Int64 = 0
    for case let u as URL in en {
        if let v = try? u.resourceValues(forKeys: Set(claves)), v.isRegularFile == true {
            total += Int64(v.fileSize ?? 0)
        }
    }
    return total
}

// ---------------------------------------------------------------------------------------------------------------- modelo
enum EstadoPaso { case pendiente, enCurso, hecho, aviso, error }

struct Paso: Identifiable {
    let id: Int
    let titulo: String
    let accion: String
    let peso: Double
    var estado: EstadoPaso = .pendiente
    var progreso: Int = -1
    var cambio = Date.distantPast
}

final class Modelo: ObservableObject {
    @Published var pasos: [Paso] = [
        Paso(id: 0, titulo: "Cerrar la versión anterior", accion: "Preparando la instalación…", peso: 0.3),
        Paso(id: 1, titulo: "Copiar el programa", accion: "Copiando el programa a Aplicaciones…", peso: 6.0),
        Paso(id: 2, titulo: "Aplicaciones y Dock", accion: "Fijándolo en el Dock…", peso: 0.4),
        Paso(id: 3, titulo: "Fuentes, color y carpetas", accion: "Instalando fuentes, color y carpetas…", peso: 1.2)]
    @Published var titulo = "Preparando la instalación…"
    @Published var info = ""
    @Published var fase = 1                  // 1 instalando · 2 listo · 3 error (como el banner de Windows)
    @Published var mostrado = 0.0            // la barra (0-1), suavizada
    var tFase = Date()

    var objetivo: Double {
        if fase == 2 { return 1 }
        var total = 0.0
        var hecho = 0.0
        for p in pasos {
            total += p.peso
            if p.estado == .hecho || p.estado == .aviso {
                hecho += p.peso
            } else if p.estado == .enCurso && p.progreso > 0 {
                hecho += p.peso * Double(min(p.progreso, 100)) / 100
            }
        }
        return total > 0 ? hecho / total : 0
    }

    func paso(_ i: Int, _ e: EstadoPaso, _ progreso: Int = -1) {
        guard i >= 0 && i < pasos.count else { return }
        if pasos[i].estado != e { pasos[i].cambio = Date() }
        pasos[i].estado = e
        pasos[i].progreso = progreso
        if e == .enCurso { titulo = pasos[i].accion }
    }

    func avanzar(_ dt: Double) {
        if fase == 3 { return }
        let obj = objetivo
        mostrado += (obj - mostrado) * min(1, dt * (fase == 2 ? 6 : 3))
        if abs(obj - mostrado) < 0.0005 { mostrado = obj }
    }

    func terminar(avisos: Bool) {
        fase = 2
        tFase = Date()
        titulo = avisos ? "¡Listo, con avisos!" : "¡Listo!"
        info = avisos
            ? "Se instaló, pero algo quedó con aviso (el programa lo vuelve a intentar al abrirse). Ya está en Aplicaciones y en el Dock."
            : "Ya está en Aplicaciones, en el Dock y en Launchpad. Abre el programa, sube tu material y pulsa el botón del centro."
    }

    func fallar(_ i: Int, _ texto: String) {
        paso(i, .error)
        fase = 3
        tFase = Date()
        titulo = "No se pudo terminar"
        info = texto + "  ·  Pulsa «Ver registro» y envíanoslo si se repite."
    }
}

// ---------------------------------------------------------------------------------------------------------------- banner
struct Recursos {
    let banner, runas, engr, fili, nucleo, logo, marca: NSImage?
    init(_ dir: String) {
        func img(_ n: String) -> NSImage? { return NSImage(contentsOfFile: dir + "/" + n) }
        banner = img("banner.jpg")
        runas = img("astro_runas.png")
        engr = img("astro_engr.png")
        fili = img("astro_fili.png")
        nucleo = img("astro_nucleo.png")
        logo = img("logo.png")
        marca = img("marca.png")
    }
}

struct Mota {
    var x, y, vy, vx, r, f: Double
}

/// Lo que se mueve en el banner (igual que la clase Banner de Windows): capas del astrolabio que giran, halo que respira,
/// motas de luz, un destello que cruza cada ~7 s y ondas al terminar. Se dibuja en un Canvas a 30 cuadros por segundo.
final class Escena {
    var ultimo = 0.0
    var giroA = 0.0
    var giroB = 0.0
    var giroC = 0.0
    var vel = 1.0
    var motas: [Mota] = []
    // la escena de la imagen: el astrolabio vive en estas coordenadas de banner.jpg (1760 x 472)
    let astroX = 1385.0, astroY = 236.0, astroLado = 400.0, imgAncho = 1760.0, imgAlto = 472.0

    init() {
        for _ in 0..<70 {
            motas.append(Mota(x: Double.random(in: 0...1), y: Double.random(in: 0...1), vy: 0.012 + Double.random(in: 0...0.03),
                              vx: (Double.random(in: 0...1) - 0.5) * 0.01, r: 0.8 + Double.random(in: 0...2.2),
                              f: Double.random(in: 0...6.28)))
        }
    }

    func avanzar(_ dt: Double, _ fase: Int, _ finT: Double) {
        let obj: Double = fase == 1 ? 3.4 : (fase == 2 ? (finT < 2.5 ? 0.25 : 1) : 0.12)
        vel += (obj - vel) * min(1, dt * 3)
        giroA += 2.4 * vel * dt
        giroB -= 3.6 * vel * dt
        giroC += 5.6 * vel * dt
        for i in motas.indices {
            motas[i].y -= motas[i].vy * dt * (0.6 + 0.4 * vel)
            motas[i].x += motas[i].vx * dt
            if motas[i].y < -0.02 { motas[i].y = 1.02 }
            if motas[i].x < 0 { motas[i].x += 1 } else if motas[i].x > 1 { motas[i].x -= 1 }
        }
    }

    func capa(_ g: inout GraphicsContext, _ img: NSImage?, _ cx: Double, _ cy: Double, _ lado: Double, _ giro: Double) {
        guard let img = img else { return }
        var c = g
        c.translateBy(x: cx, y: cy)
        c.rotate(by: .degrees(giro))
        c.draw(Image(nsImage: img), in: CGRect(x: -lado / 2, y: -lado / 2, width: lado, height: lado))
    }

    func dibujar(_ g: inout GraphicsContext, _ size: CGSize, _ t: Double, _ fase: Int, _ tFase: Date, _ r: Recursos) {
        let dt = ultimo == 0 ? 0 : min(0.1, max(0, t - ultimo))
        ultimo = t
        let finT = Date().timeIntervalSince(tFase)
        avanzar(dt, fase, finT)
        let W = Double(size.width), H = Double(size.height)
        let todo = Path(CGRect(x: 0, y: 0, width: W, height: H))
        g.fill(todo, with: .color(FONDO))
        // la escena (cubre el banner, como en Windows) y la posición del astrolabio en ella
        let esc = max(W / imgAncho, H / imgAlto)
        let ox = (W - imgAncho * esc) / 2, oy = (H - imgAlto * esc) * 0.45
        if let b = r.banner {
            g.draw(Image(nsImage: b), in: CGRect(x: ox, y: oy, width: imgAncho * esc, height: imgAlto * esc))
        }
        // solo se oscurece la zona del título (izquierda) y una franja corta abajo para fundirse con la ventana
        let oscuro = Gradient(stops: [
            Gradient.Stop(color: Color(5, 10, 14, 246.0 / 255), location: 0),
            Gradient.Stop(color: Color(5, 10, 14, 205.0 / 255), location: 0.42),
            Gradient.Stop(color: Color(5, 10, 14, 0), location: 0.6),
            Gradient.Stop(color: Color(5, 10, 14, 0), location: 1)])
        g.fill(todo, with: .linearGradient(oscuro, startPoint: CGPoint(x: 0, y: 0), endPoint: CGPoint(x: W, y: 0)))
        let pie = Gradient(stops: [
            Gradient.Stop(color: Color(8, 12, 20, 0), location: 0),
            Gradient.Stop(color: Color(8, 12, 20, 0), location: 0.8),
            Gradient.Stop(color: Color(8, 12, 20, 235.0 / 255), location: 1)])
        g.fill(todo, with: .linearGradient(pie, startPoint: CGPoint(x: 0, y: 0), endPoint: CGPoint(x: 0, y: H)))

        let cx = ox + astroX * esc, cy = oy + astroY * esc, lado = astroLado * esc
        let col: Color = fase == 3 ? Color(255, 90, 90) : Color(58, 230, 140)
        // el halo que respira
        let pulso = 0.5 + 0.5 * sin(t * 1.6)
        let radio = lado * 0.95
        let alfa = ((fase == 1 ? 80.0 : 46.0) + 26 * pulso) / 255
        let halo = Path(ellipseIn: CGRect(x: cx - radio, y: cy - radio, width: radio * 2, height: radio * 2))
        g.fill(halo, with: .radialGradient(Gradient(colors: [col.opacity(alfa), col.opacity(0)]),
                                           center: CGPoint(x: cx, y: cy), startRadius: 0, endRadius: radio))
        // las capas giratorias y el núcleo fijo
        capa(&g, r.runas, cx, cy, lado, giroA)
        capa(&g, r.engr, cx, cy, lado, giroB)
        capa(&g, r.fili, cx, cy, lado, giroC)
        capa(&g, r.nucleo, cx, cy, lado, 0)
        // ondas al terminar
        if fase >= 2 && finT < 2.4 {
            for i in 0..<3 {
                let u = (finT - Double(i) * 0.22) / 1.6
                if u <= 0 || u >= 1 { continue }
                let rr = (60 + 700 * (1 - pow(1 - u, 2.4))) * esc
                let a = 190 * (1 - u) * (1 - u) / 255
                let co: Color = fase == 3 ? Color(255, 110, 110, a) : Color(120, 255, 190, a)
                let elipse = Path(ellipseIn: CGRect(x: cx - rr, y: cy - rr * 0.92, width: rr * 2, height: rr * 1.84))
                g.stroke(elipse, with: .color(co), lineWidth: 2.4 * esc + 6 * u)
            }
        }
        // motas de luz (a la derecha, donde vive la escena)
        let x0 = W * 0.40, ancho = W - x0
        for (i, mo) in motas.enumerated() {
            let tw = 0.5 + 0.5 * sin(t * 2.2 + mo.f)
            let a = (40 + 150 * tw) / 255
            let x = x0 + mo.x * ancho, y = mo.y * H, rad = mo.r * max(0.8, esc * 0.9)
            let c: Color
            switch i % 3 {
            case 0: c = Color(150, 255, 200, a)
            case 1: c = Color(255, 255, 255, a)
            default: c = Color(90, 220, 255, a)
            }
            g.fill(Path(ellipseIn: CGRect(x: x - rad, y: y - rad, width: rad * 2, height: rad * 2)), with: .color(c))
        }
        // un destello diagonal que cruza cada ~7 s
        let fd = t.truncatingRemainder(dividingBy: 7) / 7 * 1.6 - 0.3
        if fd > -0.2 && fd < 1.2 {
            let bx = W * fd
            var banda = Path()
            banda.move(to: CGPoint(x: bx, y: 0))
            banda.addLine(to: CGPoint(x: bx + W * 0.10, y: 0))
            banda.addLine(to: CGPoint(x: bx - W * 0.06, y: H))
            banda.addLine(to: CGPoint(x: bx - W * 0.16, y: H))
            banda.closeSubpath()
            let brillo = Gradient(stops: [
                Gradient.Stop(color: Color(255, 255, 255, 0), location: 0),
                Gradient.Stop(color: Color(190, 255, 225, 34.0 / 255), location: 0.5),
                Gradient.Stop(color: Color(255, 255, 255, 0), location: 1)])
            g.fill(banda, with: .linearGradient(brillo, startPoint: CGPoint(x: bx - W * 0.16, y: 0),
                                                endPoint: CGPoint(x: bx + W * 0.10, y: 0)))
        }
    }
}

/// Los textos del banner entran deslizándose, como en Windows.
struct Entrada: ViewModifier {
    let entra: Bool
    let retraso: Double
    func body(content: Content) -> some View {
        content
            .opacity(entra ? 1 : 0)
            .offset(x: entra ? 0 : -26)
            .animation(.easeOut(duration: 0.9).delay(retraso), value: entra)
    }
}

struct Banner: View {
    @ObservedObject var m: Modelo
    let r: Recursos
    let escena: Escena
    let titulo: String
    let ficha: String
    @State private var entra = false

    var body: some View {
        ZStack(alignment: .topLeading) {
            TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { ctx in
                Canvas { g, size in
                    escena.dibujar(&g, size, ctx.date.timeIntervalSinceReferenceDate, m.fase, m.tFase, r)
                }
            }
            HStack(spacing: 12) {
                if let l = r.logo {
                    Image(nsImage: l).resizable().interpolation(.high).frame(width: 40, height: 40)
                }
                HStack(spacing: 9) {
                    Text("TRÁILER").foregroundColor(.white)
                    Text("AUTOMÁTICO").foregroundColor(VERDE_T)
                }
                .font(.system(size: 20, weight: .bold))
            }
            .offset(x: 38, y: 32)
            .modifier(Entrada(entra: entra, retraso: 0))
            Text(titulo)
                .font(.system(size: 35, weight: .bold)).foregroundColor(.white)
                .offset(x: 33, y: 82)
                .modifier(Entrada(entra: entra, retraso: 0.15))
            Text("Tu evento hecho tráiler en DaVinci Resolve")
                .font(.system(size: 16)).foregroundColor(Color(205, 218, 238))
                .offset(x: 38, y: 136)
                .modifier(Entrada(entra: entra, retraso: 0.3))
            Text(ficha)
                .font(.system(size: 12.5, weight: .bold)).foregroundColor(Color(120, 255, 200))
                .padding(.horizontal, 12).padding(.vertical, 6)
                .background(Color(10, 36, 30, 225.0 / 255))
                .overlay(Rectangle().stroke(Color(58, 230, 140, 120.0 / 255), lineWidth: 1))
                .offset(x: 38, y: 176)
                .modifier(Entrada(entra: entra, retraso: 0.45))
        }
        .frame(width: ANCHO, height: ALTO_BANNER, alignment: .topLeading)
        .clipped()
        .onAppear { entra = true }
    }
}

// ---------------------------------------------------------------------------------------------------------------- cuerpo
struct Cuerpo: View {
    @ObservedObject var m: Modelo
    let r: Recursos
    let verRegistro: () -> Void
    let cerrar: () -> Void

    var pct: String { m.fase == 3 ? "" : "\(Int((m.mostrado * 100).rounded())) %" }

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { ctx in
            let t = ctx.date.timeIntervalSinceReferenceDate
            ZStack(alignment: .topLeading) {
                FONDO
                lista(t).offset(x: 36, y: 16)
                Rectangle().fill(LINEA).frame(width: 1, height: 290).offset(x: 424, y: 18)
                Text(m.titulo)
                    .font(.system(size: 18.5, weight: .bold)).foregroundColor(.white)
                    .lineLimit(1).truncationMode(.tail)
                    .frame(width: 300, height: 46, alignment: .leading)
                    .offset(x: 450, y: 20)
                Text(pct)
                    .font(.system(size: 26.5, weight: .bold)).monospacedDigit().foregroundColor(CIAN)
                    .frame(width: 100, height: 46, alignment: .trailing)
                    .offset(x: 752, y: 20)
                barra(t).frame(width: 396, height: 14).offset(x: 452, y: 76)
                Text(m.info)
                    .font(.system(size: 12.5)).foregroundColor(SUAVE).lineSpacing(3)
                    .frame(width: 400, height: 96, alignment: .topLeading)
                    .offset(x: 450, y: 102)
                boton(t).frame(width: 398, height: 56).offset(x: 452, y: 211)
                if m.fase == 3 {
                    Button(action: verRegistro) {
                        Text("Ver registro").font(.system(size: 12.5)).foregroundColor(Color(110, 150, 200)).underline()
                    }
                    .buttonStyle(.plain)
                    .offset(x: 454, y: 284)
                }
                firma.offset(x: 40, y: 312)
            }
            .frame(width: ANCHO, height: ALTO - ALTO_BANNER, alignment: .topLeading)
        }
    }

    func colorDe(_ e: EstadoPaso) -> Color {
        switch e {
        case .enCurso: return EN_CURSO
        case .hecho: return OK_C
        case .aviso: return AVISO_C
        case .error: return ERROR_C
        case .pendiente: return PENDIENTE
        }
    }

    // ---- la lista de PASOS: · pendiente, arco que gira = en curso, ✓ hecho con un saltito, ! aviso, ✗ error
    func lista(_ t: Double) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("PASOS").font(.system(size: 12, weight: .bold)).foregroundColor(SUAVE)
                .padding(.leading, 4).frame(height: 26, alignment: .topLeading)
            ForEach(m.pasos) { p in fila(p, t) }
        }
        .frame(width: 372, alignment: .leading)
    }

    func fila(_ p: Paso, _ t: Double) -> some View {
        let c = colorDe(p.estado)
        var texto = p.titulo
        if p.estado == .enCurso && p.progreso >= 0 && p.progreso < 100 { texto += "   \(p.progreso) %" }
        let k = Date().timeIntervalSince(p.cambio)
        let pop: Double = (p.estado == .hecho && k < 0.55) ? sin(k / 0.55 * Double.pi) * 0.35 : 0
        return HStack(spacing: 0) {
            icono(p.estado, c, t, 8.5 * (1 + pop)).frame(width: 26, height: 32)
            Text(texto)
                .font(.system(size: 14, weight: p.estado == .enCurso ? .bold : .regular))
                .foregroundColor(p.estado == .enCurso ? .white : c)
                .lineLimit(1).truncationMode(.tail)
                .padding(.leading, 8)
        }
        .frame(height: 32)
    }

    @ViewBuilder
    func icono(_ e: EstadoPaso, _ c: Color, _ t: Double, _ rad: Double) -> some View {
        switch e {
        case .enCurso:
            ZStack {
                Circle().fill(c.opacity((30 + 40 * (0.5 + 0.5 * sin(t * 3.0))) / 255)).frame(width: rad * 3.4, height: rad * 3.4)
                Circle().stroke(c.opacity(70.0 / 255), lineWidth: 2).frame(width: rad * 2, height: rad * 2)
                Circle().trim(from: 0, to: 110.0 / 360)
                    .stroke(c, style: StrokeStyle(lineWidth: 2.6, lineCap: .round))
                    .frame(width: rad * 2, height: rad * 2)
                    .rotationEffect(.degrees((t * 409).truncatingRemainder(dividingBy: 360)))
            }
        case .hecho:
            ZStack {
                Circle().fill(c).frame(width: rad * 2, height: rad * 2)
                Path { pa in
                    pa.move(to: CGPoint(x: rad - rad * 0.45, y: rad + rad * 0.02))
                    pa.addLine(to: CGPoint(x: rad - rad * 0.1, y: rad + rad * 0.38))
                    pa.addLine(to: CGPoint(x: rad + rad * 0.5, y: rad - rad * 0.34))
                }
                .stroke(Color(6, 22, 14), style: StrokeStyle(lineWidth: 2.2, lineCap: .round, lineJoin: .round))
                .frame(width: rad * 2, height: rad * 2)
            }
        case .aviso, .error:
            ZStack {
                Circle().fill(c).frame(width: rad * 2, height: rad * 2)
                Text(e == .aviso ? "!" : "✗").font(.system(size: 12, weight: .heavy)).foregroundColor(Color(10, 14, 20))
            }
        case .pendiente:
            Circle().stroke(c.opacity(120.0 / 255), lineWidth: 1.6).frame(width: rad * 2, height: rad * 2)
        }
    }

    // ---- la barra: degradado esmeralda -> cian sobre todo el ancho, con un brillo que la recorre mientras trabaja
    func barra(_ t: Double) -> some View {
        GeometryReader { geo in
            let w = Double(geo.size.width), h = Double(geo.size.height)
            let v = max(0, min(1, m.mostrado))
            let wf = v <= 0 ? 0 : max(h, w * v)
            let colores: [Color] = m.fase == 3 ? [Color(194, 68, 74), ERROR_C] : [ACENTO, CIAN]
            let fb = (t * 0.3).truncatingRemainder(dividingBy: 1.8) - 0.4
            let bw = min(120, wf)
            ZStack(alignment: .leading) {
                Capsule().fill(Color(28, 38, 60))
                ZStack(alignment: .leading) {
                    Capsule().fill(LinearGradient(colors: colores, startPoint: .leading, endPoint: .trailing))
                    if m.fase == 1 && v < 1 && wf > 0 {
                        Rectangle()
                            .fill(LinearGradient(colors: [Color.white.opacity(0), Color.white.opacity(150.0 / 255 * 0.55), Color.white.opacity(0)],
                                                 startPoint: .leading, endPoint: .trailing))
                            .frame(width: bw, height: h)
                            .offset(x: wf * fb - bw / 2)
                    }
                }
                .frame(width: w, height: h)
                .mask(alignment: .leading) { Capsule().frame(width: wf, height: h) }
            }
        }
    }

    // ---- donde Windows tiene el botón INSTALAR: aquí empieza sola; el botón dice lo que pasa (y en un error, CERRAR)
    func boton(_ t: Double) -> some View {
        let activo = m.fase == 3
        let texto = m.fase == 1 ? "INSTALANDO…" : (m.fase == 2 ? "ABRIENDO…" : "CERRAR")
        let k: Double = activo || m.fase == 2 ? 1 : 0.6
        let a = Color(22 * k, 163 * k, 106 * k), b = Color(70 * k, 228 * k, 170 * k)
        let fb = (t * 0.45).truncatingRemainder(dividingBy: 2.2) - 0.6
        return Button(action: { if activo { cerrar() } }) {
            ZStack {
                Capsule().fill(LinearGradient(colors: [a, b], startPoint: .leading, endPoint: .trailing))
                Capsule().fill(LinearGradient(stops: [
                    Gradient.Stop(color: Color.white.opacity(62.0 / 255), location: 0),
                    Gradient.Stop(color: Color.white.opacity(8.0 / 255), location: 0.5),
                    Gradient.Stop(color: Color.black.opacity(28.0 / 255), location: 1)], startPoint: .top, endPoint: .bottom))
                if m.fase == 1 {
                    GeometryReader { geo in
                        Rectangle()
                            .fill(LinearGradient(colors: [Color.white.opacity(0), Color.white.opacity(110.0 / 255 * 0.5), Color.white.opacity(0)],
                                                 startPoint: .leading, endPoint: .trailing))
                            .frame(width: 140, height: geo.size.height)
                            .offset(x: Double(geo.size.width) * fb - 70)
                    }
                    .clipShape(Capsule())
                }
                Capsule().stroke(Color(190, 225, 255, 150.0 / 255), lineWidth: 1.2)
                Text(texto).font(.system(size: 18.5, weight: .bold)).foregroundColor(.white)
                    .shadow(color: Color.black.opacity(0.35), radius: 0, x: 0, y: 1.5)
            }
        }
        .buttonStyle(.plain)
        .allowsHitTesting(activo)                     // (con .disabled SwiftUI lo apaga también en «ABRIENDO…»)
    }

    var firma: some View {
        HStack(spacing: 6) {
            Text(NOMBRE).font(.system(size: 12)).foregroundColor(FIRMA)
            if let mk = r.marca {
                Image(nsImage: mk).resizable().interpolation(.high).aspectRatio(contentMode: .fit).frame(height: 15).opacity(0.62)
            }
        }
    }
}

struct VistaInstalador: View {
    @ObservedObject var m: Modelo
    let r: Recursos
    let escena: Escena
    let titulo: String
    let ficha: String
    let verRegistro: () -> Void
    let cerrar: () -> Void

    var borde: Color { m.fase == 2 ? OK_C.opacity(0.5) : (m.fase == 3 ? ERROR_C.opacity(0.55) : LINEA) }

    var body: some View {
        VStack(spacing: 0) {
            Banner(m: m, r: r, escena: escena, titulo: titulo, ficha: ficha)
            Cuerpo(m: m, r: r, verRegistro: verRegistro, cerrar: cerrar)
        }
        .frame(width: ANCHO, height: ALTO)
        .background(FONDO)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(borde, lineWidth: 1))
    }
}

// ---------------------------------------------------------------------------------------------------------------- instalación
struct Fallo: Error {
    let texto: String
}

/// La instalación de verdad (en un hilo aparte; la ventana se entera por el Modelo, en el hilo principal).
final class Instalacion {
    let m: Modelo
    let origen: String                       // Resources/TrailerAutomatico.zip
    let version: String
    var destino = ""
    var registro: FileHandle?

    init(m: Modelo, origen: String, version: String) {
        self.m = m
        self.origen = origen
        self.version = version
        let fm = FileManager.default
        try? fm.createDirectory(atPath: (REGISTRO as NSString).deletingLastPathComponent, withIntermediateDirectories: true)
        if !fm.fileExists(atPath: REGISTRO) { fm.createFile(atPath: REGISTRO, contents: Data()) }
        registro = FileHandle(forWritingAtPath: REGISTRO)
        _ = registro?.seekToEndOfFile()
    }

    func anotar(_ s: String) {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm:ss"
        registro?.write(Data("\(f.string(from: Date()))  \(s)\n".utf8))
    }

    func ui(_ f: @escaping () -> Void) { DispatchQueue.main.async(execute: f) }
    func paso(_ i: Int, _ e: EstadoPaso, _ progreso: Int = -1) { ui { self.m.paso(i, e, progreso) } }
    func info(_ s: String) { ui { self.m.info = s } }

    func correr() {
        #if arch(arm64)
        let arq = "Apple Silicon"
        #else
        let arq = "Intel"
        #endif
        anotar("== Instalar \(NOMBRE) \(version) (\(arq)) · macOS \(ProcessInfo.processInfo.operatingSystemVersionString)")
        anotar("desde \(Bundle.main.bundlePath)")
        paso(0, .enCurso)
        cerrarAnterior()
        paso(0, .hecho)

        paso(1, .enCurso, 0)
        do {
            try copiar()
        } catch let f as Fallo {
            anotar("ERROR copiar: " + f.texto)
            ui { self.m.fallar(1, f.texto) }
            return
        } catch {
            anotar("ERROR copiar: \(error.localizedDescription)")
            ui { self.m.fallar(1, error.localizedDescription) }
            return
        }
        paso(1, .hecho)

        paso(2, .enCurso)
        let dock = fijarEnDock(destino)
        anotar(dock ? "Dock: fijado" : "AVISO Dock: no se pudo fijar")
        paso(2, dock ? .hecho : .aviso)

        paso(3, .enCurso, 0)
        let (ok, texto) = tareaInstalar()
        anotar((ok ? "tarea instalar: " : "AVISO tarea instalar: ") + texto)
        paso(3, ok ? .hecho : .aviso)
        anotar("listo: \(destino)")
        ui { self.m.terminar(avisos: !dock || !ok) }
    }

    // ---- 1. cerrar la versión anterior (si está abierta) y lo que quede corriendo del programa
    func cerrarAnterior() {
        let abiertas = NSRunningApplication.runningApplications(withBundleIdentifier: ID_APP)
        if abiertas.isEmpty { return }
        anotar("cerrando \(abiertas.count) ventana(s) del programa")
        for a in abiertas { a.terminate() }
        let fin = Date().addingTimeInterval(10)
        while Date() < fin && abiertas.contains(where: { !$0.isTerminated }) { Thread.sleep(forTimeInterval: 0.3) }
        for a in abiertas where !a.isTerminated { a.forceTerminate() }
        Thread.sleep(forTimeInterval: 0.5)
    }

    // ---- 2. copiar el programa a Aplicaciones
    func copiar() throws {
        let fm = FileManager.default
        guard fm.fileExists(atPath: origen) else {
            throw Fallo(texto: "Al instalador le falta el programa (\(ZIP_APP)). Vuelve a bajar el instalador.")
        }
        let enApps = "/Applications/" + NOMBRE_APP
        let enUsuario = HOME + "/Applications/" + NOMBRE_APP
        var admin = false
        if fm.fileExists(atPath: enApps) {
            destino = enApps
            // la de las Mac instaladas con el .pkg (hasta la 1.5.1) es del sistema: reemplazarla pide la contraseña
            let dueno = (try? fm.attributesOfItem(atPath: enApps)[.ownerAccountID] as? NSNumber)?.intValue ?? -1
            admin = dueno != Int(getuid()) || !fm.isWritableFile(atPath: "/Applications")
        } else if fm.isWritableFile(atPath: "/Applications") {
            destino = enApps
        } else {
            destino = enUsuario
            try? fm.createDirectory(atPath: HOME + "/Applications", withIntermediateDirectories: true)
        }
        anotar("destino: \(destino)\(admin ? " (con contraseña: la instalada es del sistema)" : "")")
        info("Se instala en \(destino.replacingOccurrences(of: HOME, with: "~")) sin contraseña. Trae ffmpeg, las plantillas, " +
             "la música, los SFX y las fuentes. Tus carpetas y tus videos no se tocan." +
             (versionDe(destino).map { " Reemplaza la versión \($0)." } ?? ""))
        // el .zip va sin comprimir (el .dmg ya comprime): mide lo mismo que el programa descomprimido, sirve para el avance
        let total = max(1, ((try? fm.attributesOfItem(atPath: origen)[.size] as? NSNumber)?.int64Value) ?? 1)
        let nuevo = destino + ".nuevo", viejo = destino + ".viejo"
        let p = Process()
        if admin {
            // un guion temporal (ruta sin espacios ni comillas) que corre con la contraseña de un administrador
            let guion = NSTemporaryDirectory() + "trailer_instalar_\(getpid()).sh"
            func q(_ s: String) -> String { return "'" + s.replacingOccurrences(of: "'", with: "'\\''") + "'" }
            let texto = "#!/bin/bash\nset -e\nrm -rf \(q(nuevo)) \(q(viejo))\n/usr/bin/ditto -x -k \(q(origen)) \(q(nuevo))\n" +
                "[ -d \(q(destino)) ] && mv \(q(destino)) \(q(viejo))\nmv \(q(nuevo)) \(q(destino))\nrm -rf \(q(viejo))\n" +
                "/usr/bin/xattr -dr com.apple.quarantine \(q(destino)) 2>/dev/null || true\n"
            try texto.write(toFile: guion, atomically: true, encoding: .utf8)
            p.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
            p.arguments = ["-e", "do shell script \"/bin/bash \(guion)\" with administrator privileges"]
        } else {
            try? fm.removeItem(atPath: nuevo)
            try? fm.removeItem(atPath: viejo)
            p.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
            p.arguments = ["-x", "-k", origen, nuevo]
        }
        let errores = Pipe()
        p.standardError = errores
        p.standardOutput = FileHandle.nullDevice
        p.standardInput = FileHandle.nullDevice
        try p.run()
        let inicio = Date()
        while p.isRunning {
            Thread.sleep(forTimeInterval: 0.4)
            if fm.fileExists(atPath: nuevo) { paso(1, .enCurso, min(99, Int(Double(tamano(nuevo)) * 100 / Double(total)))) }
        }
        let err = String(decoding: errores.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        anotar("copia: código \(p.terminationStatus) en \(Int(Date().timeIntervalSince(inicio))) s\(err.isEmpty ? "" : " · " + err)")
        if p.terminationStatus != 0 {
            try? fm.removeItem(atPath: nuevo)
            if admin && err.contains("-128") { throw Fallo(texto: "Se canceló la contraseña: el programa no se reemplazó.") }
            throw Fallo(texto: "No se pudo copiar el programa a \(destino) (\(err.isEmpty ? "código \(p.terminationStatus)" : err)).")
        }
        if !admin {
            guard fm.isExecutableFile(atPath: nuevo + "/Contents/MacOS/TrailerAutomatico") else {
                try? fm.removeItem(atPath: nuevo)
                throw Fallo(texto: "La copia del programa quedó incompleta (¿falta espacio en el disco?).")
            }
            if fm.fileExists(atPath: destino) { try fm.moveItem(atPath: destino, toPath: viejo) }
            do {
                try fm.moveItem(atPath: nuevo, toPath: destino)
            } catch {
                if fm.fileExists(atPath: viejo) { try? fm.moveItem(atPath: viejo, toPath: destino) }
                throw Fallo(texto: "No se pudo poner el programa en su lugar: \(error.localizedDescription)")
            }
            try? fm.removeItem(atPath: viejo)
            ejecutar("/usr/bin/xattr", ["-dr", "com.apple.quarantine", destino])
        }
        guard fm.isExecutableFile(atPath: destino + "/Contents/MacOS/TrailerAutomatico") else {
            throw Fallo(texto: "El programa no quedó en \(destino).")
        }
        // la de la otra carpeta (de una instalación anterior) se quita: que quede una sola
        let otra = destino == enApps ? enUsuario : enApps
        if fm.fileExists(atPath: otra) && (try? fm.removeItem(atPath: otra)) != nil { anotar("quitada la de \(otra)") }
        // que Finder, Launchpad y el Dock la vean ya con su icono
        ejecutar(LSREGISTER, ["-f", destino])
        anotar("copiado: \(destino) (\(versionDe(destino) ?? "?"))")
    }

    // ---- 3. fijarla en el Dock (una vez; se quitan las de otras rutas). Si el Dock no tiene sus ajustes, no se toca.
    func fijarEnDock(_ app: String) -> Bool {
        let (c1, datos) = ejecutar("/usr/bin/defaults", ["export", "com.apple.dock", "-"])
        guard c1 == 0, !datos.isEmpty,
              let leido = try? PropertyListSerialization.propertyList(from: datos, options: [.mutableContainersAndLeaves], format: nil),
              var d = leido as? [String: Any],
              var apps = d["persistent-apps"] as? [[String: Any]] else { return false }
        func ruta(_ t: [String: Any]) -> String {
            guard let td = t["tile-data"] as? [String: Any], let fd = td["file-data"] as? [String: Any],
                  let s = fd["_CFURLString"] as? String else { return "" }
            var r = s
            if let u = URL(string: s), u.isFileURL { r = u.path }
            while r.count > 1 && r.hasSuffix("/") { r.removeLast() }
            return r
        }
        let antes = apps.count
        apps.removeAll { t in
            let r = ruta(t)
            return r.hasSuffix("/" + NOMBRE_APP) && r != app
        }
        if !apps.contains(where: { ruta($0) == app }) {
            let archivo: [String: Any] = ["_CFURLString": URL(fileURLWithPath: app, isDirectory: true).absoluteString,
                                          "_CFURLStringType": 15]
            let datosTile: [String: Any] = ["file-label": NOMBRE, "bundle-identifier": ID_APP, "file-data": archivo]
            apps.append(["tile-type": "file-tile", "tile-data": datosTile])
        } else if apps.count == antes {
            return true                                          // ya estaba fijada: no se reinicia el Dock
        }
        d["persistent-apps"] = apps
        guard let nuevo = try? PropertyListSerialization.data(fromPropertyList: d, format: .binary, options: 0) else { return false }
        let (c2, _) = ejecutar("/usr/bin/defaults", ["import", "com.apple.dock", "-"], entrada: nuevo)
        if c2 != 0 { return false }
        ejecutar("/usr/bin/killall", ["Dock"])
        return true
    }

    // ---- 4. lo que hacía el .pkg: el programa recién instalado lo hace con «--tarea instalar» (líneas PROGRESO|n|texto)
    func tareaInstalar() -> (Bool, String) {
        let estado = NSTemporaryDirectory() + "trailer_instalar_\(getpid()).txt"
        FileManager.default.createFile(atPath: estado, contents: Data())
        let p = Process()
        p.executableURL = URL(fileURLWithPath: destino + "/Contents/MacOS/TrailerAutomatico")
        p.arguments = ["--tarea", "instalar", estado]
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        do {
            try p.run()
        } catch {
            return (false, "no se pudo abrir el programa: \(error.localizedDescription)")
        }
        let inicio = Date()
        var ultima = ""
        func leer() {
            for l in leerTexto(estado).split(separator: "\n") {
                let partes = l.split(separator: "|", maxSplits: 2, omittingEmptySubsequences: false).map(String.init)
                if partes.first == "PROGRESO" && partes.count >= 3 {
                    paso(3, .enCurso, Int(partes[1]) ?? 0)
                } else if partes.first == "OK" || partes.first == "ERROR" {
                    ultima = String(l)
                }
            }
        }
        while p.isRunning {
            Thread.sleep(forTimeInterval: 0.3)
            leer()
            if Date().timeIntervalSince(inicio) > 300 {
                p.terminate()
                return (false, "tardó demasiado (más de 5 minutos)")
            }
        }
        leer()
        try? FileManager.default.removeItem(atPath: estado)
        if ultima.hasPrefix("OK|") { return (true, String(ultima.dropFirst(3))) }
        if ultima.hasPrefix("ERROR|") { return (false, String(ultima.dropFirst(6))) }
        return (false, "el programa terminó sin decir cómo le fue (código \(p.terminationStatus))")
    }
}

// ---------------------------------------------------------------------------------------------------------------- respaldo
/// Ventana sencilla de AppKit (título, estado y barra) para una Mac sin gráfica Metal (máquinas virtuales, como la Mac Intel
/// de GitHub): ahí la ventana animada de SwiftUI se cae al dibujarse. Instala igual. También con «instalar --sencilla».
final class VistaSencilla {
    let ventana: NSWindow
    let estado = NSTextField(labelWithString: "Preparando la instalación…")
    let barra = NSProgressIndicator()

    init(titulo: String) {
        ventana = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 520, height: 150), styleMask: [.titled, .miniaturizable],
                           backing: .buffered, defer: false)
        ventana.title = titulo
        let t = NSTextField(labelWithString: titulo)
        t.font = NSFont.boldSystemFont(ofSize: 18)
        t.frame = NSRect(x: 24, y: 98, width: 472, height: 26)
        estado.frame = NSRect(x: 24, y: 66, width: 472, height: 20)
        estado.textColor = .secondaryLabelColor
        estado.lineBreakMode = .byTruncatingTail
        barra.isIndeterminate = false
        barra.minValue = 0
        barra.maxValue = 100
        barra.style = .bar
        barra.frame = NSRect(x: 24, y: 30, width: 472, height: 20)
        ventana.contentView?.addSubview(t)
        ventana.contentView?.addSubview(estado)
        ventana.contentView?.addSubview(barra)
        ventana.center()
        ventana.makeKeyAndOrderFront(nil)
    }

    func actualizar(_ m: Modelo) {
        barra.doubleValue = m.mostrado * 100
        estado.stringValue = m.fase == 3 ? m.titulo : "\(m.titulo)  ·  \(Int((m.mostrado * 100).rounded())) %"
    }
}

// ---------------------------------------------------------------------------------------------------------------- app
final class VentanaSinMarco: NSWindow {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

final class Instalador: NSObject, NSApplicationDelegate {
    let m = Modelo()
    let escena = Escena()
    var ventana: NSWindow?
    var reloj: Timer?
    var antes = Date()
    var abierto = false
    var instalando = false
    var sencilla: VistaSencilla?
    var avisoError = false
    var demo: [(Double, () -> Void)] = []
    var tDemo = Date()
    let args = CommandLine.arguments
    var esDemo: Bool { args.contains("--demo") || args.contains("--demo-error") }
    lazy var recursos = Bundle.main.resourcePath ?? "."
    lazy var origen = recursos + "/" + ZIP_APP
    lazy var version = (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String) ?? "?"

    func applicationDidFinishLaunching(_ n: Notification) {
        // ya instalada esa versión (o una más nueva) y su primer arranque hecho: solo se abre el programa
        if !esDemo, let app = appInstalada(), let inst = versionDe(app), numeroVersion(inst) >= numeroVersion(version),
           leerTexto(DATOS + "/instalado.txt").trimmingCharacters(in: .whitespacesAndNewlines) == inst {
            NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: app), configuration: NSWorkspace.OpenConfiguration()) { _, _ in
                DispatchQueue.main.async { NSApp.terminate(nil) }
            }
            return
        }
        let titulo = "Instalar " + NOMBRE
        let ficha = "v\(version)  ·  todo incluido  ·  no pide contraseña"
        let sinMetal = MTLCreateSystemDefaultDevice() == nil
        if sinMetal || args.contains("--sencilla") {
            sencilla = VistaSencilla(titulo: titulo + " " + version)
        } else {
            let vista = VistaInstalador(m: m, r: Recursos(recursos), escena: escena, titulo: titulo, ficha: ficha,
                                        verRegistro: { [weak self] in self?.verRegistro() },
                                        cerrar: { NSApp.terminate(nil) })
            let w = VentanaSinMarco(contentRect: NSRect(x: 0, y: 0, width: ANCHO, height: ALTO), styleMask: [.borderless],
                                    backing: .buffered, defer: false)
            w.isOpaque = false
            w.backgroundColor = .clear
            w.hasShadow = true
            w.isMovableByWindowBackground = true
            w.title = titulo
            w.contentView = NSHostingView(rootView: vista)
            w.center()
            w.makeKeyAndOrderFront(nil)
            ventana = w
        }
        NSApp.activate(ignoringOtherApps: true)
        m.info = "Se instala en Aplicaciones sin contraseña. Trae ffmpeg, las plantillas, la música, los SFX y las fuentes. " +
                 "Tus carpetas y tus videos no se tocan."
        if esDemo {
            empezarDemo()
        } else {
            let inst = Instalacion(m: m, origen: origen, version: version)
            if sencilla != nil { inst.anotar("ventana sencilla (\(sinMetal ? "esta Mac no tiene gráfica Metal" : "--sencilla"))") }
            instalando = true
            DispatchQueue.global(qos: .userInitiated).async { inst.correr() }
        }
        antes = Date()
        reloj = Timer.scheduledTimer(withTimeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in self?.tic() }
    }

    func applicationShouldTerminate(_ s: NSApplication) -> NSApplication.TerminateReply {
        // no se cierra a media instalación (si solo abrió el programa ya instalado, sí: nunca empezó a instalar)
        return (instalando && m.fase == 1 && !esDemo) ? .terminateCancel : .terminateNow
    }

    func tic() {
        let ahora = Date()
        let dt = min(0.1, max(0, ahora.timeIntervalSince(antes)))
        antes = ahora
        if esDemo { alimentarDemo() }
        m.avanzar(dt)
        if let s = sencilla {
            s.actualizar(m)
            if m.fase == 3 && !avisoError && !esDemo {          // en la ventana sencilla, el error va en un aviso
                avisoError = true
                let a = NSAlert()
                a.messageText = m.titulo
                a.informativeText = m.info
                a.addButton(withTitle: "Cerrar")
                a.addButton(withTitle: "Ver registro")
                if a.runModal() == .alertSecondButtonReturn { verRegistro() }
                NSApp.terminate(nil)
            }
        }
        // al terminar: la barra llega al 100 %, se ven las ondas un momento y se abre el programa
        if m.fase == 2 && !abierto && !esDemo && ahora.timeIntervalSince(m.tFase) > 1.2 {
            abierto = true
            abrirYSalir()
        }
    }

    /// Abre el programa YA, se cierra el instalador y el disco se expulsa solo (desde un proceso aparte, cuando este ya salió).
    func abrirYSalir() {
        if let app = appInstalada() {
            NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: app), configuration: NSWorkspace.OpenConfiguration()) { _, _ in }
        }
        let expulsar = Process()
        expulsar.executableURL = URL(fileURLWithPath: "/bin/sh")
        expulsar.arguments = ["-c", "sleep 3; for v in /Volumes/*; do [ -f \"$v/\(INSTALADOR)/Contents/Resources/\(ZIP_APP)\" ] || continue; " +
                              "/usr/bin/hdiutil detach \"$v\" -quiet || /usr/bin/hdiutil detach \"$v\" -force -quiet; done; exit 0"]
        expulsar.standardInput = FileHandle.nullDevice
        expulsar.standardOutput = FileHandle.nullDevice
        expulsar.standardError = FileHandle.nullDevice
        try? expulsar.run()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { NSApp.terminate(nil) }
    }

    func verRegistro() {
        _ = NSWorkspace.shared.open(URL(fileURLWithPath: REGISTRO))
    }

    // ---- simulación (--demo / --demo-error): para ver el diseño sin instalar nada
    func empezarDemo() {
        tDemo = Date()
        let m = self.m
        func en(_ t: Double, _ f: @escaping () -> Void) { demo.append((t, f)) }
        en(0.4) { m.paso(0, .enCurso) }
        en(1.2) { m.paso(0, .hecho); m.paso(1, .enCurso, 0) }
        for k in 1...20 { en(1.2 + Double(k) * 0.3) { m.paso(1, .enCurso, k * 5) } }
        if args.contains("--demo-error") {
            en(7.6) { m.fallar(1, "No se pudo copiar el programa a /Applications (no hay espacio en el disco).") }
            return
        }
        en(7.6) { m.paso(1, .hecho); m.paso(2, .enCurso) }
        en(8.4) { m.paso(2, .hecho); m.paso(3, .enCurso, 10) }
        en(9.0) { m.paso(3, .enCurso, 35) }
        en(9.8) { m.paso(3, .enCurso, 60) }
        en(10.6) { m.paso(3, .enCurso, 92) }
        en(11.2) { m.paso(3, .hecho); m.terminar(avisos: false) }
    }

    func alimentarDemo() {
        let k = Date().timeIntervalSince(tDemo)
        while let e = demo.first, e.0 <= k {
            demo.removeFirst()
            e.1()
        }
    }
}

@main
struct Principal {
    static func main() {
        let app = NSApplication.shared
        let delegado = Instalador()
        app.delegate = delegado
        app.setActivationPolicy(.regular)
        app.run()
    }
}
