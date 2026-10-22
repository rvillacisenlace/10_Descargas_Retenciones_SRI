from datetime import date, datetime

import pytest

from archivist_app.models import (
    ClaveAcceso,
    Comprobante,
    digito_verificador,
    nros_contiguos,
    parse_fecha,
    parse_fecha_hora,
    validar_lote,
)

# Claves SINTÉTICAS (RUC y números inventados). Los dígitos verificadores se escriben a mano:
# se calcularon con el algoritmo que acertó 18 de 18 claves reales.
CLAVE_A = "2110202607170000000000120010100000042191234567812"  # retención 21/10/2026
CLAVE_B = "0501202601179000000000120020030000000158765432115"  # factura 05/01/2026
CLAVE_FECHA_IMPOSIBLE = "3102202607170000000000120010100000042191234567813"  # 31/02, dígito válido
CLAVE_D = "2210202607170000000000220010100000042201234567811"  # retención 22/10/2026, otro RUC


def _fila(**cambios):
    celdas = {
        "nro": "1",
        "ruc_y_razon": "1700000000001 \n EMPRESA DE PRUEBA S.A.",
        "tipo_y_serie": "Comprobante de Retención\n001-010-000004219",
        "clave": CLAVE_A,
        "fecha_autorizacion": "21/10/2026 14:35:12",
        "fecha_emision": "21/10/2026",
    }
    celdas.update(cambios)
    return Comprobante.desde_celdas(**celdas)


def test_digito_verificador_de_claves_conocidas():
    assert digito_verificador(CLAVE_A[:48]) == 2
    assert digito_verificador(CLAVE_B[:48]) == 5
    assert digito_verificador(CLAVE_D[:48]) == 1


def test_parse_extrae_los_campos_de_la_clave():
    c = ClaveAcceso.parse(CLAVE_A)
    assert c.fecha_emision == date(2026, 10, 21)
    assert c.codigo_tipo == "07" and c.tipo == "Comprobante de retención"
    assert c.ruc_emisor == "1700000000001"
    assert c.ambiente == "2"
    assert c.numero == "001-010-000004219"


@pytest.mark.parametrize(
    "texto, motivo",
    [
        (CLAVE_A[:-1], "49 dígitos"),
        (CLAVE_A + "0", "49 dígitos"),
        ("A" + CLAVE_A[1:], "49 dígitos"),
        (CLAVE_A[:-1] + "3", "dígito verificador"),
        (CLAVE_FECHA_IMPOSIBLE, "fecha"),
        ("", "49 dígitos"),
    ],
)
def test_parse_rechaza_claves_invalidas(texto, motivo):
    with pytest.raises(ValueError, match=motivo) as e:
        ClaveAcceso.parse(texto)
    if texto:
        assert texto not in str(e.value)  # el mensaje no repite lo que se le pasó


def test_fechas_estrictas():
    assert parse_fecha("21/10/2026") == date(2026, 10, 21)
    assert parse_fecha_hora("21/10/2026 14:35:12") == datetime(2026, 10, 21, 14, 35, 12)
    for malo in ("1/2/2026", "2026-10-21", "31/02/2026", ""):
        with pytest.raises(ValueError):
            parse_fecha(malo)
    for malo in ("21/10/2026", "21/10/2026 14:35", "21/10/2026 25:00:00"):
        with pytest.raises(ValueError):
            parse_fecha_hora(malo)


def test_desde_celdas_construye_el_comprobante():
    c = _fila()
    assert c.nro == 1
    assert c.ruc_emisor == "1700000000001"
    assert c.razon_social_emisor == "EMPRESA DE PRUEBA S.A."
    assert c.fecha_emision == date(2026, 10, 21)
    assert c.fecha_autorizacion == datetime(2026, 10, 21, 14, 35, 12)
    assert c.clave.numero == "001-010-000004219"


@pytest.mark.parametrize(
    "cambio",
    [
        {"fecha_emision": "20/10/2026"},  # no coincide con la fecha de la clave
        {"ruc_y_razon": "1700000000009 EMPRESA DE PRUEBA S.A."},  # RUC distinto al de la clave
        {"tipo_y_serie": "Comprobante de Retención 001-010-000009999"},  # número distinto
        {"tipo_y_serie": "Comprobante de Retención"},  # sin número
        {"ruc_y_razon": "EMPRESA SIN RUC"},
        {"nro": "uno"},
        {"clave": CLAVE_A[:-1] + "3"},
        {"fecha_autorizacion": "21/10/2026"},
    ],
)
def test_desde_celdas_rechaza_filas_inconsistentes(cambio):
    with pytest.raises(ValueError):
        _fila(**cambio)


def test_lote_vacio_es_valido():
    validar_lote([])
    assert nros_contiguos([])


def test_lote_rechaza_claves_repetidas():
    with pytest.raises(ValueError, match="repetidas"):
        validar_lote([_fila(nro="1"), _fila(nro="2")])


def test_lote_con_tipo_distinto_al_solicitado():
    # Se pidió factura ("01") y llegó una retención ("07").
    with pytest.raises(ValueError, match="tipo distinto"):
        validar_lote([_fila()], codigo_tipo_esperado="01")
    validar_lote([_fila()], codigo_tipo_esperado="07")  # coincide: no falla


def test_lote_con_dos_comprobantes_distintos():
    otra = _fila(
        nro="2",
        ruc_y_razon="1700000000002 OTRA EMPRESA S.A.",
        tipo_y_serie="Comprobante de Retención 001-010-000004220",
        clave=CLAVE_D,
        fecha_autorizacion="22/10/2026 09:00:00",
        fecha_emision="22/10/2026",
    )
    lote = [_fila(), otra]
    validar_lote(lote, codigo_tipo_esperado="07")
    assert nros_contiguos(lote)


def test_nros_con_saltos_no_son_contiguos():
    assert not nros_contiguos([_fila(nro="1"), _fila(nro="3")])
