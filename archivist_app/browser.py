import logging
import os
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from playwright.sync_api import Browser, BrowserContext, sync_playwright

from archivist_app.config import AUTH_DIR, DEFAULT_TIMEOUT_MS
from archivist_app.exceptions import ConfigError

log = logging.getLogger(__name__)

_EDGE_CANDIDATES = (
    Path(os.getenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.getenv("PROGRAMFILES", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
)

def _find_edge() -> Path:
    for ruta in _EDGE_CANDIDATES:
        if ruta.is_file():
            return ruta
    raise ConfigError("No se encontro Microsoft Edge en las rutas estandar de instalacion")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_port(port: int, proc: subprocess.Popen, timeout_s: float = 20.0) -> None:
    """Espera el puerto de depuracion. Se usa socket (no HTTP) para que un proxy del
    sistema no intercepte 127.0.0.1."""
    limite = time.monotonic() + timeout_s
    while time.monotonic() < limite:
        if proc.poll() is not None:
            # Caso tipico: ya habia un Edge abierto con este mismo perfil; el proceso
            # nuevo le cede el control y termina de inmediato sin abrir el puerto.
            raise ConfigError(
                f"Edge termino al arrancar (codigo {proc.returncode}). Si hay otra ventana "
                "de Edge abierta con el perfil de Archivist, cierrela y reintente."
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.25)
    raise ConfigError(f"Edge no abrio el puerto de depuracion {port} en {timeout_s:.0f} s")


def _cerrar_edge(browser: Browser, proc: subprocess.Popen) -> None:
    """Cierre ordenado: Edge guarda las cookies del perfil al salir, y de eso depende
    que la sesion sobreviva entre ejecuciones."""
    try:
        browser.new_browser_cdp_session().send("Browser.close")
    except Exception as e:
        log.warning("No se pudo cerrar Edge por CDP: %s", e)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        log.warning("Edge no cerro en 10 s; se termina el proceso")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@contextmanager
def open_context(headless: bool) -> Iterator[BrowserContext]:
    """Edge real lanzado como proceso normal, al que Playwright se conecta por CDP.
    La sesion sobrevive entre ejecuciones (perfil en .auth/).

    Historial (evidencia):
    - 2026-10-23: Firefox de Playwright no sirve: la pagina mostro "Could not connect to
      the reCAPTCHA service" y no llego a generar token. Descartado.
    - Edge lanzado por Playwright (launch_persistent_context) dio "Captcha incorrecta" de
      forma intermitente, aun sin --enable-automation.
    HIPOTESIS: lanzar Edge sin Playwright elimina las senales de automatizacion que bajan
    el puntaje de reCAPTCHA Enterprise. Sin confirmar: medir con diag_consultar y
    verificar navigator.webdriver (debe dar false o undefined).
    HIPOTESIS: la deteccion de CDP por parte de reCAPTCHA no afecta; sin confirmar.
    No agregar un solucionador de captcha (2Captcha) hasta tener esta medicion.
    """
    port = _free_port()
    args = [
        str(_find_edge()),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={AUTH_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        args.append("--headless=new")
    proc = subprocess.Popen(args)
    try:
        _wait_port(port, proc)
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            context = browser.contexts[0]
            context.set_default_timeout(DEFAULT_TIMEOUT_MS)
            try:
                yield context
            finally:
                _cerrar_edge(browser, proc)
    finally:
        if proc.poll() is None:
            proc.kill()