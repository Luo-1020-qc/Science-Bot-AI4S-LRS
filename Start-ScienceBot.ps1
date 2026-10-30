param(
    [ValidateSet('api','offline')][string]$Backend = 'api',
    [ValidateSet('rl','bc','llm','adaptive','cheap','dense','search','random')][string]$Planner = 'rl',
    [ValidateSet('generated','darcy')][string]$Dataset = 'generated',
    [int]$Budget = 10,
    [string]$Resume = '',
    [string]$Workspace = '',
    [ValidateSet('terminal','web')][string]$Interface = 'terminal',
    [string]$Model = 'deepseek-flash',
    [int]$Port = 8765,
    [switch]$Example,
    [switch]$NoBrowser,
    [switch]$Preview
)
$ErrorActionPreference = 'Stop'
$projectPath = Join-Path $PSScriptRoot 'RUT_Science'
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Missing project .venv. Run scripts/setup.ps1; see docs/REPRODUCIBILITY.md.' }
$workspaceArgument = ''
if ($Workspace) { $workspaceArgument = (Resolve-Path -LiteralPath $Workspace -ErrorAction Stop).ProviderPath }
$resumeArgument = $Resume
if ($Resume -and (Test-Path -LiteralPath $Resume)) { $resumeArgument = (Resolve-Path -LiteralPath $Resume).ProviderPath }
Push-Location -LiteralPath $projectPath
try {
    if ($Interface -eq 'web') {
        if ($Resume -or $PSBoundParameters.ContainsKey('Dataset')) { throw 'Web interface restores sessions in its recent-research list. Use the terminal for explicit numeric demos or -Resume.' }
        $botArguments = @('-B','-m','rut_science.science_bot.workbench','--port',"$Port",'--backend',$Backend,'--model',$Model)
        if ($Workspace) { $botArguments += @('--workspace',$workspaceArgument) }
        if ($Example) { $botArguments += '--example' }
        if ($NoBrowser) { $botArguments += '--no-browser' }
        & $pythonPath @botArguments
        exit $LASTEXITCODE
    }
    $botArguments = @('-B','-m','rut_science','science','--backend',$Backend,'--model',$Model,'--planner',$Planner,'--budget',"$Budget")
    if ($PSBoundParameters.ContainsKey('Dataset')) { $botArguments += @('--dataset',$Dataset) }
    if ($Resume) { $botArguments += @('--resume',$resumeArgument) }
    if ($Workspace) { $botArguments += @('--workspace',$workspaceArgument) }
    if ($Example) { $botArguments += '--example' }
    if ($Preview) { $botArguments += '--preview' }
    & $pythonPath @botArguments
    exit $LASTEXITCODE
} finally { Pop-Location }
