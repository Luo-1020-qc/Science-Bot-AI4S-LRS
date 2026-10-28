param(
    [ValidateSet('api','offline')][string]$Backend = 'api',
    [ValidateSet('rl','bc','llm','adaptive','cheap','dense','search','random')][string]$Planner = 'rl',
    [ValidateSet('generated','darcy')][string]$Dataset = 'generated',
    [int]$Budget = 10,
    [string]$Resume = '',
    [string]$Workspace = ''
)
$ErrorActionPreference = 'Stop'
$projectPath = Join-Path $PSScriptRoot 'RUT_Science'
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Missing project .venv. See delivery/README_运行与复现.md.' }
$workspaceArgument = ''
if ($Workspace) { $workspaceArgument = (Resolve-Path -LiteralPath $Workspace -ErrorAction Stop).ProviderPath }
$resumeArgument = $Resume
if ($Resume -and (Test-Path -LiteralPath $Resume)) { $resumeArgument = (Resolve-Path -LiteralPath $Resume).ProviderPath }
Push-Location -LiteralPath $projectPath
try {
    $botArguments = @('-m','rut_science','science','--backend',$Backend,'--planner',$Planner,'--budget',"$Budget")
    if ($PSBoundParameters.ContainsKey('Dataset')) { $botArguments += @('--dataset',$Dataset) }
    if ($Resume) { $botArguments += @('--resume',$resumeArgument) }
    if ($Workspace) { $botArguments += @('--workspace',$workspaceArgument) }
    & $pythonPath @botArguments
    exit $LASTEXITCODE
} finally { Pop-Location }
