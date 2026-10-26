"""Los scripts no se importan en las pruebas (abren el navegador y el portal), así que un error
de sintaxis puede llegar a GitHub sin que nada lo vea. Este test solo parsea cada .py del
proyecto; no ejecuta nada."""

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETAS = ("archivist_app", "scripts", "tests")


def archivos_py() -> list[Path]:
    archivos = [RAIZ / "main.py"]
    for carpeta in CARPETAS:
        archivos += sorted((RAIZ / carpeta).rglob("*.py"))
    return archivos


def test_todo_el_codigo_es_sintacticamente_valido():
    errores = []
    for ruta in archivos_py():
        try:
            ast.parse(ruta.read_text(encoding="utf-8-sig"), filename=str(ruta))
        except SyntaxError as e:
            errores.append(f"{ruta.relative_to(RAIZ)}:{e.lineno}: {e.msg}")
    assert not errores, "Errores de sintaxis:\n" + "\n".join(errores)