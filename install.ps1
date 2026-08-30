param(
    [switch]$Knowledge
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$workbuddyRoot = Join-Path $env:USERPROFILE ".workbuddy\skills"
$skillLink = Join-Path $workbuddyRoot "APC-report-agents"

New-Item -ItemType Directory -Path $workbuddyRoot -Force | Out-Null
if (Test-Path -LiteralPath $skillLink) {
    $existing = (Get-Item -LiteralPath $skillLink -Force).Target
    if ($existing -and ([IO.Path]::GetFullPath($existing) -eq $repoRoot)) {
        Write-Host "WorkBuddy link already configured: $skillLink"
    } else {
        throw "Install target already exists and was not changed: $skillLink"
    }
} else {
    New-Item -ItemType Junction -Path $skillLink -Target $repoRoot | Out-Null
}

$launcher = Get-Command py -ErrorAction SilentlyContinue
if ($launcher) {
    & $launcher.Source -3 -m venv (Join-Path $repoRoot ".venv")
} else {
    $launcher = Get-Command python -ErrorAction Stop
    & $launcher.Source -m venv (Join-Path $repoRoot ".venv")
}

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$requirements = if ($Knowledge) { "requirements-knowledge.txt" } else { "requirements.txt" }
& $venvPython -m pip install -r (Join-Path $repoRoot $requirements)
& $venvPython (Join-Path $repoRoot "scripts\verify_release.py")
Write-Host "Installed APC Report Agents for the current WorkBuddy user."
Write-Host "Python: $venvPython"
