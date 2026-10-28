<img src="assets/archivist_256.png" width="96" alt="Archivist">

# Archivist

Archivist descarga los comprobantes electrónicos recibidos desde el portal del SRI (PDF y XML) y los archiva ordenados por fecha y tipo, con una captura de evidencia de cada consulta. Proyecto hermano de Docket y empaquetado con la misma metodología (`METODOLOGIA_Empaquetado.md`).

**Versión 1.0.0.** Documentación en `docs/`: el **manual de usuario** (`Archivist_Manual_de_Usuario`) para quien lo usa y la **documentación técnica** (`Archivist_Documentacion_Tecnica`) para TI y desarrollo.

## Cómo funciona

1. Inicia sesión en el portal (un solo intento, para no arriesgar el bloqueo de la cuenta).
2. Avisa al usuario con una notificación de Windows: él elige el tipo y la fecha y pulsa Consultar (el portal usa reCAPTCHA).
3. Lee y valida el listado, guarda la evidencia y descarga XML y PDF **todo o nada**: si algo falla, no queda un lote parcial.

Salida en `Documentos\Archivist`: `AAAA\MM\DD\<Tipo>\<número>_<RUC emisor>.pdf|xml` y `Evidencias\AAAA-MM-DD_HHMMSS\pagina-01.png`.

## Limitaciones de la versión 1.0.0

- Hasta 50 filas por consulta (una página del listado); con más, se detiene con un aviso y no descarga nada. La paginación está pendiente.
- La consulta la dispara el usuario; no es totalmente desatendido.
- Un tipo de comprobante por ejecución. El tipo verificado de punta a punta es Comprobante de retención.

## Instalación (usuarios)

Se entrega `Archivist-Setup-<versión>.exe`: se instala por usuario, sin administrador, y pide el RUC y la clave del portal. Al actualizar no vuelve a pedirlos; al desinstalar borra la configuración y la sesión, pero **nunca** los comprobantes. Despliegue masivo y detalles: documentación técnica, secciones 8 y 9.

## Desarrollo

Requisitos: Windows, Python 3.14 (lanzador `py`) y Microsoft Edge.

```powershell
py -m pip install -r requirements-dev.txt
copy .env.example .env      # y complete PORTAL_RUC y PORTAL_PASSWORD
py -m pytest tests -q       # la suite debe quedar toda en verde
py -m main                  # corrida real
```

Opciones: `py -m main --version` y `py -m main --verificar` (comprueba Edge, configuración, carpetas, avisos y recursos sin tocar el portal); `--salida RUTA` escribe su resultado en un archivo. El ejecutable no tiene consola: sin `--salida`, el resultado sale en un cuadro de mensaje.

Por política de TI no se escriben registros en disco. Para diagnosticar, con autorización: `ARCHIVIST_LOG_ARCHIVO=1`.

Diagnósticos en `scripts/` (`diag_*`): sirven para medir el portal antes de cambiar código. Imprimen solo nombres y longitudes, nunca valores.

## Empaquetado

Requiere Inno Setup 7 (o 6) con el idioma español, además de las dependencias de desarrollo. Procedimiento de cada versión en `METODOLOGIA_Empaquetado.md`; en corto: subir `__version__` en `archivist_app\__init__.py`, **commit y etiqueta** (`git tag v1.0.0`), y

```powershell
.\build.ps1
```

Crea un entorno limpio, **corre las pruebas** (si fallan, no empaqueta), construye con PyInstaller (`--onedir --noconsole`), prueba el ejecutable, comprueba que no lleve credenciales, compila el instalador y deja `dist_installer\Archivist-Setup-<versión>.exe` con su SHA256 y el commit del que sale. Antes de repartir: probarlo en un equipo limpio (instalación **y** actualización) y coordinar con TI, porque el instalador no está firmado.

El `AppId` de `installer\archivist.iss` no se cambia nunca (una prueba lo fija).

## Reglas del repositorio

Nunca versionar `.env`, `.auth/`, comprobantes, capturas ni `build/`, `dist/`, `dist_installer/`, `.venv-build/` ni `*.spec`. Las únicas imágenes versionadas son las de `assets/` y los PDF de `docs/`. Los tests usan datos ficticios.