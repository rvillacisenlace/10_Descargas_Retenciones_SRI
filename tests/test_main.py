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

# --- opciones y empaquetado ---------------------------------------------------------------------

def test_version_imprime_y_no_ejecuta_nada(monkeypatch, capsys):
    monkeypatch.setattr(main, "ejecutar", lambda: pytest.fail("no debe ejecutar el flujo"))
    assert main.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"Archivist {main.__version__}"


def test_verificar_delega_y_devuelve_su_codigo_sin_tocar_el_portal(monkeypatch):
    monkeypatch.setattr(main, "ejecutar", lambda: pytest.fail("no debe ejecutar el flujo"))
    monkeypatch.setattr(main, "ejecutar_verificacion", lambda: 1)
    assert main.main(["--verificar"]) == 1


class FakeStdin:
    def __init__(self, interactiva):
        self.interactiva = interactiva

    def isatty(self):
        return self.interactiva


@pytest.mark.parametrize("empaquetado,codigo,interactiva,espera", [
    (False, 1, True, False),   # desarrollo: la terminal ya se queda abierta
    (True, 0, True, False),    # todo bien: la ventana se cierra sola y el aviso resume el resultado
    (True, 1, True, True),     # empaquetado, con error y con una persona delante: espera
    (True, 1, False, False),   # sin consola interactiva (tarea programada): jamás se queda colgado
])
def test_pausa_solo_en_el_ejecutable_con_error_y_con_una_persona_delante(
        monkeypatch, empaquetado, codigo, interactiva, espera):
    pedidos = []
    monkeypatch.setattr(sys, "frozen", empaquetado, raising=False)
    monkeypatch.setattr(sys, "stdin", FakeStdin(interactiva))
    monkeypatch.setattr("builtins.input", lambda prompt="": pedidos.append(prompt) or "")
    main._pausar_si_hay_error(codigo)
    assert bool(pedidos) is espera


def test_sin_stdin_no_falla(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "stdin", None)
    main._pausar_si_hay_error(1)  # no debe lanzar


def test_si_la_consola_se_cierra_mientras_espera_no_falla(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "stdin", FakeStdin(True))

    def cerrada(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", cerrada)
    main._pausar_si_hay_error(1)  # no debe lanzar


def test_un_error_inesperado_tambien_espera_en_el_ejecutable(monkeypatch):
    espiar(monkeypatch)
    pausas = []
    monkeypatch.setattr(main, "_pausar_si_hay_error", pausas.append)
    main._excepthook(KeyError, KeyError("x"), None)
    assert pausas == [1]


def test_la_variable_de_entorno_desactiva_la_pausa(monkeypatch):
    pedidos = []
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "stdin", FakeStdin(True))
    monkeypatch.setattr("builtins.input", lambda prompt="": pedidos.append(prompt) or "")
    monkeypatch.setenv("ARCHIVIST_SIN_PAUSA", "1")
    main._pausar_si_hay_error(1)
    assert pedidos == []