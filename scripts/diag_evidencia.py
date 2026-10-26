"""Diagnostico de la evidencia: genera las capturas con banner y abre la carpeta para que las veas.

No descarga nada: solo se consulta (como siempre) y se toman las capturas. Se guardan en una
carpeta temporal y se BORRAN al terminar (contienen datos de la empresa).
Imprime si la tabla desborda horizontalmente (entonces salen dos capturas: izquierda y derecha).
TU eliges el filtro y pulsas Consultar.
"""
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from archivist_app.browser import open_context
from archivist_app.config import load_settings
from archivist_app.pages.comprobantes_page import ComprobantesPage
from archivist_app.pages.login_page import LoginPage    
from archivist_app.services.evidence import JS_BUSCAR_SCROLL, JS_LIMPIAR_SCROLL, capturar, guardar
from archivist_app.workflow import _rango

if __name__ == "__main__":
    s = load_settings()
    tmp = Path(tempfile.mkdtemp(prefix="archivist_evidencia_"))
    try:
        with open_context(headless=False) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                LoginPage(page).login(s.login_url, s.recibidos_url, s.portal_ruc, s.portal_password)
                listado = ComprobantesPage(page)
                print("== Login OK. Elige TU el filtro y pulsa Consultar.")
                listado.esperar_listado(avisar=lambda m: print(f"   Aviso: {m}"))
                desde, hasta = _rango(listado.leer_filtro())
                medidas = page.evaluate(JS_BUSCAR_SCROLL)
                page.evaluate(JS_LIMPIAR_SCROLL)
                print(f"== Desborde horizontal de la tabla: {medidas if medidas else 'ninguno (cabe)'}")
                capturas = capturar(page, s.portal_ruc, desde, hasta)
                rutas = guardar(tmp, capturas, datetime.now())
                for c, r in zip(capturas, rutas):
                    print(f"== {c.nombre}: {len(c.datos) // 1024} KB")
                os.startfile(rutas[0].parent)  # solo Windows
            except Exception as e:
                print(f"ERROR ({type(e).__name__}): {e}")
            input("Enter para cerrar y borrar las capturas temporales...")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)