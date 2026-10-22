from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from archivist_app.exceptions import LoginError
from archivist_app.logger import get_logger

log = get_logger(__name__)

AUTH_PATH = "/auth/realms/"  # el login del SRI vive en esta ruta (observado en el diagnóstico)
ESTABLE_S = 8  # la sesión debe aguantar este tiempo fuera del login antes de abrir Recibidos


def _corta(url: str) -> str:
    """Sin '?query' ni '#fragmento': ambos pueden llevar parámetros de sesión o el código de login."""
    return url.split("#")[0].split("?")[0]


class LoginPage:
    USERNAME = "#usuario"  # es el campo del RUC
    PASSWORD = "#password"
    SUBMIT = "#kc-login"
    LOGGED_IN_MARKER = '[id="frmPrincipal:pnlBusqueda"]'  # solo existe en el listado, con sesión

    def __init__(self, page: Page):
        self.page = page

    def _wait_for(self, selector: str, timeout_ms: int) -> bool:
        try:
            self.page.wait_for_selector(selector, state="attached", timeout=timeout_ms)
            return True
        except PWTimeout:
            return False

    def _type(self, selector: str, text: str, label: str) -> None:
        field = self.page.locator(selector)
        field.click()
        field.fill("")
        # Los campos bloquean pegar: se escribe tecla a tecla.
        field.press_sequentially(text, delay=40)
        if len(field.input_value()) != len(text):
            raise LoginError(f"El campo {label} no recibió todo el texto escrito")

    def _wait_stable(self) -> None:
        """Tras el login, la sesión debe aguantar fuera del formulario antes de seguir."""
        for _ in range(ESTABLE_S):
            self.page.wait_for_timeout(1000)
            if AUTH_PATH in self.page.url:
                raise LoginError(
                    "El portal cerró la sesión justo después del login "
                    f"(volvió a {_corta(self.page.url)})"
                )

    def _sign_in(self, ruc: str, password: str) -> None:
        # Un solo intento: no hay reintentos, para no arriesgar el bloqueo de la cuenta.
        self._type(self.USERNAME, ruc, "RUC")
        self._type(self.PASSWORD, password, "clave")
        self.page.click(self.SUBMIT)
        log.info("Formulario enviado")

        try:
            self.page.wait_for_url(lambda u: AUTH_PATH not in u, timeout=15_000)
        except PWTimeout:
            raise LoginError(
                f"El portal no aceptó el login (sigue en {_corta(self.page.url)}): "
                "revise RUC y clave"
            ) from None
        self._wait_stable()

    def login(self, login_url: str, recibidos_url: str, ruc: str, password: str) -> None:
        # El orden importa: abrir Recibidos sin una sesión de portal creada desde el perfil
        # hace que el portal cierre la sesión (observado en el diagnóstico).
        self.page.goto(login_url, wait_until="domcontentloaded")
        if self._wait_for(self.USERNAME, 8_000):
            self._sign_in(ruc, password)
        else:
            log.info("Sin formulario en el perfil: se asume sesión vigente")

        self.page.goto(recibidos_url, wait_until="domcontentloaded")
        if not self._wait_for(self.LOGGED_IN_MARKER, 20_000):
            raise LoginError(
                f"No se encontró el listado de recibidos. URL: {_corta(self.page.url)}"
            )
        log.info("Login correcto")
