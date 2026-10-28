[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('run', 'resume', 'status', 'revise', 'validate', 'verify')]
    [string]$Action = 'run',
    [ValidateSet('darcy', 'synthetic')][string]$Workflow = 'darcy',
    [ValidateSet('offline', 'api', 'file')][string]$Backend = 'offline',
    [string]$Model,
    [string]$RunDirectory,
    [string]$SpecFile,
    [string]$PlanFile,
    [string]$DataDirectory,
    [string]$Reason = 'Operator revision of unexecuted nodes',
    [int]$StopAfter = 0,
    [int]$MaxSeconds = 180,
    [switch]$ValidationSelect,
    [switch]$Recover,
    [string]$FaultTool,
    [int]$FaultCount = 0
)

$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
$pythonExecutable = Join-Path $projectDirectory '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    throw 'Project Python is missing. Create .venv and install the planning dependencies described in docs/Structured_Planning_Agent_zh.md.'
}
if ($Action -in @('resume', 'status', 'revise', 'verify') -and [string]::IsNullOrWhiteSpace($RunDirectory)) {
    throw 'This action requires -RunDirectory pointing to the session directory.'
}
$pythonArguments = @('-m', 'rut_science', 'plan', $Action)
if ($Action -in @('run', 'validate')) {
    $pythonArguments += @('--workflow', $Workflow, '--backend', $Backend, '--max-seconds', [string]$MaxSeconds)
}
if ($RunDirectory) { $pythonArguments += @('--output', $RunDirectory) }
if ($Model) { $pythonArguments += @('--model', $Model) }
if ($SpecFile) { $pythonArguments += @('--spec', $SpecFile) }
if ($PlanFile) { $pythonArguments += @('--plan-file', $PlanFile) }
if ($DataDirectory) { $pythonArguments += @('--data', $DataDirectory) }
if ($StopAfter -gt 0) { $pythonArguments += @('--stop-after', [string]$StopAfter) }
if ($Action -eq 'revise') { $pythonArguments += @('--reason', $Reason) }
if ($ValidationSelect) { $pythonArguments += '--validation-select' }
if ($Recover) { $pythonArguments += '--recover' }
if ($FaultTool) { $pythonArguments += @('--fault-tool', $FaultTool, '--fault-count', [string]$FaultCount) }

$previousPythonEncoding = [Environment]::GetEnvironmentVariable('PYTHONIOENCODING', 'Process')
[Environment]::SetEnvironmentVariable('PYTHONIOENCODING', 'utf-8', 'Process')
Push-Location -LiteralPath $projectDirectory
try {
    & $pythonExecutable @pythonArguments
    $planningExitCode = $LASTEXITCODE
} finally {
    Pop-Location
    [Environment]::SetEnvironmentVariable('PYTHONIOENCODING', $previousPythonEncoding, 'Process')
}
exit $planningExitCode
