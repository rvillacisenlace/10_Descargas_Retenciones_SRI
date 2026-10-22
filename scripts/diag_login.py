import time

from archivist_app.browser import open_context
from archivist_app.config import load_settings
from archivist_app.pages.login_page import LoginPage

OBSERVAR_S = 20

# URL larga del archivo de pasos (con los parámetros ...MPT del menú del portal),
# con los acentos reconstruidos: en el archivo original estaban dañados.
RECIBIDOS_MPT = (
    "https://srienlinea.sri.gob.ec/comprobantes-electronicos-internet/pages/consultas/recibidos/"
    "comprobantesRecibidos.jsf?&contextoMPT=https://srienlinea.sri.gob.ec/tuportal-internet"
    "&pathMPT=Facturaci%C3%B3n%20Electr%C3%B3nica"
    "&actualMPT=Comprobantes%20electr%C3%B3nicos%20recibidos%20"
    "&linkMPT=%2Fcomprobantes-electronicos-internet%2Fpages%2Fconsultas%2Frecibidos%2F"
    "comprobantesRecibidos.jsf%3F&esFavorito=S"
)


def corta(url: str) -> str:
    """Sin query; del fragmento solo se indica si lleva 'code=' (nunca su valor)."""
    base, _, frag = url.partition("#")
    marca = " #[fragmento con code]" if "code=" in frag else (" #[fragmento]" if frag else "")
    return base.split("?")[0] + marca


def hay_listado(page) -> bool:
    try:
        return page.locator(LoginPage.LOGGED_IN_MARKER).count() > 0
    except Exception:
        return False  # navegando: el contexto de la página cambió


s = load_settings()
with open_context(headless=False) as ctx:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    t0 = time.time()

    def al_navegar(frame):
        if frame == page.main_frame:
            print(f"[{time.time() - t0:5.1f}s] navega -> {corta(frame.url)}")

    page.on("framenavigated", al_navegar)
    lp = LoginPage(page)

    def abrir(titulo: str, url: str) -> bool:
        """Abre una URL y dice si apareció el listado y/o el formulario de login."""
        print(f"== {titulo}")
        page.goto(url, wait_until="domcontentloaded")
        lp._wait_for(f"{lp.LOGGED_IN_MARKER}, {lp.USERNAME}", 15_000)
        listado = hay_listado(page)
        print("   URL:", corta(page.url), "| listado:", listado,
              "| formulario:", page.locator(lp.USERNAME).count() > 0)
        return listado

    try:
        if abrir("1. Abrir Recibidos", s.recibidos_url):
            print("   Ya había sesión: nada que diagnosticar del login.")
        else:
            print("== 2. Enviar credenciales (un solo intento)")
            lp._type(lp.USERNAME, s.portal_ruc, "RUC")
            lp._type(lp.PASSWORD, s.portal_password, "clave")
            page.click(lp.SUBMIT)
            print(f"== 3. Observar {OBSERVAR_S} s SIN navegar (cada cambio de URL se imprime arriba)")
            for _ in range(OBSERVAR_S):
                if hay_listado(page):
                    break
                page.wait_for_timeout(1000)
            print("   URL:", corta(page.url), "| listado:", hay_listado(page))

            print("== 4. Cookies tras el login (solo nombres, nunca valores)")
            for c in sorted(ctx.cookies(), key=lambda c: (c["domain"], c["name"])):
                print(f"   {c['domain']:<28} {c['name']:<30} secure={c['secure']} httpOnly={c['httpOnly']}")

            if not abrir("5. Reabrir Recibidos (lo que hace login_page hoy)", s.recibidos_url):
                if not abrir("6. Abrir el perfil del portal: ¿hay sesión en el portal?", s.login_url):
                    abrir("7. Recibidos con los parámetros MPT del menú", RECIBIDOS_MPT)
    except Exception as e:
        print("ERROR:", e)
        print("URL actual:", corta(page.url))
    input("Enter para cerrar...")
