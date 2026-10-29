from pathlib import Path

import pytest

from archivist_app.models import Comprobante, digito_verificador
from archivist_app.services.file_organizer import (
    Accion,
    carpeta_destino,
    comprobar_rutas,
    decidir,
    nombre_archivo,
    planificar,
    ruta_destino,
)

# Claves SINTÉTICAS con el dígito verificador escrito a mano (ver tests/test_models.py).
CLAVE_RETENCION = "2110202607170000000000120010100000042191234567812"  # 21/10/2026, tipo 07
CLAVE_FACTURA = "0501202601179000000000120020030000000158765432115"  # 05/01/2026, tipo 01
CLAVE_TIPO_DESCONOCIDO = "2110202699170000000000120010100000000011234567816"  # tipo 99
FACTURA_SUSTENTO = "001-001-000097687"  # factura de la que sale la retención (viene de su XML)


def _retencion(**cambios):
    celdas = dict(
        nro="1",
        ruc_y_razon="1700000000001 EMPRESA DE PRUEBA S.A.",
        tipo_y_serie="Comprobante de Retención 001-010-000004219",
        clave=CLAVE_RETENCION,
        fecha_autorizacion="21/10/2026 14:35:12",
        fecha_emision="21/10/2026",
    )
    celdas.update(cambios)
    return Comprobante.desde_celdas(**celdas)


def _factura():
    return Comprobante.desde_celdas(
        nro="2",
        ruc_y_razon="1790000000001 OTRA EMPRESA S.A.",
        tipo_y_serie="Factura 002-003-000000015",
        clave=CLAVE_FACTURA,
        fecha_autorizacion="05/01/2026 10:00:00",
        fecha_emision="05/01/2026",
    )


def test_el_nombre_es_el_numero_y_el_ruc_del_emisor_con_la_extension():
    c = _factura()  # número 002-003-000000015, emisor 1790000000001
    assert nombre_archivo(c, "pdf") == "002-003-000000015_1790000000001.pdf"
    assert nombre_archivo(c, ".XML") == "002-003-000000015_1790000000001.xml"


# --- retenciones: <factura>_<retención>, con la factura leída del XML ------------------------

def test_la_retencion_se_nombra_con_la_factura_y_el_numero_de_la_retencion():
    c = _retencion()  # número de la retención 001-010-000004219
    assert nombre_archivo(c, "pdf", FACTURA_SUSTENTO) == "001-001-000097687_001-010-000004219.pdf"
    assert nombre_archivo(c, ".XML", FACTURA_SUSTENTO) == "001-001-000097687_001-010-000004219.xml"


def test_la_retencion_sin_factura_no_se_nombra_nunca_con_el_nombre_antiguo():
    with pytest.raises(ValueError, match="Falta el número de la factura"):
        nombre_archivo(_retencion(), "pdf")
    with pytest.raises(ValueError, match="Falta el número de la factura"):
        nombre_archivo(_retencion(), "pdf", "")


@pytest.mark.parametrize("factura", ["001001000097687", "1-1-97687", "001-001-00009768X"])
def test_la_retencion_con_la_factura_en_formato_dudoso_se_rechaza(factura):
    with pytest.raises(ValueError, match="formato inesperado"):
        nombre_archivo(_retencion(), "pdf", factura)


def test_los_demas_tipos_ignoran_la_factura():
    assert nombre_archivo(_factura(), "pdf", FACTURA_SUSTENTO) == "002-003-000000015_1790000000001.pdf"


@pytest.mark.parametrize("ext", ["exe", "", "pdf.exe", "../pdf"])
def test_extensiones_no_admitidas(ext):
    with pytest.raises(ValueError, match="Extensión"):
        nombre_archivo(_retencion(), ext)


def test_carpeta_por_fecha_de_emision_y_tipo():
    base = Path("salida")
    assert carpeta_destino(base, _retencion()) == base / "2026" / "10" / "21" / "Retenciones"
    assert carpeta_destino(base, _factura()) == base / "2026" / "01" / "05" / "Facturas"


def test_tipo_desconocido_usa_una_carpeta_con_su_codigo():
    c = _retencion(
        tipo_y_serie="Otro 001-010-000000001",
        clave=CLAVE_TIPO_DESCONOCIDO,
    )
    assert carpeta_destino(Path("salida"), c).name == "Tipo 99"


def test_ruta_completa():
    base = Path("salida")
    esperada = base / "2026" / "10" / "21" / "Retenciones" / "001-001-000097687_001-010-000004219.pdf"
    assert ruta_destino(base, _retencion(), "pdf", FACTURA_SUSTENTO) == esperada


def test_ruta_demasiado_larga_se_rechaza_sin_mostrar_la_ruta():
    base = Path("salida") / ("x" * 220)
    with pytest.raises(ValueError, match="caracteres") as e:
        ruta_destino(base, _retencion(), "pdf", FACTURA_SUSTENTO)
    assert "xxxx" not in str(e.value)


def test_planificar_da_un_destino_por_comprobante_y_extension():
    destinos = planificar(
        Path("salida"), [_retencion(), _factura()], facturas={CLAVE_RETENCION: FACTURA_SUSTENTO}
    )
    assert [(d.comprobante.nro, d.extension) for d in destinos] == [
        (1, "pdf"), (1, "xml"), (2, "pdf"), (2, "xml"),
    ]
    assert len({d.ruta for d in destinos}) == 4


def test_planificar_solo_las_extensiones_pedidas():
    destinos = planificar(
        Path("salida"), [_retencion()], extensiones=("xml",), facturas={CLAVE_RETENCION: FACTURA_SUSTENTO}
    )
    assert [d.extension for d in destinos] == ["xml"]


def test_planificar_rechaza_dos_comprobantes_con_la_misma_ruta():
    with pytest.raises(ValueError, match="misma ruta"):
        planificar(
            Path("salida"), [_retencion(nro="1"), _retencion(nro="2")],
            facturas={CLAVE_RETENCION: FACTURA_SUSTENTO},
        )


def test_decidir_escribe_si_no_existe(tmp_path):
    assert decidir(tmp_path / "a.pdf", b"contenido") == Accion.ESCRIBIR


def test_decidir_omite_si_ya_existe_igual(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"contenido")
    assert decidir(tmp_path / "a.pdf", b"contenido") == Accion.OMITIR


def test_decidir_marca_conflicto_si_existe_distinto(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"otro contenido")
    assert decidir(tmp_path / "a.pdf", b"contenido") == Accion.CONFLICTO


def test_decidir_marca_conflicto_si_el_destino_es_una_carpeta(tmp_path):
    (tmp_path / "a.pdf").mkdir()
    assert decidir(tmp_path / "a.pdf", b"contenido") == Accion.CONFLICTO


# --- el nombre lleva el número del documento, pero el número solo no es único ---------------

def _con_numero(ruc, estab, pto, sec, codigo="12345678", tipo="01"):
    """Comprobante del 21/10/2026 con una clave válida armada aquí (dígito verificador calculado).
    Por defecto una FACTURA (tipo 01): el RUC en el nombre es la regla de todo menos las retenciones."""
    base = f"21102026{tipo}{ruc}1{estab}{pto}{sec:09d}{codigo}1"
    etiqueta = "Comprobante de Retención" if tipo == "07" else "Factura"
    return Comprobante.desde_celdas(
        nro="1",
        ruc_y_razon=f"{ruc} EMISOR {ruc[-3:]} S.A.",
        tipo_y_serie=f"{etiqueta} {estab}-{pto}-{sec:09d}",
        clave=base + str(digito_verificador(base)),
        fecha_autorizacion="21/10/2026 10:00:00",
        fecha_emision="21/10/2026",
    )


def test_el_nombre_empieza_con_el_numero_del_documento():
    c = _con_numero("1790000000001", "001", "001", 6089)
    assert nombre_archivo(c, "pdf").startswith("001-001-000006089")
    assert nombre_archivo(c, "pdf") == "001-001-000006089_1790000000001.pdf"


def test_mismo_numero_de_dos_emisores_no_colisiona():
    a = _con_numero("1790000000001", "001", "001", 6089)
    b = _con_numero("1791111111001", "001", "001", 6089)
    assert a.clave.numero == b.clave.numero and a.clave.valor != b.clave.valor  # la premisa
    destinos = planificar(Path("salida"), [a, b])
    assert len({d.ruta for d in destinos}) == 4


def test_el_nombre_no_depende_de_los_demas_comprobantes_del_lote():
    a = _con_numero("1790000000001", "001", "001", 6089)
    b = _con_numero("1791111111001", "001", "001", 6089)
    solo = {d.extension: d.ruta for d in planificar(Path("s"), [a])}
    con_otro = {d.extension: d.ruta for d in planificar(Path("s"), [b, a]) if d.comprobante is a}
    assert solo == con_otro  # mismo nombre en cualquier corrida: no se duplican archivos


def test_mismo_emisor_numero_y_dia_sigue_siendo_la_misma_ruta():
    # No puede ocurrir en el SRI (el secuencial es único por emisor y tipo); si ocurre, se detecta.
    a = _con_numero("1790000000001", "001", "001", 6089, codigo="11111111")
    b = _con_numero("1790000000001", "001", "001", 6089, codigo="22222222")
    with pytest.raises(ValueError, match="misma ruta"):
        planificar(Path("salida"), [a, b])


# --- retenciones: el RUC ya no va en el nombre; lo distingue la factura ------------------------

def test_retenciones_con_el_mismo_numero_y_facturas_distintas_no_colisionan():
    a = _con_numero("1790000000001", "001", "001", 6089, tipo="07")
    b = _con_numero("1791111111001", "001", "001", 6089, tipo="07")
    assert a.clave.numero == b.clave.numero and a.clave.valor != b.clave.valor  # la premisa
    facturas = {a.clave.valor: "001-001-000097687", b.clave.valor: "001-001-000097688"}
    destinos = planificar(Path("salida"), [a, b], facturas=facturas)
    assert len({d.ruta for d in destinos}) == 4


def test_retenciones_con_el_mismo_numero_y_la_misma_factura_chocan():
    a = _con_numero("1790000000001", "001", "001", 6089, tipo="07")
    b = _con_numero("1791111111001", "001", "001", 6089, tipo="07")
    facturas = {a.clave.valor: FACTURA_SUSTENTO, b.clave.valor: FACTURA_SUSTENTO}
    with pytest.raises(ValueError, match="misma ruta"):
        planificar(Path("salida"), [a, b], facturas=facturas)


def test_planificar_una_retencion_sin_su_factura_falla():
    with pytest.raises(ValueError, match="Falta el número de la factura"):
        planificar(Path("salida"), [_retencion()])


def test_comprobar_rutas_detecta_la_ruta_larga_sin_conocer_el_xml():
    with pytest.raises(ValueError, match="caracteres"):
        comprobar_rutas(Path("salida") / ("x" * 220), [_retencion()])


def test_comprobar_rutas_no_compara_retenciones_entre_si():
    # Dos retenciones con el mismo número solo se distinguen por su factura, que aún no se conoce.
    comprobar_rutas(Path("salida"), [_retencion(nro="1"), _retencion(nro="2")])