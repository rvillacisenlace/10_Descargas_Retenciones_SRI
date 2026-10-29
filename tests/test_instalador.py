"""Pruebas ESTATICAS del instalador y del empaquetado.

Leen installer/archivist.iss, .env.example, .gitignore, archivist.spec y el icono. No ejecutan Inno Setup
ni tocan el equipo, asi que corren en cualquier maquina. No sustituyen probar el instalador en un equipo
limpio (instalar, actualizar, desinstalar): solo evitan que se pierda por accidente lo que ya se decidio.
"""
import re
import struct
from pathlib import Path

import pytest

from archivist_app import __version__

RAIZ = Path(__file__).resolve().parent.parent
APPID = "94F94631-CA7E-4F84-98E9-36980F88FE03"
APPID_DOCKET = "2596502A-6DB7-4DEA-AEE8-2C4887455C90"
VARIABLES_ENV = [
    "PORTAL_LOGIN_URL", "PORTAL_RECIBIDOS_URL", "PORTAL_RUC", "PORTAL_PASSWORD",
    "CAPTCHA_ENABLED", "CAPTCHA_API_KEY", "CAPTCHA_PROVIDER",
]


def _leer(ruta: str) -> str:
    return (RAIZ / ruta).read_text(encoding="utf-8-sig")  # el .env.example lleva BOM


@pytest.fixture(scope="module")
def iss() -> str:
    return _leer("installer/archivist.iss")


@pytest.fixture(scope="module")
def env_ejemplo() -> dict:
    valores = {}
    for linea in _leer(".env.example").splitlines():
        if "=" in linea and not linea.lstrip().startswith("#"):
            clave, valor = linea.split("=", 1)
            valores[clave.strip()] = valor.strip().strip("'")
    return valores


def _seccion(iss: str, nombre: str) -> str:
    m = re.search(rf"^\[{nombre}\]\s*$(.*?)(?=^\[|\Z)", iss, re.S | re.M)
    assert m, f"no existe la seccion [{nombre}]"
    return m.group(1)


# --- identidad del instalador -----------------------------------------------------------------

def test_el_script_del_instalador_existe_y_no_esta_vacio(iss):
    assert len(iss) > 2000


def test_el_appid_es_el_de_archivist_y_no_cambia(iss):
    m = re.search(r"^AppId=\{\{([0-9A-Fa-f-]{36})\}\s*$", iss, re.M)
    assert m, "no se encontro AppId"
    assert m.group(1).upper() == APPID  # cambiarlo haria que una version nueva no actualice la instalada


def test_el_appid_no_es_el_de_docket_ni_un_marcador_sin_rellenar(iss):
    assert APPID_DOCKET not in iss.upper()
    assert "PEGUE" not in iss.upper()


def test_se_instala_por_usuario_sin_pedir_administrador(iss):
    assert re.search(r"^PrivilegesRequired=lowest\s*$", iss, re.M)


def test_el_nombre_del_instalador_lleva_la_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
    assert "OutputBaseFilename=Archivist-Setup-{#AppVersion}" in _leer("installer/archivist.iss")


# --- el .env que escribe ------------------------------------------------------------------------

def test_el_instalador_pide_los_cuatro_datos(iss):
    assert iss.count("CredPage.Add(") == 4


def test_el_env_que_escribe_el_instalador_tiene_las_siete_variables_en_orden(iss):
    escritas = re.findall(r"Lines\[(\d)\] := '([A-Z_]+)=", iss)
    assert [(int(i), n) for i, n in escritas] == list(enumerate(VARIABLES_ENV))
    assert "SetArrayLength(Lines, 7)" in iss


def test_las_variables_del_instalador_existen_en_el_env_ejemplo(env_ejemplo):
    assert set(VARIABLES_ENV) <= set(env_ejemplo)


def test_las_direcciones_del_portal_del_instalador_son_las_del_env_ejemplo(iss, env_ejemplo):
    login = re.search(r'^\s*#define PortalLoginUrl "(.*)"\s*$', iss, re.M).group(1)
    recibidos = re.search(r'^\s*#define PortalRecibidosUrl "(.*)"\s*$', iss, re.M).group(1)
    assert login == env_ejemplo["PORTAL_LOGIN_URL"]
    assert recibidos == env_ejemplo["PORTAL_RECIBIDOS_URL"]


def test_los_datos_del_usuario_se_escriben_entre_comillas_simples(iss):
    for variable in ("PORTAL_RUC", "PORTAL_PASSWORD", "CAPTCHA_API_KEY"):
        assert re.search(rf"'{variable}=' \+ Q\(", iss), f"{variable} debe escribirse con Q(...)"


def test_la_clave_de_api_no_viaja_dentro_del_instalador(iss):
    assert not re.search(r"[A-Za-z0-9]{32,}", iss), "hay una cadena larga: ?una clave pegada en el .iss?"
    assert "CaptchaKey" not in iss


# --- instalacion silenciosa, actualizacion y desinstalacion ----------------------------------

def test_sin_asistente_no_se_crea_el_env(iss):
    # Con /VERYSILENT la pagina no se muestra y el RUC queda vacio: no se escribe nada.
    assert re.search(r"CurStep = ssPostInstall\) and \(not FileExists\(EnvPath\)\) and\s+\(Trim\(CredPage\.Values\[0\]\) <> ''\)", iss)


def test_una_actualizacion_no_pide_los_datos_ni_reemplaza_el_env(iss):
    assert re.search(r"Result := \(PageID = CredPage\.ID\) and FileExists\(EnvPath\);", iss)


def test_desinstalar_borra_configuracion_y_sesion_pero_no_los_comprobantes(iss):
    seccion = _seccion(iss, "UninstallDelete")
    rutas = set(re.findall(r'Name: "([^"]+)"', seccion))
    assert rutas == {r"{localappdata}\Archivist", r"{userappdata}\Archivist"}
    assert "userdocs" not in seccion.lower() and "documen" not in seccion.lower()


# --- icono, .gitignore y spec ---------------------------------------------------------------------

def test_el_icono_existe_con_los_tamanos_que_windows_necesita(iss):
    assert "SetupIconFile=..\\assets\\archivist.ico" in iss
    assert iss.count(r'IconFilename: "{app}\archivist.ico"') == 2  # menu Inicio y escritorio
    datos = (RAIZ / "assets" / "archivist.ico").read_bytes()
    cuantos = struct.unpack_from("<H", datos, 4)[0]
    tamanos = {datos[6 + 16 * i] or 256 for i in range(cuantos)}
    assert {16, 32, 48, 256} <= tamanos


def test_el_gitignore_protege_credenciales_sesion_y_compilaciones():
    lineas = [x.strip() for x in _leer(".gitignore").splitlines()]
    for patron in (".env", ".auth/", "build/", "dist/", "dist_installer/"):
        assert patron in lineas, f"falta {patron} en .gitignore"
    assert "*.spec" in lineas and "!archivist.spec" in lineas
    assert lineas.index("!archivist.spec") > lineas.index("*.spec")  # la excepcion va despues


def test_el_spec_esta_en_la_raiz_y_genera_un_ejecutable_sin_consola():
    assert (RAIZ / "archivist.spec").is_file()
    assert not (RAIZ / "installer" / "archivist.spec").exists()  # sus rutas relativas parten de su carpeta
    assert re.search(r"^\s*console=False,", _leer("archivist.spec"), re.M)