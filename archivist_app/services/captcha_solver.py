"""Cliente minimo de 2Captcha para reCAPTCHA Enterprise.

HTTP con urllib y la verificacion TLS delegada al almacen de certificados de Windows
(truststore). Confirmado en la red de oficina (2026-10-22): hay inspeccion TLS y el
contexto por defecto de Python 3.14 falla con "CERTIFICATE_VERIFY_FAILED: Missing
Authority Key Identifier", porque exige extensiones que el certificado del proxy no trae.
A 2Captcha solo viaja la sitekey, la URL de la pagina (sin query ni ;jsessionid) y el
action. Nunca cookies, RUC ni clave del portal.
"""
import json
import ssl
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

import truststore

_CONTEXTO_TLS = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

API_IN = "https://2captcha.com/in.php"
API_RES = "https://2captcha.com/res.php"
ESPERA_INICIAL_S = 15
SONDEO_S = 5
TIMEOUT_S = 150
MIN_SCORE_V3 = 0.7  # si tarda mucho o da ERROR_CAPTCHA_UNSOLVABLE, bajarlo a 0.3


class CaptchaSolverError(Exception):
    """2Captcha rechazo la tarea o no entrego el token a tiempo."""


def url_publica(url: str) -> str:
    """Host y ruta, sin query ni ';jsessionid': no se envia nada de la sesion a un tercero."""
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}{p.path.split(';')[0]}"


def _llamar(base: str, params: dict) -> dict:
    try:
        with urlopen(f"{base}?{urlencode(params)}", timeout=30, context=_CONTEXTO_TLS) as r:
            return json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError) as e:
        # La URL no va en el mensaje: lleva la clave de API. El motivo
        # (URLError.reason: DNS, certificado TLS, timeout...) si, porque es lo
        # que permite saber que fallo.
        motivo = getattr(e, "reason", None) or e
        raise CaptchaSolverError(
            f"sin respuesta valida de 2Captcha ({type(e).__name__}: {str(motivo)[:160]})"
        ) from None


def resolver(api_key: str, sitekey: str, pagina: str, action: str, variante: str = "v3") -> str:
    """Devuelve el token. variante: 'v3' (por puntaje, con action) o 'invisible' (v2 Enterprise)."""
    params = {
        "key": api_key, "method": "userrecaptcha", "googlekey": sitekey,
        "pageurl": url_publica(pagina), "enterprise": 1, "json": 1,
    }
    if variante == "v3":
        params.update(version="v3", action=action, min_score=MIN_SCORE_V3)
    elif variante == "invisible":
        params["invisible"] = 1
    else:
        raise ValueError(f"variante desconocida: {variante!r}")

    envio = _llamar(API_IN, params)
    if envio.get("status") != 1:
        raise CaptchaSolverError(f"2Captcha rechazo la tarea: {envio.get('request')}")
    tarea = envio["request"]

    time.sleep(ESPERA_INICIAL_S)
    fin = time.time() + TIMEOUT_S
    while time.time() < fin:
        r = _llamar(API_RES, {"key": api_key, "action": "get", "id": tarea, "json": 1})
        if r.get("status") == 1:
            return r["request"]
        if r.get("request") != "CAPCHA_NOT_READY":  # asi lo escribe 2Captcha
            raise CaptchaSolverError(f"2Captcha fallo: {r.get('request')}")
        time.sleep(SONDEO_S)
    raise CaptchaSolverError(f"2Captcha no entrego el token en {TIMEOUT_S} s")