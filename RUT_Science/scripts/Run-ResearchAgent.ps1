[CmdletBinding()]
param(
    [ValidateSet('api', 'offline')][string]$Backend = 'api',
    [string]$Model = 'deepseek-flash',
    [string]$RunDirectory,
    [string]$DataDirectory,
    [string]$InputFile,
    [switch]$Resume,
    [switch]$Recover,
    [switch]$PrepareOnly,
    [int]$StopAfter = 0,
    [int]$MaxRequests = 12,
    [int]$MaxRunTokens = 120000,
    [int]$MaxSeconds = 180
)
$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
$pythonExecutable = Join-Path $projectDirectory '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw 'Create the project .venv and install .[planning] first.' }
if ($Resume -and -not $RunDirectory) { throw '-Resume requires -RunDirectory.' }
$pythonArguments = @('-m', 'rut_science', 'chat', '--backend', $Backend, '--model', $Model,
    '--max-requests', [string]$MaxRequests, '--max-run-tokens', [string]$MaxRunTokens, '--max-seconds', [string]$MaxSeconds)
if ($RunDirectory) { $pythonArguments += @('--output', $RunDirectory) }
if ($DataDirectory) { $pythonArguments += @('--data', $DataDirectory) }
if ($InputFile) { $pythonArguments += @('--script', $InputFile) }
if ($Resume) { $pythonArguments += '--resume' }
if ($Recover) { $pythonArguments += '--recover' }
if ($PrepareOnly) { $pythonArguments += '--prepare-only' }
if ($StopAfter -gt 0) { $pythonArguments += @('--stop-after', [string]$StopAfter) }
$previousPythonEncoding = [Environment]::GetEnvironmentVariable('PYTHONIOENCODING', 'Process')
[Environment]::SetEnvironmentVariable('PYTHONIOENCODING', 'utf-8', 'Process')
Push-Location -LiteralPath $projectDirectory
try {
    & $pythonExecutable @pythonArguments
    $researchExitCode = $LASTEXITCODE
} finally {
    Pop-Location
    [Environment]::SetEnvironmentVariable('PYTHONIOENCODING', $previousPythonEncoding, 'Process')
}
exit $researchExitCode
