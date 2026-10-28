# -*- mode: python ; coding: utf-8 -*-
# Archivist: paquete en CARPETA (onedir), no en un solo .exe.
#  - onedir arranca más rápido y levanta menos falsos positivos de antivirus que onefile.
#  - console=True: la ventana de consola es la salida de logs y errores (ver main._pausar_si_hay_error).
#  - NO se incluye ningún .env ni sesión: la configuración vive en %APPDATA%\Archivist\.env.
#  - No se empaqueta navegador: se usa el Edge instalado en Windows.
#  - upx desactivado: el empaquetado con UPX dispara más alertas de antivirus.
# Construir con build.ps1 (que antes corre las pruebas); no a mano.
import os

from PyInstaller.utils.hooks import collect_all

ICONO_EXE = os.path.join("assets", "archivist.ico")  # icono del .exe (multi-tamaño: 16, 32, 48, 256)
ICONO_AVISOS = os.path.join("assets", "archivist_256.png")  # imagen de los avisos (se usa en ejecución)

# El driver de Playwright (node + paquete JS) viaja como datos dentro de la librería.
datas, binaries, hiddenimports = collect_all("playwright")
datas = datas + [(ICONO_AVISOS, "assets")]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["winotify"],  # winotify se importa dentro de una función
    excludes=["pytest", "tkinter", "_pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Archivist",
    console=True,
    icon=ICONO_EXE,
    upx=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Archivist",
)
