; Installer for Master Audio Switcher. Built on the server, not on a developer
; machine — see .github/workflows/release.yml.
;
; Per user, never per machine: this is a tray utility, it needs nothing from
; administrator rights, and asking for them would put a shield on the icon and a
; consent dialog in front of a program that switches speakers. It also means the
; installer runs for people who do not have those rights at all.

#define AppName "Master Audio Switcher"
#define AppExe "MasterAudioSwitcher.exe"
#define AppPublisher "electronic-mars"
#define AppUrl "https://github.com/electronic-mars/mas"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\build\mas\MasterAudioSwitcher"
#endif

[Setup]
; Never change this: it is how Windows recognises an upgrade of the same program.
AppId={{7C4E3F2A-9B51-4D8E-A6C7-2F1D0B8E5A34}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
DefaultDirName={localappdata}\Programs\MasterAudioSwitcher
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=MasterAudioSwitcher-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExe}
; The program is 64-bit because Python is. Spelled the old way on purpose:
; x64compatible needs Inno Setup 6.3, and the compiler on the build machine is
; whatever its image happens to ship.
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
; A running copy must be closed before its files can be replaced, and it lives in
; the tray where people forget about it. The filter is left at its default on
; purpose: a PyInstaller folder holds python314.dll and a hundred others open the
; whole time it runs, and narrowing the filter to *.exe would hide from Windows
; exactly the locks that block the upgrade.
; force, not yes: "yes" is a polite request, and this program is built to refuse
; it. Closing its window means going to the tray — that is the whole point of it —
; so Windows asks it to close, it hides instead, and Setup concludes it could not
; be closed. Silently that answer defaults to Abort, and Setup rolls the update
; back and leaves. Forced, Windows ends the process instead of asking. Nothing is
; lost by that: settings are written the moment they change, not on the way out.
CloseApplications=force
; No AppMutex here, on purpose, and it cost a broken update button to learn why.
; A mutex makes Setup stop and ask the person to close the program — fine when
; there is a person. The program updating itself starts Setup silently and then
; quits so its files can be replaced, and a suppressed question is answered with
; its safe default, which is Cancel. Setup gave up ten milliseconds in, before
; the program had finished quitting, and the update ended with nothing installed
; and the program gone from the tray. Closing a running copy is what
; CloseApplications above is for: it asks Windows which processes hold the files
; and closes those, silently when Setup is silent, with a page listing them when
; it is not. Restarting them afterwards is left off because the Run entry below
; does it, deliberately and only on the update path.
RestartApplications=no
SetupMutex=MasterAudioSwitcherSetup

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "uk"; MessagesFile: "compiler:Languages\Ukrainian.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "pl"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "nl"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "cs"; MessagesFile: "compiler:Languages\Czech.isl"

[CustomMessages]
en.Autostart=Start with Windows
ru.Autostart=Запускать с Windows
uk.Autostart=Запускати з Windows
de.Autostart=Mit Windows starten
es.Autostart=Iniciar con Windows
fr.Autostart=Démarrer avec Windows
it.Autostart=Avvia con Windows
pl.Autostart=Uruchamiaj z systemem Windows
nl.Autostart=Starten met Windows
tr.Autostart=Windows ile başlat
pt.Autostart=Iniciar com o Windows
cs.Autostart=Spouštět se systémem Windows
en.KeepSettings=Keep my settings and device icons
ru.KeepSettings=Сохранить настройки и значки устройств
uk.KeepSettings=Зберегти налаштування та значки пристроїв
de.KeepSettings=Einstellungen und Gerätesymbole behalten
es.KeepSettings=Conservar mis ajustes e iconos de dispositivo
fr.KeepSettings=Conserver mes réglages et icônes d'appareil
it.KeepSettings=Mantieni impostazioni e icone dei dispositivi
pl.KeepSettings=Zachowaj ustawienia i ikony urządzeń
nl.KeepSettings=Mijn instellingen en apparaatpictogrammen behouden
tr.KeepSettings=Ayarlarımı ve cihaz simgelerimi koru
pt.KeepSettings=Manter minhas configurações e ícones de dispositivo
cs.KeepSettings=Ponechat nastavení a ikony zařízení

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked
Name: "autostart"; Description: "{cm:Autostart}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; The same value the program writes itself, so the two never disagree. The flag
; tells it that Windows started it, and then it goes to the tray without a window.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "MasterAudioSwitcher"; \
    ValueData: """{app}\{#AppExe}"" --startup"; \
    Flags: uninsdeletevalue; Tasks: autostart
; Removed on uninstall even if it was set from inside the program later: a
; leftover autostart entry pointing at a deleted file is the classic complaint
; about programs that "do not uninstall properly".
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: none; ValueName: "MasterAudioSwitcher"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent
; The program updating itself runs this installer silently and then quits, so
; that its own files can be replaced. Silent means the tick box above is skipped,
; and without this line the update would end with the program simply gone. The
; flag is ours and is passed only on that path, so an ordinary silent install —
; the one a system administrator runs — still finishes without starting anything.
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: WasStartedByTheProgram

[Code]
{ The interface is a page drawn by the WebView2 runtime. Windows 11 has it;
  Windows 10 LTSC, the N editions and freshly imaged machines do not, and without
  it the window would be an empty rectangle. The program says so for itself, but
  it is far kinder to fix it here than to explain it later. }
function WebView2Present: Boolean;
var
  Version: String;
begin
  Result :=
    (RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
     RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
     RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version))
    and (Version <> '') and (Version <> '0.0.0.0');
end;

{ True when the program itself started us to update, which it signals with
  /RELAUNCH=1. Then it is owed a restart; nothing else here passes that. }
function WasStartedByTheProgram: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

procedure InitializeWizard;
begin
  if not WebView2Present then
    { Not a blocker: the program still switches sound from the tray without a
      window, so refusing to install would be worse than warning. }
    SuppressibleMsgBox(
      'This program draws its window with the Microsoft WebView2 runtime, and this'
      + #13#10 + 'computer does not have it. Switching sound from the tray icon will'
      + #13#10 + 'work anyway; the window will not open until the runtime is installed'
      + #13#10 + 'from https://developer.microsoft.com/microsoft-edge/webview2/',
      mbInformation, MB_OK, IDOK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Data: String;
begin
  { Settings live outside the program folder so that an update does not lose
    them; that also means an uninstall leaves them behind unless we ask. }
  if CurUninstallStep = usPostUninstall then
  begin
    Data := ExpandConstant('{localappdata}\MasterAudioSwitcher');
    if DirExists(Data) then
      if SuppressibleMsgBox(ExpandConstant('{cm:KeepSettings}') + #13#10 + Data,
                            mbConfirmation, MB_YESNO, IDYES) = IDNO then
        DelTree(Data, True, True, True);
  end;
end;
