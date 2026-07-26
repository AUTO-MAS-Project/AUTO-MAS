<#
.SYNOPSIS
    verify_bundled_plugin_contract.ps1 的离线正反 fixture 自测。
.DESCRIPTION
    在新的临时目录生成最小 portable 结构和 wheel：
    - matching fixture 必须通过；
    - stale-pin fixture 模拟 Alpha .4，必须被确定性拒绝；
    - orphan-wheel fixture 在 wheelhouse 中放入一个 manifest 未声明的 wheel，必须被拒绝。

    自测不会联网，不依赖 Python，也不会删除生成的证据目录。
.PARAMETER FixtureRoot
    可选的全新 fixture 根目录。省略时在当前短 TEMP 下使用随机目录。
#>

param(
    [string] $FixtureRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

[void] (Add-Type -AssemblyName System.IO.Compression.FileSystem)

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$verifierPath = Join-Path $repositoryRoot 'scripts\verify_bundled_plugin_contract.ps1'
if (-not (Test-Path -LiteralPath $verifierPath -PathType Leaf)) {
    throw "Verifier not found: $verifierPath"
}

if ([string]::IsNullOrWhiteSpace($FixtureRoot)) {
    $FixtureRoot = Join-Path $env:TEMP "mas-bpc-$([guid]::NewGuid().ToString('N'))"
}
if (Test-Path -LiteralPath $FixtureRoot) {
    throw "FixtureRoot must not exist: $FixtureRoot"
}
[void] (New-Item -ItemType Directory -Path $FixtureRoot)

function Write-ZipEntry {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.Compression.ZipArchive] $Archive,

        [Parameter(Mandatory = $true)]
        [string] $Name,

        [Parameter(Mandatory = $true)]
        [string] $Content
    )

    $entry = $Archive.CreateEntry($Name)
    $entry.LastWriteTime = [System.DateTimeOffset]::new(2024, 1, 1, 0, 0, 0, [System.TimeSpan]::Zero)
    $stream = $entry.Open()
    try {
        $writer = [System.IO.StreamWriter]::new(
            $stream,
            [System.Text.UTF8Encoding]::new($false)
        )
        try {
            $writer.Write($Content)
        } finally {
            $writer.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

function New-ContractFixture {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Root,

        [Parameter(Mandatory = $true)]
        [string] $DeclaredVersion
    )

    $wheelsRoot = Join-Path $Root 'resources\integration-snapshot\plugins\wheels'
    [void] (New-Item -ItemType Directory -Path $wheelsRoot -Force)

    $wheelFilename = 'demo_plugin-1.2.3-py3-none-any.whl'
    $wheelPath = Join-Path $wheelsRoot $wheelFilename
    $archive = [System.IO.Compression.ZipFile]::Open(
        $wheelPath,
        [System.IO.Compression.ZipArchiveMode]::Create
    )
    try {
        Write-ZipEntry `
            -Archive $archive `
            -Name 'demo_plugin-1.2.3.dist-info/METADATA' `
            -Content "Metadata-Version: 2.4`nName: demo_plugin`nVersion: 1.2.3`n"
        Write-ZipEntry `
            -Archive $archive `
            -Name 'demo_plugin-1.2.3.dist-info/entry_points.txt' `
            -Content "[auto_mas.plugins]`ndemo = demo_plugin.plugin:Plugin`n"
    } finally {
        $archive.Dispose()
    }

    $wheelFile = Get-Item -LiteralPath $wheelPath
    $wheelHash = (Get-FileHash -LiteralPath $wheelPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $entryPoint = [ordered]@{
        group = 'auto_mas.plugins'
        name = 'demo'
        value = 'demo_plugin.plugin:Plugin'
    }
    $pluginRecord = [ordered]@{
        distribution = 'demo_plugin'
        version = '1.2.3'
        scope = 'plugin'
        filename = $wheelFilename
        size_bytes = $wheelFile.Length
        sha256 = $wheelHash
        entry_points = @($entryPoint)
    }
    $runtimeLock = [ordered]@{
        schema_version = 1
        host_runtime = @()
        plugin_runtime = @()
        plugins = @($pluginRecord)
        expected_plugin_entry_points = @($entryPoint)
    }
    $runtimeLockPath = Join-Path $wheelsRoot 'runtime-lock.json'
    $runtimeLock | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $runtimeLockPath -Encoding utf8
    $runtimeLockFile = Get-Item -LiteralPath $runtimeLockPath
    $runtimeLockHash = (
        Get-FileHash -LiteralPath $runtimeLockPath -Algorithm SHA256
    ).Hash.ToLowerInvariant()

    $manifest = [ordered]@{
        schema_version = 1
        runtime_lock = [ordered]@{
            filename = 'runtime-lock.json'
            size_bytes = $runtimeLockFile.Length
            sha256 = $runtimeLockHash
        }
        wheels = @(
            [ordered]@{
                kind = 'plugin'
                scopes = @('plugin')
                distribution = 'demo_plugin'
                version = '1.2.3'
                filename = $wheelFilename
                size_bytes = $wheelFile.Length
                sha256 = $wheelHash
                entry_points = @($entryPoint)
            }
        )
    }
    $manifest | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath (Join-Path $wheelsRoot 'manifest.json') -Encoding utf8

    @"
[tool.auto-mas.plugin-bootstrap]
packages = [
    { name = "demo-plugin", version = "$DeclaredVersion" },
]
"@ | Set-Content `
        -LiteralPath (Join-Path $Root 'resources\integration-snapshot\pyproject.toml') `
        -Encoding utf8
}

$matchingRoot = Join-Path $FixtureRoot 'matching'
$stalePinRoot = Join-Path $FixtureRoot 'stale-pin'
$orphanRoot = Join-Path $FixtureRoot 'orphan-wheel'
New-ContractFixture -Root $matchingRoot -DeclaredVersion '1.2.3'
New-ContractFixture -Root $stalePinRoot -DeclaredVersion '1.2.2'
New-ContractFixture -Root $orphanRoot -DeclaredVersion '1.2.3'

# 在 orphan fixture 的 wheelhouse 中放入一个 manifest 未声明的 wheel，模拟 MaaEnd 0.0.4 共存场景。
$orphanWheelsRoot = Join-Path $orphanRoot 'resources\integration-snapshot\plugins\wheels'
$orphanWheelFilename = 'demo_plugin-1.2.2-py3-none-any.whl'
$orphanWheelPath = Join-Path $orphanWheelsRoot $orphanWheelFilename
$orphanArchive = [System.IO.Compression.ZipFile]::Open(
    $orphanWheelPath,
    [System.IO.Compression.ZipArchiveMode]::Create
)
try {
    Write-ZipEntry `
        -Archive $orphanArchive `
        -Name 'demo_plugin-1.2.2.dist-info/METADATA' `
        -Content "Metadata-Version: 2.4`nName: demo_plugin`nVersion: 1.2.2`n"
} finally {
    $orphanArchive.Dispose()
}

$matchingOutput = @(
    & $PSHOME\pwsh.exe -NoProfile -File $verifierPath -PortableRoot $matchingRoot 2>&1
)
$matchingExitCode = $LASTEXITCODE
if ($matchingExitCode -ne 0) {
    throw "Matching fixture failed with exit $matchingExitCode`n$($matchingOutput -join [Environment]::NewLine)"
}

$stalePinOutput = @(
    & $PSHOME\pwsh.exe -NoProfile -File $verifierPath -PortableRoot $stalePinRoot 2>&1
)
$stalePinExitCode = $LASTEXITCODE
$stalePinText = $stalePinOutput -join [Environment]::NewLine
if ($stalePinExitCode -ne 1) {
    throw "Stale-pin fixture returned $stalePinExitCode instead of 1`n$stalePinText"
}
if ($stalePinText -notmatch 'expected 1\.2\.2, got 1\.2\.3') {
    throw "Stale-pin fixture did not report the expected version mismatch`n$stalePinText"
}

$orphanOutput = @(
    & $PSHOME\pwsh.exe -NoProfile -File $verifierPath -PortableRoot $orphanRoot 2>&1
)
$orphanExitCode = $LASTEXITCODE
$orphanText = $orphanOutput -join [Environment]::NewLine
if ($orphanExitCode -ne 1) {
    throw "Orphan-wheel fixture returned $orphanExitCode instead of 1`n$orphanText"
}
if ($orphanText -notmatch '孤儿 wheel') {
    throw "Orphan-wheel fixture did not report orphan wheel`n$orphanText"
}
if ($orphanText -notmatch [regex]::Escape($orphanWheelFilename)) {
    throw "Orphan-wheel fixture did not name the orphan file`n$orphanText"
}

Write-Host '[PASS] matching fixture accepted' -ForegroundColor Green
Write-Host '[PASS] stale-pin fixture rejected with expected mismatch' -ForegroundColor Green
Write-Host '[PASS] orphan-wheel fixture rejected with expected orphan name' -ForegroundColor Green
Write-Host "Fixture evidence retained at: $FixtureRoot"
exit 0
