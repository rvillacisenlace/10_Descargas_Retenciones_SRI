"""Descarga todo o nada, con fetch() dentro de la página (page.evaluate).

Evidencia 2026-10-23 (diag_descarga, fila 0): el postback de lnkXml / lnkPdf responde HTTP 200,
como adjunto, con el archivo, sin pedir un captcha nuevo y con el mismo tamaño que el clic con
expect_download. Solo se probaron 4 peticiones seguidas: que el ViewState siga válido con 2 por
fila y que el portal tolere este ritmo son HIPÓTESIS hasta medirlas (scripts/diag_lote.py).

Contrato (el de Docket): validar el contenido de cada respuesta, descargar a .staging y mover a
destino solo si el lote completo salió bien. Sin reintentos: ante el primer fallo se aborta el
lote y no se guarda nada, para no insistir contra el portal ni dejar un lote parcial.
"""

import base64
import os
import shutil
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from archivist_app.exceptions import IncompleteBatchError
from archivist_app.logger import get_logger
from archivist_app.models import Comprobante
from archivist_app.services.file_organizer import Accion, decidir, planificar

log = get_logger(__name__)

# HIPÓTESIS: 1 s entre peticiones es prudente. No está medido; si se baja, medir antes y
# después (bajar las esperas con un factor 0.6 empeoró todo en Lynx).
PAUSA_S = 1.0
CARPETA_STAGING = ".staging"
_CABECERA = 256

# Reproduce mojarra.jsfcljs: POST del formulario con el ViewState vigente más el parámetro del
# enlace. El archivo vuelve en base64 (por trozos, para no desbordar con archivos grandes).
JS_DESCARGA = r"""async (linkId) => {
    const form = document.getElementById('frmPrincipal');
    const cuerpo = new URLSearchParams(new FormData(form));
    cuerpo.set(linkId, linkId);
    const r = await fetch(form.action, {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: cuerpo.toString(),
    });
    const buf = new Uint8Array(await r.arrayBuffer());
    let bin = '';
    for (let i = 0; i < buf.length; i += 0x8000) {
        bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    }
    return {status: r.status, b64: btoa(bin)};
}"""

def _quitar_staging(staging: Path | None, raiz: Path) -> None:
    """Borra el lote y la carpeta .staging, que es temporal. rmdir solo borra una carpeta VACÍA: si
    hay restos de una corrida interrumpida no se toca nada que no sea de este lote."""
    if staging is not None:
        shutil.rmtree(staging, ignore_errors=True)
    try:
        raiz.rmdir()
    except FileNotFoundError:
        pass
    except OSError:
        log.warning("La carpeta .staging no se pudo eliminar (no está vacía o está en uso); no se toca")

class Solicitable(Protocol):
    """Lo mínimo que se necesita de una fila del listado (la entrega ComprobantesPage)."""

    comprobante: Comprobante
    id_xml: str
    id_pdf: str


@dataclass(frozen=True)
class ResultadoDescarga:
    escritos: int
    omitidos: int  # ya existían con el mismo contenido
    xml_con_clave: int  # XML que contienen la clave de acceso de su fila
    xml_total: int


def validar_contenido(extension: str, datos: bytes) -> None:
    """ValueError si los bytes no son el archivo esperado. Solo mira la cabecera."""
    if not datos:
        raise ValueError("la respuesta está vacía")
    cabecera = datos[:_CABECERA]
    if extension == "pdf":
        if not cabecera.startswith(b"%PDF"):
            raise ValueError("no empieza con %PDF")
    elif extension == "xml":
        bajo = cabecera.lower()
        if b"<html" in bajo or b"<!doctype html" in bajo or b"partial-response" in bajo:
            raise ValueError("es una página HTML o una respuesta AJAX, no un XML (¿sesión cerrada?)")
        if not cabecera.lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"<"):
            raise ValueError("no parece un XML (no empieza con '<')")
    else:
        raise ValueError("extensión no admitida")


class Downloader:
    def __init__(self, page, base: Path, pausa_s: float = PAUSA_S,
                 dormir: Callable[[float], None] = time.sleep):
        self.page, self.base = page, Path(base)
        self.pausa_s, self.dormir = pausa_s, dormir

    def _pedir(self, id_enlace: str) -> bytes:
        r = self.page.evaluate(JS_DESCARGA, id_enlace)
        if r["status"] != 200:
            raise ValueError(f"HTTP {r['status']}")
        return base64.b64decode(r["b64"], validate=True)

    def descargar_lote(self, filas: Sequence[Solicitable]) -> ResultadoDescarga:
        """Baja XML y PDF de todas las filas. Si algo falla: IncompleteBatchError y nada guardado."""
        if not filas:
            return ResultadoDescarga(0, 0, 0, 0)
        try:
            destinos = planificar(self.base, [f.comprobante for f in filas])
        except ValueError as e:
            raise IncompleteBatchError(f"No se pudo planificar el lote: {e}") from e
        ids = {}
        for f in filas:
            ids[(f.comprobante.clave.valor, "xml")] = f.id_xml
            ids[(f.comprobante.clave.valor, "pdf")] = f.id_pdf
        raiz = self.base / CARPETA_STAGING
        try:
            raiz.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix="lote_", dir=raiz))
        except OSError as e:
            _quitar_staging(None, raiz)
            raise IncompleteBatchError(
                f"No se pudo preparar la carpeta temporal ({type(e).__name__})"
            ) from e
        try:
            inicio = time.monotonic()
            pendientes, omitidos, xml_con_clave, xml_total = self._bajar(destinos, ids, staging)
            self._mover(pendientes)
        finally:
            _quitar_staging(staging, raiz)
        log.info(
            "Lote descargado: %d escritos, %d omitidos, %d peticiones en %.1f s; xml_con_clave=%d/%d",
            len(pendientes), omitidos, len(destinos), time.monotonic() - inicio,
            xml_con_clave, xml_total,
        )
        return ResultadoDescarga(len(pendientes), omitidos, xml_con_clave, xml_total)

    def _bajar(self, destinos, ids, staging: Path):
        pendientes: list[tuple[Path, Path]] = []
        omitidos = xml_con_clave = xml_total = 0
        total = len(destinos)
        for n, d in enumerate(destinos, start=1):
            if n > 1:
                self.dormir(self.pausa_s)
            ext = d.extension
            etiqueta = f"petición {n} de {total} ({ext.upper()}, fila {d.comprobante.nro})"
            try:
                datos = self._pedir(ids[(d.comprobante.clave.valor, ext)])
                validar_contenido(ext, datos)
            except ValueError as e:
                raise IncompleteBatchError(f"{etiqueta}: {e}") from e
            except Exception as e:  # fallo de Playwright o de red; el mensaje no lleva datos
                raise IncompleteBatchError(f"{etiqueta}: {type(e).__name__}") from e
            if ext == "xml":
                xml_total += 1
                # HIPÓTESIS sin confirmar: el XML trae la clave de acceso de su fila. Hasta
                # verlo con datos reales solo se advierte; si siempre coincide, pasa a error.
                if d.comprobante.clave.valor.encode("ascii") in datos:
                    xml_con_clave += 1
                else:
                    log.warning("%s: el XML no contiene la clave de acceso de su fila", etiqueta)
            accion = decidir(d.ruta, datos)
            if accion is Accion.CONFLICTO:
                raise IncompleteBatchError(f"{etiqueta}: ya existe un archivo distinto en el destino")
            if accion is Accion.OMITIR:
                omitidos += 1
                continue
            temporal = staging / f"{n:06d}.{ext}"
            temporal.write_bytes(datos)
            pendientes.append((temporal, d.ruta))
        return pendientes, omitidos, xml_con_clave, xml_total

    def _mover(self, pendientes: list[tuple[Path, Path]]) -> None:
        """Mueve el lote ya completo; si falla a mitad, revierte lo movido."""
        movidos: list[Path] = []
        try:
            for origen, destino in pendientes:
                destino.parent.mkdir(parents=True, exist_ok=True)
                os.replace(origen, destino)
                movidos.append(destino)
        except OSError as e:
            for ruta in movidos:
                ruta.unlink(missing_ok=True)
            raise IncompleteBatchError(
                f"No se pudo guardar el lote ({type(e).__name__}); se revirtió lo movido"
            ) from e