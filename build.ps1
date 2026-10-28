# Construye el paquete e instalador de Archivist. Desde la raiz del proyecto:  .\build.ps1
# Si una puerta falla, se detiene y NO deja un paquete a medias.
#
# La clave de 2Captcha NO se incluye en el instalador: la escribe TI en el asistente de instalacion.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Fallar($mensaje) {
    Write-Host "ERROR: $mensaje" -ForegroundColor Red
    exit 1
}

# El .exe es de ventana (sin consola): no imprime en stdout. Se pide su salida a un archivo (--salida)
# y se espera de verdad a que termine.
function Ejecutar-Exe($ruta, [string[]]$argumentos) {
    $tmp = Join-Path $env:TEMP ("archivist_" + [guid]::NewGuid().ToString("N") + ".txt")
    $lista = $argumentos + @("--salida", ('"' + $tmp + '"'))
    $p = Start-Process -FilePath $ruta -ArgumentList $lista -Wait -PassThru
    $texto = ""
    if (Test-Path $tmp) { $texto = (Get-Content $tmp -Raw -Encoding UTF8).Trim() }
    Remove-Item $tmp -ErrorAction SilentlyContinue
    return [pscustomobject]@{ Codigo = $p.ExitCode; Texto = $texto }
}

$version = (py -c "from archivist_app import __version__; print(__version__)").Trim()
if (-not $version) { Fallar "No se pudo leer la version (archivist_app/__init__.py)" }
Write-Host "== Archivist $version"

# 0) Antes de gastar minutos: el instalador y la clave de 2Captcha deben estar bien planteados
$iss = Join-Path $PSScriptRoot "installer\archivist.iss"
if (-not (Test-Path $iss) -or (Get-Item $iss).Length -lt 500) { Fallar "installer\archivist.iss esta vacio o no existe" }
if (Select-String -Path $iss -Pattern "PEGUE" -Quiet) { Fallar "El .iss conserva el marcador PEGUE: falta el AppId" }
if (Select-String -Path $iss -Pattern "2596502A-6DB7-4DEA-AEE8-2C4887455C90" -Quiet) { Fallar "El .iss usa el AppId de Docket" }

if (-not (Select-String -Path $iss -Pattern "CAPTCHA_API_KEY" -Quiet)) {
    Fallar "El .iss no escribe CAPTCHA_API_KEY en el .env: el programa instalado no podria resolver el captcha"
}

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

# 4) Humo del ejecutable: arranca y dice su version (si faltara un modulo, aqui se cae)
$r = Ejecutar-Exe $exe @("--version")
if ($r.Codigo -ne 0 -or $r.Texto -notmatch [regex]::Escape($version)) {
    Fallar "El ejecutable no arranca bien. Codigo: $($r.Codigo). Salida: $($r.Texto)"
}
Write-Host "Ejecutable: $($r.Texto)"

# 4b) Verificacion del paquete: Edge, los avisos de Windows y los recursos (iconos) deben estar. La configuracion puede
#     faltar en esta maquina (el ejecutable lee %APPDATA%\Archivist\.env), asi que no se exige.
$env:ARCHIVIST_SIN_PAUSA = "1"   # que ninguna falla deje la ventana esperando una tecla
$v = Ejecutar-Exe $exe @("--verificar")
Remove-Item Env:ARCHIVIST_SIN_PAUSA
foreach ($linea in @("[OK   ] Microsoft Edge", "[OK   ] Avisos de Windows", "[OK   ] Recursos")) {
    if ($v.Texto -notmatch [regex]::Escape($linea)) {
        Fallar "La verificacion del paquete no paso (falta '$linea'):`n$($v.Texto)"
    }
}

# 5) Guarda de seguridad: el paquete jamas debe llevar credenciales ni sesion
$peligrosos = Get-ChildItem $carpeta -Recurse -Force | Where-Object { $_.Name -in @(".env", ".auth") }
if ($peligrosos) { Fallar "El paquete contiene credenciales o sesion: $($peligrosos.FullName -join ', ')" }

# 6) Plantilla de configuracion y manual de usuario dentro del paquete (el PDF si existe; si no, el .docx)
Copy-Item (Join-Path $PSScriptRoot ".env.example") (Join-Path $carpeta ".env.example")
$manual = @("docs\Archivist_Manual_de_Usuario.pdf", "docs\Archivist_Manual_de_Usuario.docx") |
    ForEach-Object { Join-Path $PSScriptRoot $_ } | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($manual) { Copy-Item $manual $carpeta } else { Write-Host "AVISO: falta el manual en docs\" -ForegroundColor Yellow }

# 7) Zip y huella SHA256 (para comprobar en la otra maquina que es el mismo archivo). El paquete no lleva ninguna clave.
New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot "dist_installer") | Out-Null
$zip = Join-Path $PSScriptRoot "dist_installer\Archivist-$version-win64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path (Join-Path $carpeta "*") -DestinationPath $zip
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash
Write-Host ""
Write-Host "OK: $zip" -ForegroundColor Green
Write-Host "SHA256: $hash"

# 8) Instalador de Inno Setup, a partir de dist\Archivist
$candidatos = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)
$iscc = $candidatos | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { $iscc = $cmd.Source }
}
if (-not $iscc) { Fallar "No se encontro Inno Setup (ISCC.exe). Instalalo o agrega su carpeta al PATH." }

$isccArgs = @("/DAppVersion=$version")

& $iscc @isccArgs $iss
if ($LASTEXITCODE -ne 0) { Fallar "Inno Setup fallo" }
$setup = Join-Path $PSScriptRoot "dist_installer\Archivist-Setup-$version.exe"
if (-not (Test-Path $setup)) { Fallar "No se genero $setup" }
Write-Host "OK: $setup" -ForegroundColor Green
Write-Host "SHA256 instalador: $((Get-FileHash $setup -Algorithm SHA256).Hash)"