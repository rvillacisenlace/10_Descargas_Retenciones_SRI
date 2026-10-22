import ctypes
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from archivist_app.exceptions import ConfigError

APP_NAME = "Archivist"

AUTH_DIR = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP_NAME / ".auth"

DEFAULT_TIMEOUT_MS = 30_000
USER_WAIT_TIMEOUT_S = 600  # espera máxima a que el usuario elija el filtro y pulse Consultar


def _documents_dir() -> Path:
    """Carpeta Documentos real del usuario (respeta la redirección a OneDrive)."""
    buf = ctypes.create_unicode_buffer(260)
    # 5 = CSIDL_PERSONAL (Documentos)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
        return Path(buf.value)
    return Path.home() / "Documents"


# Pruebas: .env en la raíz del proyecto, junto a .env.example. Instalado: en AppData.
_PROJECT_ENV = Path(__file__).resolve().parent.parent / ".env"
_APPDATA_ENV = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME / ".env"
ENV_FILE = _PROJECT_ENV if _PROJECT_ENV.is_file() else _APPDATA_ENV
OUTPUT_DIR = _documents_dir() / APP_NAME


@dataclass(frozen=True)
class Settings:
    login_url: str
    recibidos_url: str
    portal_ruc: str  # RUC: es el campo #usuario del login (no hay otro usuario)
    portal_password: str
    output_dir: Path


def _check_url(name: str, value: str) -> str:
    """Una URL mal pegada se detecta aquí, no cuando el portal responde algo raro."""
    if not value.startswith("https://"):
        raise ConfigError(f"{name} debe empezar con https:// y es: {value[:60]!r}")
    if "\ufffd" in value or any(c.isspace() for c in value):
        raise ConfigError(f"{name} tiene espacios o caracteres dañados; vuelva a pegarla")
    return value


def load_settings() -> Settings:
    if not ENV_FILE.is_file():
        raise ConfigError(f"No existe el archivo de configuración: {ENV_FILE}")
    load_dotenv(ENV_FILE, encoding="utf-8-sig", interpolate=False)

    required = ("PORTAL_LOGIN_URL", "PORTAL_RECIBIDOS_URL", "PORTAL_RUC", "PORTAL_PASSWORD")
    missing = [n for n in required if not os.getenv(n)]
    if missing:
        raise ConfigError(f"Faltan variables en {ENV_FILE}: {', '.join(missing)}")

    login_url = _check_url("PORTAL_LOGIN_URL", os.environ["PORTAL_LOGIN_URL"])
    recibidos_url = _check_url("PORTAL_RECIBIDOS_URL", os.environ["PORTAL_RECIBIDOS_URL"])

    for d in (OUTPUT_DIR, AUTH_DIR):
        d.mkdir(parents=True, exist_ok=True)

    return Settings(
        login_url=login_url,
        recibidos_url=recibidos_url,
        portal_ruc=os.environ["PORTAL_RUC"],
        portal_password=os.environ["PORTAL_PASSWORD"],
        output_dir=OUTPUT_DIR,
    )
