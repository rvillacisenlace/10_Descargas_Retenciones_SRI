"""Ruta y nombre de cada archivo descargado. Lógica pura: no toca el portal ni el navegador.

Reglas:
- El archivo se llama <número>_<RUC del emisor>.<ext> (ej. 001-001-000006089_1790000000001.pdf).
- El número solo NO es único entre emisores y no hay subcarpeta por emisor; con el RUC el nombre es
  único y determinista. La clave de acceso sigue dentro del XML (validada en models.py).
- EXCEPCIÓN, Comprobante de retención (tipo 07): <número de la factura>_<número de la retención>.<ext>
  (ej. 001-001-000097687_001-001-000006089.pdf). El número de la factura NO aparece en el portal: sale
  del XML (numDocSustento, ver sustento.py), así que el nombre solo se conoce después de bajarlo.
- La carpeta es <salida>/AAAA/MM/DD/<Tipo>/ según la fecha de emisión, sin subcarpeta por emisor.
- Si el archivo ya existe con el mismo contenido no se duplica; si existe con otro, es un conflicto.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from archivist_app.models import Comprobante
from archivist_app.sustento import nombre_retencion

EXTENSIONES = ("pdf", "xml")
CODIGO_RETENCION = "07"
# Mismo largo que cualquier factura real: sirve para validar la longitud de la ruta antes de bajar el XML.
FACTURA_PROVISIONAL = "000-000-000000000"

# Nombres de carpeta SIN tildes, para que sirvan en cualquier herramienta de copia o sincronización.
CARPETA_POR_TIPO = {
    "01": "Facturas",
    "03": "Liquidaciones de compra",
    "04": "Notas de credito",
    "05": "Notas de debito",
    "06": "Guias de remision",
    "07": "Retenciones",
}

# Windows limita las rutas a 260 caracteres si no se activan las rutas largas (conocimiento
# general de Windows; no se ha comprobado en el equipo de producción). Se deja margen.
MAX_RUTA = 250


class Accion(Enum):
    ESCRIBIR = "escribir"
    OMITIR = "omitir"  # ya existe con el mismo contenido
    CONFLICTO = "conflicto"  # ya existe con contenido distinto


@dataclass(frozen=True)
class Destino:
    comprobante: Comprobante
    extension: str
    ruta: Path


def carpeta_tipo(codigo_tipo: str) -> str:
    return CARPETA_POR_TIPO.get(codigo_tipo, f"Tipo {codigo_tipo}")


def es_retencion(comprobante: Comprobante) -> bool:
    return comprobante.clave.codigo_tipo == CODIGO_RETENCION


def nombre_archivo(comprobante: Comprobante, extension: str, factura: str | None = None) -> str:
    ext = (extension or "").lower().lstrip(".")
    if ext not in EXTENSIONES:
        raise ValueError(f"Extensión no admitida (se admite: {', '.join(EXTENSIONES)})")
    if es_retencion(comprobante):
        # Sin la factura sustento no se nombra: así una retención nunca se guarda con el nombre antiguo.
        if not factura:
            raise ValueError("Falta el número de la factura sustento de la retención")
        return f"{nombre_retencion(factura, comprobante.clave.numero)}.{ext}"
    # El RUC va como sufijo: dos emisores pueden usar el mismo número el mismo día y tipo, y esas
    # rutas chocarían (el lote entero se abortaría). Determinista: no depende de otros archivos.
    return f"{comprobante.clave.numero}_{comprobante.ruc_emisor}.{ext}"


def carpeta_destino(base: Path, comprobante: Comprobante) -> Path:
    f = comprobante.fecha_emision
    return (
        Path(base)
        / f"{f.year:04d}"
        / f"{f.month:02d}"
        / f"{f.day:02d}"
        / carpeta_tipo(comprobante.clave.codigo_tipo)
    )


def ruta_destino(
    base: Path, comprobante: Comprobante, extension: str, factura: str | None = None
) -> Path:
    ruta = carpeta_destino(base, comprobante) / nombre_archivo(comprobante, extension, factura)
    if len(str(ruta)) > MAX_RUTA:
        raise ValueError(
            f"La ruta de destino mide {len(str(ruta))} caracteres (máximo {MAX_RUTA}): "
            "use una carpeta de salida más corta"
        )
    return ruta


def planificar(
    base: Path,
    comprobantes: list[Comprobante],
    extensiones: tuple[str, ...] = EXTENSIONES,
    facturas: Mapping[str, str] | None = None,
) -> list[Destino]:
    """Un destino por comprobante y extensión. Falla si dos producen la misma ruta.

    facturas: clave de acceso de cada retención -> número de su factura sustento (con guiones).
    """
    facturas = facturas or {}
    destinos = [
        Destino(c, e, ruta_destino(base, c, e, facturas.get(c.clave.valor)))
        for c in comprobantes
        for e in extensiones
    ]
    rutas = [d.ruta for d in destinos]
    if len(set(rutas)) != len(rutas):
        raise ValueError("Dos comprobantes producen la misma ruta de destino")
    return destinos


def comprobar_rutas(
    base: Path, comprobantes: list[Comprobante], extensiones: tuple[str, ...] = EXTENSIONES
) -> None:
    """Valida, SIN conocer los XML, lo que ya se puede: la longitud de cada ruta. Solo la longitud: las
    retenciones aún no tienen su nombre definitivo, así que no se comprueban rutas repetidas aquí."""
    for c in comprobantes:
        for e in extensiones:
            ruta_destino(base, c, e, FACTURA_PROVISIONAL if es_retencion(c) else None)


def decidir(destino: Path, contenido: bytes) -> Accion:
    """Qué hacer con un archivo a punto de guardarse. No escribe nada."""
    destino = Path(destino)
    if not destino.exists():
        return Accion.ESCRIBIR
    if not destino.is_file():
        return Accion.CONFLICTO
    return Accion.OMITIR if destino.read_bytes() == contenido else Accion.CONFLICTO