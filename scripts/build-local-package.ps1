#Requires -Version 7.0

[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [string]$LocalRuntimePath,
    [switch]$VerifyRuntimeOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory)]
        [string]$Command,

        [Parameter()]
        [string[]]$Arguments = @()
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "命令执行失败（退出码 $LASTEXITCODE）：$Command $($Arguments -join ' ')"
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot "frontend"
$versionFile = Join-Path $repoRoot "res\version.json"
$frontendPackageFile = Join-Path $frontendRoot "package.json"
$backendConfigFile = Join-Path $repoRoot "app\core\config.py"
$pyprojectFile = Join-Path $repoRoot "pyproject.toml"
$uvLockFile = Join-Path $repoRoot "uv.lock"
$buildWorkflowFile = Join-Path $repoRoot ".github\workflows\build-app.yml"

foreach ($requiredFile in @(
        $versionFile,
        $frontendPackageFile,
        $backendConfigFile,
        $pyprojectFile,
        $uvLockFile,
        $buildWorkflowFile
    )) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "缺少打包所需文件：$requiredFile"
    }
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "未找到 Node.js，请先安装项目要求的 Node.js 环境。"
}
if (-not (Get-Command yarn -ErrorAction SilentlyContinue)) {
    throw "未找到 Yarn，请先执行：corepack prepare yarn@4.9.1 --activate"
}

# 第一步：确认所有版本来源一致，避免打出版本信息互相冲突的安装包。
$versionConfig = Get-Content -LiteralPath $versionFile -Raw | ConvertFrom-Json
$frontendPackage = Get-Content -LiteralPath $frontendPackageFile -Raw | ConvertFrom-Json
$appVersion = [string]$versionConfig.version

if ($appVersion -notmatch '^v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$') {
    throw "res/version.json 中的版本格式无效：$appVersion"
}
if ([string]$frontendPackage.version -ne $appVersion) {
    throw "frontend/package.json 版本不一致：$($frontendPackage.version)，预期 $appVersion"
}

$backendConfigText = Get-Content -LiteralPath $backendConfigFile -Raw
$backendVersionMatch = [regex]::Match(
    $backendConfigText,
    '(?m)^\s*VERSION\s*=\s*"(?<version>v[^"]+)"'
)
if (-not $backendVersionMatch.Success -or $backendVersionMatch.Groups['version'].Value -ne $appVersion) {
    throw "app/core/config.py 版本与 $appVersion 不一致。"
}

$pythonVersion = $appVersion.Substring(1)
$pyprojectText = Get-Content -LiteralPath $pyprojectFile -Raw
$pyprojectVersionMatch = [regex]::Match(
    $pyprojectText,
    '(?m)^version\s*=\s*"(?<version>[^"]+)"'
)
if (-not $pyprojectVersionMatch.Success -or $pyprojectVersionMatch.Groups['version'].Value -ne $pythonVersion) {
    throw "pyproject.toml 版本与 $pythonVersion 不一致。"
}

$expectedLockVersion = $pythonVersion `
    -replace '-alpha\.', 'a' `
    -replace '-beta\.', 'b' `
    -replace '-rc\.', 'rc'
$uvLockText = Get-Content -LiteralPath $uvLockFile -Raw
$uvVersionMatch = [regex]::Match(
    $uvLockText,
    '(?ms)^\[\[package\]\]\r?\nname = "auto-mas"\r?\nversion = "(?<version>[^"]+)"'
)
if (-not $uvVersionMatch.Success -or $uvVersionMatch.Groups['version'].Value -ne $expectedLockVersion) {
    throw "uv.lock 中 auto-mas 的版本与 $expectedLockVersion 不一致，请先运行 uv lock。"
}

$workflowText = Get-Content -LiteralPath $buildWorkflowFile -Raw
$runtimeVersionMatch = [regex]::Match(
    $workflowText,
    '(?m)^\s*RUNTIME_VERSION:\s*["'']?(?<version>v[0-9A-Za-z.-]+)["'']?\s*$'
)
if (-not $runtimeVersionMatch.Success) {
    throw "无法从 .github/workflows/build-app.yml 读取 RUNTIME_VERSION。"
}
$runtimeVersion = $runtimeVersionMatch.Groups['version'].Value

Write-Host "应用版本：$appVersion"
Write-Host "Runtime 版本：$runtimeVersion"

# 第二步：使用指定的本地 Runtime，或下载并校验官方 Release。
$temporaryRoot = Join-Path (
    [System.IO.Path]::GetTempPath()
) "auto-mas-local-package-$([guid]::NewGuid().ToString('N'))"
$runtimeAssetName = "auto-mas-runtime-$runtimeVersion.exe"
$runtimePath = Join-Path $temporaryRoot $runtimeAssetName
$checksumPath = Join-Path $temporaryRoot "SHA256SUMS.txt"
$releaseBaseUrl = "https://github.com/AUTO-MAS-Project/AUTO-MAS-Runtime/releases/download/$runtimeVersion"

New-Item -ItemType Directory -Path $temporaryRoot | Out-Null

$savedEnvironment = @{}
foreach ($name in @(
        "SENTRY_AUTH_TOKEN",
        "SENTRY_ORG",
        "SENTRY_PROJECT",
        "CSC_IDENTITY_AUTO_DISCOVERY"
    )) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

try {
    if ($LocalRuntimePath) {
        $localRuntime = (Resolve-Path -LiteralPath $LocalRuntimePath -ErrorAction Stop).Path
        $expectedRuntimeHash = (Get-FileHash -LiteralPath $localRuntime -Algorithm SHA256).Hash
        Copy-Item -LiteralPath $localRuntime -Destination $runtimePath
    } else {
        Write-Host "正在下载 Runtime……"
        Invoke-WebRequest -Uri "$releaseBaseUrl/$runtimeAssetName" -OutFile $runtimePath
        Invoke-WebRequest -Uri "$releaseBaseUrl/SHA256SUMS.txt" -OutFile $checksumPath

        $checksumLine = Select-String `
            -LiteralPath $checksumPath `
            -Pattern ([regex]::Escape($runtimeAssetName)) |
            Select-Object -First 1
        if (-not $checksumLine) {
            throw "SHA256SUMS.txt 中找不到 $runtimeAssetName。"
        }

        $expectedRuntimeHash = ($checksumLine.Line -split '\s+')[0].ToUpperInvariant()
    }
    $actualRuntimeHash = (Get-FileHash -LiteralPath $runtimePath -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($actualRuntimeHash -ne $expectedRuntimeHash) {
        throw "Runtime SHA-256 校验失败，文件可能下载损坏。"
    }

    $runtimeVersionOutput = @(& $runtimePath --output ndjson --protocol 1 version)
    if ($LASTEXITCODE -ne 0) {
        throw "Runtime 版本检查失败（退出码 $LASTEXITCODE）。"
    }
    $runtimeVersionOutput | ForEach-Object { Write-Host $_ }

    $runtimeHello = $runtimeVersionOutput |
        ForEach-Object { $_ | ConvertFrom-Json } |
        Where-Object { $_.type -eq "hello" } |
        Select-Object -First 1
    if (-not $runtimeHello -or (-not $LocalRuntimePath -and $runtimeHello.runtimeVersion -ne $runtimeVersion)) {
        throw "Runtime 实际版本与 $runtimeVersion 不一致。"
    }

    # 用非法版本做只读协议探测，避免旧 Runtime 与新桌面包组合后无法启动。
    foreach ($probe in @(
        @{ Arguments = @('workspace', 'stage', '--version', 'invalid') },
        @{ Arguments = @('bootstrap', '--version', 'invalid', '--if-needed') }
    )) {
        $probeArguments = $probe.Arguments
        $probeOutput = @(& $runtimePath --app-root $temporaryRoot --output ndjson --protocol 1 @probeArguments)
        $probeExit = $LASTEXITCODE
        $probeResult = $probeOutput | ForEach-Object { $_ | ConvertFrom-Json } |
            Where-Object { $_.type -eq 'result' } | Select-Object -Last 1
        if ($probeExit -ne 2 -or -not $probeResult -or $probeResult.code -ne 'INVALID_VERSION') {
            throw 'Runtime 不支持后台更新启动协议，请用 -LocalRuntimePath 指定本次源码构建的 Runtime，或先更新发布版本。'
        }
    }
    if ($VerifyRuntimeOnly) {
        Write-Host "Runtime 后台更新协议与 SHA-256 已验证：$expectedRuntimeHash"
        exit 0
    }

    # 第三步：正常构建 Electron，再把 Runtime 注入解压包并重建安装程序。
    Push-Location $frontendRoot
    try {
        if (-not $SkipInstall) {
            Invoke-NativeCommand -Command "yarn" -Arguments @("install", "--immutable")
        }

        [Environment]::SetEnvironmentVariable("SENTRY_AUTH_TOKEN", $null, "Process")
        [Environment]::SetEnvironmentVariable("SENTRY_ORG", $null, "Process")
        [Environment]::SetEnvironmentVariable("SENTRY_PROJECT", $null, "Process")
        [Environment]::SetEnvironmentVariable("CSC_IDENTITY_AUTO_DISCOVERY", "false", "Process")

        Invoke-NativeCommand -Command "yarn" -Arguments @("build")

        $unpackedDirectory = Join-Path $frontendRoot "dist\win-unpacked"
        $runtimeTarget = Join-Path $unpackedDirectory "resources\auto-mas-runtime.exe"
        if (-not (Test-Path -LiteralPath $unpackedDirectory -PathType Container)) {
            throw "Electron 未生成 win-unpacked：$unpackedDirectory"
        }

        New-Item -ItemType Directory -Path (Split-Path -Parent $runtimeTarget) -Force | Out-Null
        Copy-Item -LiteralPath $runtimePath -Destination $runtimeTarget -Force

        $packagedRuntimeHash = (Get-FileHash -LiteralPath $runtimeTarget -Algorithm SHA256).Hash
        if ($packagedRuntimeHash -ne $expectedRuntimeHash) {
            throw "注入后的 Runtime SHA-256 校验失败。"
        }

        Invoke-NativeCommand `
            -Command "yarn" `
            -Arguments @(
                "electron-builder",
                "--prepackaged",
                "dist/win-unpacked",
                "--win",
                "nsis",
                "--publish",
                "never"
            )
    } finally {
        Pop-Location
    }

    # 第四步：复制到全新的时间戳目录，避免旧包运行数据或 ACL 影响下次打包。
    $installerName = "AUTO-MAS Setup $pythonVersion.exe"
    $installerPath = Join-Path $frontendRoot "dist\$installerName"
    $unpackedDirectory = Join-Path $frontendRoot "dist\win-unpacked"
    $sevenZipPath = Join-Path $frontendRoot "node_modules\7zip-bin\win\x64\7za.exe"

    foreach ($artifact in @($installerPath, $unpackedDirectory, $sevenZipPath)) {
        if (-not (Test-Path -LiteralPath $artifact)) {
            throw "缺少打包产物：$artifact"
        }
    }

    $installerListing = @(& $sevenZipPath l -slt $installerPath)
    if ($LASTEXITCODE -ne 0) {
        throw "无法检查安装程序内容（退出码 $LASTEXITCODE）。"
    }
    $installerContainsRuntime = $installerListing |
        Where-Object { $_ -eq 'Path = resources\auto-mas-runtime.exe' } |
        Select-Object -First 1
    if (-not $installerContainsRuntime) {
        throw "安装程序中未找到 resources\auto-mas-runtime.exe。"
    }

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $outputRoot = Join-Path $repoRoot "dist\AUTO-MAS-$appVersion-local-$timestamp"
    $outputUnpacked = Join-Path $outputRoot "win-unpacked"
    $outputInstaller = Join-Path $outputRoot $installerName

    New-Item -ItemType Directory -Path $outputRoot | Out-Null
    Copy-Item -LiteralPath $unpackedDirectory -Destination $outputUnpacked -Recurse
    Copy-Item -LiteralPath $installerPath -Destination $outputInstaller

    $blockmapPath = "$installerPath.blockmap"
    if (Test-Path -LiteralPath $blockmapPath -PathType Leaf) {
        Copy-Item -LiteralPath $blockmapPath -Destination $outputRoot
    }

    $outputRuntime = Join-Path $outputUnpacked "resources\auto-mas-runtime.exe"
    $outputApp = Get-Item -LiteralPath (Join-Path $outputUnpacked "AUTO-MAS.exe")
    if ($outputApp.VersionInfo.FileVersion -ne $pythonVersion) {
        throw "AUTO-MAS.exe 文件版本不正确：$($outputApp.VersionInfo.FileVersion)"
    }
    if ((Get-FileHash -LiteralPath $outputRuntime -Algorithm SHA256).Hash -ne $expectedRuntimeHash) {
        throw "最终测试目录中的 Runtime SHA-256 校验失败。"
    }

    $installerHash = (Get-FileHash -LiteralPath $outputInstaller -Algorithm SHA256).Hash

    Write-Host ""
    Write-Host "本地测试包已生成：" -ForegroundColor Green
    Write-Host "输出目录：$outputRoot"
    Write-Host "安装程序：$outputInstaller"
    Write-Host "解压运行：$(Join-Path $outputUnpacked 'AUTO-MAS.exe')"
    Write-Host "安装包 SHA-256：$installerHash"
    Write-Host "Runtime SHA-256：$expectedRuntimeHash"
} finally {
    foreach ($name in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], "Process")
    }

    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
