"""Excepciones del proyecto. Todas heredan de SriError."""


class SriError(Exception):
    """Base de todos los errores controlados de la aplicación."""


class ConfigError(SriError):
    """Falta o es inválida la configuración (.env, rutas)."""


class LoginError(SriError):
    """No se pudo iniciar sesión o la sesión se perdió."""


class PortalError(SriError):
    """El portal no respondió como se esperaba (HTML cambiado, tabla ausente, etc.)."""


class IncompleteBatchError(SriError):
    """El lote no se pudo completar; con 'todo o nada' no se guarda nada."""
