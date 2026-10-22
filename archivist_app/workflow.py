"""Orquesta el orden de los pasos y devuelve RunResult.

Orden: config -> navegador -> login -> filtro + aviso -> espera del usuario (máx. 10 min)
-> recorrer páginas + evidencias -> descarga todo o nada -> notificar resumen.
No sabe cómo se interactúa con el portal (eso es de pages/).
"""
