[CmdletBinding()]
param(
    [string] $HostRepositoryRoot,
    [string] $HsrRepositoryRoot,
    [string] $M9aRepositoryRoot,
    [string] $MaaFwRepositoryRoot,
    [string] $MxuImportRepositoryRoot,
    [string] $MaaEndAdapterRepositoryRoot,
    [string] $MaaScriptRepositoryRoot,
    [string] $EnvironmentRoot,
    [string] $UvPath,
    [string] $PythonPath,
    [string] $GitPath,
    [string] $OutputDirectory,
    [string] $PluginSeedDirectory,
    [string] $BuildStagingDirectory,
    [string] $CompletionStagingDirectory,
    [string] $DefaultIndex = 'https://pypi.org/simple',
    [string] $ExcludeNewer,
    [ValidateRange(0, [long]::MaxValue)]
    [long] $SourceDateEpoch = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-FullPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [string] $BasePath
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    if ([string]::IsNullOrWhiteSpace($BasePath)) {
        $BasePath = (Get-Location).Path
    }
    return [System.IO.Path]::GetFullPath((Join-Path $BasePath $Path))
}

$defaultHostRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($HostRepositoryRoot)) {
    $HostRepositoryRoot = $defaultHostRoot
}
$HostRepositoryRoot = Get-FullPath -Path $HostRepositoryRoot
$runId = '{0}-{1}' -f ([DateTimeOffset]::UtcNow.ToString('yyyyMMdd-HHmmss')), ([Guid]::NewGuid().ToString('N'))

if ([string]::IsNullOrWhiteSpace($EnvironmentRoot)) {
    $EnvironmentRoot = Join-Path $HostRepositoryRoot 'build\environment-tar\environment'
}
$EnvironmentRoot = Get-FullPath -Path $EnvironmentRoot -BasePath $HostRepositoryRoot
if ([string]::IsNullOrWhiteSpace($UvPath)) {
    $environmentUvPath = Join-Path $EnvironmentRoot 'python\Scripts\uv.exe'
    $workspaceUvPath = Join-Path $HostRepositoryRoot 'environment\python\Scripts\uv.exe'
    if (Test-Path -LiteralPath $environmentUvPath -PathType Leaf) {
        $UvPath = $environmentUvPath
    } else {
        # The local integration workspace keeps pinned uv beside, rather than
        # inside, the separately extracted official environment archive.
        $UvPath = $workspaceUvPath
    }
}
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = Join-Path $EnvironmentRoot 'python\python.exe'
}
if ([string]::IsNullOrWhiteSpace($GitPath)) {
    $GitPath = Join-Path $EnvironmentRoot 'git\bin\git.exe'
}
$UvPath = Get-FullPath -Path $UvPath -BasePath $HostRepositoryRoot
$PythonPath = Get-FullPath -Path $PythonPath -BasePath $HostRepositoryRoot
$GitPath = Get-FullPath -Path $GitPath -BasePath $HostRepositoryRoot

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $HostRepositoryRoot "build\wheelhouse\complete-$runId"
}
if ([string]::IsNullOrWhiteSpace($PluginSeedDirectory)) {
    $PluginSeedDirectory = Join-Path $HostRepositoryRoot "build\wheelhouse\plugin-seed-$runId"
}
$OutputDirectory = Get-FullPath -Path $OutputDirectory -BasePath $HostRepositoryRoot
$PluginSeedDirectory = Get-FullPath -Path $PluginSeedDirectory -BasePath $HostRepositoryRoot
if ($OutputDirectory.Equals($PluginSeedDirectory, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'OutputDirectory and PluginSeedDirectory must be different new directories'
}
if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Complete output directory already exists: $OutputDirectory"
}
if (Test-Path -LiteralPath $PluginSeedDirectory) {
    throw "Plugin seed directory already exists: $PluginSeedDirectory"
}

$buildArguments = @{
    HostRepositoryRoot = $HostRepositoryRoot
    EnvironmentRoot = $EnvironmentRoot
    UvPath = $UvPath
    PythonPath = $PythonPath
    GitPath = $GitPath
    OutputDirectory = $PluginSeedDirectory
    SourceDateEpoch = $SourceDateEpoch
}
foreach ($mapping in @(
    @('HsrRepositoryRoot', $HsrRepositoryRoot),
    @('M9aRepositoryRoot', $M9aRepositoryRoot),
    @('MaaFwRepositoryRoot', $MaaFwRepositoryRoot),
    @('MxuImportRepositoryRoot', $MxuImportRepositoryRoot),
    @('MaaEndAdapterRepositoryRoot', $MaaEndAdapterRepositoryRoot),
    @('MaaScriptRepositoryRoot', $MaaScriptRepositoryRoot),
    @('StagingDirectory', $BuildStagingDirectory)
)) {
    if (-not [string]::IsNullOrWhiteSpace([string] $mapping[1])) {
        $buildArguments[[string] $mapping[0]] = [string] $mapping[1]
    }
}

Write-Host 'Stage 1/2: building and validating 23 plugin distributions and 21 entry points.'
& (Join-Path $PSScriptRoot 'build_integration_wheelhouse.ps1') @buildArguments

$completionArguments = @{
    PluginWheelhouseDirectory = $PluginSeedDirectory
    HostPyProjectPath = (Join-Path $HostRepositoryRoot 'pyproject.toml')
    UvPath = $UvPath
    PythonPath = $PythonPath
    OutputDirectory = $OutputDirectory
    DefaultIndex = $DefaultIndex
}
if (-not [string]::IsNullOrWhiteSpace($CompletionStagingDirectory)) {
    $completionArguments.StagingDirectory = $CompletionStagingDirectory
}
if (-not [string]::IsNullOrWhiteSpace($ExcludeNewer)) {
    $completionArguments.ExcludeNewer = $ExcludeNewer
}

Write-Host 'Stage 2/2: resolving, locking, downloading, and validating the complete Windows x64 runtime closure.'
& (Join-Path $PSScriptRoot 'complete_integration_wheelhouse.ps1') @completionArguments

Write-Host "Complete release wheelhouse: $OutputDirectory"
Write-Host "Retained plugin seed for audit: $PluginSeedDirectory"
