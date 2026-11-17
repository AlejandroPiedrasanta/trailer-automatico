// Tráiler automático · CINEMA PRODUCTIONS
// compilar/Instalador.cs — el instalador y desinstalador (C#, .NET Framework 4), con el mismo diseño que el de CineCaptions:
// ventana sin marco, banner animado con el astrolabio que gira, lista de PASOS, % grande, barra moderna y botón píldora.
// ---------------------------------------------------------------------------
// El programa compilado (PyInstaller) va PEGADO al final de este .exe como un .zip, seguido de 16 bytes: posicion del zip
// (Int64) + "TRAILER1". El mismo .exe SIN el zip es el desinstalador (<instalacion>\Desinstalar.exe /desinstalar).
// Se instala SOLO para el usuario (sin UAC): %LOCALAPPDATA%\Programs\TrailerAutomatico. Lo que sabe hacer el programa (fuentes,
// color en DaVinci, carpetas, autoprueba) se lo pide al .exe recien instalado con "--tarea <nombre> <estado.txt>".
// Doble clic = instala solo y al terminar abre el programa y se cierra (como CineCaptions). Opciones: /silencioso  /desinstalar  /dir=<carpeta>  /sinescritorio  /noabrir
// Lo compila construir.ps1 con el csc.exe de .NET Framework 4 (C# 5: nada de $"" ni ?.).
// ---------------------------------------------------------------------------
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("Instalar Tráiler automático")]
[assembly: AssemblyCompany("CINEMA PRODUCTIONS")]
[assembly: AssemblyProduct("Tráiler automático")]
[assembly: AssemblyVersion("__VERSION__.0")]

interface IVista
{
    void PasoCambiado(int i, EstadoPaso estado, int progreso);
    void Log(string texto);
}

// (1.6.0) COM del acceso directo con propiedades (para el AppUserModelID)
[ComImport, Guid("00021401-0000-0000-C000-000000000046")]
class ShellLinkCom { }

[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("000214F9-0000-0000-C000-000000000046")]
interface IShellLinkW
{
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszFile, int cch, IntPtr pfd, int fFlags);
    void GetIDList(out IntPtr ppidl);
    void SetIDList(IntPtr pidl);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszName, int cch);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string pszName);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszDir, int cch);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string pszDir);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszArgs, int cch);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string pszArgs);
    void GetHotkey(out short pwHotkey);
    void SetHotkey(short wHotkey);
    void GetShowCmd(out int piShowCmd);
    void SetShowCmd(int iShowCmd);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszIconPath, int cch, out int piIcon);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string pszIconPath, int iIcon);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string pszPathRel, int dwReserved);
    void Resolve(IntPtr hwnd, int fFlags);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string pszFile);
}

[StructLayout(LayoutKind.Sequential, Pack = 4)]
struct ClaveProp { public Guid fmtid; public uint pid; }

[StructLayout(LayoutKind.Explicit, Size = 16)]
struct ValorProp
{
    [FieldOffset(0)] public ushort vt;
    [FieldOffset(8)] public IntPtr p;
}

[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
interface IPropertyStore
{
    void GetCount(out uint cProps);
    void GetAt(uint iProp, out ClaveProp pkey);
    void GetValue(ref ClaveProp key, out ValorProp pv);
    void SetValue(ref ClaveProp key, ref ValorProp pv);
    void Commit();
}

static class Instalador
{
    public const string APP = "TrailerAutomatico";
    public const string NOMBRE = "Tráiler automático";
    public const string VERSION = "__VERSION__";
    public const string EXE = "TrailerAutomatico.exe";
    const string MARCA = "TRAILER1";
    public static string Destino = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", APP);
    public static bool Escritorio = true, NoAbrir = false;

    [STAThread]
    static int Main(string[] args)
    {
        bool silencioso = false, desinstalar = false;
        foreach (string a in args)
        {
            string x = a.ToLowerInvariant();
            if (x == "/silencioso") silencioso = true;
            else if (x == "/desinstalar") desinstalar = true;
            else if (x == "/sinescritorio") Escritorio = false;
            else if (x == "/noabrir") NoAbrir = true;
            else if (x.StartsWith("/dir=")) Destino = a.Substring(5).Trim('"');
        }
        if (desinstalar && Path.GetFileName(Assembly.GetExecutingAssembly().Location).ToLowerInvariant() == "desinstalar.exe")
            Destino = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        if (silencioso)
            return (desinstalar ? Desinstalar(null) : Instalar(null)) == null ? 0 : 1;
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new Ventana(desinstalar));
        return 0;
    }

    public static List<Paso> PasosInstalar()
    {
        return new List<Paso> {
            new Paso("Cerrar la versión anterior", "Preparando la instalación...", 0.3),
            new Paso("Copiar el programa", "Copiando el programa...", 6.0),
            new Paso("Accesos directos", "Creando los accesos directos...", 0.4),
            new Paso("Fuentes, color y carpetas", "Instalando fuentes, color y carpetas...", 1.2) };
    }

    public static List<Paso> PasosDesinstalar()
    {
        return new List<Paso> {
            new Paso("Cerrar el programa", "Cerrando el programa...", 0.5),
            new Paso("Quitar accesos y registro", "Quitando los accesos directos...", 0.5),
            new Paso("Borrar el programa", "Borrando el programa...", 2.0) };
    }

    static void P(IVista v, int i, EstadoPaso e, int pr) { if (v != null) v.PasoCambiado(i, e, pr); }
    static void L(IVista v, string t) { if (v != null) v.Log(t); }

    // ------------------------------------------------------------------ el zip pegado al final
    static long[] Carga(string exe)
    {
        using (FileStream f = File.OpenRead(exe))
        {
            if (f.Length < 16) return null;
            f.Seek(-16, SeekOrigin.End);
            byte[] pie = new byte[16];
            f.Read(pie, 0, 16);
            if (Encoding.ASCII.GetString(pie, 8, 8) != MARCA) return null;
            long ini = BitConverter.ToInt64(pie, 0);
            return new long[] { ini, f.Length - 16 - ini };
        }
    }

    // Donde viene el programa:
    //  (1) pegado al final de este .exe: las actualizaciones, que se instalan solas en segundo plano;
    //  (2) en el archivo de al lado, con el mismo nombre y extension .dat: el instalador. Asi el .exe pesa 1 MB y
    //      Windows lo abre al instante. Con los 560 MB dentro, el antivirus lo revisaba entero ANTES de dejarlo
    //      arrancar: 8 s (o mas) sin que se viera nada despues del doble clic.
    static string ArchivoCarga;
    static long[] RangoCarga;

    static bool BuscarCarga(string yo)
    {
        long[] c = Carga(yo);
        if (c != null) { ArchivoCarga = yo; RangoCarga = c; return true; }
        string dat = Path.ChangeExtension(yo, ".dat");
        if (!File.Exists(dat))
        {
            dat = null;                 // el .exe renombrado ("Instalar (1).exe"): el .dat mas nuevo de la carpeta
            try
            {
                foreach (string f in Directory.GetFiles(Path.GetDirectoryName(yo), "*.dat"))
                    if (Path.GetFileName(f).StartsWith("Instalar Trailer automatico", StringComparison.OrdinalIgnoreCase)
                        && (dat == null || File.GetLastWriteTimeUtc(f) > File.GetLastWriteTimeUtc(dat))) dat = f;
            }
            catch { }
        }
        if (dat == null) return false;
        ArchivoCarga = dat;
        RangoCarga = new long[] { 0, new FileInfo(dat).Length };
        return true;
    }

    class Trozo : Stream    // vista de solo lectura de una parte del archivo (el zip), sin copiarlo
    {
        Stream b; long ini, largo, pos;
        public Trozo(Stream b, long ini, long largo) { this.b = b; this.ini = ini; this.largo = largo; }
        public override bool CanRead { get { return true; } }
        public override bool CanSeek { get { return true; } }
        public override bool CanWrite { get { return false; } }
        public override long Length { get { return largo; } }
        public override long Position { get { return pos; } set { pos = value; } }
        public override void Flush() { }
        public override int Read(byte[] buf, int off, int n)
        {
            if (pos >= largo) return 0;
            if (n > largo - pos) n = (int)(largo - pos);
            b.Seek(ini + pos, SeekOrigin.Begin);
            int r = b.Read(buf, off, n);
            pos += r;
            return r;
        }
        public override long Seek(long o, SeekOrigin d)
        {
            if (d == SeekOrigin.Begin) pos = o; else if (d == SeekOrigin.Current) pos += o; else pos = largo + o;
            return pos;
        }
        public override void SetLength(long v) { throw new NotSupportedException(); }
        public override void Write(byte[] buf, int off, int n) { throw new NotSupportedException(); }
    }

    // ------------------------------------------------------------------ instalar
    static int CerrarPrograma()
    {
        int n = 0;
        foreach (Process p in Process.GetProcessesByName(APP))
        {
            try { p.CloseMainWindow(); if (!p.WaitForExit(4000)) p.Kill(); n++; } catch { }
        }
        return n;
    }

    public static string VersionInstalada()
    {
        try
        {
            using (RegistryKey k = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + APP))
                return k == null ? null : k.GetValue("DisplayVersion") as string;
        }
        catch { return null; }
    }

    public static string Instalar(IVista v)
    {
        int paso = 0;
        try
        {
            string yo = Assembly.GetExecutingAssembly().Location;
            if (!BuscarCarga(yo))
                return "Falta el archivo «" + Path.GetFileNameWithoutExtension(yo) + ".dat»: va en la misma carpeta que este instalador.";
            long[] c = RangoCarga;
            P(v, 0, EstadoPaso.EnCurso, -1);
            int cerrados = CerrarPrograma();
            if (cerrados > 0) L(v, "Se cerró el programa abierto (" + cerrados + ").");
            string interno = Path.Combine(Destino, "_internal");
            if (Directory.Exists(interno)) { Directory.Delete(interno, true); L(v, "Versión anterior quitada."); }
            Directory.CreateDirectory(Destino);
            P(v, 0, EstadoPaso.Hecho, -1);

            paso = 1;
            P(v, 1, EstadoPaso.EnCurso, 0);
            using (FileStream f = File.OpenRead(ArchivoCarga))
            using (ZipArchive z = new ZipArchive(new Trozo(f, c[0], c[1]), ZipArchiveMode.Read))
            {
                long total = 0, hecho = 0;
                foreach (ZipArchiveEntry e in z.Entries) total += e.Length;
                L(v, string.Format("Copiando {0} archivos ({1:N0} MB) a {2}", z.Entries.Count, total / 1048576.0, Destino));
                byte[] buf = new byte[1 << 20];
                int ultimo = -1;
                foreach (ZipArchiveEntry e in z.Entries)
                {
                    string destino = Path.GetFullPath(Path.Combine(Destino, e.FullName));
                    if (!destino.StartsWith(Path.GetFullPath(Destino), StringComparison.OrdinalIgnoreCase)) continue;
                    if (e.FullName.EndsWith("/")) { Directory.CreateDirectory(destino); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(destino));
                    using (Stream o = e.Open())
                    using (FileStream w = File.Create(destino))
                    {
                        int n;
                        while ((n = o.Read(buf, 0, buf.Length)) > 0) { w.Write(buf, 0, n); hecho += n; }
                    }
                    int pct = (int)(100 * hecho / Math.Max(1, total));
                    if (pct != ultimo) { ultimo = pct; P(v, 1, EstadoPaso.EnCurso, pct); }
                }
            }
            P(v, 1, EstadoPaso.Hecho, -1);

            paso = 2;
            P(v, 2, EstadoPaso.EnCurso, -1);
            using (FileStream f = File.OpenRead(yo))
            using (FileStream w = File.Create(Path.Combine(Destino, "Desinstalar.exe")))
            {
                byte[] buf = new byte[1 << 16];
                long falta = ArchivoCarga == yo ? c[0] : f.Length;      // este .exe sin el programa pegado
                while (falta > 0)
                {
                    int n = f.Read(buf, 0, (int)Math.Min(buf.Length, falta));
                    if (n <= 0) break;
                    w.Write(buf, 0, n);
                    falta -= n;
                }
            }
            string exe = Path.Combine(Destino, EXE);
            Acceso(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), NOMBRE + ".lnk"), exe);
            if (Escritorio)
                Acceso(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), NOMBRE + ".lnk"), exe);
            Registrar(exe);
            try { SHChangeNotify(0x08000000, 0, IntPtr.Zero, IntPtr.Zero); } catch { }   // (1.6.0) Windows relee los iconos
            L(v, "Accesos en el menú Inicio" + (Escritorio ? " y en el Escritorio" : "") + "; aparece en Configuración > Aplicaciones.");
            P(v, 2, EstadoPaso.Hecho, -1);

            paso = 3;
            P(v, 3, EstadoPaso.EnCurso, 0);
            string res = Tarea(exe, "instalar", 180, v, 3);
            if (res != null && res.StartsWith("ERROR")) { P(v, 3, EstadoPaso.Aviso, -1); L(v, res); }
            else { P(v, 3, EstadoPaso.Hecho, -1); if (res != null) L(v, res.Substring(3)); }
            // sin autoprueba aqui: el paso anterior ya arranco el programa instalado, y al abrirse hace su chequeo
            // de arranque y lo muestra. Eran varios segundos de espera antes de poder usarlo.
            return null;
        }
        catch (Exception ex)
        {
            P(v, paso, EstadoPaso.Error, -1);
            L(v, "ERROR: " + ex.Message);
            return ex.Message;
        }
    }

    static string Tarea(string exe, string tarea, int segundos, IVista v, int paso)
    {
        string estado = Path.Combine(Path.GetTempPath(), "trailer_" + tarea + ".txt");
        try { File.Delete(estado); } catch { }
        ProcessStartInfo si = new ProcessStartInfo(exe, "--tarea " + tarea + " \"" + estado + "\"");
        si.WorkingDirectory = Path.GetDirectoryName(exe);
        si.UseShellExecute = false;
        si.CreateNoWindow = true;
        Process p = Process.Start(si);
        DateTime fin = DateTime.Now.AddSeconds(segundos);
        string ultima = null;
        int leidas = 0;
        while (DateTime.Now < fin)
        {
            Thread.Sleep(250);
            try
            {
                if (File.Exists(estado))
                {
                    // (1.6.0) leerlo DEJANDO escribir: con File.ReadAllLines el programa no podia anotar mientras se
                    // leia («Permission denied: trailer_instalar.txt», 13-nov) y la tarea se caia
                    List<string> l0 = new List<string>();
                    using (FileStream fs = new FileStream(estado, FileMode.Open, FileAccess.Read,
                                                          FileShare.ReadWrite | FileShare.Delete))
                    using (StreamReader sr = new StreamReader(fs, Encoding.UTF8))
                    {
                        string s;
                        while ((s = sr.ReadLine()) != null) l0.Add(s);
                    }
                    string[] lineas = l0.ToArray();
                    for (int i = leidas; i < lineas.Length; i++)
                    {
                        string l = lineas[i];
                        if (l.StartsWith("PROGRESO|"))
                        {
                            string[] x = l.Split(new char[] { '|' }, 3);
                            int n;
                            if (x.Length == 3 && int.TryParse(x[1], out n)) { P(v, paso, EstadoPaso.EnCurso, n); L(v, x[2]); }
                        }
                        else if (l.StartsWith("OK|") || l.StartsWith("ERROR|")) ultima = l;
                    }
                    leidas = lineas.Length;
                }
            }
            catch { }
            if (ultima != null || p.HasExited) break;
        }
        if (!p.HasExited) { try { p.Kill(); } catch { } return "ERROR|tardó demasiado"; }
        return ultima;
    }

    // (1.6.0) El acceso lleva el mismo AppUserModelID que la ventana (trailer_xv.py: SetCurrentProcessExplicit...).
    // Sin eso Windows conoce el programa por la ruta del .exe y, al abrirlo por su ID (icono anclado en la barra,
    // «Recomendado» del Inicio, una notificacion), sale «Windows no puede encontrar el archivo cinemaproductions.trailer».
    public const string AUMID = "CinemaProductions.Trailer";

    [DllImport("shell32.dll")] static extern void SHChangeNotify(int wEventId, int uFlags, IntPtr dwItem1, IntPtr dwItem2);

    static void Acceso(string lnk, string exe)
    {
        try
        {
            IShellLinkW l = (IShellLinkW)new ShellLinkCom();
            l.SetPath(exe);
            l.SetWorkingDirectory(Path.GetDirectoryName(exe));
            l.SetIconLocation(exe, 0);
            l.SetDescription("Un clic y listo · CINEMA PRODUCTIONS");
            IPropertyStore ps = (IPropertyStore)l;
            ClaveProp clave = new ClaveProp();
            clave.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");      // PKEY_AppUserModel_ID
            clave.pid = 5;
            ValorProp valor = new ValorProp();
            valor.vt = 31;                                                     // VT_LPWSTR
            valor.p = Marshal.StringToCoTaskMemUni(AUMID);
            try { ps.SetValue(ref clave, ref valor); ps.Commit(); }
            finally { Marshal.FreeCoTaskMem(valor.p); }
            ((System.Runtime.InteropServices.ComTypes.IPersistFile)l).Save(lnk, true);
            Marshal.ReleaseComObject(l);
            return;
        }
        catch { }
        AccesoSimple(lnk, exe);                       // sin el ID (si fallara la via COM): al menos el acceso
    }

    static void AccesoSimple(string lnk, string exe)
    {
        try
        {
            Type t = Type.GetTypeFromProgID("WScript.Shell");
            object sh = Activator.CreateInstance(t);
            object a = t.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, sh, new object[] { lnk });
            Type at = a.GetType();
            at.InvokeMember("TargetPath", BindingFlags.SetProperty, null, a, new object[] { exe });
            at.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, a, new object[] { Path.GetDirectoryName(exe) });
            at.InvokeMember("IconLocation", BindingFlags.SetProperty, null, a, new object[] { exe + ",0" });
            at.InvokeMember("Description", BindingFlags.SetProperty, null, a, new object[] { "Un clic y listo · CINEMA PRODUCTIONS" });
            at.InvokeMember("Save", BindingFlags.InvokeMethod, null, a, null);
        }
        catch { }
    }

    static void Registrar(string exe)
    {
        using (RegistryKey k = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + APP))
        {
            string des = Path.Combine(Destino, "Desinstalar.exe");
            k.SetValue("DisplayName", NOMBRE);
            k.SetValue("DisplayVersion", VERSION);
            k.SetValue("Publisher", "CINEMA PRODUCTIONS");
            k.SetValue("DisplayIcon", exe + ",0");
            k.SetValue("InstallLocation", Destino);
            k.SetValue("UninstallString", "\"" + des + "\" /desinstalar");
            k.SetValue("QuietUninstallString", "\"" + des + "\" /desinstalar /silencioso");
            k.SetValue("NoModify", 1, RegistryValueKind.DWord);
            k.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            long kb = 0;
            foreach (string f in Directory.GetFiles(Destino, "*", SearchOption.AllDirectories)) kb += new FileInfo(f).Length / 1024;
            k.SetValue("EstimatedSize", (int)Math.Min(int.MaxValue, kb), RegistryValueKind.DWord);
        }
    }

    // ------------------------------------------------------------------ desinstalar
    public static string Desinstalar(IVista v)
    {
        try
        {
            P(v, 0, EstadoPaso.EnCurso, -1);
            CerrarPrograma();
            P(v, 0, EstadoPaso.Hecho, -1);
            P(v, 1, EstadoPaso.EnCurso, -1);
            try { File.Delete(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), NOMBRE + ".lnk")); } catch { }
            try { File.Delete(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), NOMBRE + ".lnk")); } catch { }
            try { Registry.CurrentUser.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + APP, false); } catch { }
            try   // la tarea programada de las actualizaciones (la crea el programa: actualizar_fondo.asegurar_programada)
            {
                ProcessStartInfo st = new ProcessStartInfo("schtasks", "/Delete /TN \"Trailer automatico Actualizaciones\" /F");
                st.CreateNoWindow = true; st.UseShellExecute = false;
                using (Process q = Process.Start(st)) { q.WaitForExit(15000); }
            }
            catch { }
            L(v, "Accesos directos y entrada de Aplicaciones quitados.");
            P(v, 1, EstadoPaso.Hecho, -1);
            P(v, 2, EstadoPaso.EnCurso, -1);
            try { Directory.Delete(Path.Combine(Destino, "_internal"), true); } catch { }
            try { File.Delete(Path.Combine(Destino, EXE)); } catch { }
            // la carpeta (y este mismo Desinstalar.exe) se borran al cerrar
            ProcessStartInfo si = new ProcessStartInfo("cmd.exe", "/c ping 127.0.0.1 -n 3 > nul & rmdir /s /q \"" + Destino + "\"");
            si.CreateNoWindow = true;
            si.UseShellExecute = false;
            si.WorkingDirectory = Path.GetTempPath();
            Process.Start(si);
            L(v, "Programa borrado. Tus carpetas de trabajo y tus videos siguen intactos.");
            P(v, 2, EstadoPaso.Hecho, -1);
            return null;
        }
        catch (Exception ex)
        {
            L(v, "ERROR: " + ex.Message);
            return ex.Message;
        }
    }

    public static Process Abrir()
    {
        ProcessStartInfo si = new ProcessStartInfo(Path.Combine(Destino, EXE));
        si.WorkingDirectory = Destino;          // leccion de CineCaptions: nunca heredar la carpeta del instalador
        si.UseShellExecute = true;
        return Process.Start(si);
    }
}

// ---------------------------------------------------------------------- la ventana (como la de CineCaptions)
class Ventana : Form, IVista
{
    readonly bool desinstalar;
    readonly List<Paso> pasos;
    float esc = 1f;
    const int AltoBanner = 236, AnchoBase = 880, AltoBase = 580, ExtraDetalles = 230;
    bool trabajando, terminado, error, detalles;
    Banner banner;
    BotonCirculo bMin, bCer;
    Panel cuerpo, sep;
    ListaPasos lista;
    Label lblEstado, lblPct, lblInfo, lblFirma;
    BarraModerna barra;
    BotonPildora boton;
    LinkLabel lnkDetalles;
    PictureBox picMarca;
    RichTextBox log;

    public Ventana(bool desinstalar)
    {
        this.desinstalar = desinstalar;
        pasos = desinstalar ? Instalador.PasosDesinstalar() : Instalador.PasosInstalar();
        using (Graphics g = CreateGraphics()) esc = g.DpiX / 96f;
        Text = (desinstalar ? "Desinstalar " : "Instalar ") + Instalador.NOMBRE;
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Tema.Fondo;
        ForeColor = Color.White;
        AutoScaleMode = AutoScaleMode.None;
        ClientSize = new Size(E(AnchoBase), E(AltoBase));
        DoubleBuffered = true;
        Opacity = 0;
        Armar();
        Resize += delegate { Centrar(); };
        Shown += delegate
        {
            Centrar();
            Dibujo.Oscuro(log);
            Activate();
            Entrar();
            if (!desinstalar) Empezar();          // doble clic = instala solo
        };
    }

    int E(float v) { return (int)Math.Round(v * esc); }

    static Image Recurso(string nombre)
    {
        try { return Image.FromStream(Assembly.GetExecutingAssembly().GetManifestResourceStream(nombre)); } catch { return null; }
    }

    void Armar()
    {
        banner = new Banner();
        banner.Esc = esc;
        banner.Dock = DockStyle.Top;
        banner.Height = E(AltoBanner);
        banner.Imagen = Recurso("banner.jpg");
        banner.Logo = Recurso("logo.png");
        banner.CapaRunas = Recurso("astro_runas.png");
        banner.CapaEngr = Recurso("astro_engr.png");
        banner.CapaFili = Recurso("astro_fili.png");
        banner.CapaNucleo = Recurso("astro_nucleo.png");
        banner.Titulo = desinstalar ? "Desinstalar" : "Instalar " + Instalador.NOMBRE;
        banner.Frase = "Tu evento hecho tráiler en DaVinci Resolve";
        banner.Ficha = desinstalar ? "tus carpetas de trabajo y tus videos no se tocan"
                                   : "v" + Instalador.VERSION + "  ·  todo incluido  ·  no necesita Python";
        banner.MouseDown += delegate(object s, MouseEventArgs e) { if (e.Button == MouseButtons.Left) Dibujo.Arrastrar(this); };
        Controls.Add(banner);

        bMin = Circulo("", Color.FromArgb(109, 157, 240));
        bMin.Click += delegate { WindowState = FormWindowState.Minimized; };
        bCer = Circulo("", Color.FromArgb(240, 101, 92));
        bCer.Click += delegate { Close(); };

        cuerpo = new Panel();
        cuerpo.BackColor = Tema.Fondo;
        cuerpo.Size = new Size(E(AnchoBase), E(AltoBase - AltoBanner));
        Controls.Add(cuerpo);
        cuerpo.BringToFront();

        lista = new ListaPasos();
        lista.Esc = esc;
        lista.Pasos = pasos;
        lista.SetBounds(E(36), E(16), E(372), E(30 + 32 * pasos.Count));
        cuerpo.Controls.Add(lista);

        sep = new Panel();
        sep.BackColor = Tema.Linea;
        sep.SetBounds(E(424), E(18), Math.Max(1, E(1)), E(290));
        cuerpo.Controls.Add(sep);

        lblEstado = Etiqueta(desinstalar ? "Listo para desinstalar" : "Preparando la instalación...", 14f, true, Color.White);
        lblEstado.SetBounds(E(450), E(24), E(300), E(44));
        lblEstado.AutoEllipsis = true;
        lblPct = Etiqueta("", 20f, true, Tema.Cian);
        lblPct.TextAlign = ContentAlignment.MiddleRight;
        lblPct.SetBounds(E(752), E(20), E(100), E(46));
        barra = new BarraModerna();
        barra.SetBounds(E(452), E(76), E(396), E(14));
        cuerpo.Controls.Add(barra);
        lblInfo = Etiqueta(TextoInfo(), 9.5f, false, Tema.Suave);
        lblInfo.SetBounds(E(450), E(100), E(400), E(96));

        boton = new BotonPildora();
        boton.Text = desinstalar ? "DESINSTALAR" : "INSTALAR";
        if (desinstalar) boton.Colores(Color.FromArgb(226, 92, 80), Color.FromArgb(150, 44, 60));
        boton.SetBounds(E(452), E(211), E(398), E(56));
        boton.Click += delegate
        {
            if (!boton.Enabled) return;
            if (terminado && !error) { if (!desinstalar) Instalador.Abrir(); Close(); }
            else if (terminado && error) { Empezar(); }
            else Empezar();
        };
        cuerpo.Controls.Add(boton);

        lnkDetalles = Enlace("Ver detalles", E(452), E(284));
        lnkDetalles.LinkClicked += delegate { AlternarDetalles(); };

        Image marca = Recurso("marca.png");
        lblFirma = Etiqueta(Instalador.NOMBRE, 9f, false, Color.FromArgb(78, 96, 126));
        lblFirma.SetBounds(E(40), E(314), E(118), E(20));
        if (marca != null)
        {
            int altoM = E(15), anchoM = (int)Math.Round(altoM * (double)marca.Width / marca.Height);
            Bitmap tenue = new Bitmap(anchoM, altoM);
            using (Graphics g = Graphics.FromImage(tenue))
            using (ImageAttributes ia = new ImageAttributes())
            {
                ColorMatrix cm = new ColorMatrix();
                cm.Matrix33 = 0.62f;
                ia.SetColorMatrix(cm);
                g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                g.DrawImage(marca, new Rectangle(0, 0, anchoM, altoM), 0, 0, marca.Width, marca.Height, GraphicsUnit.Pixel, ia);
            }
            picMarca = new PictureBox();
            picMarca.Image = tenue;
            picMarca.BackColor = Tema.Fondo;
            picMarca.SetBounds(E(40) + E(124), E(317), anchoM, altoM);
            cuerpo.Controls.Add(picMarca);
        }

        log = new RichTextBox();
        log.SetBounds(E(36), E(344), E(812), E(ExtraDetalles - 16));
        log.ReadOnly = true;
        log.BackColor = Tema.FondoLog;
        log.ForeColor = Color.FromArgb(170, 190, 210);
        log.Font = new Font("Consolas", 8.5f);
        log.BorderStyle = BorderStyle.None;
        log.Visible = false;
        cuerpo.Controls.Add(log);
    }

    string TextoInfo()
    {
        string carpeta = Instalador.Destino.Replace(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "%USERPROFILE%");
        if (desinstalar)
            return "Se quita el programa, sus accesos directos y su entrada en Aplicaciones. Tus eventos terminados " +
                   "(EVENTO TERMINADO en el Escritorio) y el material guardado no se tocan.";
        string t = "Se instala solo para tu usuario (sin permisos de administrador) en " + carpeta +
                   ". Trae ffmpeg, las plantillas, la música, los SFX y las fuentes. Tus carpetas y tus videos no se tocan.";
        string v = Instalador.VersionInstalada();
        if (v != null) t += " Reemplaza la versión " + v + ".";
        return t;
    }

    BotonCirculo Circulo(string glifo, Color tono)
    {
        BotonCirculo b = new BotonCirculo();
        b.Glifo = glifo;
        b.Tono = tono;
        b.Size = new Size(E(34), E(34));
        banner.Controls.Add(b);
        return b;
    }

    Label Etiqueta(string texto, float tam, bool negrita, Color color)
    {
        Label l = new Label();
        l.Text = texto;
        l.Font = new Font("Segoe UI", tam, negrita ? FontStyle.Bold : FontStyle.Regular);
        l.ForeColor = color;
        l.BackColor = Tema.Fondo;
        cuerpo.Controls.Add(l);
        return l;
    }

    LinkLabel Enlace(string texto, int x, int y)
    {
        LinkLabel d = new LinkLabel();
        d.Text = texto;
        d.LinkColor = Color.FromArgb(110, 150, 200);
        d.ActiveLinkColor = Color.White;
        d.LinkBehavior = LinkBehavior.HoverUnderline;
        d.Font = new Font("Segoe UI", 9.5f);
        d.BackColor = Tema.Fondo;
        d.Location = new Point(x, y);
        d.AutoSize = true;
        cuerpo.Controls.Add(d);
        return d;
    }

    void Centrar()
    {
        int x = ClientSize.Width - E(2 * 42 + 14);
        foreach (BotonCirculo b in new BotonCirculo[] { bMin, bCer }) { b.Location = new Point(x, E(14)); x += E(42); }
        cuerpo.Left = Math.Max(0, (ClientSize.Width - cuerpo.Width) / 2);
        cuerpo.Top = banner.Height;
        using (GraphicsPath p = Dibujo.Redondeado(new RectangleF(0, 0, Width, Height), E(18))) Region = new Region(p);
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
        using (Pen pen = new Pen(Color.FromArgb(48, 80, 130), 2))
        using (GraphicsPath p = Dibujo.Redondeado(new RectangleF(1, 1, Width - 2, Height - 2), E(18)))
            e.Graphics.DrawPath(pen, p);
    }

    void AlternarDetalles()
    {
        detalles = !detalles;
        log.Visible = detalles;
        cuerpo.Height = E(AltoBase - AltoBanner + (detalles ? ExtraDetalles : 0));
        ClientSize = new Size(ClientSize.Width, E(AltoBase + (detalles ? ExtraDetalles : 0)));
        lnkDetalles.Text = detalles ? "Ocultar detalles" : "Ver detalles";
        Rectangle area = Screen.FromControl(this).WorkingArea;
        if (Bottom > area.Bottom) Top = Math.Max(area.Top, area.Bottom - Height);
        Centrar();
    }

    void Entrar()
    {
        System.Windows.Forms.Timer t = new System.Windows.Forms.Timer();
        t.Interval = 16;
        t.Tick += delegate { Opacity = Math.Min(1.0, Opacity + 0.08); if (Opacity >= 1.0) { t.Stop(); t.Dispose(); } };
        t.Start();
    }

    void Empezar()
    {
        if (trabajando) return;
        trabajando = true;
        terminado = error = false;
        foreach (Paso p in pasos) { p.Estado = EstadoPaso.Pendiente; p.Progreso = -1; }
        boton.Enabled = false;
        boton.Text = desinstalar ? "DESINSTALANDO..." : "INSTALANDO...";
        banner.Estado = 1;
        lblPct.Text = "0 %";
        Thread hilo = new Thread(delegate ()
        {
            string res = desinstalar ? Instalador.Desinstalar(this) : Instalador.Instalar(this);
            BeginInvoke((MethodInvoker)delegate { Terminar(res); });
        });
        hilo.IsBackground = true;
        hilo.Start();
    }

    void Terminar(string res)
    {
        trabajando = false;
        terminado = true;
        error = res != null;
        bool avisos = false;
        foreach (Paso p in pasos) if (p.Estado == EstadoPaso.Aviso) avisos = true;
        banner.Estado = error ? 3 : 2;
        barra.Valor = error ? barra.Valor : 1.0;
        lblPct.Text = error ? "" : "100 %";
        boton.Enabled = true;
        if (error)
        {
            lblEstado.Text = "No se pudo terminar";
            lblInfo.Text = res + "  ·  Mira «Ver detalles» y pulsa REINTENTAR.";
            boton.Text = "REINTENTAR";
            if (!detalles) AlternarDetalles();
        }
        else if (desinstalar)
        {
            lblEstado.Text = "Desinstalado";
            lblInfo.Text = Instalador.NOMBRE + " se quitó. Tus carpetas de trabajo y tus videos siguen intactos.";
            boton.Text = "CERRAR";
            boton.Colores(Tema.Acento, Tema.Cian);
        }
        else
        {
            lblEstado.Text = avisos ? "¡Listo, con avisos!" : "¡Listo!";
            lblInfo.Text = avisos ? "Se instaló, pero algo quedó con aviso: mira «Ver detalles»."
                                  : "Ya está en el Escritorio y en el menú Inicio. Abre el programa, sube tu material y pulsa el botón del centro.";
            boton.Text = "ABRIR";
            if (Instalador.NoAbrir) boton.Text = "CERRAR";
            else
            {   // la persona: "cuando se termine de instalar se abre automaticamente y se cierra el instalador"
                lblInfo.Text = (avisos ? "Se instaló con avisos (el programa te los muestra). " : "") +
                               "Abriendo " + Instalador.NOMBRE + "...";
                // sin esperas: el programa se abre YA y esta ventana se queda hasta que la suya se ve (asi no hay un
                // momento con la pantalla vacia); con avisos, un instante mas para poder leerlos
                bool conAvisos = avisos;
                Thread abre = new Thread(delegate ()
                {
                    Process p = null;
                    try { p = Instalador.Abrir(); } catch { }
                    DateTime fin = DateTime.Now.AddSeconds(25);
                    while (p != null && DateTime.Now < fin)
                    {
                        try { p.Refresh(); if (p.HasExited || p.MainWindowHandle != IntPtr.Zero) break; } catch { break; }
                        Thread.Sleep(100);
                    }
                    if (conAvisos) Thread.Sleep(2500);
                    try { BeginInvoke((MethodInvoker)delegate { Close(); }); } catch { }
                });
                abre.IsBackground = true;
                abre.Start();
            }
        }
    }

    public void PasoCambiado(int i, EstadoPaso estado, int progreso)
    {
        if (InvokeRequired) { BeginInvoke((MethodInvoker)delegate { PasoCambiado(i, estado, progreso); }); return; }
        if (i < 0 || i >= pasos.Count) return;
        pasos[i].Estado = estado;
        pasos[i].Progreso = progreso;
        if (estado == EstadoPaso.EnCurso) lblEstado.Text = pasos[i].Accion;
        double total = 0, hecho = 0;
        foreach (Paso p in pasos)
        {
            total += p.Peso;
            if (p.Estado == EstadoPaso.Hecho || p.Estado == EstadoPaso.Aviso || p.Estado == EstadoPaso.Omitido) hecho += p.Peso;
            else if (p.Estado == EstadoPaso.EnCurso && p.Progreso > 0) hecho += p.Peso * p.Progreso / 100.0;
        }
        double f = total > 0 ? hecho / total : 0;
        barra.Valor = f;
        lblPct.Text = ((int)Math.Round(f * 100)) + " %";
        lista.Invalidate();
    }

    public void Log(string texto)
    {
        if (InvokeRequired) { BeginInvoke((MethodInvoker)delegate { Log(texto); }); return; }
        log.AppendText(DateTime.Now.ToString("HH:mm:ss") + "  " + texto + "\n");
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        if (trabajando && MessageBox.Show("Todavía está trabajando. ¿Cerrar de todos modos?", Instalador.NOMBRE,
                MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes)
        {
            e.Cancel = true;
            return;
        }
        base.OnFormClosing(e);
    }
}

// ---------------------------------------------------------------------- piezas de interfaz de CineCaptions

enum EstadoPaso { Pendiente, EnCurso, Hecho, Aviso, Error, Omitido }

class Paso
{
    public string Titulo;              // en la lista de PASOS (corto)
    public string Accion;              // titulo grande de la derecha mientras corre ("Copiando el programa...")
    public string Detalle = "";
    public EstadoPaso Estado = EstadoPaso.Pendiente;
    public int Progreso = -1;          // 0-100 dentro del paso, -1 = sin dato
    public double Peso = 1;            // cuanto pesa en la barra general
    public Paso(string t, string accion, double peso) { Titulo = t; Accion = accion; Peso = peso; }
}

static class Tema
{
    public static readonly Color Fondo = Color.FromArgb(8, 12, 20);          // BG_COLOR del programa
    public static readonly Color FondoLog = Color.FromArgb(4, 7, 13);
    public static readonly Color Suave = Color.FromArgb(150, 165, 192);
    public static readonly Color Pendiente = Color.FromArgb(118, 132, 158);
    public static readonly Color Linea = Color.FromArgb(30, 42, 66);          // BORDER_COLOR
    public static readonly Color Acento = Color.FromArgb(22, 163, 106);       // esmeralda (como el programa nuevo)
    public static readonly Color Cian = Color.FromArgb(70, 228, 170);
    public static readonly Color EnCurso = Color.FromArgb(96, 236, 178);
    public static readonly Color Ok = Color.FromArgb(98, 209, 150);
    public static readonly Color Aviso = Color.FromArgb(255, 184, 107);
    public static readonly Color Error = Color.FromArgb(255, 107, 107);
}

static class Dibujo
{
    [DllImport("user32.dll")] static extern bool ReleaseCapture();
    [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr h, int msg, int wp, int lp);
    [DllImport("uxtheme.dll", CharSet = CharSet.Unicode)] static extern int SetWindowTheme(IntPtr h, string app, string id);

    public static void Arrastrar(Form f)
    {
        if (f.WindowState == FormWindowState.Maximized) return;
        ReleaseCapture();
        SendMessage(f.Handle, 0xA1, 2, 0);
    }
    public static GraphicsPath Redondeado(RectangleF r, float radio)
    {
        GraphicsPath g = new GraphicsPath();
        float d = Math.Max(1f, Math.Min(radio * 2, Math.Min(r.Width, r.Height)));
        g.AddArc(r.X, r.Y, d, d, 180, 90);
        g.AddArc(r.Right - d, r.Y, d, d, 270, 90);
        g.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
        g.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
        g.CloseFigure();
        return g;
    }
    public static void Oscuro(Control c) { try { SetWindowTheme(c.Handle, "DarkMode_Explorer", null); } catch { } }
    public static void Brillo(Graphics g, GraphicsPath forma, RectangleF r, float fase, int alfa, float ancho)
    {
        float x = r.X + fase * r.Width;
        RectangleF rb = new RectangleF(x - ancho / 2, r.Y, ancho, r.Height);
        using (LinearGradientBrush lb = new LinearGradientBrush(rb, Color.Transparent, Color.Transparent, 0f))
        {
            ColorBlend cb = new ColorBlend();
            cb.Colors = new Color[] { Color.FromArgb(0, 255, 255, 255), Color.FromArgb(alfa, 255, 255, 255), Color.FromArgb(0, 255, 255, 255) };
            cb.Positions = new float[] { 0f, 0.5f, 1f };
            lb.InterpolationColors = cb;
            Region antes = g.Clip;
            g.SetClip(forma, CombineMode.Intersect);
            g.FillRectangle(lb, rb);
            g.Clip = antes;
        }
    }
}

/// Boton principal en forma de pildora con degradado. Deshabilitado = "trabajando": mismo diseno con un brillo que lo
/// recorre y el texto SIEMPRE blanco.
class BotonPildora : Control
{
    bool hover;
    float fase = -0.6f;
    readonly System.Windows.Forms.Timer reloj;
    public Color ColorA = Tema.Acento;
    public Color ColorB = Tema.Cian;
    public BotonPildora()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint |
                 ControlStyles.SupportsTransparentBackColor | ControlStyles.ResizeRedraw, true);
        BackColor = Color.Transparent;
        ForeColor = Color.White;
        Cursor = Cursors.Hand;
        Font = new Font("Segoe UI", 14f, FontStyle.Bold);
        reloj = new System.Windows.Forms.Timer();
        reloj.Interval = 40;
        reloj.Tick += delegate { fase += 0.018f; if (fase > 1.6f) fase = -0.6f; Invalidate(); };
    }
    public void Colores(Color a, Color b) { ColorA = a; ColorB = b; Invalidate(); }
    static Color Oscurecer(Color c, float k) { return Color.FromArgb((int)(c.R * k), (int)(c.G * k), (int)(c.B * k)); }
    protected override void OnEnabledChanged(EventArgs e)
    {
        if (Enabled) reloj.Stop(); else { fase = -0.6f; reloj.Start(); }
        Cursor = Enabled ? Cursors.Hand : Cursors.Default;
        Invalidate();
        base.OnEnabledChanged(e);
    }
    protected override void OnTextChanged(EventArgs e) { Invalidate(); base.OnTextChanged(e); }
    protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
    protected override void OnMouseLeave(EventArgs e) { hover = false; Invalidate(); base.OnMouseLeave(e); }
    protected override void OnPaint(PaintEventArgs e)
    {
        Graphics g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;
        RectangleF r = new RectangleF(1.5f, 1.5f, Width - 3f, Height - 3f);
        using (GraphicsPath p = Dibujo.Redondeado(r, r.Height / 2f))
        {
            Color a = Enabled ? ColorA : Oscurecer(ColorA, 0.6f), b = Enabled ? ColorB : Oscurecer(ColorB, 0.6f);
            using (LinearGradientBrush lg = new LinearGradientBrush(r, a, b, LinearGradientMode.Horizontal)) g.FillPath(lg, p);
            using (LinearGradientBrush ls = new LinearGradientBrush(r, Color.Transparent, Color.Transparent, LinearGradientMode.Vertical))
            {
                ColorBlend cb = new ColorBlend();
                cb.Colors = new Color[] { Color.FromArgb(hover && Enabled ? 95 : 62, 255, 255, 255), Color.FromArgb(8, 255, 255, 255), Color.FromArgb(28, 0, 0, 0) };
                cb.Positions = new float[] { 0f, 0.5f, 1f };
                ls.InterpolationColors = cb;
                g.FillPath(ls, p);
            }
            if (!Enabled) Dibujo.Brillo(g, p, r, fase, 110, r.Height * 2.5f);
            using (Pen pen = new Pen(Color.FromArgb(hover && Enabled ? 230 : 150, 190, 225, 255), 1.2f)) g.DrawPath(pen, p);
        }
        StringFormat sf = new StringFormat();
        sf.Alignment = StringAlignment.Center;
        sf.LineAlignment = StringAlignment.Center;
        using (SolidBrush sombra = new SolidBrush(Color.FromArgb(90, 0, 0, 0))) g.DrawString(Text, Font, sombra, new RectangleF(r.X, r.Y + 1.5f, r.Width, r.Height), sf);
        using (SolidBrush b = new SolidBrush(Color.White)) g.DrawString(Text, Font, b, r, sf);
    }
    protected override void Dispose(bool d) { if (d && reloj != null) { reloj.Stop(); reloj.Dispose(); } base.Dispose(d); }
}

/// Barra de progreso: pista redondeada y relleno en degradado azul -> cian con un brillo que la recorre.
class BarraModerna : Control
{
    double valor;
    float brillo = -0.4f;
    readonly System.Windows.Forms.Timer reloj;
    public BarraModerna()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint |
                 ControlStyles.SupportsTransparentBackColor | ControlStyles.ResizeRedraw, true);
        BackColor = Color.Transparent;
        reloj = new System.Windows.Forms.Timer();
        reloj.Interval = 40;
        reloj.Tick += delegate { brillo += 0.012f; if (brillo > 1.4f) brillo = -0.4f; if (valor > 0 && valor < 1) Invalidate(); };
        reloj.Start();
    }
    public double Valor { get { return valor; } set { double v = Math.Max(0, Math.Min(1, value)); if (Math.Abs(v - valor) > 0.0005) { valor = v; Invalidate(); } } }
    protected override void OnPaint(PaintEventArgs e)
    {
        Graphics g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        RectangleF r = new RectangleF(0.5f, 0.5f, Width - 1, Height - 1);
        using (GraphicsPath p = Dibujo.Redondeado(r, r.Height / 2))
        using (SolidBrush b = new SolidBrush(Color.FromArgb(28, 38, 60))) g.FillPath(b, p);
        if (valor <= 0) return;
        float w = (float)Math.Max(r.Height, r.Width * valor);
        RectangleF rf = new RectangleF(r.X, r.Y, w, r.Height);
        using (GraphicsPath p = Dibujo.Redondeado(rf, r.Height / 2))
        {
            using (LinearGradientBrush lg = new LinearGradientBrush(r, Tema.Acento, Tema.Cian, LinearGradientMode.Horizontal)) g.FillPath(lg, p);
            if (valor < 1) Dibujo.Brillo(g, p, rf, brillo, 150, Math.Min(120, rf.Width));
        }
    }
    protected override void Dispose(bool d) { if (d && reloj != null) { reloj.Stop(); reloj.Dispose(); } base.Dispose(d); }
}

/// Boton circular de la barra superior (fijar, minimizar, maximizar, cerrar) con un glifo de Segoe MDL2 Assets.
class BotonCirculo : Control
{
    bool hover;
    public string Glifo = "", GlifoMarcado = null;
    public Color Tono = Color.FromArgb(240, 101, 92);
    public bool Marcable, Marcado;
    public BotonCirculo()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint |
                 ControlStyles.SupportsTransparentBackColor, true);
        BackColor = Color.Transparent;
        Cursor = Cursors.Hand;
    }
    protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
    protected override void OnMouseLeave(EventArgs e) { hover = false; Invalidate(); base.OnMouseLeave(e); }
    protected override void OnClick(EventArgs e) { if (Marcable) { Marcado = !Marcado; Invalidate(); } base.OnClick(e); }
    protected override void OnPaint(PaintEventArgs e)
    {
        Graphics g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;
        Color c = (Marcable && !Marcado) ? Color.FromArgb(125, 140, 160) : Tono;
        float m = Width * 0.09f;
        RectangleF r = new RectangleF(m, m, Width - 2 * m - 1, Height - 2 * m - 1);
        using (SolidBrush b = new SolidBrush(Color.FromArgb(hover || (Marcable && Marcado) ? 80 : 30, c))) g.FillEllipse(b, r);
        using (Pen p = new Pen(Color.FromArgb(235, c), 1.6f)) g.DrawEllipse(p, r);
        string gl = (Marcable && Marcado && GlifoMarcado != null) ? GlifoMarcado : Glifo;
        using (Font f = new Font("Segoe MDL2 Assets", 9f))
        using (SolidBrush b = new SolidBrush(Color.FromArgb(240, 245, 248)))
        {
            StringFormat sf = new StringFormat();
            sf.Alignment = StringAlignment.Center;
            sf.LineAlignment = StringAlignment.Center;
            g.DrawString(gl, f, b, new RectangleF(0, 1, Width, Height), sf);
        }
    }
}

/// Banner animado: la escena (banner.jpg) con el astrolabio del programa dibujado capa a capa que GIRA (runas, engranaje y filigrana en
/// sentidos y velocidades distintos), un halo que respira, motas de luz, un destello que cruza de vez en cuando y el titulo que
/// entra deslizandose. Estado: 0 reposo, 1 trabajando (gira mas rapido, halo fuerte), 2 listo (ondas verdes), 3 error (rojo).
/// La escena y los degradados se dibujan UNA vez en una imagen (cache); cada cuadro solo pinta lo que se mueve.
class Banner : Control
{
    public Image Imagen, Logo, CapaRunas, CapaEngr, CapaFili, CapaNucleo;
    public string Titulo = "", Frase = "", Ficha = "";
    public float Esc = 1f;
    int estado;
    public int Estado
    {
        get { return estado; }
        set { if (value != estado) { estado = value; finT = (value >= 2) ? 0f : -1f; } }
    }
    readonly System.Windows.Forms.Timer reloj;
    DateTime ultimo = DateTime.Now;
    float t, giroA, giroB, giroC, vel = 1f, entra, finT = -1f;
    Bitmap cache; Size cacheTam;
    Bitmap bRunas, bEngr, bFili, bNucleo; int ladoCapas;
    struct Mota { public float x, y, vy, vx, r, fase; }
    readonly Mota[] motas = new Mota[70];

    // la escena de la imagen: el astrolabio vive en estas coordenadas de banner.jpg (1760 x 472)
    const float AstroX = 1385f, AstroY = 236f, AstroLado = 400f, ImgAncho = 1760f;

    public Banner()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint | ControlStyles.ResizeRedraw, true);
        BackColor = Tema.Fondo;
        Random r = new Random(7);
        for (int i = 0; i < motas.Length; i++)
            motas[i] = new Mota { x = (float)r.NextDouble(), y = (float)r.NextDouble(), vy = 0.012f + (float)r.NextDouble() * 0.03f,
                                  vx = ((float)r.NextDouble() - 0.5f) * 0.01f, r = 0.8f + (float)r.NextDouble() * 2.2f, fase = (float)r.NextDouble() * 6.28f };
        reloj = new System.Windows.Forms.Timer();
        reloj.Interval = 33;
        reloj.Tick += delegate { Avanzar(); Invalidate(); };
        reloj.Start();
    }

    void Avanzar()
    {
        DateTime ahora = DateTime.Now;
        float dt = (float)Math.Min(0.1, (ahora - ultimo).TotalSeconds);
        ultimo = ahora;
        t += dt;
        entra = Math.Min(1f, entra + dt / 1.0f);
        float obj = estado == 1 ? 3.4f : estado == 2 ? (finT < 2.5f ? 0.25f : 1f) : estado == 3 ? 0.12f : 1f;
        vel += (obj - vel) * Math.Min(1f, dt * 3f);
        giroA += 2.4f * vel * dt;
        giroB -= 3.6f * vel * dt;
        giroC += 5.6f * vel * dt;
        if (finT >= 0f) finT += dt;
        for (int i = 0; i < motas.Length; i++)
        {
            motas[i].y -= motas[i].vy * dt * (0.6f + 0.4f * vel);
            motas[i].x += motas[i].vx * dt;
            if (motas[i].y < -0.02f) { motas[i].y = 1.02f; }
            if (motas[i].x < 0f) motas[i].x += 1f; else if (motas[i].x > 1f) motas[i].x -= 1f;
        }
    }

    int E(float v) { return (int)Math.Round(v * Esc); }

    Bitmap Escalar(Image img, int lado)
    {
        if (img == null) return null;
        Bitmap b = new Bitmap(lado, lado, System.Drawing.Imaging.PixelFormat.Format32bppPArgb);
        using (Graphics g = Graphics.FromImage(b))
        {
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
            g.DrawImage(img, new Rectangle(0, 0, lado, lado));
        }
        return b;
    }

    void Preparar(Rectangle r)
    {
        float esc = Imagen != null ? Math.Max(r.Width / (float)Imagen.Width, r.Height / (float)Imagen.Height) : 1f;
        int lado = Math.Max(16, (int)Math.Round(AstroLado * esc * (Imagen != null ? Imagen.Width / ImgAncho : 1f)));
        if (cache == null || cacheTam != r.Size)
        {
            if (cache != null) cache.Dispose();
            cacheTam = r.Size;
            cache = new Bitmap(Math.Max(1, r.Width), Math.Max(1, r.Height), System.Drawing.Imaging.PixelFormat.Format32bppPArgb);
            using (Graphics g = Graphics.FromImage(cache))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                g.Clear(Tema.Fondo);
                Rectangle rr = new Rectangle(0, 0, r.Width, r.Height);
                if (Imagen != null)
                {
                    float w = Imagen.Width * esc, h = Imagen.Height * esc;
                    g.DrawImage(Imagen, new RectangleF((r.Width - w) / 2f, (r.Height - h) * 0.45f, w, h));
                }
                // solo se oscurece la zona del titulo (izquierda) y una franja corta abajo para fundirse con la ventana
                using (LinearGradientBrush lg = new LinearGradientBrush(rr, Color.Transparent, Color.Transparent, LinearGradientMode.Horizontal))
                {
                    ColorBlend cb = new ColorBlend();
                    int a0 = Imagen != null ? 246 : 255;
                    cb.Colors = new Color[] { Color.FromArgb(a0, 5, 10, 14), Color.FromArgb(Imagen != null ? 205 : 255, 5, 10, 14),
                                              Color.FromArgb(Imagen != null ? 0 : 255, 5, 10, 14), Color.FromArgb(Imagen != null ? 0 : 255, 5, 10, 14) };
                    cb.Positions = new float[] { 0f, 0.42f, 0.6f, 1f };
                    lg.InterpolationColors = cb;
                    g.FillRectangle(lg, rr);
                }
                using (LinearGradientBrush lg2 = new LinearGradientBrush(rr, Color.Transparent, Color.Transparent, LinearGradientMode.Vertical))
                {
                    ColorBlend cb = new ColorBlend();
                    cb.Colors = new Color[] { Color.FromArgb(0, 8, 12, 20), Color.FromArgb(0, 8, 12, 20), Color.FromArgb(235, 8, 12, 20) };
                    cb.Positions = new float[] { 0f, 0.80f, 1f };
                    lg2.InterpolationColors = cb;
                    g.FillRectangle(lg2, rr);
                }
            }
        }
        if (ladoCapas != lado)
        {
            ladoCapas = lado;
            if (bRunas != null) bRunas.Dispose();
            if (bEngr != null) bEngr.Dispose();
            if (bFili != null) bFili.Dispose();
            if (bNucleo != null) bNucleo.Dispose();
            bRunas = Escalar(CapaRunas, lado); bEngr = Escalar(CapaEngr, lado); bFili = Escalar(CapaFili, lado); bNucleo = Escalar(CapaNucleo, lado);
        }
    }

    void Capa(Graphics g, Bitmap b, float cx, float cy, float giro)
    {
        if (b == null) return;
        GraphicsState s0 = g.Save();
        g.TranslateTransform(cx, cy);
        g.RotateTransform(giro);
        g.DrawImage(b, -b.Width / 2f, -b.Height / 2f, b.Width, b.Height);
        g.Restore(s0);
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        Graphics g = e.Graphics;
        Rectangle r = ClientRectangle;
        if (r.Width < 8 || r.Height < 8) return;
        Preparar(r);
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.InterpolationMode = InterpolationMode.HighQualityBilinear;
        g.PixelOffsetMode = PixelOffsetMode.HighQuality;
        g.DrawImageUnscaled(cache, 0, 0);
        // posicion del astrolabio en el control (misma transformacion que la imagen)
        float esc = Imagen != null ? Math.Max(r.Width / (float)Imagen.Width, r.Height / (float)Imagen.Height) : 1f;
        float k = Imagen != null ? esc * Imagen.Width / ImgAncho : 1f;
        float ox = Imagen != null ? (r.Width - Imagen.Width * esc) / 2f : 0f, oy = Imagen != null ? (r.Height - Imagen.Height * esc) * 0.45f : 0f;
        float ek = Imagen != null ? esc * Imagen.Width / ImgAncho : 1f;
        float cx = ox + AstroX * ek, cy = oy + AstroY * ek;
        Color col = estado == 3 ? Color.FromArgb(255, 90, 90) : Color.FromArgb(58, 230, 140);
        // el halo que respira
        float pulso = 0.5f + 0.5f * (float)Math.Sin(t * 1.6);
        float radio = AstroLado * 0.95f * ek;
        int alfaHalo = (int)((estado == 1 ? 80 : 46) + 26 * pulso);
        using (GraphicsPath gp = new GraphicsPath())
        {
            gp.AddEllipse(cx - radio, cy - radio, radio * 2, radio * 2);
            using (PathGradientBrush pg = new PathGradientBrush(gp))
            {
                pg.CenterColor = Color.FromArgb(alfaHalo, col);
                pg.SurroundColors = new Color[] { Color.FromArgb(0, col) };
                g.FillPath(pg, gp);
            }
        }
        // las capas giratorias y el nucleo fijo
        Capa(g, bRunas, cx, cy, giroA);
        Capa(g, bEngr, cx, cy, giroB);
        Capa(g, bFili, cx, cy, giroC);
        if (bNucleo != null) g.DrawImageUnscaled(bNucleo, (int)(cx - bNucleo.Width / 2f), (int)(cy - bNucleo.Height / 2f));
        // ondas al terminar
        if (finT >= 0f && finT < 2.4f)
            for (int i = 0; i < 3; i++)
            {
                float u = (finT - i * 0.22f) / 1.6f;
                if (u <= 0f || u >= 1f) continue;
                float rr = (60f + 700f * (1f - (float)Math.Pow(1f - u, 2.4))) * ek;
                using (Pen p = new Pen(Color.FromArgb((int)(190 * (1f - u) * (1f - u)), estado == 3 ? Color.FromArgb(255, 110, 110) : Color.FromArgb(120, 255, 190)), 2.4f * ek + 6f * u))
                    g.DrawEllipse(p, cx - rr, cy - rr * 0.92f, rr * 2, rr * 1.84f);
            }
        // motas de luz (a la derecha, donde vive la escena)
        float x0 = r.Width * 0.40f, ancho = r.Width - x0;
        using (SolidBrush sb = new SolidBrush(Color.White))
            for (int i = 0; i < motas.Length; i++)
            {
                float tw = 0.5f + 0.5f * (float)Math.Sin(t * 2.2f + motas[i].fase);
                int a = (int)(40 + 150 * tw);
                float x = x0 + motas[i].x * ancho, y = motas[i].y * r.Height, rad = motas[i].r * Math.Max(0.8f, ek * 0.9f);
                sb.Color = i % 3 == 0 ? Color.FromArgb(a, 150, 255, 200) : i % 3 == 1 ? Color.FromArgb(a, 255, 255, 255) : Color.FromArgb(a, 90, 220, 255);
                g.FillEllipse(sb, x - rad, y - rad, rad * 2, rad * 2);
            }
        // un destello diagonal que cruza cada ~7 s
        float fase = (t % 7f) / 7f * 1.6f - 0.3f;
        if (fase > -0.2f && fase < 1.2f)
        {
            float bx = r.Width * fase;
            PointF[] banda = { new PointF(bx, 0), new PointF(bx + r.Width * 0.10f, 0), new PointF(bx - r.Width * 0.06f, r.Height), new PointF(bx - r.Width * 0.16f, r.Height) };
            using (LinearGradientBrush lb = new LinearGradientBrush(new RectangleF(bx - r.Width * 0.16f, 0, r.Width * 0.26f, r.Height), Color.Transparent, Color.Transparent, 0f))
            {
                ColorBlend cb = new ColorBlend();
                cb.Colors = new Color[] { Color.FromArgb(0, 255, 255, 255), Color.FromArgb(34, 190, 255, 225), Color.FromArgb(0, 255, 255, 255) };
                cb.Positions = new float[] { 0f, 0.5f, 1f };
                lb.InterpolationColors = cb;
                g.FillPolygon(lb, banda);
            }
        }
        // logo + TRÁILER AUTOMÁTICO + titulo (entran deslizandose)
        g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAlias;
        float u0 = 1f - (float)Math.Pow(1f - entra, 3);
        int x1 = E(38), y1 = E(32);
        float desl = (1f - u0) * E(22);
        int al = (int)(255 * u0);
        if (Logo != null) { g.DrawImage(Logo, new Rectangle(x1 - (int)desl, y1, E(40), E(40))); x1 += E(52); }
        using (Font f = new Font("Segoe UI", 15f, FontStyle.Bold))
        using (SolidBrush b1 = new SolidBrush(Color.FromArgb(al, 255, 255, 255)))
        using (SolidBrush b2 = new SolidBrush(Color.FromArgb(al, 58, 230, 140)))
        {
            SizeF s1 = g.MeasureString("TRÁILER", f, 1000, StringFormat.GenericTypographic);
            g.DrawString("TRÁILER", f, b1, x1 - desl, y1 + E(6), StringFormat.GenericTypographic);
            g.DrawString("AUTOMÁTICO", f, b2, x1 - desl + s1.Width + E(9), y1 + E(6), StringFormat.GenericTypographic);
        }
        float u1 = Math.Max(0f, Math.Min(1f, (entra - 0.15f) / 0.85f)); u1 = 1f - (float)Math.Pow(1f - u1, 3);
        using (Font f = new Font("Segoe UI", 26f, FontStyle.Bold))
        using (SolidBrush b = new SolidBrush(Color.FromArgb((int)(255 * u1), 255, 255, 255)))
            g.DrawString(Titulo, f, b, E(33) - (1f - u1) * E(26), E(88), StringFormat.GenericTypographic);
        float u2 = Math.Max(0f, Math.Min(1f, (entra - 0.3f) / 0.7f)); u2 = 1f - (float)Math.Pow(1f - u2, 3);
        using (Font f = new Font("Segoe UI", 12f))
        using (SolidBrush b = new SolidBrush(Color.FromArgb((int)(255 * u2), 205, 218, 238)))
            g.DrawString(Frase, f, b, E(38) - (1f - u2) * E(26), E(140), StringFormat.GenericTypographic);
        float u3 = Math.Max(0f, Math.Min(1f, (entra - 0.45f) / 0.55f)); u3 = 1f - (float)Math.Pow(1f - u3, 3);
        using (Font f = new Font("Segoe UI", 9.5f, FontStyle.Bold))
        {
            SizeF s = g.MeasureString(Ficha, f, 2000, StringFormat.GenericTypographic);
            RectangleF rc = new RectangleF(E(38) - (1f - u3) * E(26), E(176), s.Width + E(24), s.Height + E(12));
            using (SolidBrush b = new SolidBrush(Color.FromArgb((int)(225 * u3), 10, 36, 30))) g.FillRectangle(b, rc);
            using (Pen p = new Pen(Color.FromArgb((int)(120 * u3), 58, 230, 140), 1f)) g.DrawRectangle(p, rc.X, rc.Y, rc.Width, rc.Height);
            using (SolidBrush b = new SolidBrush(Color.FromArgb((int)(255 * u3), 120, 255, 200)))
                g.DrawString(Ficha, f, b, rc.X + E(12), rc.Y + E(6), StringFormat.GenericTypographic);
        }
    }

    protected override void Dispose(bool d)
    {
        if (d)
        {
            if (reloj != null) { reloj.Stop(); reloj.Dispose(); }
            if (cache != null) cache.Dispose();
            if (bRunas != null) bRunas.Dispose();
            if (bEngr != null) bEngr.Dispose();
            if (bFili != null) bFili.Dispose();
            if (bNucleo != null) bNucleo.Dispose();
        }
        base.Dispose(d);
    }
}

/// La lista de PASOS: un circulo por paso (· pendiente, arco que gira = en curso, ✓ hecho con un saltito, ! aviso, ✗ error, – omitido)
/// y el nombre, a color. El paso en curso late y su circulo gira (reloj de 40 ms solo mientras hay uno en curso).
class ListaPasos : Control
{
    public List<Paso> Pasos;
    public float Esc = 1f;
    readonly System.Windows.Forms.Timer reloj;
    float fase;
    readonly Dictionary<Paso, float> popup = new Dictionary<Paso, float>();
    readonly Dictionary<Paso, EstadoPaso> vistos = new Dictionary<Paso, EstadoPaso>();
    public ListaPasos()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint | ControlStyles.ResizeRedraw, true);
        BackColor = Tema.Fondo;
        reloj = new System.Windows.Forms.Timer();
        reloj.Interval = 33;
        reloj.Tick += delegate
        {
            fase += 0.045f;
            bool hay = false;
            if (Pasos != null)
                foreach (Paso p in Pasos)
                {
                    if (p.Estado == EstadoPaso.EnCurso) hay = true;
                    EstadoPaso antes;
                    if (!vistos.TryGetValue(p, out antes)) antes = EstadoPaso.Pendiente;
                    if (antes != p.Estado) { vistos[p] = p.Estado; if (p.Estado == EstadoPaso.Hecho) popup[p] = 0f; }
                }
            List<Paso> fin = new List<Paso>();
            foreach (Paso p in new List<Paso>(popup.Keys)) { popup[p] += 0.06f; hay = true; if (popup[p] >= 1f) fin.Add(p); }
            foreach (Paso p in fin) popup.Remove(p);
            if (hay) Invalidate();
        };
        reloj.Start();
    }
    protected override void OnPaint(PaintEventArgs e)
    {
        Graphics g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
        using (Font fp = new Font("Segoe UI", 9f, FontStyle.Bold))
            TextRenderer.DrawText(g, "PASOS", fp, new Point((int)(4 * Esc), 0), Tema.Suave, TextFormatFlags.NoPadding);
        if (Pasos == null) return;
        using (Font f = new Font("Segoe UI", 10.5f))
        using (Font fb = new Font("Segoe UI", 10.5f, FontStyle.Bold))
        {
            int y = (int)(26 * Esc), alto = (int)(32 * Esc);
            foreach (Paso p in Pasos)
            {
                Color c;
                switch (p.Estado)
                {
                    case EstadoPaso.EnCurso: c = Tema.EnCurso; break;
                    case EstadoPaso.Hecho: c = Tema.Ok; break;
                    case EstadoPaso.Aviso: c = Tema.Aviso; break;
                    case EstadoPaso.Error: c = Tema.Error; break;
                    default: c = Tema.Pendiente; break;
                }
                float cx = 13 * Esc, cy = y + alto / 2f, rad = 8.5f * Esc;
                float pop = 0f;
                if (popup.ContainsKey(p)) pop = (float)Math.Sin(popup[p] * Math.PI) * 0.35f;
                rad *= 1f + pop;
                if (p.Estado == EstadoPaso.EnCurso)
                {
                    float late = 0.5f + 0.5f * (float)Math.Sin(fase * 2.2f);
                    using (SolidBrush b = new SolidBrush(Color.FromArgb((int)(30 + 40 * late), c))) g.FillEllipse(b, cx - rad * 1.7f, cy - rad * 1.7f, rad * 3.4f, rad * 3.4f);
                    using (Pen pp = new Pen(Color.FromArgb(70, c), 2f * Esc)) g.DrawEllipse(pp, cx - rad, cy - rad, rad * 2, rad * 2);
                    using (Pen pa = new Pen(c, 2.6f * Esc)) { pa.StartCap = LineCap.Round; pa.EndCap = LineCap.Round; g.DrawArc(pa, cx - rad, cy - rad, rad * 2, rad * 2, fase * 360f / 1.2f, 110f); }
                }
                else if (p.Estado == EstadoPaso.Hecho)
                {
                    using (SolidBrush b = new SolidBrush(c)) g.FillEllipse(b, cx - rad, cy - rad, rad * 2, rad * 2);
                    using (Pen pc = new Pen(Color.FromArgb(6, 22, 14), 2.2f * Esc))
                    {
                        pc.StartCap = LineCap.Round; pc.EndCap = LineCap.Round; pc.LineJoin = LineJoin.Round;
                        g.DrawLines(pc, new PointF[] { new PointF(cx - rad * 0.45f, cy + rad * 0.02f), new PointF(cx - rad * 0.1f, cy + rad * 0.38f), new PointF(cx + rad * 0.5f, cy - rad * 0.34f) });
                    }
                }
                else if (p.Estado == EstadoPaso.Aviso || p.Estado == EstadoPaso.Error)
                {
                    using (SolidBrush b = new SolidBrush(c)) g.FillEllipse(b, cx - rad, cy - rad, rad * 2, rad * 2);
                    TextRenderer.DrawText(g, p.Estado == EstadoPaso.Aviso ? "!" : "✗", fb, new Rectangle((int)(cx - rad), (int)(cy - rad), (int)(rad * 2), (int)(rad * 2)),
                                          Color.FromArgb(10, 14, 20), TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.NoPadding | TextFormatFlags.NoPrefix);
                }
                else
                {
                    using (Pen pp = new Pen(Color.FromArgb(120, c), 1.6f * Esc)) g.DrawEllipse(pp, cx - rad, cy - rad, rad * 2, rad * 2);
                    if (p.Estado == EstadoPaso.Omitido) using (Pen pp = new Pen(c, 1.6f * Esc)) g.DrawLine(pp, cx - rad * 0.4f, cy, cx + rad * 0.4f, cy);
                }
                string t = p.Titulo;
                if (p.Estado == EstadoPaso.EnCurso && p.Progreso >= 0 && p.Progreso < 100) t += "   " + p.Progreso + " %";
                TextRenderer.DrawText(g, t, p.Estado == EstadoPaso.EnCurso ? fb : f, new Rectangle((int)(34 * Esc), y, Width - (int)(34 * Esc), alto), p.Estado == EstadoPaso.EnCurso ? Color.White : c,
                                      TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis | TextFormatFlags.NoPrefix);
                y += alto;
            }
        }
    }
    protected override void Dispose(bool d) { if (d && reloj != null) { reloj.Stop(); reloj.Dispose(); } base.Dispose(d); }
}
