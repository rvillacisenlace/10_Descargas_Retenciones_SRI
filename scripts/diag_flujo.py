import time
from urllib.parse import parse_qs, urlsplit

from archivist_app.browser import open_context
from archivist_app.config import load_settings
from archivist_app.pages.login_page import LoginPage

OBSERVAR_S = 15     # espera máxima a que el login termine
ESTABLE_S = 8       # segundos que debe aguantar la sesión fuera del login
CONFIG_AUTH = ("client_id", "response_mode", "response_type", "prompt")  # valores no sensibles


def describir(url: str) -> str:
    """URL sin valores de parámetros: solo nombres (y valores de configuración o 'error')."""
    p = urlsplit(url)
    txt = f"{p.scheme}://{p.netloc}{p.path}"
    q, f = parse_qs(p.query), parse_qs(p.fragment)
    if "/auth/realms/" in p.path:
        cfg = ", ".join(f"{k}={q[k][0]}" for k in CONFIG_AUTH if k in q)
        if cfg:
            txt += f" [{cfg}]"
    elif q:
        txt += " ?[" + ",".join(sorted(q)) + "]"
    if f:
        txt += " #[" + ",".join(sorted(f)) + "]"
    for datos in (q, f):
        if "error" in datos:
            txt += f" error={datos['error'][0]}"
    return txt


def en_login(url: str) -> bool:
    return "/auth/realms/" in url


s = load_settings()
with open_context(headless=False) as ctx:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    t0 = time.time()

    def t() -> str:
        return f"{time.time() - t0:6.1f}s"

    def al_navegar(frame):
        if frame == page.main_frame:
            print(f"[{t()}] navega -> {describir(frame.url)}")

    def al_responder(resp):
        try:
            redirige = 300 <= resp.status < 400 and resp.request.resource_type == "document"
            if resp.status >= 400 or redirige:
                p = urlsplit(resp.url)
                destino = ""
                if redirige:
                    try:
                        d = urlsplit(resp.all_headers().get("location", ""))
                        if d.netloc or d.path:
                            destino = f" -> {d.scheme + '://' if d.scheme else ''}{d.netloc}{d.path}"
                    except Exception:
                        destino = " -> (sin cabecera Location)"
                print(f"[{t()}] HTTP {resp.status} {resp.request.method} {p.netloc}{p.path}{destino}")
        except Exception:
            pass

    page.on("framenavigated", al_navegar)
    page.on("response", al_responder)
    lp = LoginPage(page)

    def hay_listado() -> bool:
        try:
            return page.locator(lp.LOGGED_IN_MARKER).count() > 0
        except Exception:
            return False  # navegando: el contexto de la página cambió

    try:
        print("URL de Recibidos configurada:", describir(s.recibidos_url))
        print("== 1. Abrir el portal (perfil), como lo haces tú")
        page.goto(s.login_url, wait_until="domcontentloaded")
        hay_form = lp._wait_for(lp.USERNAME, 15_000)
        print("   URL:", describir(page.url), "| formulario:", hay_form)

        rebote = False
        if hay_form:
            print("== 2. Enviar credenciales (un solo intento)")
            lp._type(lp.USERNAME, s.portal_ruc, "RUC")
            lp._type(lp.PASSWORD, s.portal_password, "clave")
            page.click(lp.SUBMIT)
            salida = None
            for _ in range(OBSERVAR_S + ESTABLE_S):
                if salida is None and not en_login(page.url):
                    salida = time.time()
                    print(f"[{t()}] salió del login: observo {ESTABLE_S} s")
                elif salida is not None:
                    if en_login(page.url):
                        print(f"[{t()}] REBOTE: volvió al login {time.time() - salida:.1f} s después")
                        rebote = True
                        break
                    if time.time() - salida >= ESTABLE_S:
                        print(f"[{t()}] la sesión aguanta {ESTABLE_S} s en el portal")
                        break
                page.wait_for_timeout(1000)
            else:
                print("   No se completó el inicio de sesión a tiempo.")
        else:
            print("   Sin formulario: puede que ya haya sesión.")

        print("== 3. Cookies (solo nombres, nunca valores)")
        for c in sorted(ctx.cookies(), key=lambda c: (c["domain"], c["name"])):
            print(f"   {c['domain']:<28} {c['name']:<30} secure={c['secure']} httpOnly={c['httpOnly']}")

        if rebote:
            print("== 4. No se abre Recibidos: el portal ya cerró la sesión.")
        else:
            print("== 4. Ir a Recibidos desde el portal")
            page.goto(s.recibidos_url, wait_until="domcontentloaded")
            lp._wait_for(f"{lp.LOGGED_IN_MARKER}, {lp.USERNAME}", 20_000)
            print("   URL:", describir(page.url), "| listado:", hay_listado(),
                  "| formulario:", page.locator(lp.USERNAME).count() > 0)
            print("   RESULTADO:", "FLUJO COMPLETO OK" if hay_listado() else "falló en Recibidos")
    except Exception as e:
        print("ERROR:", e)
        print("URL actual:", describir(page.url))
    input("Enter para cerrar...")
