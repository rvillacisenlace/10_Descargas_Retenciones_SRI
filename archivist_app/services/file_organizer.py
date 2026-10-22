"""Ruta y nombre de cada archivo descargado. Lógica pura: no toca el portal ni el navegador.

Reglas:
- El archivo se llama como su clave de acceso (única y validada en models.py).
- La carpeta es <salida>/AAAA/MM/DD/<Tipo>/ según la fecha de emisión, sin subcarpeta por emisor.
- Si el archivo ya existe con el mismo contenido no se duplica; si existe con otro, es un conflicto.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from archivist_app.models import Comprobante

EXTENSIONES = ("pdf", "xml")

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


def nombre_archivo(comprobante: Comprobante, extension: str) -> str:
    ext = (extension or "").lower().lstrip(".")
    if ext not in EXTENSIONES:
        raise ValueError(f"Extensión no admitida (se admite: {', '.join(EXTENSIONES)})")
    return f"{comprobante.clave.valor}.{ext}"


def carpeta_destino(base: Path, comprobante: Comprobante) -> Path:
    f = comprobante.fecha_emision
    return (
        Path(base)
        / f"{f.year:04d}"
        / f"{f.month:02d}"
        / f"{f.day:02d}"
        / carpeta_tipo(comprobante.clave.codigo_tipo)
    )


def ruta_destino(base: Path, comprobante: Comprobante, extension: str) -> Path:
    ruta = carpeta_destino(base, comprobante) / nombre_archivo(comprobante, extension)
    if len(str(ruta)) > MAX_RUTA:
        raise ValueError(
            f"La ruta de destino mide {len(str(ruta))} caracteres (máximo {MAX_RUTA}): "
            "use una carpeta de salida más corta"
        )
    return ruta


def planificar(
    base: Path, comprobantes: list[Comprobante], extensiones: tuple[str, ...] = EXTENSIONES
) -> list[Destino]:
    """Un destino por comprobante y extensión. Falla si dos producen la misma ruta."""
    destinos = [
        Destino(c, e, ruta_destino(base, c, e)) for c in comprobantes for e in extensiones
    ]
    rutas = [d.ruta for d in destinos]
    if len(set(rutas)) != len(rutas):
        raise ValueError("Dos comprobantes producen la misma ruta de destino")
    return destinos


def decidir(destino: Path, contenido: bytes) -> Accion:
    """Qué hacer con un archivo a punto de guardarse. No escribe nada."""
    destino = Path(destino)
    if not destino.exists():
        return Accion.ESCRIBIR
    if not destino.is_file():
        return Accion.CONFLICTO
    return Accion.OMITIR if destino.read_bytes() == contenido else Accion.CONFLICTO
