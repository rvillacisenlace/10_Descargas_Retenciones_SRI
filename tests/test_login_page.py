import pytest
from playwright.sync_api import TimeoutError as PWTimeout

from archivist_app.exceptions import LoginError
from archivist_app.pages.login_page import LoginPage

PERFIL = "https://portal.test/sri-en-linea/contribuyente/perfil"
RECIBIDOS = "https://portal.test/tuportal-internet/accederAplicacion.jspa?redireccion=57&idGrupo=55"
AUTH = "https://portal.test/auth/realms/Internet/protocol/openid-connect/auth?state=abc"
PERFIL_CON_CODIGO = PERFIL + "#state=abc&session_state=xyz&code=secreto-123"
VERIFICA = "https://portal.test/tuportal-internet/verificaEmail.jspa?token=t0k3n#code=secreto-123"
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

    def __init__(self, *, sesion=False, acepta=True, rebota=False, listado=True,
                 pierde_caracter=False, url_sin_listado=VERIFICA):
        self.sesion, self.acepta, self.rebota = sesion, acepta, rebota
        self.listado, self.pierde_caracter = listado, pierde_caracter
        self.url_sin_listado = url_sin_listado
        self.logueado = sesion
        self.url, self.present, self.values, self.events = "", set(), {}, []
        self._tras_login = False

    def goto(self, url, wait_until=None):
        self.events.append(("goto", url))
        if url == PERFIL:
            if self.logueado:
                self.url, self.present = PERFIL, set()
            else:
                self.url, self.present = AUTH, set(FORM)
        elif url == RECIBIDOS:
            if self.logueado and self.listado:
                self.url, self.present = RECIBIDOS, set(LISTADO)
            elif self.logueado:
                self.url, self.present = self.url_sin_listado, set()  # página sin listado
            else:
                self.url, self.present = AUTH, set(FORM)

    def wait_for_selector(self, selector, state=None, timeout=None):
        if not any(s.strip() in self.present for s in selector.split(", ")):
            raise PWTimeout("timeout")

    def locator(self, selector):
        return FakeLocator(self, selector)

    def click(self, selector):
        self.events.append(("submit", selector))
        if self.acepta:
            self.logueado, self._tras_login = True, True
            self.url, self.present = PERFIL_CON_CODIGO, set()

    def wait_for_url(self, predicado, timeout=None):
        if not predicado(self.url):
            raise PWTimeout("timeout")

    def wait_for_timeout(self, ms):
        if self.rebota and self._tras_login:
            self.logueado = False
            self.url, self.present = AUTH, set(FORM)


def _login(page):
    LoginPage(page).login(PERFIL, RECIBIDOS, "1700000000001", "clave-secreta")


def test_sesion_vigente_no_escribe_ni_envia():
    page = FakePage(sesion=True)
    _login(page)
    assert page.events == [("goto", PERFIL), ("goto", RECIBIDOS)]
    assert page.values == {}


def test_login_envia_y_solo_despues_abre_recibidos():
    page = FakePage()
    _login(page)
    assert page.events == [("goto", PERFIL), ("submit", LoginPage.SUBMIT), ("goto", RECIBIDOS)]
    assert page.values[LoginPage.USERNAME] == "1700000000001"
    assert page.values[LoginPage.PASSWORD] == "clave-secreta"


def test_portal_no_acepta_y_el_error_no_filtra_la_clave():
    page = FakePage(acepta=False)
    with pytest.raises(LoginError, match="no aceptó") as e:
        _login(page)
    assert "clave-secreta" not in str(e.value) and "state=abc" not in str(e.value)
    assert ("goto", RECIBIDOS) not in page.events


def test_portal_cierra_la_sesion_tras_el_login():
    page = FakePage(rebota=True)
    with pytest.raises(LoginError, match="cerró la sesión"):
        _login(page)
    assert ("goto", RECIBIDOS) not in page.events


def test_campo_que_pierde_caracteres_no_envia_el_formulario():
    page = FakePage(pierde_caracter=True)
    with pytest.raises(LoginError, match="RUC"):
        _login(page)
    assert ("submit", LoginPage.SUBMIT) not in page.events


def test_sin_listado_el_error_no_filtra_parametros_ni_codigo():
    page = FakePage(listado=False)
    with pytest.raises(LoginError, match="No se encontró el listado") as e:
        _login(page)
    msg = str(e.value)
    assert "verificaEmail" in msg
    assert "t0k3n" not in msg and "code=" not in msg and "secreto-123" not in msg


def test_sin_listado_el_error_no_filtra_el_fragmento_de_login():
    # URL con fragmento y SIN '?': el caso que filtraba el código de autorización.
    page = FakePage(listado=False, url_sin_listado=PERFIL_CON_CODIGO)
    with pytest.raises(LoginError, match="No se encontró el listado") as e:
        _login(page)
    assert "code=" not in str(e.value) and "secreto-123" not in str(e.value)
