"""Orquesta el orden de los pasos y devuelve RunResult.

Orden: config -> navegador -> login -> filtro + aviso -> espera del usuario (máx. 10 min)
-> recorrer páginas + evidencias -> descarga todo o nada -> notificar resumen.
No sabe cómo se interactúa con el portal (eso es de pages/).

Pendiente: evidencias (capturas con banner). La paginación falla cerrado (PortalError) hasta
verificarla contra el portal; ver ComprobantesPage.leer_todas.
"""

from dataclasses import dataclass

from archivist_app.browser import open_context
from archivist_app.config import USER_WAIT_TIMEOUT_S, load_settings
from archivist_app.logger import get_logger
from archivist_app.pages.comprobantes_page import ComprobantesPage
from archivist_app.pages.login_page import LoginPage
from archivist_app.services.downloader import Downloader
from archivist_app.services.notifier import notificar

log = get_logger(__name__)

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


def _avisar_captcha(motivo: str) -> None:
    notificar("Archivist: consulta no completada", _AVISOS_CAPTCHA.get(motivo, motivo), "long")


def ejecutar() -> RunResult:
    settings = load_settings()
    with open_context(headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        LoginPage(page).login(
            settings.login_url, settings.recibidos_url, settings.portal_ruc, settings.portal_password
        )
        notificar(
            "Archivist: elija el filtro",
            f"Elija año, mes, día y tipo, y pulse Consultar. Tiene {USER_WAIT_TIMEOUT_S // 60} minutos.",
            "long",
        )
        listado = ComprobantesPage(page)
        listado.esperar_listado(avisar=_avisar_captcha)
        filas = listado.leer_todas()
        log.info("Se descargarán %d comprobantes (%d archivos)", len(filas), len(filas) * 2)
        lote = Downloader(page, settings.output_dir).descargar_lote(filas)
    resultado = RunResult(len(filas), lote.escritos, lote.omitidos, lote.xml_con_clave, lote.xml_total)
    notificar(
        "Archivist: descarga completa",
        f"{resultado.comprobantes} comprobantes: {resultado.escritos} archivos nuevos y "
        f"{resultado.omitidos} que ya estaban.",
    )
    return resultado