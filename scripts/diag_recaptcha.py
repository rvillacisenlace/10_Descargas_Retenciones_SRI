import os
import re
import time
from urllib.parse import urlsplit

from archivist_app.browser import open_context
from archivist_app.config import load_settings
from archivist_app.pages.login_page import LoginPage

ESPERA_S = 12  # tiempo de observación en Recibidos (NO se pulsa Consultar)


def sin_query(url: str) -> str:
    """Solo host y ruta: la query de reCAPTCHA lleva parámetros que no hace falta ver."""
    p = urlsplit(url)
    return f"{p.netloc}{p.path}"


def limpia(texto: str) -> str:
    return re.sub(r"\?\S*", "?[...]", texto)[:200]


def de_interes(url: str) -> bool:
    return "recaptcha" in url.lower()


s = load_settings()
with open_context(headless=False) as ctx:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    t0 = time.time()

    def t() -> str:
        return f"{time.time() - t0:6.1f}s"

    def al_responder(resp):
        if de_interes(resp.url):
            print(f"[{t()}] HTTP {resp.status} {resp.request.method} "
                  f"{resp.request.resource_type:<10} {sin_query(resp.url)}")

    def al_fallar(req):
        if de_interes(req.url):
            print(f"[{t()}] FALLA {req.method} {req.resource_type:<10} "
                  f"{sin_query(req.url)} -> {req.failure}")

    def al_consola(msg):
        if "recaptcha" in msg.text.lower():
            print(f"[{t()}] consola {msg.type}: {limpia(msg.text)}")

    ctx.on("response", al_responder)
    ctx.on("requestfailed", al_fallar)
    ctx.on("console", al_consola)

    try:
        proxies = [k for k in os.environ if k.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")]
        print("Variables de proxy definidas (solo nombres):", proxies)
        LoginPage(page).login(s.login_url, s.recibidos_url, s.portal_ruc, s.portal_password)
        print(f"== Login OK. Observo {ESPERA_S} s en Recibidos (no se pulsa Consultar)")
        page.wait_for_timeout(ESPERA_S * 1000)

        info = page.evaluate("""() => ({
            webdriver: navigator.webdriver,
            agente: navigator.userAgent,
            grecaptcha: typeof window.grecaptcha,
            enterprise: !!(window.grecaptcha && window.grecaptcha.enterprise),
        })""")
        print("Navegador:", info)
        print("Texto del error de reCAPTCHA en la página:",
              [x.strip() for x in page.locator(".grecaptcha-error").all_inner_texts() if x.strip()])
        print("¿Aparece el mensaje 'Could not connect'?:",
              page.get_by_text("Could not connect to the reCAPTCHA service").count() > 0)
        print("Iframes de reCAPTCHA:", [sin_query(f.url) for f in page.frames if de_interes(f.url)])
    except Exception as e:
        print("ERROR:", e)
    input("Enter para cerrar...")
