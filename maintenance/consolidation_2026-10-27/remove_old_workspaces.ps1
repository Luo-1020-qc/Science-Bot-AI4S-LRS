$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).ProviderPath
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'migration.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$audit = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'migration_audit.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $audit.passed) { throw 'Migration audit has not passed' }
$expectedNames = @{ g2_2 = 'G2_2_Test_Workspace'; g2_3 = 'G2_3_Test_Workspace' }
$checkedTargets = @()
foreach ($study in @('g2_2', 'g2_3')) {
    $entry = $manifest.studies.$study
    $target = (Resolve-Path -LiteralPath (Join-Path $projectRoot $expectedNames[$study])).ProviderPath
    if ([IO.Path]::GetDirectoryName($target) -ne $projectRoot -or [IO.Path]::GetFileName($target) -ne $expectedNames[$study] -or $target -ne $entry.old_root) {
        throw 'Resolved removal target is outside the two explicitly authorized project folders'
    }
    if ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refuse redirected removal target' }
    $destination = (Resolve-Path -LiteralPath (Join-Path $projectRoot ('RUT_Science\research\strategy_learning\studies\' + $study))).ProviderPath
    if ($destination -ne $entry.new_root) { throw 'Consolidated study path mismatch' }
    $verification = Get-Content -LiteralPath (Join-Path $destination 'evidence\current_verification.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $verification.passed -or -not $audit.studies.$study.old_source_matches_baseline) { throw 'Study has not passed current checks' }
    $files = @(Get-ChildItem -LiteralPath $target -Recurse -File -Force)
    if ($files.Count -ne $entry.file_count) { throw 'Original folder file count changed since migration' }
    foreach ($record in $entry.files.PSObject.Properties) {
        $original = Join-Path $target $record.Name
        $item = Get-Item -LiteralPath $original
        if ($item.Length -ne $record.Value.bytes -or (Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash.ToLowerInvariant() -ne $record.Value.sha256) {
            throw ('Original folder changed since migration: ' + $study + '/' + $record.Name)
        }
    }
    $checkedTargets += $target
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'migration_audit.json') -Destination (Join-Path $PSScriptRoot 'migration_audit_before_removal.json')
foreach ($target in $checkedTargets) {
    Remove-Item -LiteralPath $target -Recurse -Force
    if (Test-Path -LiteralPath $target) { throw 'Former folder still exists after removal' }
}
@{ date = '2026-10-27'; removed = $checkedTargets; source_hashes_checked_immediately_before_removal = $true; migrated_original_files = 517; passed = $true } |
    ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'removal.json') -Encoding UTF8
Write-Output 'Removed only the two verified former research workspaces; consolidated studies retained'
