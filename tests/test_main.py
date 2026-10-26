import sys

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
    assert main.main() == 0 and avisos == []


def test_error_controlado_devuelve_1_y_avisa_con_su_mensaje(monkeypatch):
    avisos = espiar(monkeypatch)

    def falla():
        raise PortalError("El listado tiene 2 páginas")

    monkeypatch.setattr(main, "ejecutar", falla)
    assert main.main() == 1
    assert avisos == [("Archivist: no se pudo completar", "El listado tiene 2 páginas")]


def test_lote_incompleto_tambien_devuelve_1(monkeypatch):
    espiar(monkeypatch)

    def falla():
        raise IncompleteBatchError("petición 3 de 6: HTTP 500")

    monkeypatch.setattr(main, "ejecutar", falla)
    assert main.main() == 1


def test_excepthook_avisa_sin_filtrar_el_mensaje_del_error(monkeypatch):
    avisos = espiar(monkeypatch)
    main._excepthook(KeyError, KeyError("dato-sensible"), None)
    assert avisos == [("Archivist: error inesperado", "KeyError. Revise la consola.")]


def test_excepthook_no_avisa_ante_ctrl_c(monkeypatch):
    avisos = espiar(monkeypatch)
    llamadas = []
    monkeypatch.setattr(sys, "__excepthook__", lambda *a: llamadas.append(a))
    main._excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    assert avisos == [] and len(llamadas) == 1