from archivist_app.browser import open_context
from archivist_app.config import load_settings
from archivist_app.pages.login_page import LoginPage

s = load_settings()
with open_context(headless=False) as ctx:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        LoginPage(page).login(s.login_url, s.recibidos_url, s.portal_ruc, s.portal_password)
        print("Login OK. URL:", page.url.split("?")[0])
    except Exception as e:
        print("ERROR:", e)
        print("URL actual:", page.url.split("?")[0])
    input("Enter para cerrar...")