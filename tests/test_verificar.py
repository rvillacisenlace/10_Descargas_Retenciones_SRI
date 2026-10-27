from pathlib import Path

from archivist_app import verificar
from archivist_app.exceptions import ConfigError
from archivist_app.verificar import Resultado, ejecutar_verificacion, formatear


def test_edge_encontrado(monkeypatch):
    monkeypatch.setattr(verificar.browser, "_find_edge", lambda: Path("C:/Edge/msedge.exe"))
    r = verificar._edge()
    assert r.ok and "msedge.exe" in r.detalle


def test_edge_ausente(monkeypatch):
    def falla():
        raise ConfigError("No se encontro Microsoft Edge en las rutas estandar de instalacion")

    monkeypatch.setattr(verificar.browser, "_find_edge", falla)
    r = verificar._edge()
    assert not r.ok and "No se encontro Microsoft Edge" in r.detalle


def test_configuracion_valida(monkeypatch):
    monkeypatch.setattr(verificar.config, "load_settings", lambda: object())
    monkeypatch.setattr(verificar.config, "ENV_FILE", Path("C:/Users/x/AppData/Roaming/Archivist/.env"))
    r = verificar._configuracion()
    assert r.ok and r.detalle.endswith(".env")


def test_configuracion_incompleta_muestra_nombres_no_valores(monkeypatch):
    def falla():
        raise ConfigError("Faltan variables en C:/x/.env: PORTAL_RUC, PORTAL_PASSWORD")

    monkeypatch.setattr(verificar.config, "load_settings", falla)
    r = verificar._configuracion()
    assert not r.ok and "PORTAL_RUC" in r.detalle


def test_carpeta_escribible(tmp_path):
    r = verificar._escritura("Carpeta de salida", tmp_path / "nueva")
    assert r.ok and (tmp_path / "nueva").is_dir()
    assert not any((tmp_path / "nueva").iterdir())  # no deja el archivo de prueba


def test_carpeta_que_no_se_puede_crear(tmp_path):
    (tmp_path / "es_un_archivo").write_text("x")
    r = verificar._escritura("Carpeta de salida", tmp_path / "es_un_archivo" / "sub")
    assert not r.ok and "no se puede escribir" in r.detalle


def test_avisos_disponibles_y_ausentes():
    assert verificar._avisos("json").ok
    r = verificar._avisos("modulo_que_no_existe_xyz")
    assert not r.ok and "modulo_que_no_existe_xyz" in r.detalle


def test_formato_y_codigo_de_salida_todo_bien():
    salida = []
    cs = (lambda: Resultado("A", True, "uno"), lambda: Resultado("B", True, "dos"))
    assert ejecutar_verificacion(salida.append, cs) == 0
    assert "[OK   ] A: uno" in salida[0] and "Todo listo para usar." in salida[0]


def test_con_una_falla_el_codigo_es_1_y_lo_dice():
    salida = []
    cs = (lambda: Resultado("A", True, "uno"), lambda: Resultado("B", False, "no esta"))
    assert ejecutar_verificacion(salida.append, cs) == 1
    assert "[FALLA] B: no esta" in salida[0] and "puntos por corregir" in salida[0]


def test_la_verificacion_corre_todas_las_comprobaciones_aunque_una_falle():
    vistas = []

    def a():
        vistas.append("a")
        return Resultado("A", False, "x")

    def b():
        vistas.append("b")
        return Resultado("B", True, "y")

    assert len(verificar.verificar((a, b))) == 2 and vistas == ["a", "b"]


def test_las_comprobaciones_por_defecto_no_contactan_el_portal():
    nombres = [c.__name__ for c in verificar.COMPROBACIONES]
    assert nombres == ["_edge", "_configuracion", "_carpeta_salida", "_carpeta_perfil", "_avisos", "_recursos"]


def test_recursos_presentes_y_ausentes(monkeypatch, tmp_path):
    icono = tmp_path / "assets" / "archivist_256.png"
    monkeypatch.setattr(verificar.config, "ICONO_AVISOS", icono)
    r = verificar._recursos()
    assert not r.ok and "archivist_256.png" in r.detalle
    icono.parent.mkdir()
    icono.write_bytes(b"\x89PNG")
    r = verificar._recursos()
    assert r.ok and r.detalle == str(icono.parent)