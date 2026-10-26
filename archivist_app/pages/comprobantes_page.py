"""SABE cómo interactuar con filtro, listado y paginación.

Selectores y estructura observados el 2026-10-23 con un listado real (27 filas, comprobantes de
retención). El usuario elige el filtro y pulsa Consultar (reCAPTCHA invisible): esta página solo
ESPERA el resultado, lo LEE y lo VALIDA. Una consulta vacía NO es error; si el listado no cumple
lo esperado es PortalError y no se devuelve un lote parcial.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from playwright.sync_api import Page

from archivist_app.config import USER_WAIT_TIMEOUT_S
from archivist_app.exceptions import PortalError
from archivist_app.logger import get_logger
from archivist_app.models import TIPO_PORTAL_A_CODIGO, Comprobante, nros_contiguos, validar_lote

log = get_logger(__name__)

# Existe solo después de una consulta contestada; antes, panelListaComprobantes está vacío
# (observado 2026-10-23). HIPÓTESIS: con una consulta sin resultados el contenedor también
# aparece, con la tabla vacía; falta un HTML real de ese caso.
CONTENEDOR = '[id="frmPrincipal:tablaCompRecibidos"]'
FILAS = '[id="frmPrincipal:tablaCompRecibidos_data"] > tr[data-ri]'
PAGINADOR = '[id="frmPrincipal:tablaCompRecibidos_paginator_bottom"] .ui-paginator-current'

# Textos del portal y de reCAPTCHA, en minúsculas. "aptcha incorrect" cubre "Captcha incorrecta"
# (observado) y "incorrecto" (un detector que buscaba "incorrecto" dio un falso negativo).
TEXTO_RECHAZO = "aptcha incorrect"
TEXTO_SIN_SERVICIO = "could not connect to the recaptcha"  # visto con Firefox de Playwright

_RE_PAGINAS = re.compile(r"\((\d+) of (\d+)\)")
_COLUMNAS = 6  # nro, emisor, tipo y serie, clave, fecha de autorización, fecha de emisión

# El texto de cada celda se normaliza aquí; los ids de descarga se leen del DOM en vez de
# deducirlos del índice de fila (no se sabe cómo se numeran en la página 2).
JS_FILAS = r"""() => [...document.querySelectorAll(
    '[id="frmPrincipal:tablaCompRecibidos_data"] > tr[data-ri]')].map(tr => ({
    celdas: [...tr.children].slice(0, 6).map(td => td.textContent.replace(/\s+/g, ' ').trim()),
    id_xml: (tr.querySelector('[id$=":lnkXml"]') || {}).id || null,
    id_pdf: (tr.querySelector('[id$=":lnkPdf"]') || {}).id || null,
}))"""


@dataclass(frozen=True)
class FiltroConsulta:
    ano: int
    mes: int
    dia: int  # 0 = "Todos"
    tipo_portal: str  # valor del combo "Tipo de comprobante"


@dataclass(frozen=True)
class FilaListado:
    comprobante: Comprobante
    id_xml: str
    id_pdf: str


class ComprobantesPage:
    def __init__(self, page: Page):
        self.page = page

    def esperar_listado(
        self,
        timeout_s: float = USER_WAIT_TIMEOUT_S,
        intervalo_ms: int = 500,
        avisar: Callable[[str], None] | None = None,
    ) -> None:
        """Espera a que el usuario consulte y el portal conteste. Se llama con el panel vacío.

        Un rechazo de captcha se avisa AL INSTANTE (avisar("rechazo_captcha")) y se sigue
        esperando, para que el usuario vuelva a pulsar Consultar sin agotar los 10 minutos.
        Cada intento deja una línea 'consulta resultado=...' en el log: sirve de medición.
        """
        fin = time.monotonic() + timeout_s
        rechazos = 0
        rechazo_visible = sin_servicio_visible = False
        while time.monotonic() < fin:
            if self.page.locator(CONTENEDOR).count() > 0:
                log.info("consulta resultado=ok rechazos_previos=%d", rechazos)
                return
            texto = self.page.inner_text("body").lower()
            rechazo = TEXTO_RECHAZO in texto
            if rechazo and not rechazo_visible:
                rechazos += 1
                log.warning("consulta resultado=rechazo_captcha intento=%d: pulse Consultar de nuevo", rechazos)
                if avisar:
                    avisar("rechazo_captcha")
            rechazo_visible = rechazo
            sin_servicio = TEXTO_SIN_SERVICIO in texto
            if sin_servicio and not sin_servicio_visible:
                log.warning("consulta resultado=sin_token: reCAPTCHA no conectó")
                if avisar:
                    avisar("sin_token")
            sin_servicio_visible = sin_servicio
            self.page.wait_for_timeout(intervalo_ms)
        raise PortalError(f"No apareció el listado en {timeout_s:.0f} s")

    def leer_filtro(self) -> FiltroConsulta:
        """Valores ACTUALES de los combos (propiedad, no el atributo 'selected' del HTML)."""

        def valor(combo: str) -> str:
            return self.page.locator(f'[id="frmPrincipal:{combo}"]').input_value()

        try:
            return FiltroConsulta(
                ano=int(valor("ano")), mes=int(valor("mes")), dia=int(valor("dia")),
                tipo_portal=valor("cmbTipoComprobante"),
            )
        except ValueError:
            raise PortalError("Los combos del filtro devolvieron valores inesperados") from None

    def paginas(self) -> tuple[int, int]:
        """(página actual, total de páginas) según el paginador '(1 of 1)'."""
        if self.page.locator(PAGINADOR).count() == 0:
            if self.page.locator(FILAS).count() == 0:
                return 1, 1  # listado vacío sin paginador (HIPÓTESIS, ver CONTENEDOR)
            raise PortalError("El listado trae filas pero no se encontró el paginador")
        texto = self.page.locator(PAGINADOR).first.inner_text()
        m = _RE_PAGINAS.search(texto)
        if not m:
            raise PortalError("No se pudo leer el paginador del listado")
        return int(m.group(1)), int(m.group(2))

    def _leer_pagina(self) -> list[FilaListado]:
        filas = []
        for i, f in enumerate(self.page.evaluate(JS_FILAS), start=1):
            if len(f["celdas"]) < _COLUMNAS:
                raise PortalError(f"La fila {i} del listado trae menos de {_COLUMNAS} columnas")
            if not f["id_xml"] or not f["id_pdf"]:
                raise PortalError(f"La fila {i} del listado no trae enlace de XML y de PDF")
            try:
                comprobante = Comprobante.desde_celdas(*f["celdas"][:_COLUMNAS])
            except ValueError as e:
                raise PortalError(f"La fila {i} del listado es inválida: {e}") from e
            filas.append(FilaListado(comprobante, f["id_xml"], f["id_pdf"]))
        return filas

    def leer_todas(self) -> list[FilaListado]:
        """Todas las filas del listado, validadas. Lote parcial = PortalError."""
        _, total = self.paginas()
        if total > 1:
            # NO PROBADO: solo se ha visto una página (2026-10-23). No se adivina cómo se
            # pagina ni si lleva captcha; devolver solo la primera sería un lote incompleto.
            raise PortalError(
                f"El listado tiene {total} páginas y la paginación aún no está verificada "
                "contra el portal; no se devuelve un lote parcial"
            )
        tipo = TIPO_PORTAL_A_CODIGO.get(self.leer_filtro().tipo_portal)
        if tipo is None:
            raise PortalError("El tipo de comprobante del filtro no está reconocido")
        filas = self._leer_pagina()
        comprobantes = [f.comprobante for f in filas]
        try:
            validar_lote(comprobantes, tipo)
        except ValueError as e:
            raise PortalError(f"El listado no es consistente: {e}") from e
        if not nros_contiguos(comprobantes):
            raise PortalError("La numeración (Nro) del listado no es contigua: faltan filas")
        log.info("Listado leído: %d filas", len(filas))
        return filas