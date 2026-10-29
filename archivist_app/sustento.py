"""Documento sustento de una retencion: numero de la factura que la origina.

El XML de un Comprobante de Retencion (esquema 2.0.0) trae el documento sustento en
<docsSustento>/<docSustento>/<numDocSustento> (15 digitos, sin guiones) junto con
<codDocSustento> ("01" = factura). El esquema 1.0.0 lo repite dentro de cada <impuesto>.
Aqui se lee con la biblioteca estandar, sin dependencias nuevas.

Funciones puras: no tocan el disco, el navegador ni el portal.
"""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

COD_FACTURA = "01"
MAX_BYTES = 5_000_000
_NUM = re.compile(r"^(\d{3})-?(\d{3})-?(\d{9})$")          # 001001000097687 o 001-001-000097687
_NUM_GUIONES = re.compile(r"^\d{3}-\d{3}-\d{9}$")
_DECLARACION = re.compile(r"^\s*<\?xml[^>]*\?>")


class SustentoError(ValueError):
    """No se pudo determinar el documento sustento. El mensaje no incluye datos del XML."""


@dataclass(frozen=True)
class Sustento:
    codigo: str    # codDocSustento: "01" factura, "04" nota de credito, ...
    numero: str    # con guiones: 001-001-000097687


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _raiz(xml: bytes, desenvolver: bool = True):
    if not isinstance(xml, (bytes, bytearray)):
        raise SustentoError("El contenido del XML debe ser bytes")
    if len(xml) > MAX_BYTES:
        raise SustentoError("El XML es demasiado grande")
    alto = bytes(xml).upper()
    # Un comprobante del SRI no lleva DTD. Se rechaza para no exponerse a entidades maliciosas.
    if b"<!DOCTYPE" in alto or b"<!ENTITY" in alto:
        raise SustentoError("El XML trae una definicion DTD: no se procesa")
    try:
        raiz = ET.fromstring(bytes(xml))
    except ET.ParseError:
        raise SustentoError("El archivo no es un XML valido") from None
    if desenvolver and _local(raiz.tag) == "autorizacion":
        # XML autorizado: el comprobante viaja como texto dentro de <comprobante>
        for el in raiz.iter():
            if _local(el.tag) == "comprobante" and (el.text or "").strip():
                interno = _DECLARACION.sub("", el.text.strip(), count=1)
                return _raiz(interno.encode("utf-8"), desenvolver=False)
    return raiz


def leer_sustentos(xml: bytes) -> list:
    """Pares (codigo, numero) distintos, en el orden del documento."""
    raiz = _raiz(xml)
    vistos, salida = set(), []
    for padre in raiz.iter():
        hojas = {_local(h.tag): (h.text or "").strip() for h in padre if len(h) == 0}
        if "numDocSustento" not in hojas:
            continue
        m = _NUM.match(hojas["numDocSustento"])
        if not m:
            raise SustentoError("numDocSustento con formato inesperado (se esperan 15 digitos)")
        par = (hojas.get("codDocSustento", ""), "-".join(m.groups()))
        if par not in vistos:
            vistos.add(par)
            salida.append(Sustento(*par))
    return salida


def factura_sustento(xml: bytes) -> str:
    """Numero de la factura que origina la retencion, con guiones. Falla cerrado ante cualquier duda."""
    sustentos = leer_sustentos(xml)
    if not sustentos:
        raise SustentoError("El XML de la retencion no trae documento sustento (numDocSustento)")
    if len(sustentos) > 1:
        raise SustentoError(
            f"La retencion tiene {len(sustentos)} documentos sustento distintos: no se puede elegir el nombre")
    s = sustentos[0]
    if s.codigo != COD_FACTURA:
        raise SustentoError(f"El documento sustento no es una factura (codDocSustento={s.codigo[:5] or 'vacio'})")
    return s.numero


def nombre_retencion(factura: str, retencion: str) -> str:
    """<NumeroFactura>_<NumeroRetencion>, ambos con guiones. Sin extension."""
    if not _NUM_GUIONES.match(factura or ""):
        raise SustentoError("Numero de factura con formato inesperado")
    if not _NUM_GUIONES.match(retencion or ""):
        raise SustentoError("Numero de retencion con formato inesperado")
    return f"{factura}_{retencion}"