$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot)
function Run-CheckedProcess($Executable, $Arguments) {
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Process failed: $Executable ($($process.ExitCode))" }
}
$base = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$root = Join-Path $base ('ccd-installed-' + [guid]::NewGuid().ToString('N'))
$app = Join-Path $root 'App'
New-Item -ItemType Directory -Force -Path $root | Out-Null
$installer = (Resolve-Path '.\dist\installer\CCDLineMigrator-Setup.exe').Path
$installArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=`"$app`"")
Run-CheckedProcess $installer $installArgs
$exe = Join-Path $app 'CCDLineMigrator.exe'
$tool = Join-Path $app '_internal\tools\exiftool.exe'
if (!(Test-Path $exe) -or !(Test-Path $tool)) { throw 'Installed payload is incomplete' }
$check = Join-Path $root 'self-check.json'
$savedPath = $env:PATH
try {
    # Exercise the installed executable without Python/ExifTool available on PATH.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    Run-CheckedProcess $exe @('--self-check', '--check-output', "`"$check`"")
} finally { $env:PATH = $savedPath }
$result = Get-Content $check -Raw | ConvertFrom-Json
if ($result.exiftool -ne '13.59') { throw 'Installed ExifTool check failed' }
& .\.venv\Scripts\python.exe .\packaging\installed_fixture.py create $root
if ($LASTEXITCODE -ne 0) { throw 'Fixture creation failed' }
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    Run-CheckedProcess $exe @('--dry-run', "`"$root\photos`"", '--date', '2025-05-09', '--output', "`"$root\output`"")
} finally { $env:PATH = $savedPath }
& .\.venv\Scripts\python.exe .\packaging\installed_fixture.py verify $root $tool
if ($LASTEXITCODE -ne 0) { throw 'Installed dry-run validation failed' }
$shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'CCD LINE Album Migrator V2.0\CCD LINE Album Migrator V2.0.lnk'
if (!(Test-Path $shortcut)) { throw 'Start Menu shortcut is missing' }
$userData = Join-Path $env:LOCALAPPDATA 'CCDLineMigrator'
New-Item -ItemType Directory -Force $userData | Out-Null
$sentinel = Join-Path $userData ('ci-preservation-' + [guid]::NewGuid().ToString('N') + '.txt')
$sentinelValue = [guid]::NewGuid().ToString('N')
Set-Content $sentinel $sentinelValue
try {
    Run-CheckedProcess $installer $installArgs
    if ((Get-Content $sentinel -Raw).Trim() -ne $sentinelValue) { throw 'Upgrade changed user data' }
    Run-CheckedProcess (Join-Path $app 'unins000.exe') @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
    if ((Get-Content $sentinel -Raw).Trim() -ne $sentinelValue) { throw 'Uninstall changed user data' }
} finally { Remove-Item -LiteralPath $sentinel -ErrorAction SilentlyContinue }
@{
    app_version = $result.app_version
    platform = 'GitHub Actions windows-2022; not a clean Windows 11 device'
    installed_self_check = 'passed with Python/ExifTool removed from PATH'
    bundled_exiftool = $result.exiftool
    synthetic_photos_verified = 3
    start_menu_shortcut = 'passed'
    upgrade_preserves_user_data = 'passed'
    uninstall_preserves_user_data = 'passed'
    live_google_upload = 'not_run'
} | ConvertTo-Json | Set-Content '.\dist\installer\installed-validation.json' -Encoding utf8
