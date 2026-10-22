from contextlib import contextmanager
from typing import Iterator

from playwright.sync_api import BrowserContext, sync_playwright

from archivist_app.config import AUTH_DIR, DEFAULT_TIMEOUT_MS


@contextmanager
def open_context(headless: bool) -> Iterator[BrowserContext]:
    """Contexto persistente: la sesión sobrevive entre ejecuciones (.auth/)."""
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(AUTH_DIR),
            channel="msedge",
            headless=headless,
            accept_downloads=True,
            # Reducen las señales de automatizacion que bajan el puntaje de
            # reCAPTCHA Enterprise. Confirmado en prueba real: sin esto el
            # portal respondia "Captcha incorrecto" al consultar; con esto
            # carga la tabla. No agregar un solucionador de captcha (2Captcha)
            # mientras esto siga funcionando.
            ignore_default_args=["--enable-automation"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        context.set_default_timeout(DEFAULT_TIMEOUT_MS)
        try:
            yield context
        finally:
            context.close()