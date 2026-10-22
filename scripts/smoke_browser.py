from archivist_app.browser import open_context
from archivist_app.config import load_settings

ESPERA_MS = 15_000
SETTINGS = load_settings()


def corta(url: str) -> str:
    """Sin la parte tras '?', que puede llevar parámetros de sesión."""
    return url.split("?")[0]


with open_context(headless=False) as ctx:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto(SETTINGS.login_url, wait_until="domcontentloaded")
        print("Tras goto   ->", corta(page.url))
        try:
            page.wait_for_selector("#usuario", state="attached", timeout=ESPERA_MS)
            print("Campo RUC (#usuario): apareció")
        except Exception:
            print(f"Campo RUC (#usuario): NO apareció en {ESPERA_MS // 1000} s")
        print("URL final   ->", corta(page.url))
        print("Título      ->", page.title())
        for i, fr in enumerate(page.frames):
            print(f"Frame {i}: {corta(fr.url)}")
            for sel in ("#usuario", "#password", "#kc-login"):
                print(f"   {sel}: {fr.locator(sel).count()}")
    except Exception as e:
        print("ERROR:", e)
        print("URL actual:", corta(page.url))
    input("Enter para cerrar...")
