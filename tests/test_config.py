import pytest

from archivist_app import config
from archivist_app.exceptions import ConfigError

VARS = ("PORTAL_USER", "PORTAL_PASSWORD")


@pytest.fixture(autouse=True)
def entorno_aislado(monkeypatch, tmp_path):
    # load_dotenv escribe en os.environ: se registra el estado original para restaurarlo.
    for n in VARS:
        monkeypatch.setenv(n, "x")
        monkeypatch.delenv(n)
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "salida")
    monkeypatch.setattr(config, "AUTH_DIR", tmp_path / "auth")
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")


def _env(texto: str) -> None:
    config.ENV_FILE.write_text(texto, encoding="utf-8-sig")


def test_sin_archivo():
    with pytest.raises(ConfigError, match="No existe"):
        config.load_settings()


def test_faltan_variables():
    _env("PORTAL_USER='1700000000001'\n")
    with pytest.raises(ConfigError, match="PORTAL_PASSWORD"):
        config.load_settings()


def test_carga_con_caracteres_especiales():
    _env("PORTAL_USER='1700000000001'\nPORTAL_PASSWORD='a#b$c\"d'\n")
    s = config.load_settings()
    assert s.portal_user == "1700000000001"
    assert s.portal_password == 'a#b$c"d'
    assert s.output_dir == config.OUTPUT_DIR
    assert config.OUTPUT_DIR.is_dir() and config.AUTH_DIR.is_dir()
