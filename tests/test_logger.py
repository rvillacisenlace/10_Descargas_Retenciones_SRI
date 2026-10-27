import logging
from logging.handlers import RotatingFileHandler

import pytest

from archivist_app.logger import activar_log_en_archivo, get_logger


@pytest.fixture
def limpio():
    """Quita de la raíz cualquier handler de archivo que deje la prueba (no contaminar las demás)."""
    yield
    raiz = logging.getLogger()
    for h in list(raiz.handlers):
        if isinstance(h, RotatingFileHandler):
            raiz.removeHandler(h)
            h.close()


def test_el_log_de_la_app_llega_al_archivo(tmp_path, limpio):
    ruta = activar_log_en_archivo(tmp_path / "logs")
    get_logger("archivist_app.prueba").info("consulta resultado=ok rechazos_previos=0")
    for h in logging.getLogger().handlers:
        h.flush()
    texto = ruta.read_text(encoding="utf-8")
    assert ruta == tmp_path / "logs" / "archivist.log"
    assert "INFO | archivist_app.prueba | consulta resultado=ok rechazos_previos=0" in texto


def test_activarlo_dos_veces_no_duplica_las_lineas(tmp_path, limpio):
    activar_log_en_archivo(tmp_path / "logs")
    segunda = activar_log_en_archivo(tmp_path / "otra")
    assert segunda == tmp_path / "logs" / "archivist.log"  # devuelve el ya activo
    get_logger("archivist_app.prueba2").info("una sola vez")
    for h in logging.getLogger().handlers:
        h.flush()
    assert (tmp_path / "logs" / "archivist.log").read_text(encoding="utf-8").count("una sola vez") == 1
    assert not (tmp_path / "otra").exists()


def test_si_no_se_puede_crear_la_carpeta_no_detiene_nada(tmp_path, limpio):
    (tmp_path / "es_un_archivo").write_text("x")
    assert activar_log_en_archivo(tmp_path / "es_un_archivo" / "logs") is None


def test_los_errores_con_traza_quedan_en_el_archivo(tmp_path, limpio):
    ruta = activar_log_en_archivo(tmp_path / "logs")
    try:
        raise KeyError("x")
    except KeyError:
        get_logger("archivist").critical("Error inesperado", exc_info=True)
    for h in logging.getLogger().handlers:
        h.flush()
    assert "KeyError" in ruta.read_text(encoding="utf-8")