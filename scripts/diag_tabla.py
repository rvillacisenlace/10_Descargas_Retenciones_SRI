import re
import shutil
import tempfile
import time
from pathlib import Path

from archivist_app.browser import open_context
from archivist_app.config import load_settings
from archivist_app.pages.login_page import LoginPage

TABLA = '[id="frmPrincipal:tablaCompRecibidos"]'

# Solo estructura: conteos, etiquetas de columnas, ids con los números enmascarados, el número
# de fila (Nro), los valores del filtro y los mensajes del portal. NUNCA el contenido de las celdas.
RESUMEN_JS = """() => {
    const T = '[id="frmPrincipal:tablaCompRecibidos"]';
    const filas = [...document.querySelectorAll(T + ' tr[data-ri]')];
    const texto = (f) => f ? (f.querySelector('td') ? f.querySelector('td').innerText.trim() : null) : null;
    const pags = [...document.querySelectorAll('.ui-paginator')].map(p => {
        const sel = p.querySelector('select');
        const sig = p.querySelector('.ui-paginator-next');
        const ant = p.querySelector('.ui-paginator-prev');
        return {
            actual: (p.querySelector('.ui-paginator-current') || {}).innerText || null,
            paginas: [...p.querySelectorAll('.ui-paginator-page')].map(x => x.innerText.trim()),
            siguiente_deshabilitado: sig ? sig.classList.contains('ui-state-disabled') : null,
            anterior_deshabilitado: ant ? ant.classList.contains('ui-state-disabled') : null,
            filas_por_pagina: sel ? [...sel.options].map(o => o.value) : null,
            filas_por_pagina_elegida: sel ? sel.value : null,
        };
    });
    const sel = (id) => { const e = document.getElementById(id); return e ? e.value : null; };
    const radio = document.querySelector('input[name="frmPrincipal:opciones"]:checked');
    return {
        tabla_existe: !!document.querySelector(T),
        filas: filas.length,
        celdas_por_fila: [...new Set(filas.map(f => f.querySelectorAll(':scope > td').length))],
        data_ri: filas.length ? [filas[0].getAttribute('data-ri'), filas[filas.length - 1].getAttribute('data-ri')] : [],
        nro_primera_y_ultima: [texto(filas[0]), texto(filas[filas.length - 1])],
        encabezados: [...document.querySelectorAll(T + ' thead th')].map(th => th.innerText.trim()),
        ids_enlaces_primera_fila: filas.length
            ? [...filas[0].querySelectorAll('a[id]')].map(a => a.id.replace(/[0-9]+/g, 'N')) : [],
        enlaces_xml: document.querySelectorAll('[id$=":lnkXml"]').length,
        enlaces_pdf: document.querySelectorAll('[id$=":lnkPdf"]').length,
        paginadores: pags,
        filtro: {
            ano: sel('frmPrincipal:ano'), mes: sel('frmPrincipal:mes'), dia: sel('frmPrincipal:dia'),
            tipo: sel('frmPrincipal:cmbTipoComprobante'), opcion: radio ? radio.value : null,
        },
        mensajes: [...document.querySelectorAll('.ui-messages, .ui-message, .grecaptcha-error')]
            .map(e => e.innerText.trim().slice(0, 200)).filter(Boolean).slice(0, 5),
    };
}"""


def enmascara(texto: str) -> str:
    """Dígitos -> 9: deja ver la forma de un nombre sin mostrar claves ni números."""
    return re.sub(r"[0-9]", "9", texto or "")


def clasificar(cabeza: bytes) -> str:
    inicio = cabeza.lstrip(b"\xef\xbb\xbf \r\n\t")[:20].lower()
    if inicio.startswith(b"%pdf"):
        return "PDF (empieza por %PDF)"
    if inicio.startswith(b"<?xml"):
        return "XML (empieza por <?xml)"
    if inicio.startswith(b"<!doctype html") or inicio.startswith(b"<html"):
        return "HTML: NO es un comprobante"
    return "desconocido"


def probar_descarga(page, sufijo: str) -> None:
    enlace = page.locator(f'{TABLA} tr[data-ri] a[id$=":{sufijo}"]').first
    carpeta = Path(tempfile.mkdtemp(prefix="archivist_diag_"))
    try:
        t0 = time.time()
        with page.expect_download(timeout=30_000) as info:
            enlace.click()
        d = info.value
        destino = carpeta / "descarga.bin"
        d.save_as(destino)
        datos = destino.read_bytes()
        print(f"   {sufijo}: nombre sugerido (enmascarado): {enmascara(d.suggested_filename)!r} | "
              f"{len(datos)} bytes | {clasificar(datos[:200])} | {time.time() - t0:.1f} s")
    except Exception as e:
        print(f"   {sufijo}: ERROR {type(e).__name__}: {str(e).splitlines()[0][:150] if str(e) else ''}")
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)  # no se conserva nada


if __name__ == "__main__":
    s = load_settings()
    with open_context(headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            LoginPage(page).login(s.login_url, s.recibidos_url, s.portal_ruc, s.portal_password)
            print("== Login OK. Elige TÚ el filtro y pulsa Consultar. Cuando aparezca la tabla")
            print("   (o un mensaje), vuelve aquí. El script no consulta ni pulsa nada por su cuenta.")
            input("Enter cuando el resultado esté en pantalla: ")
            descargado = False
            while True:
                print("== Resumen de la página:")
                for clave, valor in page.evaluate(RESUMEN_JS).items():
                    print(f"   {clave}: {valor}")
                if not descargado:
                    if input("¿Probar la descarga del PRIMER comprobante (1 XML y 1 PDF)? s/N: ").strip().lower() == "s":
                        descargado = True
                        print("== Descargas de prueba (a una carpeta temporal que se borra):")
                        probar_descarga(page, "lnkXml")
                        probar_descarga(page, "lnkPdf")
                        print("== Resumen tras las descargas (¿sigue la tabla y la página?):")
                        page.wait_for_timeout(1500)
                        continue
                if input("Enter = volver a resumir (p. ej. tras cambiar de página), q = salir: ").strip().lower() == "q":
                    break
        except Exception as e:
            print("ERROR:", e)
        input("Enter para cerrar...")
