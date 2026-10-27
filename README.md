<img src="assets/archivist_256.png" width="96" alt="Archivist">

# Archivist

Archivist descarga los comprobantes electrónicos recibidos desde el portal del SRI (PDF y XML) y los archiva ordenados por fecha y tipo, con una captura de evidencia de cada consulta. Proyecto hermano de Docket.

**Versión 1.0.0.** Para instalar y operar el programa empaquetado, vea la guía en `docs/Guia_Instalacion_y_Operacion_Archivist.docx`.

## Cómo funciona

1. Inicia sesión en el portal (un solo intento, para no arriesgar el bloqueo de la cuenta).
2. Avisa al usuario con una notificación de Windows: él elige el tipo y la fecha y pulsa Consultar (el portal usa reCAPTCHA).
3. Lee y valida el listado, guarda la evidencia y descarga XML y PDF **todo o nada**: si algo falla, no queda un lote parcial.

Salida en `Documentos\Archivist`: `AAAA\MM\DD\<Tipo>\<número>_<RUC emisor>.pdf|xml` y `Evidencias\AAAA-MM-DD_HHMMSS\pagina-01.png`.

## Limitaciones de la versión 1.0.0

- Hasta 50 filas por consulta (una página del listado); con más, se detiene con un aviso y no descarga nada. La paginación está pendiente.
- La consulta la dispara el usuario; no es totalmente desatendido.
- Un tipo de comprobante por ejecución. El tipo verificado de punta a punta es Comprobante de retención.

## Desarrollo

Requisitos: Windows, Python 3.14 (lanzador `py`) y Microsoft Edge.

```powershell
py -m pip install -r requirements-dev.txt
copy .env.example .env      # y complete PORTAL_RUC y PORTAL_PASSWORD
py -m pytest tests -q       # la suite debe quedar toda en verde
py -m main                  # corrida real
```

Opciones: `py -m main --version` y `py -m main --verificar` (comprueba Edge, configuración, carpetas, avisos y recursos sin tocar el portal).

Diagnósticos en `scripts/` (`diag_*`): sirven para medir el portal antes de cambiar código. Imprimen solo nombres y longitudes, nunca valores.

## Empaquetado

```powershell
.\build.ps1
```

Crea un entorno limpio, **corre las pruebas** (si fallan, no empaqueta), construye con PyInstaller en modo carpeta (`archivist.spec`), prueba el ejecutable (`--version` y `--verificar`), comprueba que no lleve credenciales y deja `dist_installer\Archivist-<versión>-win64.zip` con su huella SHA256. Requiere `assets\archivist.ico` y `assets\archivist_256.png`.

El ejecutable no está firmado: SmartScreen, un antivirus o Smart App Control pueden bloquearlo (ver la guía). El zip se distribuye por canales internos; no se publica en este repositorio.

## Reglas del repositorio

Nunca versionar `.env`, `.auth/`, comprobantes, capturas ni `dist/` y `build/`. Las únicas imágenes versionadas son las de `assets/`. Los tests usan datos ficticios.