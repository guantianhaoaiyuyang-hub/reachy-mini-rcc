#define MyAppName "Reachy Mini RCC"
#define MyAppVersion "3.0.0"
#define MyAppExeName "Start_RCC.vbs"

[Setup]
AppId={{A9B64C2D-16F5-4D92-8D61-5B71A9FE0D34}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}

DefaultDirName={localappdata}\Programs\Reachy Mini RCC
DefaultGroupName=Reachy Mini RCC

DisableProgramGroupPage=yes
DisableWelcomePage=no
AllowNoIcons=yes

PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.10240

WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes

OutputDir=dist
OutputBaseFilename=ReachyMini_RCC_Setup_x64

SetupIconFile=resources\icons\reachy_control_center.ico
UninstallDisplayIcon={app}\resources\icons\reachy_control_center.ico

ChangesEnvironment=no
CloseApplications=yes
RestartApplications=no

VersionInfoVersion=3.0.0.0
VersionInfoProductName=Reachy Mini RCC
VersionInfoProductVersion=3.0.0
VersionInfoDescription=Reachy Mini Robot Control Center

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; \
    Description: "Create a &desktop shortcut"; \
    GroupDescription: "Additional shortcuts:"; \
    Flags: unchecked

[Files]
Source: "*"; \
    DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs; \
    Excludes: "dist\*;tests\installer\*;Start_RCC_Debug.bat;ReachyMini_RCC_Setup.iss;*.before_*;*.bak;*.pyc;*.pyo;__pycache__\*;.env"

[Icons]
Name: "{group}\Reachy Mini RCC"; \
    Filename: "{app}\Start_RCC.vbs"; \
    WorkingDir: "{app}"; \
    IconFilename: "{app}\resources\icons\reachy_control_center.ico"

Name: "{autodesktop}\Reachy Mini RCC"; \
    Filename: "{app}\Start_RCC.vbs"; \
    WorkingDir: "{app}"; \
    IconFilename: "{app}\resources\icons\reachy_control_center.ico"; \
    Tasks: desktopicon

Name: "{group}\Uninstall Reachy Mini RCC"; \
    Filename: "{uninstallexe}"

[Run]
Filename: "{app}\Start_RCC.vbs"; \
    Description: "Launch Reachy Mini RCC"; \
    WorkingDir: "{app}"; \
    Flags: postinstall nowait skipifsilent shellexec

[Code]

var
  DeleteUserData: Boolean;

function IsChineseLanguage: Boolean;
begin
  Result := CompareText(ActiveLanguage, 'chinesesimp') = 0;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
  PythonExe: String;
  PythonArgs: String;
  UserDataDir: String;
  PromptText: String;
begin
  if CurUninstallStep = usUninstall then
  begin

    if IsChineseLanguage then
      PromptText :=
        '是否同时删除 Reachy Mini RCC 的用户配置和豆包凭据？' +
        Chr(13) + Chr(10) + Chr(13) + Chr(10) +
        '选择“是”：删除 settings.json 以及 Windows 凭据管理器中的豆包密钥。' +
        Chr(13) + Chr(10) +
        '选择“否”：保留配置，重新安装后可以继续使用。'
    else
      PromptText :=
        'Also delete Reachy Mini RCC user configuration and Doubao credentials?' +
        Chr(13) + Chr(10) + Chr(13) + Chr(10) +
        'Yes: delete settings.json and Doubao secrets stored in Windows Credential Manager.' +
        Chr(13) + Chr(10) +
        'No: keep configuration for future reinstallations.';

    DeleteUserData :=
      MsgBox(
        PromptText,
        mbConfirmation,
        MB_YESNO
      ) = IDYES;

    if DeleteUserData then
    begin

      PythonExe :=
        ExpandConstant(
          '{app}\runtime\python\python.exe'
        );

      if FileExists(PythonExe) then
      begin

        PythonArgs :=
          '-c "from launcher.setup.credential_store import CredentialStore; ' +
          's=CredentialStore(); ' +
          's.delete_secret(''DOUBAO_ACCESS_TOKEN''); ' +
          's.delete_secret(''DOUBAO_APP_KEY'')"';

        Exec(
          PythonExe,
          PythonArgs,
          ExpandConstant('{app}'),
          SW_HIDE,
          ewWaitUntilTerminated,
          ResultCode
        );

      end;

      UserDataDir :=
        ExpandConstant(
          '{localappdata}\ReachyMiniRCC'
        );

      if DirExists(UserDataDir) then
      begin
        DelTree(
          UserDataDir,
          True,
          True,
          True
        );
      end;

    end;

  end;
end;
