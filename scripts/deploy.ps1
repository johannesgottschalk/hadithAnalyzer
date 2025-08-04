# Minimaler Deploy per scp/rsync (hier Platzhalter)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

$USER = "<uberspace-user>"
$HOST = "$USER.uber.space"
$BASE = "/var/www/virtual/$USER/hadith-analyzer"

# Code syncen (ohne große Daten)
# Nutze WinSCP GUI oder rsync über WSL; hier Beispiel mit scp (nur wenn OpenSSH+pfade vorhanden):
scp -r `
  "$root\app" `
  "$root\hadith_analyzer" `
  "$root\requirements.txt" `
  "$USER@$HOST:$BASE/"

# Datenpaket separat:
scp -r "$root\data\hf-2025.08" "$USER@$HOST:$BASE/data/"
Write-Host "Deploy done."
