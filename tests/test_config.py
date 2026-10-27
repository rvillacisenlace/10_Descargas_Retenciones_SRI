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


# --- el .env según se ejecute desde el proyecto o empaquetado ------------------------------------

def test_empaquetado_usa_siempre_el_env_de_appdata(tmp_path):
    from archivist_app.config import _resolver_env
    proyecto, appdata = tmp_path / "proyecto.env", tmp_path / "appdata.env"
    proyecto.write_text("PORTAL_RUC=x")  # aunque exista uno dentro del paquete, no se usa
    assert _resolver_env(True, proyecto, appdata) == appdata


def test_en_desarrollo_usa_el_env_del_proyecto_si_existe(tmp_path):
    from archivist_app.config import _resolver_env
    proyecto, appdata = tmp_path / "proyecto.env", tmp_path / "appdata.env"
    assert _resolver_env(False, proyecto, appdata) == appdata  # no existe: cae a AppData
    proyecto.write_text("PORTAL_RUC=x")
    assert _resolver_env(False, proyecto, appdata) == proyecto


# --- recursos graficos (iconos) ---------------------------------------------------------------------

def test_los_recursos_empaquetados_salen_de_meipass(tmp_path):
    from archivist_app.config import _resolver_assets
    assert _resolver_assets(str(tmp_path / "_internal"), tmp_path / "proyecto") == tmp_path / "_internal" / "assets"


def test_en_desarrollo_los_recursos_salen_de_la_carpeta_assets_del_proyecto(tmp_path):
    from archivist_app.config import _resolver_assets
    assert _resolver_assets(None, tmp_path / "proyecto") == tmp_path / "proyecto" / "assets"


def test_el_icono_de_los_avisos_es_el_png_de_256():
    from archivist_app.config import ICONO_AVISOS
    assert ICONO_AVISOS.name == "archivist_256.png" and ICONO_AVISOS.parent.name == "assets"