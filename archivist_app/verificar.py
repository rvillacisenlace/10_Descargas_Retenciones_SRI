"""Verificación previa (--verificar): comprueba el equipo SIN contactar el portal ni la cuenta.

Pensada para el primer arranque en una máquina nueva: un fallo de entorno (Edge ausente,
configuración incompleta, carpeta sin permisos) se ve aquí y no a mitad de una corrida real.
Muestra nombres y rutas, nunca valores de la configuración.
"""

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from archivist_app import browser
from archivist_app import config
from archivist_app.exceptions import ConfigError


@dataclass(frozen=True)
class Resultado:
    nombre: str
    ok: bool
    detalle: str


def _edge() -> Resultado:
    try:
        return Resultado("Microsoft Edge", True, str(browser._find_edge()))
    except ConfigError as e:
        return Resultado("Microsoft Edge", False, str(e))


def _configuracion() -> Resultado:
    try:
        config.load_settings()  # valida variables y URLs; crea las carpetas de salida y de perfil
    except ConfigError as e:
        return Resultado("Configuración", False, str(e))
    return Resultado("Configuración", True, str(config.ENV_FILE))


def _escritura(nombre: str, carpeta: Path) -> Resultado:
    prueba = carpeta / ".verificar.tmp"
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        prueba.write_bytes(b"ok")
        prueba.unlink()
    except OSError as e:
        return Resultado(nombre, False, f"{carpeta} no se puede escribir ({type(e).__name__})")
    return Resultado(nombre, True, str(carpeta))


def _carpeta_salida() -> Resultado:
    return _escritura("Carpeta de salida", config.OUTPUT_DIR)


def _carpeta_perfil() -> Resultado:
    return _escritura("Carpeta de sesión", config.AUTH_DIR)


def _avisos(modulo: str = "winotify") -> Resultado:
    try:
        importlib.import_module(modulo)
    except ImportError:
        return Resultado("Avisos de Windows", False, f"falta el módulo {modulo}")
    return Resultado("Avisos de Windows", True, "disponibles")


def _recursos() -> Resultado:
    """En el paquete confirma que los iconos viajaron dentro; sin ellos los avisos salen sin imagen."""
    icono = config.ICONO_AVISOS
    if icono.is_file():
        return Resultado("Recursos (iconos)", True, str(icono.parent))
    return Resultado("Recursos (iconos)", False, f"falta {icono.name} en {icono.parent}")


COMPROBACIONES: tuple[Callable[[], Resultado], ...] = (
    _edge, _configuracion, _carpeta_salida, _carpeta_perfil, _avisos, _recursos,
)


def verificar(comprobaciones: tuple[Callable[[], Resultado], ...] | None = None) -> list[Resultado]:
    return [c() for c in (comprobaciones or COMPROBACIONES)]


def formatear(resultados: list[Resultado]) -> str:
    lineas = [f"[{'OK' if r.ok else 'FALLA':5}] {r.nombre}: {r.detalle}" for r in resultados]
    lineas.append("")
    lineas.append("Todo listo para usar." if all(r.ok for r in resultados)
                  else "Hay puntos por corregir antes de usarlo (líneas FALLA).")
    return "\n".join(lineas)


def ejecutar_verificacion(salida: Callable[[str], None] = print,
                          comprobaciones: tuple[Callable[[], Resultado], ...] | None = None) -> int:
    resultados = verificar(comprobaciones)
    salida(formatear(resultados))
    return 0 if all(r.ok for r in resultados) else 1