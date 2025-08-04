# Baut das HF-Datenpaket aus Rohdaten
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. "$root\.venv\Scripts\Activate.ps1"

$input = Join-Path $root "data\raw"
$out   = Join-Path $root "data\hf-2025.08"

python "$root\scripts\build_hf.py" --input $input --out $out
