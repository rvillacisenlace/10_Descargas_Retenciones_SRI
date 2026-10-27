import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from archivist_app.config import APP_NAME


def get_logger(name: str = "archivist") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    logger.addHandler(handler)
    return logger


def activar_log_en_archivo(carpeta: Path | None = None) -> Path | None:
    """Además de la consola, deja el log en un archivo rotativo (1 MB x 5) para poder atender un
    problema cuando la ventana ya se cerró. Solo lo llama main: las pruebas no escriben logs reales.
    Los logs no llevan credenciales ni claves de acceso. Si no se puede crear, no detiene nada."""
    raiz = logging.getLogger()
    for h in raiz.handlers:
        if isinstance(h, RotatingFileHandler):
            return Path(h.baseFilename)  # ya activo
    carpeta = carpeta or Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP_NAME / "logs"
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(carpeta / "archivist.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    except OSError:
        return None
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    raiz.addHandler(handler)  # los loggers de la app propagan a la raíz
    return Path(handler.baseFilename)