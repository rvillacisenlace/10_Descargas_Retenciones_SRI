import sys

import pytest

import main
from archivist_app.exceptions import IncompleteBatchError, PortalError
from archivist_app.workflow import RunResult


def espiar(monkeypatch):
    avisos = []
    monkeypatch.setattr(main, "notificar", lambda t, m, d="short": avisos.append((t, m)))
    return avisos


def test_exito_devuelve_0_y_no_avisa(monkeypatch):
    avisos = espiar(monkeypatch)
    monkeypatch.setattr(main, "ejecutar", lambda: RunResult(1, 2, 0, 1, 1, "Factura", "2026-10-23", "2026-10-23"))
    assert main.main([]) == 0 and avisos == []


def test_error_controlado_devuelve_1_y_avisa_con_su_mensaje(monkeypatch):
    avisos = espiar(monkeypatch)

    def falla():
        raise PortalError("El listado tiene 2 páginas")

    monkeypatch.setattr(main, "ejecutar", falla)
    assert main.main([]) == 1
    assert avisos == [("Archivist: no se pudo completar", "El listado tiene 2 páginas")]


def test_lote_incompleto_tambien_devuelve_1(monkeypatch):
    espiar(monkeypatch)

    def falla():
        raise IncompleteBatchError("petición 3 de 6: HTTP 500")

    monkeypatch.setattr(main, "ejecutar", falla)
    assert main.main([]) == 1


def test_excepthook_lleva_el_tipo_y_el_texto_del_error_porque_no_hay_consola(monkeypatch):
    avisos = espiar(monkeypatch)
    main._excepthook(KeyError, KeyError("columna"), None)
    assert avisos == [("Archivist: error inesperado", "KeyError: 'columna'")]


def test_excepthook_no_avisa_ante_ctrl_c(monkeypatch):
    avisos = espiar(monkeypatch)
    llamadas = []
    monkeypatch.setattr(sys, "__excepthook__", lambda *a: llamadas.append(a))
    main._excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    assert avisos == [] and len(llamadas) == 1


# --- opciones: --version, --verificar y --salida --------------------------------------------------

def test_version_imprime_y_no_ejecuta_nada(monkeypatch, capsys):
    monkeypatch.setattr(main, "ejecutar", lambda: pytest.fail("no debe ejecutar el flujo"))
    assert main.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"Archivist {main.__version__}"


def test_salida_escribe_el_resultado_en_el_archivo_y_no_imprime(monkeypatch, tmp_path, capsys):
    destino = tmp_path / "version.txt"
    assert main.main(["--version", "--salida", str(destino)]) == 0
    assert destino.read_text(encoding="utf-8").strip() == f"Archivist {main.__version__}"
    assert capsys.readouterr().out == ""


def test_sin_consola_el_resultado_va_a_un_cuadro_de_mensaje(monkeypatch):
    mensajes = []
    monkeypatch.setattr(main, "_mensaje_windows", mensajes.append)
    monkeypatch.setattr(sys, "stdout", None)  # ejecutable --noconsole
    assert main.main(["--version"]) == 0
    assert mensajes == [f"Archivist {main.__version__}"]


def test_con_salida_no_se_muestra_ningun_cuadro_aunque_no_haya_consola(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "_mensaje_windows", lambda t: pytest.fail("no debe mostrar el cuadro"))
    monkeypatch.setattr(sys, "stdout", None)
    destino = tmp_path / "v.txt"
    assert main.main(["--version", "--salida", str(destino)]) == 0 and destino.exists()


def test_verificar_delega_usa_la_misma_salida_y_devuelve_su_codigo(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "ejecutar", lambda: pytest.fail("no debe ejecutar el flujo"))
    monkeypatch.setattr(main, "ejecutar_verificacion", lambda salida: (salida("[OK   ] algo"), 1)[1])
    destino = tmp_path / "verificacion.txt"
    assert main.main(["--verificar", "--salida", str(destino)]) == 1
    assert destino.read_text(encoding="utf-8").strip() == "[OK   ] algo"


def test_salida_sin_ruta_se_ignora(monkeypatch, capsys):
    assert main.main(["--version", "--salida"]) == 0
    assert capsys.readouterr().out.strip() == f"Archivist {main.__version__}"


# --- registro en archivo: desactivado por política de TI -------------------------------------------

def test_el_registro_en_archivo_esta_desactivado_por_defecto(monkeypatch):
    monkeypatch.delenv("ARCHIVIST_LOG_ARCHIVO", raising=False)
    monkeypatch.setattr(main, "activar_log_en_archivo", lambda: pytest.fail("no debe escribir a disco"))
    assert main._activar_log() is None


def test_el_registro_en_archivo_solo_se_activa_si_se_pide(monkeypatch, tmp_path):
    monkeypatch.setenv("ARCHIVIST_LOG_ARCHIVO", "1")
    monkeypatch.setattr(main, "activar_log_en_archivo", lambda: tmp_path / "archivist.log")
    assert main._activar_log() == tmp_path / "archivist.log"