; =============================================================================
; AM4 Ops Center - Inno Setup Installer Script
; =============================================================================
; Builds a per-user Windows installer that:
;   1. Bootstraps Python 3.14 if missing (via bundled python.org installer)
;   2. Creates a venv under {app}\runtime
;   3. Installs app dependencies + am4 wheel from bundled offline wheels
;   4. Drops AM4OpsCenter.exe / AM4OpsCenter-Stop.exe shortcuts
;   5. Finished page: optional "Launch AM4 Ops Center now" checkbox
;   6. On uninstall, asks whether to preserve %APPDATA%\AM4OpsCenter
;
; Build: iscc /DAppVersion=1.0.0 packaging\installer\am4opscenter.iss
; CI overrides AppVersion from the git tag.
; =============================================================================

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

#define AppName           "AM4 Ops Center"
#define AppPublisher      "Saqib Jawaid"
#define AppURL            "https://github.com/saqibjawaid/am4-ops-center"
#define AppExeName        "AM4OpsCenter.exe"
#define AppStopExeName    "AM4OpsCenter-Stop.exe"
#define PythonVersion     "3.14"
#define PythonTargetDir   "{localappdata}\Programs\Python\Python314"

[Setup]
AppId={{B3F9D7E2-4A5C-4E8F-9B1D-7C2A8F3E6D51}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={localappdata}\Programs\AM4OpsCenter
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir=Output
OutputBaseFilename=AM4OpsCenter-Setup-{#AppVersion}
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardSizePercent=110
Compression=lzma2/max
SolidCompression=yes
LicenseFile=assets\license.txt
CloseApplications=force
RestartApplications=no
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoCompany={#AppPublisher}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; -- FastAPI application code (staged into dist\app\ by CI before iscc runs) --
Source: "..\..\dist\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs

; -- Compiled launchers (PyInstaller output from dist\launcher\) --
Source: "..\..\dist\launcher\AM4OpsCenter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\dist\launcher\AM4OpsCenter-Stop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; -- Offline pip wheels (populated by build_wheels.ps1 before iscc) --
Source: "wheels\*"; DestDir: "{tmp}\wheels"; Flags: deleteafterinstall recursesubdirs

; -- Bundled Python 3.14 installer (downloaded by CI from python.org) --
; Only extracted when NeedsPython returns True
Source: "bootstrap\python-installer.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsPython

; -- Static assets --
Source: "assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\icon.ico"; WorkingDir: "{app}"
Name: "{group}\Stop {#AppName}"; Filename: "{app}\{#AppStopExeName}"; IconFilename: "{app}\icon.ico"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\icon.ico"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; ---- Step 1: Install Python 3.14 if missing ----
Filename: "{tmp}\python-installer.exe"; \
  Parameters: "/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=1 Include_test=0 Include_pip=1 Include_doc=0 Include_dev=0 Shortcuts=0 AssociateFiles=0 TargetDir=""{#PythonTargetDir}"""; \
  StatusMsg: "Installing Python {#PythonVersion}..."; \
  Flags: waituntilterminated; \
  Check: NeedsPython

; ---- Step 2: Create the venv ----
Filename: "{code:GetPythonExe}"; \
  Parameters: "-m venv ""{app}\runtime"""; \
  StatusMsg: "Creating Python environment..."; \
  Flags: runhidden waituntilterminated

; ---- Step 3: Upgrade pip inside the venv (offline) ----
Filename: "{app}\runtime\Scripts\python.exe"; \
  Parameters: "-m pip install --no-index --find-links=""{tmp}\wheels"" --upgrade pip"; \
  StatusMsg: "Upgrading pip..."; \
  Flags: runhidden waituntilterminated

; ---- Step 4: Install app requirements (offline) ----
Filename: "{app}\runtime\Scripts\python.exe"; \
  Parameters: "-m pip install --no-index --find-links=""{tmp}\wheels"" -r ""{app}\app\requirements.txt"""; \
  StatusMsg: "Installing dependencies..."; \
  Flags: runhidden waituntilterminated

; ---- Step 5: Install the prebuilt am4 wheel (offline) ----
Filename: "{app}\runtime\Scripts\python.exe"; \
  Parameters: "-m pip install --no-index --find-links=""{tmp}\wheels"" am4"; \
  StatusMsg: "Installing am4 engine..."; \
  Flags: runhidden waituntilterminated

; Launch after install is handled in [Code] (checkbox on the Finished page).

[UninstallDelete]
; Remove the venv directory (pip-installed files that Inno Setup didn't track)
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\app\__pycache__"
; NOTE: Intentionally NOT deleting {userappdata}\AM4OpsCenter here.
; CurUninstallStepChanged handles that with a user prompt.

; =============================================================================
; [Code] - Pascal procedures
; =============================================================================
[Code]
uses
  NewCheck;

// Forward declarations
function NeedsPython(): Boolean; forward;
function GetPythonExe(Param: String): String; forward;
function FindExistingPython(): String; forward;
function IsAppRunning(): Boolean; forward;

var
  CachedPythonExe: String;
  LaunchCheckbox: TNewCheckBox;

// ---------------------------------------------------------------------------
// TryPythonLauncher314
// Uses the Windows "py.exe" launcher: py -3.14 -c "import sys; print(sys.executable)"
// so python.org installs that registered the launcher but not PythonCore are found.
// ---------------------------------------------------------------------------
function TryPythonLauncher314: String;
var
  Lines: TArrayOfString;
  ResultCode: Integer;
  TmpFile: String;
begin
  Result := '';
  TmpFile := ExpandConstant('{tmp}\am4_py314_exe.txt');
  if Exec(ExpandConstant('{cmd}'),
     '/C py -3.14 -c "import sys; print(sys.executable)" > "' + TmpFile + '" 2>nul',
     '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if LoadStringsFromFile(TmpFile, Lines) and (GetArrayLength(Lines) > 0) then
    begin
      Result := Trim(Lines[0]);
      if not FileExists(Result) then
        Result := '';
    end;
  end;
end;

// ---------------------------------------------------------------------------
// FindExistingPython
// Returns the full path to a usable python.exe for version 3.14, or ''
// if not found. Checks in order:
//   1. HKCU\Software\Python\PythonCore\3.14\InstallPath
//   2. HKLM\Software\Python\PythonCore\3.14\InstallPath (64-bit view)
//   3. py.exe launcher: py -3.14 (prints sys.executable)
//   4. The target dir we'll install to (in case Step 1 already ran this session)
// ---------------------------------------------------------------------------
function FindExistingPython(): String;
var
  InstallPath: String;
  Candidate: String;
begin
  Result := '';

  // Check HKCU first (per-user install, most likely for non-admin users)
  if RegQueryStringValue(HKEY_CURRENT_USER,
     'Software\Python\PythonCore\{#PythonVersion}\InstallPath', '', InstallPath) then
  begin
    Candidate := AddBackslash(InstallPath) + 'python.exe';
    if FileExists(Candidate) then
    begin
      Result := Candidate;
      Exit;
    end;
  end;

  // Check HKLM 64-bit view
  if RegQueryStringValue(HKEY_LOCAL_MACHINE,
     'Software\Python\PythonCore\{#PythonVersion}\InstallPath', '', InstallPath) then
  begin
    Candidate := AddBackslash(InstallPath) + 'python.exe';
    if FileExists(Candidate) then
    begin
      Result := Candidate;
      Exit;
    end;
  end;

  Candidate := TryPythonLauncher314;
  if Candidate <> '' then
  begin
    Result := Candidate;
    Exit;
  end;

  // Check the target dir we would install to — if a prior run of this installer
  // already installed Python this session, it will be here.
  Candidate := ExpandConstant('{#PythonTargetDir}\python.exe');
  if FileExists(Candidate) then
  begin
    Result := Candidate;
    Exit;
  end;
end;

// ---------------------------------------------------------------------------
// NeedsPython
// True if we should run the bundled python.org installer.
// Caches the discovered python.exe for GetPythonExe to reuse.
// ---------------------------------------------------------------------------
function NeedsPython(): Boolean;
begin
  if CachedPythonExe = '' then
    CachedPythonExe := FindExistingPython();

  Result := (CachedPythonExe = '');
end;

// ---------------------------------------------------------------------------
// GetPythonExe
// Returns the full path to python.exe, called from [Run] entries via
// {code:GetPythonExe}. If Python was just installed by the bootstrapper,
// returns the known target path. Otherwise returns the cached discovery.
// ---------------------------------------------------------------------------
function GetPythonExe(Param: String): String;
begin
  // If we needed Python, the bootstrapper just installed it to the known path
  if (CachedPythonExe = '') then
    Result := ExpandConstant('{#PythonTargetDir}\python.exe')
  else
    Result := CachedPythonExe;
end;

// ---------------------------------------------------------------------------
// IsAppRunning
// Checks whether AM4OpsCenter.exe is currently running, so we can warn
// before uninstall or upgrade.
// ---------------------------------------------------------------------------
function IsAppRunning(): Boolean;
var
  ResultCode: Integer;
begin
  // tasklist exits 0 always; use findstr to detect presence
  Result := Exec(ExpandConstant('{cmd}'),
                 '/C tasklist /FI "IMAGENAME eq {#AppExeName}" /NH | findstr /I "{#AppExeName}" > nul',
                 '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

// ---------------------------------------------------------------------------
// InitializeWizard
// Checkbox on the Finished page: launch the app when setup completes.
// ---------------------------------------------------------------------------
procedure InitializeWizard;
begin
  if WizardSilent then
    Exit;

  LaunchCheckbox := TNewCheckBox.Create(WizardForm);
  with LaunchCheckbox do
  begin
    Parent := WizardForm.FinishedPage;
    Left := ScaleX(8);
    Top := WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + ScaleY(12);
    Width := WizardForm.FinishedPage.ClientWidth - ScaleX(16);
    Height := ScaleY(17);
    Caption := 'Launch AM4 Ops Center now';
    Checked := True;
  end;
end;

// ---------------------------------------------------------------------------
// DeinitializeSetup
// Run the main exe if the user left the launch checkbox enabled.
// ---------------------------------------------------------------------------
procedure DeinitializeSetup;
var
  ResultCode: Integer;
begin
  if WizardSilent then
    Exit;
  if Assigned(LaunchCheckbox) and LaunchCheckbox.Checked then
    Exec(ExpandConstant('{app}\{#AppExeName}'), '', '', SW_SHOW, ewNoWait, ResultCode);
end;

// ---------------------------------------------------------------------------
// InitializeSetup
// Pre-install checks. If the app is running, stop it via the Stop exe.
// ---------------------------------------------------------------------------
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  StopExe: String;
  Response: Integer;
begin
  Result := True;

  if IsAppRunning() then
  begin
    Response := MsgBox(
      '{#AppName} is currently running.' + #13#10 + #13#10 +
      'Setup needs to close it before continuing. Stop it now?',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON1);

    if Response = IDYES then
    begin
      // Try the graceful stop exe first (previous install)
      StopExe := ExpandConstant('{localappdata}\Programs\AM4OpsCenter\{#AppStopExeName}');
      if FileExists(StopExe) then
        Exec(StopExe, '', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

      // Hard kill as fallback
      if IsAppRunning() then
        Exec(ExpandConstant('{cmd}'),
             '/C taskkill /F /IM "{#AppExeName}" /T',
             '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

      Sleep(500);

      if IsAppRunning() then
      begin
        MsgBox('Could not stop {#AppName}. Please close it manually and run setup again.',
               mbError, MB_OK);
        Result := False;
      end;
    end
    else
      Result := False;
  end;
end;

// ---------------------------------------------------------------------------
// InitializeUninstall
// Same check for uninstall path.
// ---------------------------------------------------------------------------
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
  StopExe: String;
begin
  Result := True;

  if IsAppRunning() then
  begin
    if MsgBox('{#AppName} is running. Stop it and continue uninstalling?',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON1) = IDYES then
    begin
      StopExe := ExpandConstant('{app}\{#AppStopExeName}');
      if FileExists(StopExe) then
        Exec(StopExe, '', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

      if IsAppRunning() then
        Exec(ExpandConstant('{cmd}'),
             '/C taskkill /F /IM "{#AppExeName}" /T',
             '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

      Sleep(500);
    end
    else
      Result := False;
  end;
end;

// ---------------------------------------------------------------------------
// CurUninstallStepChanged
// After files are removed, ask the user whether to also delete their
// data directory (%APPDATA%\AM4OpsCenter). Default is No (keep data).
// ---------------------------------------------------------------------------
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  UserDataDir: String;
  Response: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    UserDataDir := ExpandConstant('{userappdata}\AM4OpsCenter');

    if DirExists(UserDataDir) then
    begin
      Response := MsgBox(
        'Do you also want to delete your {#AppName} data?' + #13#10 + #13#10 +
        'This includes your extracted route database, saved credentials,' + #13#10 +
        'and logs, located at:' + #13#10 + #13#10 +
        UserDataDir + #13#10 + #13#10 +
        'Click No to keep your data for future reinstalls (recommended).',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON2);

      if Response = IDYES then
      begin
        if not DelTree(UserDataDir, True, True, True) then
          MsgBox('Could not fully delete ' + UserDataDir + '.' + #13#10 +
                 'You may need to remove it manually.',
                 mbInformation, MB_OK);
      end;
    end;
  end;
end;
