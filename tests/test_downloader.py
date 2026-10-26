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


def fila_dict(i: int, sec: int) -> dict:
    base = f"19102026{'07'}{RUC}1038005{sec:09d}014992741"  # 48 digitos
    return {
        "celdas": [
            str(i), f"{RUC} EMISOR DE PRUEBA S.A.", f"Comprobante de Retención 038-005-{sec:09d}",
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


def fila(i: int, sec: int) -> Fila:
    d = fila_dict(i, sec)
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


def staging_vacio(base: Path) -> bool:
    raiz = base / ".staging"
    return not raiz.exists() or not any(raiz.iterdir())


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
    assert len(archivos(tmp_path)) == 6 and staging_vacio(tmp_path)
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
    assert archivos(tmp_path) == [] and staging_vacio(tmp_path)
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
    assert archivos(tmp_path) == [] and staging_vacio(tmp_path)


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
    assert staging_vacio(tmp_path)


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
    assert archivos(tmp_path) == [] and staging_vacio(tmp_path)