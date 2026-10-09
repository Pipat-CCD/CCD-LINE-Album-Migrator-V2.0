param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$expected = '44b512b25af500724ba579d0a53c8fc5851628b692dd5e5d94ae4a15c2cba9ec'
# Published by the ExifTool author: https://exiftool.org/checksums-13.59.txt
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$zip = Join-Path $Destination 'exiftool-13.59_64.zip'
if (!(Test-Path $zip) -or (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
    Invoke-WebRequest 'https://downloads.sourceforge.net/project/exiftool/exiftool-13.59_64.zip' -OutFile $zip
}
if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
    throw 'ExifTool checksum failed. Do not use this download.'
}
$expanded = Join-Path $Destination 'expanded'
if (!(Test-Path $expanded)) { Expand-Archive -Path $zip -DestinationPath $expanded }
$launcher = @(Get-ChildItem $expanded -Recurse -File | Where-Object {
    $_.Name -eq 'exiftool(-k).exe' -or $_.Name -eq 'exiftool.exe'
})
if ($launcher.Count -ne 1) { throw 'Expected exactly one official ExifTool launcher' }
$directory = $launcher[0].DirectoryName
if ($launcher[0].Name -ne 'exiftool.exe') {
    Rename-Item -LiteralPath $launcher[0].FullName -NewName 'exiftool.exe'
}
if (!(Test-Path (Join-Path $directory 'exiftool_files\exiftool.pl'))) {
    throw 'ExifTool companion directory is incomplete'
}
$version = & (Join-Path $directory 'exiftool.exe') -ver
if ($LASTEXITCODE -ne 0 -or $version.Trim() -ne '13.59') { throw 'ExifTool version check failed' }
Write-Output $directory
