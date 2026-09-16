# One-time setup (Windows PowerShell). Run from the repo root:  .\scripts\setup.ps1
$ErrorActionPreference = "Stop"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Created .env - add your OPENAI_API_KEY" }
Push-Location frontend; npm install; Pop-Location
Write-Host "Setup complete."
