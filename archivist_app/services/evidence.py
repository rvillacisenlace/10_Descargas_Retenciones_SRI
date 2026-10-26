"""Capturas de evidencia con banner rojo (usuario, rango, fecha y hora), al estilo de Docket.

Formato de referencia (capturas de Docket, 2026-10-26): franja blanca con texto rojo arriba a la
izquierda, SUPERPUESTA a la página:
  Evidencia: <nombre> | Usuario: <usuario> | Consulta <desde> a <hasta> | Página <n> | <lado> | <fecha hora>
y carpeta por corrida: <salida>\\Evidencias\\AAAA-MM-DD_HHMMSS\\pagina-01.png.
Si la tabla es más ancha que su contenedor se toman dos capturas (Izquierda y Derecha, esta con
sufijo -derecha); si cabe, una sola y sin campo de lado.

DIFERENCIA con Docket (decisión): sus capturas son del área visible (1280x720); aquí el listado
es una página larga con hasta 50 filas, así que se captura la PÁGINA COMPLETA.
HIPÓTESIS sin confirmar (falta una corrida real; ver scripts/diag_evidencia.py): que la tabla del
SRI desborde horizontalmente dentro de un contenedor, y cómo se ve la captura con Edge por CDP.
La evidencia es la prueba de la CONSULTA: se guarda antes de descargar y se conserva si falla.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from archivist_app.exceptions import EvidenceError
from archivist_app.logger import get_logger

log = get_logger(__name__)

CARPETA = "Evidencias"  # ya prevista en .gitignore
PREFIJO = "archivist"  # Docket usa "docket_pagina-01"
_PNG = b"\x89PNG\r\n\x1a\n"

# Estilo que Playwright aplica SOLO mientras dura la captura y retira solo (también si falla).
# Evidencia 2026-10-26 (primera captura real): el badge de reCAPTCHA es position:fixed y en una
# captura de página completa cae a media página, tapando datos del listado (fecha de autorización
# y clave de acceso de las primeras filas). Se oculta con visibility, sin quitarlo del DOM, así que
# reCAPTCHA no se entera.
ESTILO_CAPTURA = ".grecaptcha-badge { visibility: hidden !important; }"

# Superpuesto (fixed) arriba a la izquierda, como en Docket: no mueve el contenido de la página.
JS_PONER_BANNER = r"""(texto) => {
    const b = document.createElement('div');
    b.id = 'archivist-banner';
    b.textContent = texto;
    b.style.cssText = 'position:fixed;top:0;left:0;z-index:2147483647;background:#fff;' +
        'color:#c8102e;font:17px Arial,sans-serif;padding:2px 8px;white-space:nowrap;';
    document.body.appendChild(b);
}"""
JS_QUITAR_BANNER = """() => {
    const b = document.getElementById('archivist-banner');
    if (b) b.remove();
}"""

# Busca, desde la tabla hacia arriba, un contenedor más ancho que su área visible y lo marca. El
# desborde de la PÁGINA entera no cuenta: la captura de página completa ya lo incluye.
JS_BUSCAR_SCROLL = r"""() => {
    let el = document.querySelector('[id="frmPrincipal:tablaCompRecibidos"]');
    while (el && el !== document.body && el !== document.documentElement) {
        const sobra = el.scrollWidth - el.clientWidth;
        if (/(auto|scroll|hidden)/.test(getComputedStyle(el).overflowX) && sobra > 20) {
            el.setAttribute('data-archivist-scroll', '1');
            return {ancho: el.scrollWidth, visible: el.clientWidth};
        }
        el = el.parentElement;
    }
    return null;
}"""
JS_SCROLL_X = """(x) => {
    const el = document.querySelector('[data-archivist-scroll="1"]');
    if (el) el.scrollLeft = x;
}"""
JS_LIMPIAR_SCROLL = """() => {
    const el = document.querySelector('[data-archivist-scroll="1"]');
    if (el) { el.scrollLeft = 0; el.removeAttribute('data-archivist-scroll'); }
}"""


@dataclass(frozen=True)
class Captura:
    nombre: str  # pagina-01.png / pagina-01-derecha.png
    datos: bytes  # PNG


def texto_banner(evidencia: str, usuario: str, desde: str, hasta: str, pagina: int,
                 lado: str | None, ahora: datetime) -> str:
    partes = [f"Evidencia: {evidencia}", f"Usuario: {usuario}", f"Consulta {desde} a {hasta}",
              f"Página {pagina}"]
    if lado:
        partes.append(lado)
    partes.append(f"{ahora:%Y-%m-%d %H:%M:%S}")
    return " | ".join(partes)


def _intentar(page, js: str, que: str) -> None:
    try:
        page.evaluate(js)
    except Exception as e:  # no debe tapar el error original ni perder una captura buena
        log.warning("No se pudo restaurar %s (%s)", que, type(e).__name__)


def _una(page, usuario: str, desde: str, hasta: str, pagina: int, ahora: datetime,
         lado: str | None, sufijo: str) -> Captura:
    base = f"pagina-{pagina:02d}{sufijo}"
    texto = texto_banner(f"{PREFIJO}_{base}", usuario, desde, hasta, pagina, lado, ahora)
    try:
        page.evaluate(JS_PONER_BANNER, texto)
        try:
            datos = page.screenshot(full_page=True, type="png", style=ESTILO_CAPTURA)
        finally:
            _intentar(page, JS_QUITAR_BANNER, "la página (banner)")
    except Exception as e:
        raise EvidenceError(f"No se pudo capturar la evidencia del listado ({type(e).__name__})") from e
    if not datos.startswith(_PNG):
        raise EvidenceError("La captura de evidencia no es una imagen PNG válida")
    return Captura(f"{base}.png", datos)


def capturar(page, usuario: str, desde: str, hasta: str, pagina: int = 1,
             ahora: datetime | None = None) -> list[Captura]:
    """Una captura si la tabla cabe; dos (izquierda y derecha) si desborda su contenedor."""
    ahora = ahora or datetime.now()  # la misma hora en las dos mitades, como en Docket
    try:
        scroll = page.evaluate(JS_BUSCAR_SCROLL)
    except Exception as e:
        raise EvidenceError(f"No se pudo preparar la captura del listado ({type(e).__name__})") from e
    if scroll is None:
        return [_una(page, usuario, desde, hasta, pagina, ahora, None, "")]
    try:
        page.evaluate(JS_SCROLL_X, 0)
        izquierda = _una(page, usuario, desde, hasta, pagina, ahora, "Izquierda", "")
        page.evaluate(JS_SCROLL_X, scroll["ancho"])  # el navegador lo limita al máximo
        derecha = _una(page, usuario, desde, hasta, pagina, ahora, "Derecha", "-derecha")
        return [izquierda, derecha]
    except EvidenceError:
        raise
    except Exception as e:
        raise EvidenceError(f"No se pudo capturar la evidencia del listado ({type(e).__name__})") from e
    finally:
        _intentar(page, JS_LIMPIAR_SCROLL, "la tabla (desplazamiento)")


def guardar(base: Path, capturas: Sequence[Captura], inicio: datetime) -> list[Path]:
    """Guarda en <base>/Evidencias/<AAAA-MM-DD_HHMMSS>/ (una carpeta por corrida). No pisa nada."""
    carpeta = Path(base) / CARPETA / f"{inicio:%Y-%m-%d_%H%M%S}"
    rutas: list[Path] = []
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        for c in capturas:
            ruta = carpeta / c.nombre
            with open(ruta, "xb") as f:  # 'x': falla si ya existe
                f.write(c.datos)
            rutas.append(ruta)
    except OSError as e:
        raise EvidenceError(f"No se pudo guardar la evidencia ({type(e).__name__})") from e
    return rutas