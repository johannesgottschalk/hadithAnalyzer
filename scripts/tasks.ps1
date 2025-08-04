param(
  [ValidateSet("install","run","build","package","deploy")]
  [string]$task = "run"
)

$root = Split-Path -Parent $PSScriptRoot
switch ($task) {
  "install" {
    python -m venv "$root\.venv"
    . "$root\.venv\Scripts\Activate.ps1"
    python -m pip install --upgrade pip wheel
    pip install -r "$root\requirements.txt"
  }
  "run"     { & "$PSScriptRoot\run.ps1" }
  "build"   { & "$PSScriptRoot\build.ps1" }
  "package" { & "$PSScriptRoot\package.ps1" }
  "deploy"  { & "$PSScriptRoot\deploy.ps1" }
}
