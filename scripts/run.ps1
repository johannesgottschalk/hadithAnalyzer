# Startet die Flask-App lokal
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. "$root\.venv\Scripts\Activate.ps1"

$env:APP_DATA_DIR = "$root\data\hf-2025.08"
$env:FLASK_SECRET = "dev"

flask --app app/wsgi.py run
