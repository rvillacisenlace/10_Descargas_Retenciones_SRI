import pytest

from archivist_app import config
from archivist_app.exceptions import ConfigError

VARS = ("PORTAL_LOGIN_URL", "PORTAL_RECIBIDOS_URL", "PORTAL_RUC", "PORTAL_PASSWORD")

LOGIN = "https://srienlinea.sri.gob.ec/sri-en-linea/contribuyente/perfil"
RECIBIDOS = (
    "https://srienlinea.sri.gob.ec/comprobantes-electronicos-internet"
    "/pages/consultas/recibidos/comprobantesRecibidos.jsf"
)


@pytest.fixture(autouse=True)
def entorno_aislado(monkeypatch, tmp_path):
    # load_dotenv escribe en os.environ: se registra el estado original para restaurarlo.
    for n in VARS:
        monkeypatch.setenv(n, "x")
        monkeypatch.delenv(n)
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "salida")
    monkeypatch.setattr(config, "AUTH_DIR", tmp_path / "auth")
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")


def _env(**cambios) -> None:
    """Escribe un .env válido; cada cambio lo reemplaza, y None quita la variable."""
    valores = {
        "PORTAL_LOGIN_URL": LOGIN,
        "PORTAL_RECIBIDOS_URL": RECIBIDOS,
        "PORTAL_RUC": "1700000000001",
        "PORTAL_PASSWORD": "clave",
    }
    valores.update(cambios)
    texto = "".join(f"{k}='{v}'\n" for k, v in valores.items() if v is not None)
    config.ENV_FILE.write_text(texto, encoding="utf-8-sig")


def test_sin_archivo():
    with pytest.raises(ConfigError, match="No existe"):
        config.load_settings()


def test_faltan_variables():
    _env(PORTAL_RECIBIDOS_URL=None, PORTAL_PASSWORD=None)
    with pytest.raises(ConfigError, match="PORTAL_RECIBIDOS_URL, PORTAL_PASSWORD"):
        config.load_settings()


def test_carga_con_caracteres_especiales():
    larga = RECIBIDOS + "?&contextoMPT=https://x/y&linkMPT=%2Fa%2Fb%3F#z"
    _env(PORTAL_RECIBIDOS_URL=larga, PORTAL_PASSWORD='a#b$c"d')
    s = config.load_settings()
    assert s.login_url == LOGIN
    assert s.recibidos_url == larga
    assert s.portal_ruc == "1700000000001"
    assert s.portal_password == 'a#b$c"d'
    assert s.output_dir == config.OUTPUT_DIR
    assert config.OUTPUT_DIR.is_dir() and config.AUTH_DIR.is_dir()


def test_url_sin_https():
    _env(PORTAL_LOGIN_URL="http://srienlinea.sri.gob.ec/perfil")
    with pytest.raises(ConfigError, match="PORTAL_LOGIN_URL"):
        config.load_settings()
    assert not config.OUTPUT_DIR.exists()  # config inválida: no se crean carpetas


def test_url_con_caracter_danado():
    _env(PORTAL_RECIBIDOS_URL="https://srienlinea.sri.gob.ec/Facturaci\ufffdn")
    with pytest.raises(ConfigError, match="PORTAL_RECIBIDOS_URL"):
        config.load_settings()


def test_url_con_espacio_al_final():
    _env(PORTAL_RECIBIDOS_URL=RECIBIDOS + " ")
    with pytest.raises(ConfigError, match="PORTAL_RECIBIDOS_URL"):
        config.load_settings()