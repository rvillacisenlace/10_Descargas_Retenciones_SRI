import pytest

from archivist_app.sustento import (
    SustentoError, factura_sustento, leer_sustentos, nombre_retencion,
)

XML_V2 = b"""<?xml version="1.0" encoding="UTF-8"?>
<comprobanteRetencion id="comprobante" version="2.0.0">
<infoTributaria><razonSocial>EMISOR DE PRUEBA</razonSocial></infoTributaria>
<docsSustento><docSustento>
<codSustento>01</codSustento>
<codDocSustento>01</codDocSustento>
<numDocSustento>001001000097687</numDocSustento>
<fechaEmisionDocSustento>20/10/2026</fechaEmisionDocSustento>
</docSustento></docsSustento>
</comprobanteRetencion>"""


def _v2(*pares):
    cuerpo = "".join(
        f"<docSustento><codDocSustento>{c}</codDocSustento><numDocSustento>{n}</numDocSustento></docSustento>"
        for c, n in pares)
    return f'<comprobanteRetencion version="2.0.0"><docsSustento>{cuerpo}</docsSustento></comprobanteRetencion>'.encode()


def test_factura_del_xml_real_de_retencion():
    assert factura_sustento(XML_V2) == "001-001-000097687"


def test_esquema_1_repite_el_sustento_en_cada_impuesto():
    xml = (b'<comprobanteRetencion version="1.0.0"><impuestos>'
           b"<impuesto><codigo>1</codigo><codDocSustento>01</codDocSustento><numDocSustento>001001000097687</numDocSustento></impuesto>"
           b"<impuesto><codigo>2</codigo><codDocSustento>01</codDocSustento><numDocSustento>001001000097687</numDocSustento></impuesto>"
           b"</impuestos></comprobanteRetencion>")
    assert [s.numero for s in leer_sustentos(xml)] == ["001-001-000097687"]
    assert factura_sustento(xml) == "001-001-000097687"


def test_xml_autorizado_con_el_comprobante_en_cdata():
    interno = XML_V2.decode().replace("\n", "")
    envuelto = ('<autorizacion><estado>AUTORIZADO</estado><comprobante><![CDATA[' + interno +
                ']]></comprobante></autorizacion>').encode()
    assert factura_sustento(envuelto) == "001-001-000097687"


def test_acepta_el_numero_ya_con_guiones():
    assert factura_sustento(_v2(("01", "001-001-000097687"))) == "001-001-000097687"


def test_sustento_que_no_es_factura_falla():
    with pytest.raises(SustentoError, match="no es una factura"):
        factura_sustento(_v2(("04", "001001000000012")))


def test_codigo_ausente_falla():
    xml = (b"<c><docSustento><numDocSustento>001001000097687</numDocSustento></docSustento></c>")
    with pytest.raises(SustentoError, match="no es una factura"):
        factura_sustento(xml)


def test_varios_sustentos_distintos_fallan():
    with pytest.raises(SustentoError, match="2 documentos sustento"):
        factura_sustento(_v2(("01", "001001000097687"), ("01", "001001000097688")))


def test_varios_sustentos_identicos_cuentan_como_uno():
    assert factura_sustento(_v2(("01", "001001000097687"), ("01", "001001000097687"))) == "001-001-000097687"


def test_sin_sustento_falla():
    with pytest.raises(SustentoError, match="no trae documento sustento"):
        factura_sustento(b"<comprobanteRetencion><infoTributaria/></comprobanteRetencion>")


@pytest.mark.parametrize("num", ["00100100009768", "0010010000976870", "001001ABC0097687", ""])
def test_numero_con_formato_inesperado_falla(num):
    with pytest.raises(SustentoError, match="formato inesperado"):
        factura_sustento(_v2(("01", num)))


def test_rechaza_dtd_y_entidades():
    malo = (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><comprobanteRetencion>'
            b"&a;</comprobanteRetencion>")
    with pytest.raises(SustentoError, match="DTD"):
        factura_sustento(malo)


@pytest.mark.parametrize("contenido", [b"<html><body>login</body></html", b"", b"no es xml"])
def test_contenido_que_no_es_xml_falla(contenido):
    with pytest.raises(SustentoError):
        factura_sustento(contenido)


def test_rechaza_tipos_distintos_de_bytes_y_tamanos_excesivos():
    with pytest.raises(SustentoError):
        factura_sustento("<a/>")
    with pytest.raises(SustentoError, match="demasiado grande"):
        factura_sustento(b"<a>" + b"x" * 5_000_001 + b"</a>")


def test_el_mensaje_de_error_no_incluye_datos_del_xml():
    with pytest.raises(SustentoError) as e:
        factura_sustento(_v2(("04", "001001000000012")))
    assert "000000012" not in str(e.value)


def test_nombre_retencion():
    assert nombre_retencion("001-001-000097687", "001-001-000006089") == "001-001-000097687_001-001-000006089"


@pytest.mark.parametrize("fac,ret", [("001001000097687", "001-001-000006089"),
                                     ("001-001-000097687", "1-1-6089"), ("", "001-001-000006089")])
def test_nombre_retencion_rechaza_formatos_dudosos(fac, ret):
    with pytest.raises(SustentoError):
        nombre_retencion(fac, ret)


_CUERPO = (
    '<comprobanteRetencion id="comprobante" version="2.0.0"><infoTributaria>'
    "<razonSocial>EMPRESA \u00d1ANDU S.A.</razonSocial></infoTributaria><docsSustento><docSustento>"
    "<codDocSustento>01</codDocSustento><numDocSustento>001001000097687</numDocSustento>"
    "</docSustento></docsSustento></comprobanteRetencion>"
)


@pytest.mark.parametrize("xml", [
    b"\xef\xbb\xbf" + ('<?xml version="1.0" encoding="UTF-8"?>' + _CUERPO).encode("utf-8"),
    ('<?xml version="1.0" encoding="ISO-8859-1"?>' + _CUERPO).encode("latin-1"),
    ('<autorizacion><comprobante><![CDATA[<?xml version="1.0" encoding="ISO-8859-1"?>' + _CUERPO
     + "]]></comprobante></autorizacion>").encode("utf-8"),
    ("<autorizacion><comprobante>" + _CUERPO.replace("<", "&lt;").replace(">", "&gt;")
     + "</comprobante></autorizacion>").encode("utf-8"),
], ids=["bom-utf8", "iso-8859-1", "cdata-con-declaracion", "texto-escapado"])
def test_codificaciones_y_envoltorios_reales(xml):
    assert factura_sustento(xml) == "001-001-000097687"