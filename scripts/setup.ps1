param(
    [string]$Python = 'python',
    [switch]$Exact
)
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$appPath = Join-Path $repoPath 'RUT_Science'
$envPath = Join-Path $appPath '.venv'
$envPython = Join-Path $envPath 'Scripts\python.exe'

if (-not (Test-Path -LiteralPath $envPython)) {
    & $Python -m venv $envPath
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed. Use Python 3.12.' }
}
& $envPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
if ($Exact) {
    & $envPython -m pip install -r (Join-Path $repoPath 'requirements-science-bot.lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Exact dependency install failed. See docs/REPRODUCIBILITY.md.' }
    & $envPython -m pip install --no-deps -e $appPath
} else {
    & $envPython -m pip install -e "${appPath}[science-bot]"
}
if ($LASTEXITCODE -ne 0) { throw 'Science Bot installation failed.' }
Write-Host 'Installed. Run .\science-bot.cmd -Backend offline from the repository root.'
Write-Host 'For API mode, create API_key_Agent.json using API_key_Agent.example.json. Existing credentials were not changed.'
