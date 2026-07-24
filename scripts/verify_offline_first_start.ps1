<#
.SYNOPSIS
    AUTO-MAS v6 离线首次启动验证脚本
.DESCRIPTION
    对 AUTO-MAS v6 Experimental Alpha Full 包执行离线首启的结构预检与人工手测辅助。
    此脚本不会把任意本机 health endpoint 当作本次首启的成功证据，也不会关闭
    或强杀应用/后端进程。首次初始化须由测试者在 UI 中完成，结果应连同手测卡记录。
    检查项：
    1. Alpha Full win-unpacked 目录结构完整性
    2. bundled wheelhouse、runtime lock 与 portable runtime 存在
    3. 目标后端端口在启动前未被占用
    4. Alpha Electron 进程可启动并在人工初始化窗口内保持存活
    5. 人工完成初始化后，配置与本次新增日志的基础检查
.PARAMETER AppDir
    独立的 win-unpacked 测试副本目录。脚本不会清理已有用户数据；
    该目录必须在执行前不含 config 目录。
.PARAMETER Port
    后端端口；当前应用固定使用 36163，传入其他值会被拒绝。
.PARAMETER StartTimeout
    启动超时秒数（默认 30）
.PARAMETER AssumeOffline
    已由操作者断网或在防火墙中阻止出站时，跳过交互确认。
.EXAMPLE
    .\verify_offline_first_start.ps1 -AppDir "D:\build\alpha-test-copy\win-unpacked" -AssumeOffline
.NOTES
    执行前请确保：
    - 断开网络连接（或通过防火墙阻止 Python/Electron 出站）
    - 使用新解压或复制出的测试目录，不能指向用户正在使用的安装目录
    退出码：0=结构预检与人工确认项通过，1=有失败项。
    这不是 GUI 自动化或真实断网证明；UAC、初始化 UI、真实防火墙/断网、安装升级
    与退出后无残留仍须按手测卡执行。
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$AppDir,

    [int]$Port = 36163,

    [int]$StartTimeout = 30,

    [switch]$AssumeOffline
)

$ErrorActionPreference = "Continue"
$exitCode = 0
$results = [System.Collections.ArrayList]::new()
$fixedBackendPort = 36163

if ($Port -ne $fixedBackendPort) {
    Write-Error "当前 AUTO-MAS 后端端口固定为 $fixedBackendPort；离线首启预检不接受 -Port $Port。"
    exit 2
}

function Write-Check {
    param([string]$Name, [bool]$Pass, [string]$Detail = "")
    $status = if ($Pass) { "PASS" } else { "FAIL" }
    $color = if ($Pass) { "Green" } else { "Red" }
    $line = "[$status] $Name"
    if ($Detail) { $line += " — $Detail" }
    Write-Host $line -ForegroundColor $color
    $results.Add([PSCustomObject]@{
        Check = $Name
        Status = $status
        Detail = $Detail
    }) | Out-Null
    if (-not $Pass) { $script:exitCode = 1 }
}

# ── 1. 目录结构检查 ──
Write-Host "`n=== 1. 目录结构检查 ===" -ForegroundColor Cyan

$appExe = Join-Path $AppDir "AUTO-MAS-v6-Experimental-Alpha.exe"
Write-Check "Alpha 可执行文件存在" (Test-Path -LiteralPath $appExe -PathType Leaf) $appExe
if (-not (Test-Path -LiteralPath $appExe -PathType Leaf)) {
    exit 1
}

$snapshotRoot = Join-Path $AppDir "resources\integration-snapshot"
Write-Check "resources\integration-snapshot 存在" (Test-Path $snapshotRoot -PathType Container) $snapshotRoot

$snapshotPath = Join-Path $snapshotRoot "manifest.json"
$snapshotExists = Test-Path $snapshotPath
Write-Check "integration snapshot manifest 存在" $snapshotExists $snapshotPath

if ($snapshotExists) {
    $snapshotSize = (Get-Item $snapshotPath).Length
    Write-Check "snapshot 非空" ($snapshotSize -gt 0) "大小: $snapshotSize bytes"
}

$wheelsDir = Join-Path $snapshotRoot "plugins\wheels"
$wheelsExists = Test-Path $wheelsDir
Write-Check "plugins\wheels 存在" $wheelsExists $wheelsDir

if ($wheelsExists) {
    $wheelCount = (Get-ChildItem -Path $wheelsDir -Filter "*.whl" -File).Count
    Write-Check "wheel 文件数量 > 0" ($wheelCount -gt 0) "共 $wheelCount 个 .whl"
}

$runtimeLockPath = Join-Path $wheelsDir "runtime-lock.json"
Write-Check "runtime-lock.json 存在" (Test-Path $runtimeLockPath -PathType Leaf) $runtimeLockPath

$runtimePython = Join-Path $AppDir "environment\python\python.exe"
$runtimeUv = Join-Path $AppDir "environment\python\Scripts\uv.exe"
Write-Check "Full 包 Python runtime 存在" (Test-Path $runtimePython -PathType Leaf) $runtimePython
Write-Check "Full 包 uv runtime 存在" (Test-Path $runtimeUv -PathType Leaf) $runtimeUv

# ── 2. 进程与端口冲突检查 ──
Write-Host "`n=== 2. 进程与端口冲突检查 ===" -ForegroundColor Cyan

$processName = [System.IO.Path]::GetFileNameWithoutExtension($appExe)
$existingProcesses = Get-Process -Name $processName -ErrorAction SilentlyContinue
if ($existingProcesses) {
    Write-Check "同名测试程序未运行" $false "请手动关闭后重试；脚本不会终止已有进程"
    exit 1
} else {
    Write-Check "同名测试程序未运行" $true
}

try {
    $portListeners = @(
        Get-NetTCPConnection -State Listen -LocalPort $fixedBackendPort -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
} catch {
    Write-Check "后端端口可用" $false "无法安全检查 $fixedBackendPort 端口：$($_.Exception.Message)"
    exit 1
}

if ($portListeners.Count -gt 0) {
    Write-Check "后端端口可用" $false "$fixedBackendPort 已被 PID $($portListeners -join ', ') 占用；脚本不会终止占用者"
    exit 1
}
Write-Check "后端端口可用" $true "$fixedBackendPort 未被监听"

# ── 3. 启动应用 ──
Write-Host "`n=== 3. 启动应用（离线模式）===" -ForegroundColor Cyan
if (-not $AssumeOffline) {
    Write-Host "请确认网络已断开或已通过防火墙阻止出站连接" -ForegroundColor Yellow
    Write-Host "按 Enter 键继续，或按 Ctrl+C 取消..." -ForegroundColor Yellow
    Read-Host
}

$configDir = Join-Path $AppDir "config"
$runtimeArtifactDirectories = @(
    $configDir,
    (Join-Path $AppDir "debug"),
    (Join-Path $AppDir "logs")
) | Where-Object { Test-Path -LiteralPath $_ }
if ($runtimeArtifactDirectories.Count -gt 0) {
    Write-Check "独立首次启动目录" $false "已存在运行时数据：$($runtimeArtifactDirectories -join '; ')；请改用新解压/复制出的测试目录，脚本拒绝删除配置或日志"
    exit 1
}

$testStartedAt = Get-Date

Write-Host "启动 AUTO-MAS..." -ForegroundColor Cyan
$process = Start-Process -FilePath $appExe -PassThru -ErrorAction SilentlyContinue
Write-Check "进程已启动" ($null -ne $process) "PID: $($process.Id)"

if ($null -eq $process) {
    Write-Host "无法启动进程，终止验证" -ForegroundColor Red
    exit 1
}

# ── 4. Alpha UI 启动与人工初始化 ──
Write-Host "`n=== 4. Alpha UI 启动与人工离线初始化 ===" -ForegroundColor Cyan

$elapsed = 0
while ($elapsed -lt $StartTimeout -and -not $process.HasExited) {
    Start-Sleep -Seconds 1
    $elapsed += 1
}

Write-Check "Alpha Electron 进程保持运行" (-not $process.HasExited) "启动观察 ${elapsed}s，PID: $($process.Id)"
if ($process.HasExited) {
    Write-Host "Alpha Electron 在初始化 UI 出现前退出；请保留 debug/logs 供排查。" -ForegroundColor Red
    exit 1
}

Write-Host "`n请在已启动的 Alpha UI 中完成首次初始化：确认 bundled snapshot 部署、离线 bootstrap、插件加载与首页可用。" -ForegroundColor Yellow
Write-Host "完成后按 Enter 继续检查；若无法完成，请按 Ctrl+C 并保留当前目录与日志。" -ForegroundColor Yellow
Read-Host | Out-Null

# ── 5. 配置文件创建检查 ──
Write-Host "`n=== 5. 配置文件创建检查 ===" -ForegroundColor Cyan

Start-Sleep -Seconds 2

if (Test-Path $configDir) {
    Write-Check "config 目录已创建" $true $configDir
    $configFiles = Get-ChildItem -Path $configDir -Filter "*.json" -File -ErrorAction SilentlyContinue
    Write-Check "JSON 配置文件已生成" ($configFiles.Count -gt 0) "共 $($configFiles.Count) 个 JSON"

    $v2TomlFiles = Get-ChildItem -Path $configDir -Filter "*.v2.toml" -File -ErrorAction SilentlyContinue
    $v2ShadowFiles = Get-ChildItem -Path $configDir -Filter "*.v2.shadow.toml" -File -ErrorAction SilentlyContinue
    $totalV2 = ($v2TomlFiles | Measure-Object).Count + ($v2ShadowFiles | Measure-Object).Count
    Write-Check "v2 TOML 文件已生成" ($totalV2 -gt 0) "共 $totalV2 个 v2 文件"
} else {
    Write-Check "config 目录已创建" $false "目录不存在: $configDir"
}

# ── 6. 日志网络错误检查 ──
Write-Host "`n=== 6. 日志网络错误检查 ===" -ForegroundColor Cyan

$logDirectories = @(
    (Join-Path $AppDir "debug"),
    (Join-Path $AppDir "logs")
) | Where-Object { Test-Path -LiteralPath $_ -PathType Container }
if ($logDirectories.Count -gt 0) {
    $logFiles = @(
        foreach ($logDirectory in $logDirectories) {
            Get-ChildItem -LiteralPath $logDirectory -Filter "*.log" -File -ErrorAction SilentlyContinue |
                Where-Object { $_.LastWriteTime -ge $testStartedAt.AddSeconds(-2) }
        }
    )
    $networkErrors = @()
    $networkPatterns = @(
        "ConnectionError",
        "ConnectionRefusedError",
        "ConnectionResetError",
        "ConnectionAbortedError",
        "TimeoutError",
        "socket\.timeout",
        "NameResolutionError",
        "getaddrinfo failed",
        "Network is unreachable",
        "urllib.*URLError",
        "requests.*ConnectionError"
    )
    $pattern = ($networkPatterns -join "|")

    foreach ($logFile in $logFiles) {
        $content = Get-Content $logFile.FullName -Raw -ErrorAction SilentlyContinue
        $matches = [regex]::Matches($content, $pattern, "IgnoreCase")
        if ($matches.Count -gt 0) {
            $networkErrors += "$($logFile.Name): $($matches.Count) 处网络错误"
        }
    }

    if ($networkErrors.Count -eq 0) {
        Write-Check "日志无网络错误" $true "扫描了 $($logFiles.Count) 个日志文件"
    } else {
        $detail = $networkErrors -join "; "
        Write-Check "日志无网络错误" $false $detail
    }
} else {
    Write-Check "启动日志可读取" $false "debug/logs 目录均不存在"
}

# ── 7. 人工收尾边界 ──
Write-Host "`n=== 7. 人工收尾边界 ===" -ForegroundColor Cyan
Write-Host "本脚本不会调用 /api/core/close，也不会终止任何进程。请测试者在 UI 中正常退出，再按手测卡确认 Python 子进程与 $fixedBackendPort 无残留。" -ForegroundColor Yellow
Write-Check "自动化边界已保留" $true "真实 UI 初始化、离线网络隔离与进程清理由人工手测卡负责"

# ── 汇总 ──
Write-Host "`n=== 验证汇总 ===" -ForegroundColor Cyan
$results | Format-Table -AutoSize

$totalChecks = $results.Count
$passedChecks = ($results | Where-Object { $_.Status -eq "PASS" }).Count
$failedChecks = ($results | Where-Object { $_.Status -eq "FAIL" }).Count

Write-Host "`n总计: $totalChecks 项检查, $passedChecks 通过, $failedChecks 失败" -ForegroundColor $(if ($failedChecks -eq 0) { "Green" } else { "Red" })

if ($exitCode -eq 0) {
    Write-Host "`n离线首次启动结构预检与人工确认: 通过（不等同于 GUI 自动化或真实断网认证）" -ForegroundColor Green
} else {
    Write-Host "`n离线首次启动验证: 存在失败项，请检查上方详情" -ForegroundColor Red
}

exit $exitCode
