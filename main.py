"""Punto de entrada.

Contrato:
- Ejecuta el workflow.
- Cualquier error (controlado o no) termina en notificación de Windows (sys.excepthook).
- Código de salida: 0 si todo salió bien, 1 si hubo error.
"""

import sys

from archivist_app.exceptions import SriError
from archivist_app.logger import get_logger
from archivist_app.services.notifier import notificar
from archivist_app.workflow import ejecutar

log = get_logger("archivist")


def _excepthook(tipo, valor, traza) -> None:
    """Errores NO controlados: traza en consola y aviso genérico (sin datos del error)."""
    if issubclass(tipo, KeyboardInterrupt):
        sys.__excepthook__(tipo, valor, traza)
        return
    log.critical("Error inesperado", exc_info=(tipo, valor, traza))
    notificar("Archivist: error inesperado", f"{tipo.__name__}. Revise la consola.", "long")


def main() -> int:
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
    sys.exit(main())