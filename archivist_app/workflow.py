"""Orquesta el orden de los pasos y devuelve RunResult.

Orden: config -> navegador -> login -> filtro + aviso -> espera del usuario (máx. 10 min)
-> recorrer páginas + evidencias -> descarga todo o nada -> notificar resumen.
No sabe cómo se interactúa con el portal (eso es de pages/).

Pendiente: evidencias (capturas con banner). La paginación falla cerrado (PortalError) hasta
verificarla contra el portal; ver ComprobantesPage.leer_todas.
"""

import calendar
from dataclasses import dataclass

from archivist_app.browser import open_context
from archivist_app.config import APP_NAME, load_settings
from archivist_app.logger import get_logger
from archivist_app.models import TIPO_PORTAL_A_CODIGO, TIPOS
from archivist_app.pages.comprobantes_page import ComprobantesPage, FiltroConsulta
from archivist_app.pages.login_page import LoginPage
from archivist_app.services.downloader import Downloader
from archivist_app.services.notifier import notificar

log = get_logger(__name__)

# Texto idéntico al del proyecto hermano (Docket). Ya no menciona el límite de 10 minutos.
AVISO_INICIAL = "Elige el tipo de comprobante y el rango de fechas, y pulsa Consultar en el portal."

# Qué se le dice al usuario ante cada situación que detecta ComprobantesPage.
_AVISOS_CAPTCHA = {
    "rechazo_captcha": "El portal rechazó la consulta (captcha). Espere unos segundos y "
                       "pulse Consultar de nuevo.",
    "sin_token": "reCAPTCHA no pudo conectarse. Revise la conexión y pulse Consultar de nuevo.",
}


@dataclass(frozen=True)
class RunResult:
    comprobantes: int  # filas del listado
    escritos: int  # archivos nuevos (XML y PDF)
    omitidos: int  # archivos que ya existían con el mismo contenido
    xml_con_clave: int
    xml_total: int
    tipo: str  # nombre del tipo de comprobante consultado
    desde: str  # AAAA-MM-DD
    hasta: str  # AAAA-MM-DD
    # Todo o nada: un fallo aborta el lote, así que en un resumen de éxito siempre es 0.
    fallidos: int = 0


def _rango(filtro: FiltroConsulta) -> tuple[str, str]:
    """El portal filtra por año, mes y día (0 = 'Todos'): con 'Todos' el rango es el mes completo."""
    if filtro.dia:
        dia = f"{filtro.ano:04d}-{filtro.mes:02d}-{filtro.dia:02d}"
        return dia, dia
    ultimo = calendar.monthrange(filtro.ano, filtro.mes)[1]
    return f"{filtro.ano:04d}-{filtro.mes:02d}-01", f"{filtro.ano:04d}-{filtro.mes:02d}-{ultimo:02d}"


def mensaje_resumen(r: RunResult) -> str:
    """Mismo formato que Docket; Nuevos/omitidos/fallidos cuentan archivos (XML y PDF)."""
    palabra = "comprobante" if r.comprobantes == 1 else "comprobantes"
    return (
        f"{r.tipo} | {r.desde} a {r.hasta}: {r.comprobantes} {palabra}. "
        f"Nuevos {r.escritos}, omitidos {r.omitidos}, fallidos {r.fallidos}."
    )


def _avisar_captcha(motivo: str) -> None:
    notificar("Archivist: consulta no completada", _AVISOS_CAPTCHA.get(motivo, motivo), "long")


def ejecutar() -> RunResult:
    settings = load_settings()
    with open_context(headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        LoginPage(page).login(
            settings.login_url, settings.recibidos_url, settings.portal_ruc, settings.portal_password
        )
        notificar(APP_NAME, AVISO_INICIAL, "long")
        listado = ComprobantesPage(page)
        listado.esperar_listado(avisar=_avisar_captcha)
        filtro = listado.leer_filtro()  # lo consultado, para el resumen (el navegador se cierra)
        filas = listado.leer_todas()
        log.info("Se descargarán %d comprobantes (%d archivos)", len(filas), len(filas) * 2)
        lote = Downloader(page, settings.output_dir).descargar_lote(filas)
    desde, hasta = _rango(filtro)
    # leer_todas ya rechazó los tipos desconocidos; el nombre sale del mapa verificado de models.
    tipo = TIPOS.get(TIPO_PORTAL_A_CODIGO.get(filtro.tipo_portal, ""), f"Tipo {filtro.tipo_portal}")
    resultado = RunResult(
        len(filas), lote.escritos, lote.omitidos, lote.xml_con_clave, lote.xml_total, tipo, desde, hasta
    )
    notificar(APP_NAME, mensaje_resumen(resultado))
    return resultado