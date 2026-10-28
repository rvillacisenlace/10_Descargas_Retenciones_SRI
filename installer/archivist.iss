; Instalador de Archivist (Inno Setup 6 o 7). Compilar con build.ps1.
; Metodologia: METODOLOGIA_Empaquetado.md. NO cambiar el AppId nunca: con el, una version nueva actualiza
; la instalada sin duplicarla.
; La clave de API de 2Captcha NO viaja en el instalador: la escribe TI en el asistente.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

; Direcciones del portal que el instalador escribe en el .env. Deben coincidir con .env.example.
#ifndef PortalLoginUrl
  #define PortalLoginUrl "https://srienlinea.sri.gob.ec/auth/realms/Internet/protocol/openid-connect/auth?client_id=app-sri-claves-angular&redirect_uri=https%3A%2F%2Fsrienlinea.sri.gob.ec%2Fsri-en-linea%2F%2Fcontribuyente%2Fperfil&state=42efaa2b-c239-48c8-b148-d8209155df53&nonce=2e55581c-529c-47dd-8375-3abfc74c79f3&response_mode=fragment&response_type=code&scope=openid"
#endif
#ifndef PortalRecibidosUrl
  #define PortalRecibidosUrl "https://srienlinea.sri.gob.ec/tuportal-internet/accederAplicacion.jspa?redireccion=57&idGrupo=55"
#endif

[Setup]
AppId={{94F94631-CA7E-4F84-98E9-36980F88FE03}
AppName=Archivist
AppVersion={#AppVersion}
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
Type: filesandordirs; Name: "{localappdata}\Archivist"
Type: filesandordirs; Name: "{userappdata}\Archivist"

[Code]
var
  CredPage: TInputQueryWizardPage;

function EnvPath: String;
begin
  Result := ExpandConstant('{userappdata}\Archivist\.env');
end;

{ Valor entre comillas simples: evita que # o comillas rompan la lectura del .env }
function Q(const S: String): String;
var
  R: String;
begin
  R := S;
  StringChangeEx(R, '\', '\\', True);
  StringChangeEx(R, '''', '\''', True);
  Result := '''' + R + '''';
end;

procedure InitializeWizard;
begin
  CredPage := CreateInputQueryPage(wpSelectTasks,
    'Credenciales del portal del SRI',
    'Ingrese los datos de la cuenta y la clave de API de 2Captcha',
    'Se guardan solo en este equipo, en el perfil del usuario.');
  CredPage.Add('RUC:', False);
  CredPage.Add('Clave:', True);
  CredPage.Add('Repita la clave:', True);
  CredPage.Add('Clave de API de 2Captcha (la entrega TI):', True);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  { En una actualizacion el .env ya existe: no se pide ni se reemplaza }
  Result := (PageID = CredPage.ID) and FileExists(EnvPath);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = CredPage.ID then
  begin
    if (Trim(CredPage.Values[0]) = '') or (CredPage.Values[1] = '') then
    begin
      MsgBox('Complete el RUC y la clave.', mbError, MB_OK);
      Result := False;
    end
    else if CredPage.Values[1] <> CredPage.Values[2] then
    begin
      MsgBox('Las claves no coinciden.', mbError, MB_OK);
      Result := False;
    end
    else if Trim(CredPage.Values[3]) = '' then
    begin
      MsgBox('Ingrese la clave de API de 2Captcha (la entrega TI).', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Lines: TArrayOfString;
begin
  { Sin asistente (instalacion silenciosa) no se crea el .env: lo debe crear TI }
  if (CurStep = ssPostInstall) and (not FileExists(EnvPath)) and
     (Trim(CredPage.Values[0]) <> '') then
  begin
    ForceDirectories(ExtractFileDir(EnvPath));
    SetArrayLength(Lines, 7);
    Lines[0] := 'PORTAL_LOGIN_URL=' + Q('{#PortalLoginUrl}');
    Lines[1] := 'PORTAL_RECIBIDOS_URL=' + Q('{#PortalRecibidosUrl}');
    Lines[2] := 'PORTAL_RUC=' + Q(Trim(CredPage.Values[0]));
    Lines[3] := 'PORTAL_PASSWORD=' + Q(CredPage.Values[1]);
    Lines[4] := 'CAPTCHA_ENABLED=true';
    Lines[5] := 'CAPTCHA_API_KEY=' + Q(Trim(CredPage.Values[3]));
    Lines[6] := 'CAPTCHA_PROVIDER=2captcha';
    SaveStringsToUTF8File(EnvPath, Lines, False);
  end;
end;
