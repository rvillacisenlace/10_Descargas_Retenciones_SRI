"""Punto de entrada.

Contrato:
- Ejecuta el workflow.
- Cualquier error (controlado o no) termina en notificación de Windows (sys.excepthook).
- Código de salida: 0 si todo salió bien, 1 si hubo error.
- Opciones: --version (imprime la versión) y --verificar (comprueba el equipo, sin tocar el portal).
- Empaquetado: si hubo error, la ventana espera una tecla antes de cerrarse, para poder leerlo
  (solo con una consola interactiva; ARCHIVIST_SIN_PAUSA=1 lo desactiva, p. ej. en build.ps1).
"""

import os
import sys

from archivist_app import __version__
from archivist_app.config import APP_NAME
from archivist_app.exceptions import SriError
from archivist_app.logger import activar_log_en_archivo, get_logger
from archivist_app.services.notifier import notificar
from archivist_app.verificar import ejecutar_verificacion
from archivist_app.workflow import ejecutar

log = get_logger("archivist")


def _pausar_si_hay_error(codigo: int) -> None:
    """Solo en el ejecutable (su ventana de consola se cierra sola) y solo si hubo error: sin esta
    pausa, en otra máquina el mensaje desaparece antes de poder leerlo."""
    if not getattr(sys, "frozen", False) or codigo == 0:
        return
    if os.getenv("ARCHIVIST_SIN_PAUSA"):
        return
    if not (sys.stdin and sys.stdin.isatty()):
        return  # sin consola interactiva (tarea programada, otro programa): no hay a quién esperar
    try:
        input("\nPresione Enter para cerrar esta ventana...")
    except EOFError:
        pass


def _excepthook(tipo, valor, traza) -> None:
    """Errores NO controlados: traza en consola y aviso genérico (sin datos del error)."""
    if issubclass(tipo, KeyboardInterrupt):
        sys.__excepthook__(tipo, valor, traza)
        return
    log.critical("Error inesperado", exc_info=(tipo, valor, traza))
    notificar("Archivist: error inesperado", f"{tipo.__name__}. Revise la consola.", "long")
    _pausar_si_hay_error(1)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if "--version" in args:
        print(f"{APP_NAME} {__version__}")
        return 0
    if "--verificar" in args:
        return ejecutar_verificacion()
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
    ruta_log = activar_log_en_archivo()
    log.info("%s %s | log: %s", APP_NAME, __version__, ruta_log or "(sin archivo de log)")
    codigo = main()
    _pausar_si_hay_error(codigo)
    sys.exit(codigo)