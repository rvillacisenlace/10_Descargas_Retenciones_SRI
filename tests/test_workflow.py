from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from archivist_app import workflow
from archivist_app.exceptions import IncompleteBatchError, LoginError, PortalError
from archivist_app.pages.comprobantes_page import FiltroConsulta
from archivist_app.services.downloader import ResultadoDescarga


class Escenario:
    """Sustituye navegador, páginas y notificaciones; registra el orden de las llamadas.
    Simula las decisiones del flujo; NO prueba el portal real."""

    def __init__(self, monkeypatch, falla_en=None, avisos_captcha=(), filtro=None):
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

            def leer_filtro(s):
                e.append("filtro")
                return filtro or FiltroConsulta(ano=2026, mes=10, dia=23, tipo_portal="6")

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
        "config", "abrir(headless=False)", "login('u1', 'u2', 'r', 'p')", "esperar", "filtro", "leer",
        "bajador(base=OUT)", "descargar(3)", "cerrar",
    ]
    assert r == workflow.RunResult(
        comprobantes=3, escritos=5, omitidos=1, xml_con_clave=3, xml_total=3,
        tipo="Comprobante de retención", desde="2026-10-23", hasta="2026-10-23",
    )


def test_avisos_al_usuario_en_orden_con_el_formato_de_docket(monkeypatch):
    esc = Escenario(monkeypatch)
    workflow.ejecutar()
    assert esc.notificaciones == [
        ("Archivist", "Elige el tipo de comprobante y el rango de fechas, y pulsa Consultar en el portal."),
        ("Archivist", "Comprobante de retención | 2026-10-23 a 2026-10-23: 3 comprobantes. "
                      "Nuevos 5, omitidos 1, fallidos 0."),
    ]


def test_con_todos_los_dias_el_resumen_cubre_el_mes(monkeypatch):
    esc = Escenario(monkeypatch, filtro=FiltroConsulta(ano=2026, mes=11, dia=0, tipo_portal="1"))
    workflow.ejecutar()
    assert esc.notificaciones[1][1].startswith("Factura | 2026-11-01 a 2026-11-30: 3 comprobantes.")


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
    assert all(m == workflow.AVISO_INICIAL for _, m in esc.notificaciones)  # sin resumen de éxito


def test_si_falla_el_login_no_se_pide_nada_al_usuario(monkeypatch):
    esc = Escenario(monkeypatch, falla_en="login")
    with pytest.raises(LoginError):
        workflow.ejecutar()
    assert esc.notificaciones == [] and "esperar" not in esc.eventos

# --- formato de los mensajes (idéntico al de las capturas de Docket) ------------------------

def _resultado(**cambios):
    datos = dict(comprobantes=15, escritos=0, omitidos=30, xml_con_clave=15, xml_total=15,
                 tipo="Factura", desde="2026-10-23", hasta="2026-10-23")
    datos.update(cambios)
    return workflow.RunResult(**datos)


def test_resumen_identico_al_de_la_captura_de_docket():
    assert workflow.mensaje_resumen(_resultado()) == (
        "Factura | 2026-10-23 a 2026-10-23: 15 comprobantes. Nuevos 0, omitidos 30, fallidos 0."
    )


def test_resumen_en_singular_y_sin_resultados():
    assert workflow.mensaje_resumen(_resultado(comprobantes=1, escritos=2, omitidos=0)).startswith(
        "Factura | 2026-10-23 a 2026-10-23: 1 comprobante. Nuevos 2,")
    assert ": 0 comprobantes. Nuevos 0, omitidos 0, fallidos 0." in workflow.mensaje_resumen(
        _resultado(comprobantes=0, omitidos=0))


def test_el_aviso_inicial_es_el_de_la_captura_de_docket():
    assert workflow.AVISO_INICIAL == (
        "Elige el tipo de comprobante y el rango de fechas, y pulsa Consultar en el portal."
    )


@pytest.mark.parametrize("ano,mes,dia,esperado", [
    (2026, 10, 23, ("2026-10-23", "2026-10-23")),  # un día: la misma fecha dos veces
    (2026, 10, 0, ("2026-10-01", "2026-10-31")),  # 'Todos': el mes completo
    (2026, 11, 0, ("2026-11-01", "2026-11-30")),
    (2026, 2, 0, ("2026-02-01", "2026-02-28")),
    (2028, 2, 0, ("2028-02-01", "2028-02-29")),  # bisiesto
    (2026, 11, 31, ("2026-11-31", "2026-11-31")),  # el combo permite 31 en un mes de 30: no se cae
])
def test_rango_de_fechas(ano, mes, dia, esperado):
    assert workflow._rango(FiltroConsulta(ano=ano, mes=mes, dia=dia, tipo_portal="6")) == esperado