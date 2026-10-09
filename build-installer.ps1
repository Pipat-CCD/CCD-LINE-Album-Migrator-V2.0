param([string]$ExifToolDirectory = '')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (!(Test-Path '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed' }
}
if (!$ExifToolDirectory) {
    $ExifToolDirectory = & .\packaging\download-exiftool.ps1 -Destination (Join-Path $env:TEMP 'ccd-exiftool-13.59')
}
& .\build.ps1 -ExifToolDirectory $ExifToolDirectory
$compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
$iscc = if ($compiler) { $compiler.Source } else { Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe' }
if (!(Test-Path $iscc)) { throw 'Install Inno Setup 6.5 or newer to build the installer' }
$version = & .\.venv\Scripts\python.exe -c 'from migrator import __version__; print(__version__)'
if ($LASTEXITCODE -ne 0) { throw 'Cannot read application version' }
& $iscc "/DAppVersion=$($version.Trim())" '.\packaging\installer.iss'
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
$installer = Join-Path $PSScriptRoot 'dist\installer\CCDLineMigrator-Setup.exe'
if (!(Test-Path $installer)) { throw 'Installer output is missing' }
$hash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  CCDLineMigrator-Setup.exe" | Set-Content (Join-Path (Split-Path $installer) 'SHA256SUMS.txt') -Encoding ascii
Write-Host "Installer: $installer"
