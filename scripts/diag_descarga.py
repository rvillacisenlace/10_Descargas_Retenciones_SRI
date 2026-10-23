"""Diagnostico de descarga: que ocurre al pedir un XML y un PDF del listado.

Imprime SOLO metadatos (extension, tamano, tipo detectado por los primeros bytes).
Nunca imprime nombres completos, contenido, claves de acceso, tokens ni cookies.
TU eliges el filtro y pulsas Consultar (el script no hace clic en Consultar).
Usa un filtro que devuelva filas: una consulta vacia no sirve para esta prueba.
"""
import re
import shutil
import tempfile
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PwTimeout

from archivist_app.browser import open_context
from archivist_app.config import load_settings
from archivist_app.exceptions import PortalError
from archivist_app.pages.login_page import LoginPage

ESPERA_TABLA_S = 180
ESPERA_DESCARGA_MS = 30_000
PAUSA_MS = 4000  # pausa entre pruebas: no se pide nada en rafaga
FILAS = '[id="frmPrincipal:tablaCompRecibidos"] tr[data-ri]'
ENLACE = "frmPrincipal:tablaCompRecibidos:0:{}"  # fila 0, solo nombres de componente
_RE_CLAVE = re.compile(r"[0-9]{49}")

JS_ESTADO = """() => ({
    dialogos: [...document.querySelectorAll('.ui-dialog:not(.ui-overlay-hidden) .ui-dialog-title')]
        .map(e => e.innerText.trim().slice(0, 60)),
    mensajes: [...document.querySelectorAll('.ui-messages, .ui-message, .grecaptcha-error')]
        .map(e => e.innerText.trim().slice(0, 120)).filter(Boolean).slice(0, 5),
    ruta: location.pathname,
})"""

# Reproduce lo que hace mojarra.jsfcljs: POST del formulario con el ViewState vigente
# mas el parametro del enlace. Devuelve solo cabeceras HTTP y los primeros 256 bytes.
JS_FETCH = """async (linkId) => {
    const form = document.getElementById('frmPrincipal');
    const cuerpo = new URLSearchParams(new FormData(form));
    cuerpo.set(linkId, linkId);
    const r = await fetch(form.action, {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: cuerpo.toString(),
    });
    const buf = new Uint8Array(await r.arrayBuffer());
    return {
        status: r.status,
        tipo: r.headers.get('content-type'),
        adjunto: /attachment/i.test(r.headers.get('content-disposition') || ''),
        bytes: buf.length,
        cabecera: Array.from(buf.slice(0, 256)),
    };
}"""


def clasificar(cabecera: bytes) -> str:
    """Solo mira los primeros bytes; no devuelve contenido."""
    bajo = cabecera.lower()
    if cabecera.startswith(b"%PDF"):
        return "PDF"
    if b"partial-response" in bajo:
        return "respuesta AJAX de JSF (no es un archivo)"
    if b"<html" in bajo or b"<!doctype html" in bajo:
        return "HTML (probable pagina de error o de sesion)"
    inicio = cabecera.lstrip(b"\xef\xbb\xbf \r\n\t")
    if inicio.startswith(b"<?xml"):
        return "XML"
    if inicio.startswith(b"<"):
        return "XML sin declaracion (empieza con <)"
    return "otro"


def mostrar_estado(page) -> None:
    print("   Estado de la pagina:", page.evaluate(JS_ESTADO))


def esperar_tabla(page) -> None:
    fin = time.time() + ESPERA_TABLA_S
    avisado = False
    while time.time() < fin:
        if page.locator(FILAS).count() > 0:
            return
        if not avisado and "aptcha incorrect" in page.inner_text("body"):
            print("   El portal respondio 'Captcha incorrecta'. Vuelve a pulsar Consultar.")
            avisado = True
        page.wait_for_timeout(500)
    raise PortalError(f"No cargo la tabla en {ESPERA_TABLA_S} s")


def probar_clic(page, tipo: str, destino: Path) -> None:
    enlace_id = ENLACE.format(tipo)
    print(f"-- Clic en {tipo} (fila 0)")
    try:
        with page.expect_download(timeout=ESPERA_DESCARGA_MS) as info:
            page.locator(f'[id="{enlace_id}"]').click()
        descarga = info.value
    except PwTimeout:
        print(f"   No hubo evento de descarga en {ESPERA_DESCARGA_MS // 1000} s.")
        mostrar_estado(page)
        return
    nombre = descarga.suggested_filename
    ext = Path(nombre).suffix
    print(f"   Evento de descarga OK. extension={ext!r} largo_nombre={len(nombre)} "
          f"clave_en_nombre={bool(_RE_CLAVE.search(nombre))}")
    try:
        ruta = destino / f"muestra{ext}"
        descarga.save_as(str(ruta))
        with open(ruta, "rb") as f:
            cabecera = f.read(256)
        print(f"   save_as OK: {ruta.stat().st_size} bytes | tipo por cabecera: {clasificar(cabecera)}")
    except Exception as e:
        print(f"   save_as fallo: {type(e).__name__}: {str(e)[:120]}")


def probar_fetch(page, tipo: str) -> None:
    print(f"-- fetch del postback de {tipo} (fila 0, sin clic)")
    try:
        r = page.evaluate(JS_FETCH, ENLACE.format(tipo))
    except Exception as e:
        print(f"   fetch fallo: {type(e).__name__}: {str(e)[:120]}")
        return
    print(f"   HTTP {r['status']} | content-type={r['tipo']} | adjunto={r['adjunto']} | "
          f"{r['bytes']} bytes | tipo por cabecera: {clasificar(bytes(r['cabecera']))}")


if __name__ == "__main__":
    s = load_settings()
    tmp = Path(tempfile.mkdtemp(prefix="archivist_diag_"))
    try:
        with open_context(headless=False) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                LoginPage(page).login(s.login_url, s.recibidos_url, s.portal_ruc, s.portal_password)
                print("== Login OK. Elige TU el filtro y pulsa Consultar (con filas en el resultado).")
                esperar_tabla(page)
                print(f"== Tabla cargada: {page.locator(FILAS).count()} filas")
                for tipo in ("lnkXml", "lnkPdf"):
                    probar_clic(page, tipo, tmp)
                    page.wait_for_timeout(PAUSA_MS)
                for tipo in ("lnkXml", "lnkPdf"):
                    probar_fetch(page, tipo)
                    page.wait_for_timeout(PAUSA_MS)
            except Exception as e:
                print("ERROR:", e)
            input("Enter para cerrar...")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)