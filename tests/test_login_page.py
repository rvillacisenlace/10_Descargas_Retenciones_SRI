import pytest
from playwright.sync_api import TimeoutError as PWTimeout

from archivist_app.exceptions import LoginError
from archivist_app.pages.login_page import LoginPage

LOGIN = "https://portal.test/perfil"
LANDING = "https://portal.test/recibidos.jsf"
AUTH = "https://portal.test/auth/realms/Internet/protocol/openid-connect/auth?state=abc"
FORM = {LoginPage.USERNAME, LoginPage.PASSWORD, LoginPage.SUBMIT}
LISTADO = {LoginPage.LOGGED_IN_MARKER}


class FakeLocator:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    def count(self):
        return 1 if self.selector in self.page.present else 0

    def click(self):
        pass

    def fill(self, text):
        self.page.values[self.selector] = text

    def press_sequentially(self, text, delay=0):
        self.page.values[self.selector] = text[:-1] if self.page.pierde_caracter else text

    def input_value(self):
        return self.page.values[self.selector]


class FakePage:
    """Simula las decisiones del portal; NO prueba el portal real."""

    def __init__(self, *, sesion=False, redirige=True, acepta=True, pierde_caracter=False):
        self.sesion, self.redirige, self.acepta = sesion, redirige, acepta
        self.pierde_caracter = pierde_caracter
        self.url, self.present, self.values, self.enviado = "", set(), {}, False

    def goto(self, url, wait_until=None):
        if url == LANDING and self.sesion:
            self.url, self.present = LANDING, set(LISTADO)
        elif url == LANDING and self.redirige:
            self.url, self.present = AUTH, set(FORM)
        elif url == LOGIN:
            self.url, self.present = AUTH, set(FORM)
        else:  # el listado no redirigió ni mostró nada
            self.url, self.present = url, set()

    def wait_for_selector(self, selector, state=None, timeout=None):
        if not any(s.strip() in self.present for s in selector.split(", ")):
            raise PWTimeout("timeout")

    def locator(self, selector):
        return FakeLocator(self, selector)

    def click(self, selector):
        self.enviado = True
        if self.acepta:
            self.url, self.present = LANDING, set(LISTADO)

    def wait_for_url(self, predicado, timeout=None):
        if not predicado(self.url):
            raise PWTimeout("timeout")

    def wait_for_load_state(self, state):
        pass


def _login(page):
    LoginPage(page).login(LOGIN, LANDING, "1700000000001", "clave-secreta")


def test_sesion_vigente_no_escribe_ni_envia():
    page = FakePage(sesion=True)
    _login(page)
    assert not page.enviado and page.values == {}


def test_login_exitoso_escribe_ruc_y_clave():
    page = FakePage()
    _login(page)
    assert page.enviado
    assert page.values[LoginPage.USERNAME] == "1700000000001"
    assert page.values[LoginPage.PASSWORD] == "clave-secreta"


def test_sin_redireccion_abre_la_url_de_login():
    page = FakePage(redirige=False)
    _login(page)
    assert page.enviado


def test_portal_no_acepta_y_el_error_no_filtra_la_clave():
    page = FakePage(acepta=False)
    with pytest.raises(LoginError, match="no aceptó") as e:
        _login(page)
    assert "clave-secreta" not in str(e.value) and "state=abc" not in str(e.value)


def test_campo_que_pierde_caracteres_no_envia_el_formulario():
    page = FakePage(pierde_caracter=True)
    with pytest.raises(LoginError, match="RUC"):
        _login(page)
    assert not page.enviado