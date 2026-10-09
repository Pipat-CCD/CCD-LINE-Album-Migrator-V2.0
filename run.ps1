$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (!(Test-Path '.venv\Scripts\python.exe')) { throw 'Run setup.ps1 first' }
& .\.venv\Scripts\python.exe main.py
if ($LASTEXITCODE -ne 0) { throw 'Application exited with an error' }
