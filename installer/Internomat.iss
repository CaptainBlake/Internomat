#ifndef MyAppName
#define MyAppName "Internomat"
#endif

#ifndef MyAppVersion
#define MyAppVersion "1.0.0"
#endif

#ifndef MyAppPublisher
#define MyAppPublisher "Internomat"
#endif

#ifndef MyAppExeName
#define MyAppExeName "Internomat.exe"
#endif

#ifndef MyAppSourceDir
#define MyAppSourceDir "..\\dist\\Internomat"
#endif

[Setup]
AppId={{4496D9F2-D98D-4B8A-9F81-FD8B55D685E2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Internomat-Setup-{#MyAppVersion}
SetupIconFile=..\assets\duck_icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MyAppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
var
	RemoveAllData: Boolean;

function InitializeUninstall(): Boolean;
var
	MsgResult: Integer;
begin
	Result := True;
	RemoveAllData := False;

	if UninstallSilent then
		exit;

	MsgResult := MsgBox(
		'Delete all Internomat data as well?' + #13#10 + #13#10 +
		'This removes database, demos, logs, cache, and settings in:' + #13#10 +
		ExpandConstant('{app}'),
		mbConfirmation,
		MB_YESNO
	);

	RemoveAllData := (MsgResult = IDYES);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
	if (CurUninstallStep = usPostUninstall) and RemoveAllData then
	begin
		DelTree(ExpandConstant('{app}\.secrets'), True, True, True);
		DelTree(ExpandConstant('{app}\demos'), True, True, True);
		DelTree(ExpandConstant('{app}\log'), True, True, True);
		DelTree(ExpandConstant('{app}\__pycache__'), True, True, True);
		DelTree(ExpandConstant('{app}\_internal'), True, True, True);
		DelTree(ExpandConstant('{app}\lib'), True, True, True);

		DeleteFile(ExpandConstant('{app}\internomat.db'));
		DeleteFile(ExpandConstant('{app}\internomat_backup.json'));
		DeleteFile(ExpandConstant('{app}\internomat_settings.cfg'));
		DeleteFile(ExpandConstant('{app}\internomat_settings.json'));
		DeleteFile(ExpandConstant('{app}\players.json'));

		DelTree(ExpandConstant('{app}'), True, True, True);
	end;
end;
