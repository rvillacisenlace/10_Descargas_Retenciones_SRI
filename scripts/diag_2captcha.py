"""Prueba de 2Captcha contra el portal real. NO pulsa Consultar: eliges TU el filtro.

Por cada variante pide un token (cada intento cuesta una fraccion de centavo; revisa la
tarifa vigente de Enterprise en tu cuenta), lo inyecta y dice si el portal lo acepto.
Se detiene en la primera que funcione. Nunca imprime la clave ni el token.
"""
import os

from archivist_app.browser import open_context
from archivist_app.config import load_settings
from archivist_app.pages.login_page import LoginPage
from archivist_app.services.captcha_solver import CaptchaSolverError, resolver

ACTION = "consulta_cel_recibidos"
SITEKEY_RESPALDO = "6LdukTQsAAAAAIcciM4GZq4ibeyplUhmWvlScuQE"
VARIANTES = ("v3", "invisible")

SITEKEY_JS = """() => {
    const s = document.querySelector('script[src*="recaptcha/enterprise.js"]');
    return s ? new URL(s.src).searchParams.get('render') : null;
}"""

INYECTAR_JS = """(token) => {
    const area = document.getElementById('g-recaptcha-response');
    if (!area) return 'sin textarea g-recaptcha-response';
    if (typeof rcBuscar !== 'function') return 'sin rcBuscar';
    area.value = token;
    rcBuscar();
    return 'ok';
}"""

MENSAJES_JS = """() => [...document.querySelectorAll('.ui-messages, .grecaptcha-error')]
    .map(e => e.innerText.trim().slice(0, 200)).filter(Boolean)"""

FILAS_JS = """() => document.querySelectorAll('[id="frmPrincipal:tablaCompRecibidos"] tr[data-ri]').length"""


def es_consulta_con_token(resp) -> bool:
    try:
        req = resp.request
        return (req.method == "POST" and "comprobantesRecibidos.jsf" in resp.url
                and "g-recaptcha-response" in (req.post_data or ""))
    except Exception:
        return False


if __name__ == "__main__":
    s = load_settings()  # tambien carga el .env en el entorno
    if os.getenv("CAPTCHA_ENABLED", "true").strip().lower() not in ("1", "true", "yes", "si"):
        raise SystemExit("CAPTCHA_ENABLED esta desactivado en el .env: no se piden tokens.")
    if os.getenv("CAPTCHA_PROVIDER", "2captcha").strip().lower() != "2captcha":
        raise SystemExit("CAPTCHA_PROVIDER debe ser 2captcha para este script.")
    api_key = os.getenv("CAPTCHA_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Falta CAPTCHA_API_KEY en el .env
    with open_context(headless=False) as ctx:diag_descarga.py
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            LoginPage(page).login(s.login_url, s.recibidos_url, s.portal_ruc, s.portal_password)
            sitekey = page.evaluate(SITEKEY_JS) or SITEKEY_RESPALDO
            print("== Login OK")
            input("Elige TU el filtro en la ventana y pulsa Enter aqui (NO pulses Consultar)... ")

            for variante in VARIANTES:
                print(f"\n-- Variante '{variante}': pidiendo token a 2Captcha (15 a 60 s)...")
                try:
                    token = resolver(api_key, sitekey, page.url, ACTION, variante)
                except CaptchaSolverError as e:
                    print("   2Captcha:", e)
                    continue
                print(f"   Token recibido ({len(token)} caracteres). Inyectando...")

                with page.expect_response(es_consulta_con_token, timeout=30_000) as info:
                    res = page.evaluate(INYECTAR_JS, token)
                    if res != "ok":
                        raise RuntimeError(f"Inyeccion fallida: {res}")
                print("   El portal respondio HTTP", info.value.status)

                try:
                    cuerpo = info.value.text()
                except Exception:
                    cuerpo = ""
                page.wait_for_timeout(3000)
                mensajes = page.evaluate(MENSAJES_JS)
                rechazo_cuerpo = "aptcha incorrect" in cuerpo
                rechazo_pagina = any("aptcha" in m for m in mensajes)
                print("   Mensajes de la pagina:", mensajes, "| filas en la tabla:", page.evaluate(FILAS_JS))
                print("   Rechazo en la respuesta:", rechazo_cuerpo, "| en la pagina:", rechazo_pagina)
                if not (rechazo_cuerpo or rechazo_pagina):
                    print(f"   >>> ACEPTADO con la variante '{variante}'")
                    break
                print(f"   Rechazado con la variante '{variante}'.")
            else:
                print("\nNinguna variante fue aceptada.")
        except Exception as e:
            print("ERROR:", e)
        input("Enter para cerrar...")