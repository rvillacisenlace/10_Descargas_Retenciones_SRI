from datetime import datetime

import pytest

from archivist_app.exceptions import EvidenceError
from archivist_app.services import evidence
from archivist_app.services.evidence import (
    ESTILO_CAPTURA, JS_BUSCAR_SCROLL, JS_LIMPIAR_SCROLL, JS_PONER_BANNER, JS_QUITAR_BANNER,
    JS_SCROLL_X, Captura, capturar, guardar, texto_banner,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"datos-de-la-imagen"
AHORA = datetime(2026, 10, 21, 12, 16, 59)
ANCHO = {"ancho": 2400, "visible": 1000}


class FakePage:
    """Simula Playwright; NO toma capturas reales ni toca el portal.
    llamadas registra el orden exacto de lo que se le pide a la página."""

    def __init__(self, scroll=None, png=PNG, falla_captura_n=None, falla_quitar=False, falla_buscar=False):
        self.scroll, self.png = scroll, png
        self.falla_captura_n, self.falla_quitar, self.falla_buscar = falla_captura_n, falla_quitar, falla_buscar
        self.llamadas, self.banners = [], []

    def evaluate(self, js, *args):
        if js == JS_BUSCAR_SCROLL:
            self.llamadas.append("buscar")
            if self.falla_buscar:
                raise RuntimeError("Execution context was destroyed")
            return self.scroll
        if js == JS_PONER_BANNER:
            self.llamadas.append("poner")
            self.banners.append(args[0])
        elif js == JS_QUITAR_BANNER:
            self.llamadas.append("quitar")
            if self.falla_quitar:
                raise RuntimeError("Target closed")
        elif js == JS_SCROLL_X:
            self.llamadas.append(f"scroll({args[0]})")
        else:
            assert js == JS_LIMPIAR_SCROLL
            self.llamadas.append("limpiar")

    def screenshot(self, **opciones):
        assert opciones == {"full_page": True, "type": "png", "style": ESTILO_CAPTURA}
        self.llamadas.append("captura")
        if self.falla_captura_n == self.llamadas.count("captura"):
            raise TimeoutError("la pagina no responde")
        return self.png


# --- formato: idéntico al de las capturas de Docket ----------------------------------------

def test_texto_del_banner_con_lado_como_en_docket():
    assert texto_banner("docket_pagina-01-derecha", "usuario@ejemplo.ec", "2026-10-21", "2026-10-21",
                        1, "Derecha", AHORA) == (
        "Evidencia: docket_pagina-01-derecha | Usuario: usuario@ejemplo.ec | "
        "Consulta 2026-10-21 a 2026-10-21 | Página 1 | Derecha | 2026-10-21 12:16:59"
    )
    assert texto_banner("docket_pagina-01", "usuario@ejemplo.ec", "2026-10-21", "2026-10-21",
                        1, "Izquierda", AHORA).endswith("| Página 1 | Izquierda | 2026-10-21 12:16:59")


def test_texto_del_banner_sin_lado_omite_ese_campo():
    assert texto_banner("archivist_pagina-01", "1790000000001", "2026-10-01", "2026-10-31", 1, None, AHORA) == (
        "Evidencia: archivist_pagina-01 | Usuario: 1790000000001 | "
        "Consulta 2026-10-01 a 2026-10-31 | Página 1 | 2026-10-21 12:16:59"
    )


# --- capturar: la tabla cabe ---------------------------------------------------------------

def test_si_la_tabla_cabe_se_toma_una_sola_captura_sin_lado():
    page = FakePage(scroll=None)
    caps = capturar(page, "1790000000001", "2026-10-23", "2026-10-23", ahora=AHORA)
    assert caps == [Captura("pagina-01.png", PNG)]
    assert page.llamadas == ["buscar", "poner", "captura", "quitar"]
    assert page.banners == [
        "Evidencia: archivist_pagina-01 | Usuario: 1790000000001 | Consulta 2026-10-23 a 2026-10-23 | "
        "Página 1 | 2026-10-21 12:16:59"
    ]


def test_el_numero_de_pagina_lleva_dos_digitos_en_el_nombre_y_uno_en_el_banner():
    caps = capturar(FakePage(), "u", "a", "b", pagina=12, ahora=AHORA)
    assert caps[0].nombre == "pagina-12.png"


# --- capturar: la tabla desborda ----------------------------------------------------------

def test_si_la_tabla_desborda_se_toman_izquierda_y_derecha_con_la_misma_hora():
    page = FakePage(scroll=ANCHO)
    caps = capturar(page, "u", "2026-10-23", "2026-10-23", ahora=AHORA)
    assert [c.nombre for c in caps] == ["pagina-01.png", "pagina-01-derecha.png"]
    assert page.llamadas == [
        "buscar", "scroll(0)", "poner", "captura", "quitar",
        "scroll(2400)", "poner", "captura", "quitar", "limpiar",
    ]
    assert "| Página 1 | Izquierda | 2026-10-21 12:16:59" in page.banners[0]
    assert "archivist_pagina-01-derecha |" in page.banners[1]
    assert "| Página 1 | Derecha | 2026-10-21 12:16:59" in page.banners[1]


def test_si_falla_la_segunda_mitad_se_restaura_la_pagina_y_el_error_es_controlado():
    page = FakePage(scroll=ANCHO, falla_captura_n=2)
    with pytest.raises(EvidenceError, match="TimeoutError") as e:
        capturar(page, "u", "a", "b", ahora=AHORA)
    assert page.llamadas[-2:] == ["quitar", "limpiar"]  # ni banner ni desplazamiento quedan puestos
    assert "la pagina no responde" not in str(e.value)  # el mensaje no arrastra detalles


# --- errores comunes -------------------------------------------------------------------------

def test_si_la_captura_falla_el_banner_se_quita_igual():
    page = FakePage(falla_captura_n=1)
    with pytest.raises(EvidenceError, match="TimeoutError"):
        capturar(page, "u", "a", "b", ahora=AHORA)
    assert page.llamadas == ["buscar", "poner", "captura", "quitar"]


def test_si_no_se_puede_quitar_el_banner_la_captura_buena_no_se_pierde():
    caps = capturar(FakePage(falla_quitar=True), "u", "a", "b", ahora=AHORA)
    assert caps[0].datos == PNG


def test_error_al_medir_el_desborde_es_controlado():
    with pytest.raises(EvidenceError, match="RuntimeError"):
        capturar(FakePage(falla_buscar=True), "u", "a", "b", ahora=AHORA)


def test_una_imagen_que_no_es_png_se_rechaza():
    with pytest.raises(EvidenceError, match="PNG"):
        capturar(FakePage(png=b"<html>error"), "u", "a", "b", ahora=AHORA)


# --- guardar: una carpeta por corrida -----------------------------------------------------------

INICIO = datetime(2026, 10, 21, 12, 16, 22)


def test_guardar_usa_una_carpeta_por_corrida_con_la_hora_de_inicio(tmp_path):
    rutas = guardar(tmp_path, [Captura("pagina-01.png", PNG), Captura("pagina-01-derecha.png", PNG)], INICIO)
    carpeta = tmp_path / "Evidencias" / "2026-10-21_121622"
    assert rutas == [carpeta / "pagina-01.png", carpeta / "pagina-01-derecha.png"]
    assert all(r.read_bytes() == PNG for r in rutas)


def test_dos_corridas_no_se_mezclan(tmp_path):
    guardar(tmp_path, [Captura("pagina-01.png", PNG)], INICIO)
    guardar(tmp_path, [Captura("pagina-01.png", PNG)], datetime(2026, 10, 21, 15, 0, 0))
    assert sorted(p.name for p in (tmp_path / "Evidencias").iterdir()) == ["2026-10-21_121622", "2026-10-21_150000"]


def test_guardar_nunca_pisa_una_evidencia_existente(tmp_path):
    guardar(tmp_path, [Captura("pagina-01.png", PNG)], INICIO)
    with pytest.raises(EvidenceError, match="FileExistsError") as e:
        guardar(tmp_path, [Captura("pagina-01.png", PNG + b"distinta")], INICIO)
    assert (tmp_path / "Evidencias" / "2026-10-21_121622" / "pagina-01.png").read_bytes() == PNG
    assert str(tmp_path) not in str(e.value)  # no muestra rutas


def test_guardar_error_de_disco_es_controlado(tmp_path):
    (tmp_path / "Evidencias").write_text("esto es un archivo, no una carpeta")
    with pytest.raises(EvidenceError):
        guardar(tmp_path, [Captura("pagina-01.png", PNG)], INICIO)


# --- el badge de reCAPTCHA no debe tapar datos de la captura ---------------------------------------

def test_la_captura_oculta_el_badge_de_recaptcha_solo_mientras_dura():
    # El estilo viaja en la propia llamada de captura: Playwright lo aplica y lo retira solo, así
    # que no queda nada que restaurar en la página (ni siquiera si la captura falla).
    assert ".grecaptcha-badge" in ESTILO_CAPTURA
    assert "visibility: hidden" in ESTILO_CAPTURA and "!important" in ESTILO_CAPTURA
    assert "display" not in ESTILO_CAPTURA  # visibility, no display: no cambia el diseño