"""Notificaciones de Windows (winotify). Separar dos avisos consecutivos en el tiempo."""

import time

from archivist_app.config import APP_NAME, ICONO_AVISOS
from archivist_app.logger import get_logger

log = get_logger(__name__)

# HIPÓTESIS: Windows descarta o apila avisos muy seguidos, y el segundo no se ve. 3 s es un
# valor prudente, no medido.
SEPARACION_S = 3.0

_ultimo: float | None = None


def _mostrar(titulo: str, mensaje: str, duracion: str) -> None:
    from winotify import Notification  # import diferido: solo funciona en Windows

    # winotify pide una ruta absoluta a la imagen; sin el archivo, el aviso sale sin icono.
    icono = str(ICONO_AVISOS) if ICONO_AVISOS.is_file() else ""
    Notification(app_id=APP_NAME, title=titulo, msg=mensaje, icon=icono, duration=duracion).show()


def notificar(titulo: str, mensaje: str, duracion: str = "short") -> None:
    """Muestra un aviso. Un aviso que falla NO debe tumbar la descarga: solo se registra."""
    global _ultimo
    if _ultimo is not None:
        espera = SEPARACION_S - (time.monotonic() - _ultimo)
        if espera > 0:
            time.sleep(espera)
    try:
        _mostrar(titulo, mensaje, duracion)
    except Exception as e:
        log.warning("No se pudo mostrar la notificación (%s)", type(e).__name__)
    _ultimo = time.monotonic()