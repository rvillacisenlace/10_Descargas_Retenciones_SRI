from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from archivist_app import workflow
from archivist_app.exceptions import IncompleteBatchError, LoginError, PortalError
from archivist_app.services.downloader import ResultadoDescarga


class Escenario:
    """Sustituye navegador, páginas y notificaciones; registra el orden de las llamadas.
    Simula las decisiones del flujo; NO prueba el portal real."""

    def __init__(self, monkeypatch, falla_en=None, avisos_captcha=()):
        self.eventos, self.notificaciones = [], []
        e = self.eventos

        monkeypatch.setattr(workflow, "load_settings", lambda: (
            e.append("config"),
            SimpleNamespace(login_url="u1", recibidos_url="u2", portal_ruc="r", portal_password="p", output_dir="OUT"),
        )[1])

        @contextmanager
        def abrir(headless):
            e.append(f"abrir(headless={headless})")
            try:
                yield SimpleNamespace(pages=["PAGINA"])
            finally:
                e.append("cerrar")

        monkeypatch.setattr(workflow, "open_context", abrir)

        class Login:
            def __init__(s, page):
                assert page == "PAGINA"

            def login(s, *args):
                e.append(f"login{args}")
                if falla_en == "login":
                    raise LoginError("credenciales rechazadas")

        class Listado:
            def __init__(s, page):
                pass

            def esperar_listado(s, avisar=None):
                e.append("esperar")
                for motivo in avisos_captcha:
                    avisar(motivo)

            def leer_todas(s):
                e.append("leer")
                if falla_en == "leer":
                    raise PortalError("El listado tiene 2 páginas")
                return ["f1", "f2", "f3"]

        class Bajador:
            def __init__(s, page, base):
                e.append(f"bajador(base={base})")

            def descargar_lote(s, filas):
                e.append(f"descargar({len(filas)})")
                if falla_en == "descargar":
                    raise IncompleteBatchError("petición 3 de 6 (PDF, fila 2): HTTP 500")
                return ResultadoDescarga(escritos=5, omitidos=1, xml_con_clave=3, xml_total=3)

        monkeypatch.setattr(workflow, "LoginPage", Login)
        monkeypatch.setattr(workflow, "ComprobantesPage", Listado)
        monkeypatch.setattr(workflow, "Downloader", Bajador)
        monkeypatch.setattr(workflow, "notificar", lambda t, m, d="short": self.notificaciones.append((t, m)))


def test_orden_completo_y_resultado(monkeypatch):
    esc = Escenario(monkeypatch)
    r = workflow.ejecutar()
    assert esc.eventos == [
        "config", "abrir(headless=False)", "login('u1', 'u2', 'r', 'p')", "esperar", "leer",
        "bajador(base=OUT)", "descargar(3)", "cerrar",
    ]
    assert r == workflow.RunResult(comprobantes=3, escritos=5, omitidos=1, xml_con_clave=3, xml_total=3)


def test_avisos_al_usuario_en_orden(monkeypatch):
    esc = Escenario(monkeypatch)
    workflow.ejecutar()
    assert [t for t, _ in esc.notificaciones] == [
        "Archivist: elija el filtro", "Archivist: descarga completa",
    ]
    assert "3 comprobantes: 5 archivos nuevos y 1 que ya estaban" in esc.notificaciones[1][1]


def test_el_rechazo_de_captcha_se_avisa_al_usuario(monkeypatch):
    esc = Escenario(monkeypatch, avisos_captcha=("rechazo_captcha", "sin_token"))
    workflow.ejecutar()
    textos = [m for t, m in esc.notificaciones if t == "Archivist: consulta no completada"]
    assert len(textos) == 2 and "rechazó la consulta" in textos[0] and "no pudo conectarse" in textos[1]


@pytest.mark.parametrize("falla_en,error", [
    ("login", LoginError), ("leer", PortalError), ("descargar", IncompleteBatchError),
])
def test_un_error_se_propaga_sin_aviso_de_exito_y_cierra_el_navegador(monkeypatch, falla_en, error):
    esc = Escenario(monkeypatch, falla_en=falla_en)
    with pytest.raises(error):
        workflow.ejecutar()
    assert esc.eventos[-1] == "cerrar"
    assert "Archivist: descarga completa" not in [t for t, _ in esc.notificaciones]


def test_si_falla_el_login_no_se_pide_nada_al_usuario(monkeypatch):
    esc = Escenario(monkeypatch, falla_en="login")
    with pytest.raises(LoginError):
        workflow.ejecutar()
    assert esc.notificaciones == [] and "esperar" not in esc.eventos