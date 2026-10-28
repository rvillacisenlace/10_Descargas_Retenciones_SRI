; Instalador de Archivist (Inno Setup 7; compatible con la 6.3 o superior).
; Metodologia: METODOLOGIA_Empaquetado.md. NO cambiar el AppId nunca: con el, una version nueva actualiza
; la instalada en lugar de instalarse como otro programa y dejar dos entradas en "Aplicaciones".
; Este archivo se guarda en UTF-8 con BOM: sin BOM, Inno Setup lee los acentos como ANSI.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
; Direcciones del portal que el instalador escribe en el .env. Deben coincidir con .env.example (lo
; comprueba tests/test_instalador.py). Para otro ambiente: /DPortalLoginUrl=... /DPortalRecibidosUrl=...
#ifndef PortalLoginUrl
  #define PortalLoginUrl "https://srienlinea.sri.gob.ec/auth/realms/Internet/protocol/openid-connect/auth?client_id=app-sri-claves-angular&redirect_uri=https%3A%2F%2Fsrienlinea.sri.gob.ec%2Fsri-en-linea%2F%2Fcontribuyente%2Fperfil&state=42efaa2b-c239-48c8-b148-d8209155df53&nonce=2e55581c-529c-47dd-8375-3abfc74c79f3&response_mode=fragment&response_type=code&scope=openid"
#endif
#ifndef PortalRecibidosUrl
  #define PortalRecibidosUrl "https://srienlinea.sri.gob.ec/tuportal-internet/accederAplicacion.jspa?redireccion=57&idGrupo=55"
#endif

#if !FileExists(SourcePath + "..\dist\Archivist\Archivist.exe")
  #error "Falta dist\Archivist\Archivist.exe: compile con build.ps1 (primero PyInstaller)."
#endif

[Setup]
AppId={{94F94631-CA7E-4F84-98E9-36980F88FE03}
AppName=Archivist
AppVersion={#AppVersion}
AppPublisher=Enlace Negocios Fiduciarios
DefaultDirName={autopf}\Archivist
DefaultGroupName=Archivist
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist_installer
OutputBaseFilename=Archivist-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Archivist
SetupIconFile=..\assets\archivist.ico
UninstallDisplayIcon={app}\Archivist.exe

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"

[Files]
Source: "..\dist\Archivist\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\assets\archivist.ico"; DestDir: "{app}"

[Icons]
Name: "{group}\Archivist"; Filename: "{app}\Archivist.exe"; IconFilename: "{app}\archivist.ico"
Name: "{autodesktop}\Archivist"; Filename: "{app}\Archivist.exe"; Tasks: desktopicon; IconFilename: "{app}\archivist.ico"

[UninstallDelete]
; Desinstalar borra la configuracion (con la clave) y la sesion del navegador. NO toca Documentos.
Type: filesandordirs; Name: "{localappdata}\Archivist"
Type: filesandordirs; Name: "{userappdata}\Archivist"

[Code]
var
  CredPage: TInputQueryWizardPage;

function EnvPath: String;
begin
  Result := ExpandConstant('{userappdata}\Archivist\.env');
end;

// Valor entre comillas simples: evita que # o comillas rompan la lectura del .env
function Q(const S: String): String;
var
  R: String;
begin
  R := S;
  StringChangeEx(R, '\', '\\', True);
  StringChangeEx(R, '''', '\''', True);
  Result := '''' + R + '''';
end;

function SoloDigitos(const S: String): Boolean;
var
  I: Integer;
begin
  Result := S <> '';
  for I := 1 to Length(S) do
    if (S[I] < '0') or (S[I] > '9') then
      Result := False;
end;

procedure InitializeWizard;
begin
  CredPage := CreateInputQueryPage(wpSelectTasks,
    'Credenciales del portal',
    'Ingrese los datos de su cuenta del portal SRI en línea',
    'Se guardan solo en este equipo, en su perfil de usuario.');
  CredPage.Add('RUC:', False);
  CredPage.Add('Clave:', True);
  CredPage.Add('Repita la clave:', True);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  // En una actualizacion el .env ya existe: no se pide ni se reemplaza.
  // En instalacion silenciosa no hay quien escriba: se omite la pagina.
  Result := (PageID = CredPage.ID) and (WizardSilent or FileExists(EnvPath));
end;

// Devuelve el mensaje de error de lo escrito en la pagina, o '' si esta bien.
function ValidarCredenciales(const Ruc, Clave, Repita: String): String;
begin
  Result := '';
  if (Trim(Ruc) = '') or (Clave = '') then
    Result := 'Complete el RUC y la clave.'
  else if (Length(Trim(Ruc)) <> 13) or (not SoloDigitos(Trim(Ruc))) then
    Result := 'El RUC debe tener 13 dígitos numéricos.'
  else if Clave <> Repita then
    Result := 'Las claves no coinciden.';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Mensaje: String;
begin
  Result := True;
  // Inno Setup llama a esta funcion tambien en modo silencioso, con la pagina vacia. Un MsgBox aqui
  // dejaria colgado un despliegue masivo (/SUPPRESSMSGBOXES no suprime los MsgBox de [Code]).
  if WizardSilent then Exit;
  if CurPageID = CredPage.ID then
  begin
    Mensaje := ValidarCredenciales(CredPage.Values[0], CredPage.Values[1], CredPage.Values[2]);
    if Mensaje <> '' then
    begin
      MsgBox(Mensaje, mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Lines: TArrayOfString;
begin
  // El .env lo crea solo el instalador, solo si no existe y solo si se capturo el RUC.
  // En instalacion silenciosa no hay pagina: no se crea (TI lo crea en el contexto de cada usuario).
  if (CurStep = ssPostInstall) and (not FileExists(EnvPath)) and
     (Trim(CredPage.Values[0]) <> '') then
  begin
    ForceDirectories(ExtractFileDir(EnvPath));
    SetArrayLength(Lines, 4);
    Lines[0] := 'PORTAL_LOGIN_URL=' + Q('{#PortalLoginUrl}');
    Lines[1] := 'PORTAL_RECIBIDOS_URL=' + Q('{#PortalRecibidosUrl}');
    Lines[2] := 'PORTAL_RUC=' + Q(Trim(CredPage.Values[0]));
    Lines[3] := 'PORTAL_PASSWORD=' + Q(CredPage.Values[1]);
    SaveStringsToUTF8File(EnvPath, Lines, False);
  end;
end;
