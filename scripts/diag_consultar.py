import re
import time
from urllib.parse import parse_qs

from archivist_app.browser import open_context
from archivist_app.config import load_settings
from archivist_app.pages.login_page import LoginPage

ESPERA_S = 180  # tiempo máximo esperando a que TÚ pulses Consultar
# Solo estos campos muestran su valor (son de configuración del filtro); del resto, solo el nombre.
SEGUROS = ("frmPrincipal:ano", "frmPrincipal:mes", "frmPrincipal:dia",
           "frmPrincipal:cmbTipoComprobante", "frmPrincipal:opciones")

# Solo cuentas, nombres de columnas y mensajes del portal: nunca el contenido de las celdas.
RESUMEN_JS = """() => {
    const tabla = document.querySelector('[id="frmPrincipal:tablaCompRecibidos"]');
    const filas = document.querySelectorAll('[id="frmPrincipal:tablaCompRecibidos"] tr[data-ri]').length;
    const encabezados = [...document.querySelectorAll('[id="frmPrincipal:tablaCompRecibidos"] thead th')]
        .map(th => th.innerText.trim()).filter(Boolean);
    const pag = document.querySelector('.ui-paginator-current');
    const msgs = [...document.querySelectorAll('.ui-messages, .ui-message, .grecaptcha-error')]
        .map(e => e.innerText.trim().slice(0, 200)).filter(Boolean);
    return {
        tabla: !!tabla,
        filas: filas,
        encabezados: encabezados,
        paginador: pag ? pag.innerText.trim() : null,
        enlaces_xml: document.querySelectorAll('[id$=":lnkXml"]').length,
        enlaces_pdf: document.querySelectorAll('[id$=":lnkPdf"]').length,
        mensajes: msgs.slice(0, 5),
    };
}"""


def limpia(texto: str) -> str:
    return re.sub(r"\?\S*", "?[...]", texto)[:200]


def registrar(resp, estado: dict, t) -> None:
    """Registra cada POST AJAX de Recibidos. Nunca lanza: una excepción en un manejador de
    eventos de Playwright rompe el resto de la ejecución."""
    try:
        req = resp.request
        if req.method != "POST" or "comprobantesRecibidos.jsf" not in resp.url:
            return  # se filtra por URL ANTES de leer el cuerpo (los POST de Google son binarios)
        estado["consultas"] += 1
        post = (req.post_data_buffer or b"").decode("utf-8", errors="replace")
        datos = parse_qs(post)
        valores = {k: datos[k][0] for k in SEGUROS if k in datos}
        origen = datos.get("javax.faces.source", ["?"])[0]  # id del componente, no es un dato
        campos_token = {
            k: max(len(v) for v in datos[k])
            for k in datos
            if ("recaptcha" in k.lower() or "token" in k.lower()) and any(len(v) > 20 for v in datos[k])
        }
        try:
            cuerpo = resp.text()
        except Exception:
            cuerpo = ""
        print(f"[{t()}] POST #{estado['consultas']} origen={origen}: HTTP {resp.status} | "
              f"respuesta {len(cuerpo)} caracteres")
        print("   filtro enviado:", valores)
        print("   nombres de campos:", sorted(datos))
        print("   campos con token (nombre -> longitud, nunca el valor):", campos_token)
        print("   la respuesta menciona la tabla:", "tablaCompRecibidos" in cuerpo,
              "| enlaces XML:", cuerpo.count("lnkXml"), "| enlaces PDF:", cuerpo.count("lnkPdf"))
    except Exception as e:
        print(f"[{t()}] (no se pudo registrar una petición: {type(e).__name__})")


if __name__ == "__main__":
    s = load_settings()
    with open_context(headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        t0 = time.time()
        estado = {"consultas": 0}

        def t() -> str:
            return f"{time.time() - t0:6.1f}s"

        def al_consola(msg):
            try:
                if "recaptcha" in msg.text.lower():
                    print(f"[{t()}] consola {msg.type}: {limpia(msg.text)}")
            except Exception:
                pass

        ctx.on("response", lambda resp: registrar(resp, estado, t))
        ctx.on("console", al_consola)
        try:
            LoginPage(page).login(s.login_url, s.recibidos_url, s.portal_ruc, s.portal_password)
            print("== Login OK. Elige TÚ el filtro y pulsa Consultar en la ventana (el script no hace clic).")
            while True:
                previas = estado["consultas"]
                fin = time.time() + ESPERA_S
                while estado["consultas"] == previas and time.time() < fin:
                    page.wait_for_timeout(500)
                if estado["consultas"] == previas:
                    print(f"   No se detectó ninguna consulta en {ESPERA_S} s.")
                    break
                page.wait_for_timeout(6000)  # deja terminar la actualización de la tabla
                print("   Resumen de la página:", page.evaluate(RESUMEN_JS))
                if input("Enter = observar otra consulta, q = salir: ").strip().lower() == "q":
                    break
        except Exception as e:
            print("ERROR:", e)
        input("Enter para cerrar...")
