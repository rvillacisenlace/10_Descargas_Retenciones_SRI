from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from archivist_app.exceptions import LoginError
from archivist_app.logger import get_logger

log = get_logger(__name__)

AUTH_PATH = "/auth/realms/"  # el login del SRI vive en esta ruta (observado en el smoke)


def _corta(url: str) -> str:
    """Sin la parte tras '?', que puede llevar parámetros de sesión."""
    return url.split("?")[0]


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

    def _already_logged_in(self, landing: str) -> bool:
        self.page.goto(landing, wait_until="domcontentloaded")
        # Sin sesión el portal redirige al login: aparece el formulario en vez del listado.
        self._wait_for(f"{self.LOGGED_IN_MARKER}, {self.USERNAME}", 15_000)
        return self.page.locator(self.LOGGED_IN_MARKER).count() > 0

    def _type(self, selector: str, text: str, label: str) -> None:
        field = self.page.locator(selector)
        field.click()
        field.fill("")
        # Los campos bloquean pegar: se escribe tecla a tecla.
        field.press_sequentially(text, delay=40)
        if len(field.input_value()) != len(text):
            raise LoginError(f"El campo {label} no recibió todo el texto escrito")

    def login(self, login_url: str, recibidos_url: str, ruc: str, password: str) -> None:
        if self._already_logged_in(recibidos_url):
            log.info("Sesión vigente, se omite el login")
            return

        if self.page.locator(self.USERNAME).count() == 0:
            log.info("El listado no redirigió al login; se abre %s", _corta(login_url))
            self.page.goto(login_url, wait_until="domcontentloaded")
            if not self._wait_for(self.USERNAME, 15_000):
                raise LoginError(f"No apareció el formulario en {_corta(self.page.url)}")

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
        self.page.wait_for_load_state("load")

        if not self._wait_for(self.LOGGED_IN_MARKER, 5_000):
            self.page.goto(recibidos_url, wait_until="domcontentloaded")
            if not self._wait_for(self.LOGGED_IN_MARKER, 15_000):
                raise LoginError(
                    f"No se encontró el listado tras el login. URL: {_corta(self.page.url)}"
                )
        log.info("Login correcto")