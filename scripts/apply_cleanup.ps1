param([string]$Plan = '')
$ErrorActionPreference = 'Stop'
$taskProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if (-not $Plan) { $Plan = Join-Path $taskProjectRoot 'docs\cleanup\2026-10-28\plan.json' }
$taskPlan = Get-Content -Encoding UTF8 -LiteralPath $Plan -Raw | ConvertFrom-Json
$taskArchiveRoot = [IO.Path]::GetFullPath($taskPlan.archive_root)
if ([IO.Path]::GetFullPath($taskPlan.project_root) -ne $taskProjectRoot) { throw 'Cleanup project mismatch' }
if ((Split-Path -Parent $taskArchiveRoot) -ne (Split-Path -Parent $taskProjectRoot)) { throw 'Archive must be an explicitly named sibling' }
if (Test-Path -LiteralPath $taskArchiveRoot) { throw 'Archive already exists; do not overwrite a previous operation' }

# Validate every absolute source and target before any move/delete.
foreach ($taskItem in @($taskPlan.moves) + @($taskPlan.deletes)) {
    $taskSource = [IO.Path]::GetFullPath((Join-Path $taskProjectRoot $taskItem.source))
    if (-not $taskSource.StartsWith(($taskProjectRoot + '\'), [StringComparison]::OrdinalIgnoreCase)) { throw 'Source outside project' }
    if ($taskItem.source -match '(^|/)(\.git|\.venv)(/|$)' -or $taskItem.source -eq 'API_key_Agent.json') { throw 'Protected local path in cleanup plan' }
    if ($taskItem.destination) {
        $taskTarget = [IO.Path]::GetFullPath($taskItem.destination)
        $taskInArchive = $taskTarget.StartsWith(($taskArchiveRoot + '\'), [StringComparison]::OrdinalIgnoreCase)
        $taskCheckpointTarget = Join-Path $taskProjectRoot 'RUT_Science\models\retained_delivery_checkpoint'
        if (-not $taskInArchive -and $taskTarget -ne $taskCheckpointTarget) { throw 'Unapproved move destination' }
        if (Test-Path -LiteralPath $taskTarget) { throw "Refusing to replace existing destination: $taskTarget" }
    }
}
New-Item -ItemType Directory -Path $taskArchiveRoot | Out-Null
foreach ($taskItem in $taskPlan.moves) {
    $taskSource = [IO.Path]::GetFullPath((Join-Path $taskProjectRoot $taskItem.source))
    $taskTarget = [IO.Path]::GetFullPath($taskItem.destination)
    New-Item -ItemType Directory -Path (Split-Path -Parent $taskTarget) -Force | Out-Null
    Move-Item -LiteralPath ('\\?\' + $taskSource) -Destination ('\\?\' + $taskTarget) -ErrorAction Stop
}
foreach ($taskItem in $taskPlan.deletes) {
    $taskSource = [IO.Path]::GetFullPath((Join-Path $taskProjectRoot $taskItem.source))
    if (Test-Path -LiteralPath $taskSource) { Remove-Item -LiteralPath ('\\?\' + $taskSource) -Recurse -Force -ErrorAction Stop }
}
Write-Output ('Completed verified moves: ' + $taskPlan.moves.Count + '; retired entries removed: ' + $taskPlan.deletes.Count)
