import base64
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from archivist_app.exceptions import IncompleteBatchError
from archivist_app.models import Comprobante, digito_verificador
from archivist_app.services import downloader as dl
from archivist_app.services.downloader import (
    JS_DESCARGA, Downloader, validar_contenido,
)
from archivist_app.services.file_organizer import ruta_destino

RUC = "1790000000001"  # RUC ficticio, solo para pruebas


def fila_dict(i: int, sec: int, tipo: str = "01", ruc: str = RUC) -> dict:
    """tipo "01" (factura) por defecto: la mecánica de la descarga no depende del tipo. Las retenciones
    ("07") se nombran con la factura de su XML y tienen sus propias pruebas al final."""
    base = f"19102026{tipo}{ruc}1038005{sec:09d}014992741"  # 48 digitos
    etiqueta = "Comprobante de Retención" if tipo == "07" else "Factura"
    return {
        "celdas": [
            str(i), f"{ruc} EMISOR DE PRUEBA S.A.", f"{etiqueta} 038-005-{sec:09d}",
            base + str(digito_verificador(base)), "19/10/2026 10:29:17", "19/10/2026",
        ],
        "id_xml": f"frmPrincipal:tablaCompRecibidos:{i - 1}:lnkXml",
        "id_pdf": f"frmPrincipal:tablaCompRecibidos:{i - 1}:lnkPdf",
    }


@dataclass(frozen=True)
class Fila:
    comprobante: Comprobante
    id_xml: str
    id_pdf: str


def fila(i: int, sec: int, tipo: str = "01", ruc: str = RUC) -> Fila:
    d = fila_dict(i, sec, tipo, ruc)
    return Fila(Comprobante.desde_celdas(*d["celdas"]), d["id_xml"], d["id_pdf"])


def pdf(f: Fila) -> bytes:
    return b"%PDF-1.4 " + f.comprobante.clave.valor.encode()


def xml(f: Fila, con_clave: bool = True) -> bytes:
    clave = f.comprobante.clave.valor if con_clave else "0" * 49
    return f"<?xml version='1.0'?><autorizacion><numeroAutorizacion>{clave}</numeroAutorizacion></autorizacion>".encode()


class FakePage:
    """Simula la respuesta del postback; NO prueba el portal real."""

    def __init__(self, filas, cambios=None, falla_en=None):
        self.respuestas = {}
        for f in filas:
            self.respuestas[f.id_xml] = {"status": 200, "datos": xml(f)}
            self.respuestas[f.id_pdf] = {"status": 200, "datos": pdf(f)}
        for id_, r in (cambios or {}).items():
            self.respuestas[id_] = r
        self.falla_en, self.pedidos = falla_en, []

    def evaluate(self, js, id_enlace):
        assert js == JS_DESCARGA
        self.pedidos.append(id_enlace)
        if self.falla_en == len(self.pedidos):
            raise RuntimeError("Target closed")
        r = self.respuestas[id_enlace]
        return {"status": r["status"], "b64": base64.b64encode(r["datos"]).decode()}


def bajador(page, base, pausas=None) -> Downloader:
    return Downloader(page, base, pausa_s=0.5, dormir=(pausas.append if pausas is not None else lambda s: None))


def archivos(base: Path) -> list[Path]:
    return [p for p in base.rglob("*") if p.is_file()]


def sin_staging(base: Path) -> bool:
    """La carpeta .staging es temporal: no debe quedar ni vacía."""
    return not (base / ".staging").exists()


# --- validar_contenido -------------------------------------------------------------------

@pytest.mark.parametrize("ext,datos", [
    ("pdf", b"%PDF-1.7\n..."), ("xml", b"<?xml version='1.0'?><a/>"),
    ("xml", b"\xef\xbb\xbf<?xml version='1.0'?><a/>"), ("xml", b"<comprobanteRetencion id='x'/>"),
])
def test_contenido_valido(ext, datos):
    validar_contenido(ext, datos)


@pytest.mark.parametrize("ext,datos,texto", [
    ("pdf", b"", "vacía"), ("pdf", b"<html><body>login", "%PDF"),
    ("xml", b"<!DOCTYPE html><html><head>", "HTML"),
    ("xml", b"<?xml version='1.0'?><partial-response>", "AJAX"),
    ("xml", b"no es xml", "no parece"), ("txt", b"x", "extensión"),
])
def test_contenido_invalido(ext, datos, texto):
    with pytest.raises(ValueError, match=texto):
        validar_contenido(ext, datos)


# --- lote completo -----------------------------------------------------------------------

def test_lote_ok_guarda_en_las_rutas_del_organizer_y_limpia_staging(tmp_path):
    filas = [fila(1, 101), fila(2, 102), fila(3, 103)]
    pausas = []
    r = bajador(FakePage(filas), tmp_path, pausas).descargar_lote(filas)
    assert (r.escritos, r.omitidos, r.xml_con_clave, r.xml_total) == (6, 0, 3, 3)
    for f in filas:
        for ext, contenido in (("xml", xml(f)), ("pdf", pdf(f))):
            assert ruta_destino(tmp_path, f.comprobante, ext).read_bytes() == contenido
    assert len(archivos(tmp_path)) == 6 and sin_staging(tmp_path)
    assert pausas == [0.5] * 5  # entre las 6 peticiones, ninguna pausa antes de la primera


def test_lote_vacio_no_hace_nada(tmp_path):
    page = FakePage([])
    assert bajador(page, tmp_path).descargar_lote([]).escritos == 0
    assert page.pedidos == [] and not (tmp_path / ".staging").exists()


def test_xml_sin_su_clave_solo_advierte_y_se_cuenta(tmp_path):
    filas = [fila(1, 101), fila(2, 102)]
    page = FakePage(filas, cambios={filas[1].id_xml: {"status": 200, "datos": xml(filas[1], False)}})
    r = bajador(page, tmp_path).descargar_lote(filas)
    assert (r.escritos, r.xml_con_clave, r.xml_total) == (4, 1, 2)


# --- todo o nada -------------------------------------------------------------------------

@pytest.mark.parametrize("cambio,texto", [
    ({"status": 500, "datos": b"x"}, "HTTP 500"),
    ({"status": 200, "datos": b"<html>sesion cerrada"}, "no empieza con %PDF"),
    ({"status": 200, "datos": b""}, "vacía"),
])
def test_fallo_a_mitad_no_deja_nada_guardado(tmp_path, cambio, texto):
    filas = [fila(1, 101), fila(2, 102), fila(3, 103)]
    page = FakePage(filas, cambios={filas[1].id_pdf: cambio})  # falla en la petición 3 de 6
    with pytest.raises(IncompleteBatchError, match=texto) as e:
        bajador(page, tmp_path).descargar_lote(filas)
    assert "petición 3 de 6" in str(e.value) and "fila 2" in str(e.value)
    assert archivos(tmp_path) == [] and sin_staging(tmp_path)
    assert len(page.pedidos) == 3  # se aborta: no se sigue pidiendo al portal


def test_xml_que_es_una_pagina_html(tmp_path):
    filas = [fila(1, 101)]
    page = FakePage(filas, cambios={filas[0].id_xml: {"status": 200, "datos": b"<!DOCTYPE html><html>"}})
    with pytest.raises(IncompleteBatchError, match="HTML"):
        bajador(page, tmp_path).descargar_lote(filas)
    assert archivos(tmp_path) == []


def test_error_de_playwright_se_envuelve_sin_datos(tmp_path):
    filas = [fila(1, 101), fila(2, 102)]
    with pytest.raises(IncompleteBatchError, match="RuntimeError") as e:
        bajador(FakePage(filas, falla_en=2), tmp_path).descargar_lote(filas)
    assert "Target closed" not in str(e.value)
    assert archivos(tmp_path) == [] and sin_staging(tmp_path)


def test_los_mensajes_no_llevan_la_clave(tmp_path):
    filas = [fila(1, 101)]
    page = FakePage(filas, cambios={filas[0].id_pdf: {"status": 200, "datos": b"nope"}})
    with pytest.raises(IncompleteBatchError) as e:
        bajador(page, tmp_path).descargar_lote(filas)
    assert filas[0].comprobante.clave.valor not in str(e.value)


# --- existentes y conflictos -------------------------------------------------------------

def test_omite_lo_que_ya_existe_igual(tmp_path):
    filas = [fila(1, 101), fila(2, 102)]
    ya = ruta_destino(tmp_path, filas[0].comprobante, "pdf")
    ya.parent.mkdir(parents=True)
    ya.write_bytes(pdf(filas[0]))
    r = bajador(FakePage(filas), tmp_path).descargar_lote(filas)
    assert (r.escritos, r.omitidos) == (3, 1)


def test_conflicto_con_archivo_distinto_aborta_y_no_toca_nada(tmp_path):
    filas = [fila(1, 101), fila(2, 102)]
    ya = ruta_destino(tmp_path, filas[1].comprobante, "xml")
    ya.parent.mkdir(parents=True)
    ya.write_bytes(b"<otro/>")
    with pytest.raises(IncompleteBatchError, match="archivo distinto"):
        bajador(FakePage(filas), tmp_path).descargar_lote(filas)
    assert archivos(tmp_path) == [ya] and ya.read_bytes() == b"<otro/>"
    assert sin_staging(tmp_path)


def test_ruta_demasiado_larga_se_detecta_antes_de_pedir(tmp_path):
    filas = [fila(1, 101)]
    page = FakePage(filas)
    with pytest.raises(IncompleteBatchError, match="No se pudo planificar"):
        bajador(page, tmp_path / ("x" * 200)).descargar_lote(filas)
    assert page.pedidos == []


def test_si_falla_el_movimiento_se_revierte_lo_movido(tmp_path, monkeypatch):
    filas = [fila(1, 101), fila(2, 102)]
    reales, llamadas = os.replace, []

    def replace_que_falla(origen, destino):
        llamadas.append(destino)
        if len(llamadas) == 3:
            raise PermissionError("bloqueado")
        reales(origen, destino)

    monkeypatch.setattr(dl.os, "replace", replace_que_falla)
    with pytest.raises(IncompleteBatchError, match="PermissionError.*revirtió"):
        bajador(FakePage(filas), tmp_path).descargar_lote(filas)
    assert archivos(tmp_path) == [] and sin_staging(tmp_path)

# --- la carpeta .staging es temporal -------------------------------------------------------------

def test_un_lote_exitoso_no_deja_ni_la_carpeta_staging(tmp_path):
    filas = [fila(1, 101)]
    bajador(FakePage(filas), tmp_path).descargar_lote(filas)
    assert not (tmp_path / ".staging").exists()


def test_un_lote_fallido_tampoco_deja_la_carpeta_staging(tmp_path):
    filas = [fila(1, 101)]
    page = FakePage(filas, cambios={filas[0].id_pdf: {"status": 500, "datos": b"x"}})
    with pytest.raises(IncompleteBatchError):
        bajador(page, tmp_path).descargar_lote(filas)
    assert not (tmp_path / ".staging").exists()


def test_los_restos_de_otra_corrida_en_staging_no_se_borran(tmp_path):
    resto = tmp_path / ".staging" / "lote_antiguo"
    resto.mkdir(parents=True)
    (resto / "000001.pdf").write_bytes(b"%PDF dato de una corrida interrumpida")
    filas = [fila(1, 101)]
    bajador(FakePage(filas), tmp_path).descargar_lote(filas)
    assert (resto / "000001.pdf").read_bytes() == b"%PDF dato de una corrida interrumpida"
    assert [p.name for p in (tmp_path / ".staging").iterdir()] == ["lote_antiguo"]  # solo queda lo ajeno


def test_si_no_se_puede_crear_la_carpeta_temporal_no_queda_staging(tmp_path, monkeypatch):
    def falla(*args, **kwargs):
        raise PermissionError("denegado")

    monkeypatch.setattr(dl.tempfile, "mkdtemp", falla)
    filas = [fila(1, 101)]
    with pytest.raises(IncompleteBatchError, match="carpeta temporal"):
        bajador(FakePage(filas), tmp_path).descargar_lote(filas)
    assert not (tmp_path / ".staging").exists()


# === retenciones: el nombre lleva la factura del XML, así que el XML se baja PRIMERO ===========

def xml_ret(f: Fila, factura: str = "001001000097687", codigo: str = "01") -> bytes:
    """XML autorizado de una retención (comprobante en CDATA) con su documento sustento."""
    clave = f.comprobante.clave.valor
    interno = (
        "<comprobanteRetencion><docsSustento><docSustento>"
        f"<codDocSustento>{codigo}</codDocSustento><numDocSustento>{factura}</numDocSustento>"
        "</docSustento></docsSustento></comprobanteRetencion>"
    )
    return (
        f"<?xml version='1.0'?><autorizacion><numeroAutorizacion>{clave}</numeroAutorizacion>"
        f"<comprobante><![CDATA[{interno}]]></comprobante></autorizacion>"
    ).encode()


def con_sustento(filas, *facturas, codigo="01") -> dict:
    """Cambios para FakePage: el XML de cada retención trae su factura sustento (15 dígitos)."""
    return {
        f.id_xml: {"status": 200, "datos": xml_ret(f, fac, codigo)} for f, fac in zip(filas, facturas)
    }


def carpeta_ret(base: Path) -> Path:
    return base / "2026" / "10" / "19" / "Retenciones"


def test_retenciones_se_nombran_con_la_factura_de_su_xml(tmp_path):
    filas = [fila(1, 101, "07"), fila(2, 102, "07")]
    page = FakePage(filas, cambios=con_sustento(filas, "001001000097687", "001001000097688"))
    r = bajador(page, tmp_path).descargar_lote(filas)
    assert (r.escritos, r.omitidos, r.xml_con_clave, r.xml_total) == (4, 0, 2, 2)
    carpeta = carpeta_ret(tmp_path)
    assert sorted(p.name for p in carpeta.iterdir()) == [
        "001-001-000097687_038-005-000000101.pdf", "001-001-000097687_038-005-000000101.xml",
        "001-001-000097688_038-005-000000102.pdf", "001-001-000097688_038-005-000000102.xml",
    ]
    assert (carpeta / "001-001-000097687_038-005-000000101.pdf").read_bytes() == pdf(filas[0])
    assert (carpeta / "001-001-000097688_038-005-000000102.xml").read_bytes() == xml_ret(filas[1], "001001000097688")
    assert len(archivos(tmp_path)) == 4 and sin_staging(tmp_path)


def test_el_xml_de_cada_retencion_se_pide_una_sola_vez_y_antes_que_los_pdf(tmp_path):
    filas = [fila(1, 101, "07"), fila(2, 102, "07")]
    page = FakePage(filas, cambios=con_sustento(filas, "001001000097687", "001001000097688"))
    pausas = []
    bajador(page, tmp_path, pausas).descargar_lote(filas)
    assert page.pedidos == [filas[0].id_xml, filas[1].id_xml, filas[0].id_pdf, filas[1].id_pdf]
    assert pausas == [0.5] * 3  # entre las 4 peticiones, ninguna pausa antes de la primera


def test_fallo_en_un_pdf_de_retencion_numera_las_peticiones_en_su_orden_real(tmp_path):
    filas = [fila(1, 101, "07"), fila(2, 102, "07")]
    cambios = con_sustento(filas, "001001000097687", "001001000097688")
    cambios[filas[1].id_pdf] = {"status": 500, "datos": b"x"}
    page = FakePage(filas, cambios=cambios)
    with pytest.raises(IncompleteBatchError, match="HTTP 500") as e:
        bajador(page, tmp_path).descargar_lote(filas)
    assert "petición 4 de 4 (PDF, fila 2)" in str(e.value)
    assert archivos(tmp_path) == [] and sin_staging(tmp_path)


def test_sustento_que_no_es_factura_aborta_sin_guardar_ni_seguir_pidiendo(tmp_path):
    filas = [fila(1, 101, "07"), fila(2, 102, "07")]
    page = FakePage(filas, cambios=con_sustento(filas, "001001000097687", "001001000097688", codigo="04"))
    with pytest.raises(IncompleteBatchError, match="no es una factura") as e:
        bajador(page, tmp_path).descargar_lote(filas)
    assert "petición 1 de 4 (XML, fila 1)" in str(e.value)
    assert len(page.pedidos) == 1 and archivos(tmp_path) == [] and sin_staging(tmp_path)


def test_retencion_sin_documento_sustento_aborta(tmp_path):
    filas = [fila(1, 101, "07")]
    with pytest.raises(IncompleteBatchError, match="no trae documento sustento"):
        bajador(FakePage(filas), tmp_path).descargar_lote(filas)  # el XML por defecto no lo trae
    assert archivos(tmp_path) == [] and sin_staging(tmp_path)


def test_retencion_con_dos_sustentos_distintos_aborta(tmp_path):
    filas = [fila(1, 101, "07")]
    doble = (
        b"<comprobanteRetencion><docsSustento>"
        b"<docSustento><codDocSustento>01</codDocSustento><numDocSustento>001001000097687</numDocSustento></docSustento>"
        b"<docSustento><codDocSustento>01</codDocSustento><numDocSustento>001001000097688</numDocSustento></docSustento>"
        b"</docsSustento></comprobanteRetencion>"
    )
    page = FakePage(filas, cambios={filas[0].id_xml: {"status": 200, "datos": doble}})
    with pytest.raises(IncompleteBatchError, match="2 documentos sustento"):
        bajador(page, tmp_path).descargar_lote(filas)
    assert archivos(tmp_path) == []


def test_acepta_el_xml_sin_envoltorio_con_raiz_comprobante_retencion(tmp_path):
    filas = [fila(1, 101, "07")]
    clave = filas[0].comprobante.clave.valor
    plano = (
        f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><comprobanteRetencion id=\"comprobante\" version=\"2.0.0\">"
        f"<infoTributaria><claveAcceso>{clave}</claveAcceso></infoTributaria>"
        "<docsSustento><docSustento><codDocSustento>01</codDocSustento>"
        "<numDocSustento>001001000097687</numDocSustento></docSustento></docsSustento>"
        "</comprobanteRetencion>"
    ).encode()
    page = FakePage(filas, cambios={filas[0].id_xml: {"status": 200, "datos": plano}})
    r = bajador(page, tmp_path).descargar_lote(filas)
    assert (r.escritos, r.xml_con_clave) == (2, 1)
    assert (carpeta_ret(tmp_path) / "001-001-000097687_038-005-000000101.xml").read_bytes() == plano


def test_la_ruta_larga_de_retenciones_se_detecta_antes_de_pedir(tmp_path):
    filas = [fila(1, 101, "07")]
    page = FakePage(filas, cambios=con_sustento(filas, "001001000097687"))
    with pytest.raises(IncompleteBatchError, match="No se pudo planificar"):
        bajador(page, tmp_path / ("x" * 200)).descargar_lote(filas)
    assert page.pedidos == []


def test_repetir_un_lote_de_retenciones_lo_omite_todo(tmp_path):
    filas = [fila(1, 101, "07"), fila(2, 102, "07")]
    cambios = con_sustento(filas, "001001000097687", "001001000097688")
    assert bajador(FakePage(filas, cambios=cambios), tmp_path).descargar_lote(filas).escritos == 4
    r = bajador(FakePage(filas, cambios=cambios), tmp_path).descargar_lote(filas)
    assert (r.escritos, r.omitidos) == (0, 4)
    assert len(archivos(tmp_path)) == 4


def test_retenciones_con_el_mismo_numero_de_otro_emisor_conviven_si_su_factura_es_otra(tmp_path):
    filas = [fila(1, 101, "07"), fila(2, 101, "07", ruc="1791111111001")]  # mismo número de retención
    assert filas[0].comprobante.clave.numero == filas[1].comprobante.clave.numero
    page = FakePage(filas, cambios=con_sustento(filas, "001001000097687", "001001000097688"))
    r = bajador(page, tmp_path).descargar_lote(filas)
    assert r.escritos == 4 and len(archivos(tmp_path)) == 4


def test_retenciones_con_el_mismo_numero_y_la_misma_factura_abortan_al_planificar(tmp_path):
    filas = [fila(1, 101, "07"), fila(2, 101, "07", ruc="1791111111001")]
    page = FakePage(filas, cambios=con_sustento(filas, "001001000097687", "001001000097687"))
    with pytest.raises(IncompleteBatchError, match="No se pudo planificar.*misma ruta"):
        bajador(page, tmp_path).descargar_lote(filas)
    assert len(page.pedidos) == 2  # solo los dos XML; no se pidió ningún PDF
    assert archivos(tmp_path) == [] and sin_staging(tmp_path)


def test_los_mensajes_de_retenciones_no_llevan_la_clave_ni_la_factura(tmp_path):
    filas = [fila(1, 101, "07")]
    page = FakePage(filas, cambios=con_sustento(filas, "001001000097687", codigo="04"))
    with pytest.raises(IncompleteBatchError) as e:
        bajador(page, tmp_path).descargar_lote(filas)
    assert filas[0].comprobante.clave.valor not in str(e.value) and "097687" not in str(e.value)