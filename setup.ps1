$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE)" } }
if (!(Test-Path '.venv\Scripts\python.exe')) {
    py -3.12 -m venv .venv
    Check-Exit
}
& .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
Check-Exit
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
Check-Exit
Write-Host 'ติดตั้งแล้ว: เปิดโปรแกรมด้วย .\run.ps1 แล้วเลือก ExifTool และ OAuth Desktop client'
