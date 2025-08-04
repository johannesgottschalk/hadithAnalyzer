# Packt das Datenpaket als tgz (für Upload)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$src  = Join-Path $root "data\hf-2025.08"
$dst  = Join-Path $root "hf-2025.08.tgz"

# Windows 11+ hat tar integriert
tar -czf $dst -C (Join-Path $root "data") "hf-2025.08"
Write-Host "Packaged -> $dst"
