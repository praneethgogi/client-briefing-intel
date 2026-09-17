<#
  Serves the production build behind nginx on http://localhost:8080, with /api
  proxied to uvicorn on :8000 - one origin, the way it runs when deployed.

  Prereqs: nginx unpacked (see deploy/README.md) and the API already running
  via .\scripts\run_backend.ps1.

  Use -Stop to shut nginx down.
#>
param(
  [string]$NginxHome = "$env:USERPROFILE\nginx-cbi\nginx-1.27.3",
  [switch]$Stop
)
$ErrorActionPreference = "Stop"

if (-not (Test-Path "$NginxHome\nginx.exe")) {
  Write-Error "nginx not found at $NginxHome. See deploy/README.md."
}

if ($Stop) {
  & "$NginxHome\nginx.exe" -p $NginxHome -s stop
  Write-Host "nginx stopped."
  return
}

# Rebuild so nginx serves the current frontend rather than a stale bundle.
Push-Location frontend
npm run build
Pop-Location

& "$NginxHome\nginx.exe" -p $NginxHome -t
if (Get-Process nginx -ErrorAction SilentlyContinue) {
  & "$NginxHome\nginx.exe" -p $NginxHome -s reload
  Write-Host "nginx reloaded."
} else {
  Start-Process -FilePath "$NginxHome\nginx.exe" -ArgumentList "-p", $NginxHome `
                -WorkingDirectory $NginxHome -WindowStyle Hidden
  Write-Host "nginx started."
}
Write-Host "  app -> http://localhost:8080"
