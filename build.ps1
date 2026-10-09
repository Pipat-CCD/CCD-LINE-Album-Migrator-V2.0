param([Parameter(Mandatory=$true)][string]$ExifToolDirectory)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE)" } }
if (!(Test-Path '.venv\Scripts\python.exe')) { throw 'Run setup.ps1 first' }
$toolDir = (Resolve-Path $ExifToolDirectory).Path
if (!(Test-Path (Join-Path $toolDir 'exiftool.exe'))) {
    throw 'Use the official complete ExifTool Windows directory; rename exiftool(-k).exe to exiftool.exe'
}
$version = & (Join-Path $toolDir 'exiftool.exe') -ver
Check-Exit
if ($version.Trim() -ne '13.59') { throw "Expected ExifTool 13.59, got $version" }
$env:CCD_TEST_EXIFTOOL = Join-Path $toolDir 'exiftool.exe'
& .\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
Check-Exit
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
Check-Exit
$licenses = Join-Path $PSScriptRoot 'build\bundled-licenses'
& .\.venv\Scripts\python.exe .\packaging\export_licenses.py $licenses
Check-Exit
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name CCDLineMigrator --collect-all pillow_heif --collect-all tzdata `
    --add-data "$toolDir;tools" --add-data "$licenses;licenses" main.py
Check-Exit
# Windowed applications write self-check output to a file instead of stdout.
$check = Join-Path $env:TEMP 'ccd-migrator-selfcheck.json'
if (Test-Path $check) { Remove-Item $check }
$process = Start-Process -FilePath '.\dist\CCDLineMigrator\CCDLineMigrator.exe' `
    -ArgumentList @('--self-check', '--check-output', "`"$check`"") -Wait -PassThru
if ($process.ExitCode -ne 0 -or !(Test-Path $check)) { throw 'Packaged self-check failed' }
$result = Get-Content $check -Raw | ConvertFrom-Json
if ($result.exiftool -ne '13.59') { throw 'Packaged ExifTool version mismatch' }
Write-Host 'Build complete. Distribute the ENTIRE dist\CCDLineMigrator folder, not just the EXE.'
