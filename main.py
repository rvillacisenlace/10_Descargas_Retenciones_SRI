"""Punto de entrada.

Contrato:
- Ejecuta el workflow.
- Cualquier error (controlado o no) termina en notificación de Windows (sys.excepthook).
- Código de salida: 0 si todo salió bien, 1 si hubo error.
- Opciones: --version y --verificar (comprueba el equipo sin tocar el portal), y --salida RUTA para
  escribir su resultado en un archivo. El ejecutable se genera sin consola (--noconsole): sin
  --salida, su resultado se muestra en un cuadro de mensaje de Windows.
- No se escriben registros en disco (política de TI, igual que Docket). Para diagnosticar, con
  autorización de TI, ARCHIVIST_LOG_ARCHIVO=1 activa un registro rotativo en AppData.
"""

import ctypes
import os
import sys
from pathlib import Path

from archivist_app import __version__
from archivist_app.config import APP_NAME
from archivist_app.exceptions import SriError
from archivist_app.logger import activar_log_en_archivo, get_logger
from archivist_app.services.notifier import notificar
from archivist_app.verificar import ejecutar_verificacion
from archivist_app.workflow import ejecutar

log = get_logger("archivist")


def _mensaje_windows(texto: str) -> None:
    """Sin consola no hay dónde imprimir: se muestra un cuadro de mensaje (MB_ICONINFORMATION)."""
    ctypes.windll.user32.MessageBoxW(None, texto, APP_NAME, 0x40)


def _emitir(texto: str, ruta: str | None) -> None:
    """Resultado de --version y --verificar: a un archivo si se pidió (--salida), a la consola si
    existe, y si no (ejecutable sin consola) a un cuadro de mensaje."""
    if ruta:
        Path(ruta).write_text(texto + "\n", encoding="utf-8")
    elif sys.stdout is not None:
        print(texto)
    else:
        _mensaje_windows(texto)


def _valor(args: list[str], opcion: str) -> str | None:
    if opcion in args:
        i = args.index(opcion)
        return args[i + 1] if i + 1 < len(args) else None
    return None


def _activar_log() -> Path | None:
    """El registro en archivo es opcional: por política de TI no se escribe a disco por defecto."""
    return activar_log_en_archivo() if os.getenv("ARCHIVIST_LOG_ARCHIVO") else None


def _excepthook(tipo, valor, traza) -> None:
    """Errores NO controlados: sin consola, el texto del error viaja en el aviso para soporte."""
    if issubclass(tipo, KeyboardInterrupt):
        sys.__excepthook__(tipo, valor, traza)
        return
    log.critical("Error inesperado", exc_info=(tipo, valor, traza))
    notificar("Archivist: error inesperado", f"{tipo.__name__}: {valor}", "long")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    ruta = _valor(args, "--salida")
    if "--version" in args:
        _emitir(f"{APP_NAME} {__version__}", ruta)
        return 0
    if "--verificar" in args:
        return ejecutar_verificacion(lambda texto: _emitir(texto, ruta))
    try:
        resultado = ejecutar()
    except SriError as e:
        # Los mensajes de los errores controlados no llevan claves ni datos del contribuyente.
        log.error("Error: %s", e)
        notificar("Archivist: no se pudo completar", str(e), "long")
        return 1
    log.info("Terminado: %s", resultado)
    return 0


if __name__ == "__main__":
    sys.excepthook = _excepthook
    ruta_log = _activar_log()
    log.info("%s %s | registro en archivo: %s", APP_NAME, __version__, ruta_log or "desactivado")
    sys.exit(main())