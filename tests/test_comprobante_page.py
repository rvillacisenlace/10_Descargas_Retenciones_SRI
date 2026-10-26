import pytest

from archivist_app.exceptions import PortalError
from archivist_app.models import digito_verificador
from archivist_app.pages.comprobantes_page import (
    CONTENEDOR, FILAS, JS_FILAS, PAGINADOR, ComprobantesPage,
)

RUC = "1790000000001"  # RUC ficticio, solo para pruebas


def clave(sec: int, tipo: str = "07", fecha: str = "19102026") -> str:
    base = f"{fecha}{tipo}{RUC}1038005{sec:09d}014992741"  # 48 dígitos
    return base + str(digito_verificador(base))


def fila(i: int, sec: int, tipo: str = "07", c: str | None = None) -> dict:
    return {
        "celdas": [
            str(i), f"{RUC} EMISOR DE PRUEBA S.A.", f"Comprobante de Retención 038-005-{sec:09d}",
            c or clave(sec, tipo), "19/10/2026 10:29:17", "19/10/2026",
        ],
        "id_xml": f"frmPrincipal:tablaCompRecibidos:{i - 1}:lnkXml",
        "id_pdf": f"frmPrincipal:tablaCompRecibidos:{i - 1}:lnkPdf",
    }


class FakeLocator:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    @property
    def first(self):
        return self

    def count(self):
        if self.selector == CONTENEDOR:
            return 1 if self.page.estado()[1] else 0
        if self.selector == PAGINADOR:
            return 0 if self.page.paginador is None else 1
        if self.selector == FILAS:
            return len(self.page.filas)
        return 0

    def inner_text(self):
        return self.page.paginador

    def input_value(self):
        return self.page.combos[self.selector.split(":")[1].rstrip('"]')]


class FakePage:
    """Simula las decisiones del portal; NO prueba el portal real.
    guion: lista de (texto del body, contenedor presente) que avanza en cada espera."""

    def __init__(self, guion=None, filas=(), paginador="(1 of 1)", tipo="6"):
        self.guion, self.i = guion or [("", True)], 0
        self.filas, self.paginador = list(filas), paginador
        self.combos = {"ano": "2026", "mes": "10", "dia": "0", "cmbTipoComprobante": tipo}

    def estado(self):
        return self.guion[min(self.i, len(self.guion) - 1)]

    def locator(self, selector):
        return FakeLocator(self, selector)

    def inner_text(self, selector):
        return self.estado()[0]

    def wait_for_timeout(self, ms):
        self.i += 1

    def evaluate(self, js):
        assert js == JS_FILAS
        return self.filas


def pagina(**kw) -> ComprobantesPage:
    return ComprobantesPage(FakePage(**kw))


# --- esperar_listado ---------------------------------------------------------------------

def test_espera_ok_sin_avisos():
    avisos = []
    pagina(guion=[("", False), ("", True)]).esperar_listado(avisar=avisos.append)
    assert avisos == []


def test_rechazo_se_avisa_una_vez_por_aparicion_y_sigue_esperando():
    avisos = []
    guion = [("", False), ("Captcha incorrecta", False), ("Captcha incorrecta", False),
             ("", False), ("Captcha incorrecto", False), ("", True)]
    pagina(guion=guion).esperar_listado(avisar=avisos.append)
    assert avisos == ["rechazo_captcha", "rechazo_captcha"]


def test_sin_token_se_avisa():
    avisos = []
    guion = [("Could not connect to the reCAPTCHA service. Please check", False), ("", True)]
    pagina(guion=guion).esperar_listado(avisar=avisos.append)
    assert avisos == ["sin_token"]


def test_timeout_es_portal_error():
    with pytest.raises(PortalError, match="No apareció el listado"):
        pagina(guion=[("", False)]).esperar_listado(timeout_s=0.05, intervalo_ms=5)


# --- paginas / filtro --------------------------------------------------------------------

def test_paginas_lee_el_paginador():
    assert pagina(paginador="(2 of 3)").paginas() == (2, 3)


def test_listado_vacio_sin_paginador_es_una_pagina():
    assert pagina(paginador=None, filas=[]).paginas() == (1, 1)


def test_filas_sin_paginador_es_error():
    with pytest.raises(PortalError, match="paginador"):
        pagina(paginador=None, filas=[fila(1, 1)]).paginas()


def test_paginador_ilegible_es_error():
    with pytest.raises(PortalError, match="paginador"):
        pagina(paginador="pagina uno").paginas()


def test_leer_filtro_usa_valores_actuales():
    f = pagina().leer_filtro()
    assert (f.ano, f.mes, f.dia, f.tipo_portal) == (2026, 10, 0, "6")


# --- leer_todas --------------------------------------------------------------------------

def test_leer_todas_ok_conserva_ids_de_descarga():
    filas = pagina(filas=[fila(1, 101), fila(2, 102), fila(3, 103)]).leer_todas()
    assert [f.comprobante.nro for f in filas] == [1, 2, 3]
    assert filas[0].id_xml.endswith(":0:lnkXml") and filas[2].id_pdf.endswith(":2:lnkPdf")


def test_listado_vacio_es_valido():
    assert pagina(paginador=None, filas=[]).leer_todas() == []


def test_mas_de_una_pagina_no_devuelve_lote_parcial():
    with pytest.raises(PortalError, match="2 páginas"):
        pagina(paginador="(1 of 2)", filas=[fila(1, 101)]).leer_todas()


def test_tipo_distinto_al_del_filtro():
    with pytest.raises(PortalError, match="tipo distinto"):
        pagina(tipo="1", filas=[fila(1, 101)]).leer_todas()  # filtro Factura, filas de retención


def test_tipo_de_filtro_desconocido():
    with pytest.raises(PortalError, match="no está reconocido"):
        pagina(tipo="99", filas=[fila(1, 101)]).leer_todas()


def test_claves_repetidas():
    with pytest.raises(PortalError, match="repetidas"):
        pagina(filas=[fila(1, 101), fila(2, 101)]).leer_todas()


def test_numeracion_con_saltos():
    with pytest.raises(PortalError, match="contigua"):
        pagina(filas=[fila(1, 101), fila(3, 103)]).leer_todas()


def test_fila_sin_enlace_de_pdf():
    f = fila(1, 101)
    f["id_pdf"] = None
    with pytest.raises(PortalError, match="fila 1"):
        pagina(filas=[f]).leer_todas()


def test_fila_con_pocas_columnas():
    f = fila(1, 101)
    f["celdas"] = f["celdas"][:4]
    with pytest.raises(PortalError, match="menos de 6 columnas"):
        pagina(filas=[f]).leer_todas()


def test_clave_invalida_no_se_repite_en_el_mensaje():
    mala = clave(101)[:-1] + str((int(clave(101)[-1]) + 1) % 10)
    with pytest.raises(PortalError) as e:
        pagina(filas=[fila(1, 101, c=mala)]).leer_todas()
    assert "fila 1" in str(e.value) and mala not in str(e.value)