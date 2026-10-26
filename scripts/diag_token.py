"""Diagnostico: como entrega la pagina el token de reCAPTCHA al servidor.

No pulsa Consultar: lo pulsas TU. Imprime codigo publico del portal (las funciones
de reCAPTCHA de la pagina), sitekey/action, y de los POST solo NOMBRES de campos
y la LONGITUD de los candidatos a token. Nunca imprime un token.
"""
import time
from urllib.parse import parse_qs

from archivist_app.browser import open_context
from archivist_app.config import load_settings
from archivist_app.pages.login_page import LoginPage

ESPERA_S = 180

FUNCIONES_JS = """() => {
    const nombres = ['executeRecaptcha', 'cargarRecaptcha', 'resetarRecaptcha',
                     'deshabilitarBoton', 'reactivarBoton'];
    const salida = {};
    for (const n of nombres) {
        salida[n] = typeof window[n] === 'function' ? window[n].toString() : null;
    }
    return salida;
}"""

# Envuelve execute() SOLO para observar: no cambia lo que devuelve.
OBSERVAR_JS = """() => {
    try {
        const e = window.grecaptcha && window.grecaptcha.enterprise;
        if (!e || typeof e.execute !== 'function') return 'sin grecaptcha.enterprise.execute';
        window.__rc = [];
        const original = e.execute.bind(e);
        e.execute = (key, opts) => {
            const fila = { sitekey: key, action: opts && opts.action };
            window.__rc.push(fila);
            const r = original(key, opts);
            if (r && typeof r.then === 'function') r.then(t => { fila.token_len = t ? t.length : 0; });
            return r;
        };
        return 'observando';
    } catch (err) {
        return 'no se pudo observar: ' + err;
    }
}"""

MENSAJES_JS = """() => [...document.querySelectorAll('.ui-messages, .grecaptcha-error')]
    .map(e => e.innerText.trim().slice(0, 200)).filter(Boolean)"""


def registrar(resp, estado: dict) -> None:
    """Nunca lanza: una excepcion en un manejador de Playwright rompe el resto."""
    try:
        req = resp.request
        if req.method != "POST" or "comprobantesRecibidos.jsf" not in resp.url:
            return
        datos = parse_qs((req.post_data_buffer or b"").decode("utf-8", errors="replace"))
        estado["posts"] += 1
        print(f"\nPOST #{estado['posts']} origen={datos.get('javax.faces.source', ['?'])[0]} HTTP {resp.status}")
        print("   campos:", sorted(datos))
        print("   campos largos (nombre -> longitud):",
              {k: max(len(v) for v in datos[k]) for k in datos if any(len(v) > 100 for v in datos[k])})
        try:
            cuerpo = resp.text()
        except Exception:
            cuerpo = ""
        print("   la respuesta dice 'Captcha incorrecto':", "aptcha incorrecto" in cuerpo)
    except Exception as e:
        print(f"(no se pudo registrar una peticion: {type(e).__name__})")


if __name__ == "__main__":
    s = load_settings()
    with open_context(headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        estado = {"posts": 0}
        ctx.on("response", lambda resp: registrar(resp, estado))
        try:
            LoginPage(page).login(s.login_url, s.recibidos_url, s.portal_ruc, s.portal_password)
            print("== Login OK")
            print("\n-- Funciones de reCAPTCHA de la pagina (codigo publico del portal):")
            for nombre, codigo in page.evaluate(FUNCIONES_JS).items():
                print(f"\n### {nombre}\n{codigo}")
            print("\n-- Observador de execute():", page.evaluate(OBSERVAR_JS))
            print("\n== Elige TU el filtro y pulsa Consultar (el script no hace clic).")
            fin = time.time() + ESPERA_S
            while estado["posts"] == 0 and time.time() < fin:
                page.wait_for_timeout(500)
            page.wait_for_timeout(6000)
            print("\n-- Llamadas a execute() observadas:", page.evaluate("() => window.__rc || []"))
            print("-- Mensajes del portal:", page.evaluate(MENSAJES_JS))
        except Exception as e:
            print("ERROR:", e)
        input("Enter para cerrar...")