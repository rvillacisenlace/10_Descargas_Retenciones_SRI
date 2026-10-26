"""Diagnostico del lote: descarga TODAS las filas del listado a una carpeta temporal y mide.

Imprime solo cifras. Borra la carpeta temporal al terminar (son datos de la empresa).
TU eliges el filtro y pulsas Consultar. Empieza con un filtro de pocas filas (unas 10):
son 2 peticiones por fila, con 1 s de pausa entre ellas.
"""
import shutil
import tempfile
import time
from pathlib import Path

from archivist_app.browser import open_context
from archivist_app.config import load_settings
from archivist_app.pages.comprobantes_page import ComprobantesPage
from archivist_app.pages.login_page import LoginPage
from archivist_app.services.downloader import Downloader

if __name__ == "__main__":
    s = load_settings()
    tmp = Path(tempfile.mkdtemp(prefix="archivist_lote_"))
    try:
        with open_context(headless=False) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                LoginPage(page).login(s.login_url, s.recibidos_url, s.portal_ruc, s.portal_password)
                listado = ComprobantesPage(page)
                print("== Login OK. Elige TU el filtro y pulsa Consultar.")
                listado.esperar_listado(avisar=lambda m: print(f"   Aviso: {m}"))
                filas = listado.leer_todas()
                print(f"== {len(filas)} filas validadas; se piden {len(filas) * 2} archivos")
                t0 = time.monotonic()
                resultado = Downloader(page, tmp).descargar_lote(filas)
                print(f"== Lote OK en {time.monotonic() - t0:.1f} s: {resultado}")
            except Exception as e:
                print(f"ERROR ({type(e).__name__}): {e}")
            input("Enter para cerrar...")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)