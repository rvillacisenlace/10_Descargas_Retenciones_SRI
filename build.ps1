# Construye el paquete de Archivist (carpeta + zip). Desde la raíz del proyecto:  .\build.ps1
# Si una puerta falla, se detiene y NO deja un paquete a medias.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Fallar($mensaje) {
    Write-Host "ERROR: $mensaje" -ForegroundColor Red
    exit 1
}

$version = (py -c "from archivist_app import __version__; print(__version__)").Trim()
if (-not $version) { Fallar "No se pudo leer la version (archivist_app/__init__.py)" }
Write-Host "== Archivist $version"

# 1) Entorno limpio: asi no se empaqueta por accidente nada que no sea del proyecto
if (Test-Path .venv-build) { Remove-Item .venv-build -Recurse -Force }
py -m venv .venv-build
if ($LASTEXITCODE -ne 0) { Fallar "No se pudo crear el entorno .venv-build" }
$py = Join-Path $PSScriptRoot ".venv-build\Scripts\python.exe"
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { Fallar "No se pudieron instalar las dependencias" }

# 2) Puerta: si las pruebas fallan, no se empaqueta
& $py -m pytest tests -q
if ($LASTEXITCODE -ne 0) { Fallar "Las pruebas fallan: no se empaqueta" }

# 2b) Recursos graficos: sin ellos el .exe saldria sin icono y los avisos sin imagen
foreach ($recurso in @("assets\archivist.ico", "assets\archivist_256.png")) {
    if (-not (Test-Path (Join-Path $PSScriptRoot $recurso))) { Fallar "Falta $recurso" }
}
try {   # informativo: Windows se ve bien con un .ico que incluya 16, 32, 48 y 256 px
    $bytes = [System.IO.File]::ReadAllBytes((Join-Path $PSScriptRoot "assets\archivist.ico"))
    $cuantos = [BitConverter]::ToUInt16($bytes, 4)
    $tamanos = 0..($cuantos - 1) | ForEach-Object {
        $ancho = if ($bytes[6 + 16 * $_] -eq 0) { 256 } else { $bytes[6 + 16 * $_] }
        "${ancho}px"
    }
    Write-Host "Icono: $cuantos tamanos ($($tamanos -join ', '))"
    if ($cuantos -lt 4) { Write-Host "AVISO: se recomienda un .ico con 16, 32, 48 y 256 px" -ForegroundColor Yellow }
} catch { Write-Host "AVISO: no se pudo leer el .ico ($_)" -ForegroundColor Yellow }

# 3) Construccion
if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist)  { Remove-Item dist  -Recurse -Force }
& $py -m PyInstaller archivist.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { Fallar "PyInstaller fallo" }
$carpeta = Join-Path $PSScriptRoot "dist\Archivist"
$exe = Join-Path $carpeta "Archivist.exe"
if (-not (Test-Path $exe)) { Fallar "No se genero $exe" }

# 4) Humo del ejecutable: arranca e imprime su version (si faltara un modulo, aqui se cae)
$salida = (& $exe --version) -join " "
if ($LASTEXITCODE -ne 0 -or $salida -notmatch [regex]::Escape($version)) {
    Fallar "El ejecutable no arranca bien. Salida: $salida"
}

# 4b) Verificacion del paquete: Edge, los avisos de Windows y los recursos (iconos) deben estar. La configuracion puede
#     faltar en esta maquina (el ejecutable lee %APPDATA%\Archivist\.env), asi que no se exige.
$env:ARCHIVIST_SIN_PAUSA = "1"   # que ninguna falla deje la ventana esperando una tecla
$verificacion = (& $exe --verificar) -join "`n"
Remove-Item Env:ARCHIVIST_SIN_PAUSA
foreach ($linea in @("[OK   ] Microsoft Edge", "[OK   ] Avisos de Windows", "[OK   ] Recursos")) {
    if ($verificacion -notmatch [regex]::Escape($linea)) {
        Fallar "La verificacion del paquete no paso (falta '$linea'):`n$verificacion"
    }
}

# 5) Guarda de seguridad: el paquete jamas debe llevar credenciales ni sesion
$peligrosos = Get-ChildItem $carpeta -Recurse -Force | Where-Object { $_.Name -in @(".env", ".auth") }
if ($peligrosos) { Fallar "El paquete contiene credenciales o sesion: $($peligrosos.FullName -join ', ')" }

# 6) Plantilla de configuracion y guia dentro del paquete
Copy-Item (Join-Path $PSScriptRoot ".env.example") (Join-Path $carpeta ".env.example")
$guia = Join-Path $PSScriptRoot "docs\Guia_Instalacion_y_Operacion_Archivist.docx"
if (Test-Path $guia) { Copy-Item $guia $carpeta } else { Write-Host "AVISO: falta la guia en docs\" -ForegroundColor Yellow }

# 7) Zip y huella SHA256 (para comprobar en la otra maquina que es el mismo archivo)
New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot "dist_installer") | Out-Null
$zip = Join-Path $PSScriptRoot "dist_installer\Archivist-$version-win64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path (Join-Path $carpeta "*") -DestinationPath $zip
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash
Write-Host ""
Write-Host "OK: $zip" -ForegroundColor Green
Write-Host "SHA256: $hash"