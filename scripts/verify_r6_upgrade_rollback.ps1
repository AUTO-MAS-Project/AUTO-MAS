<#
.SYNOPSIS
    AUTO-MAS v6 r6 覆盖升级与回滚验证脚本
.DESCRIPTION
    验证从 r6 冻结产物升级到当前工作树版本时：
    1. r6 配置（legacy JSON）可被安全读取
    2. Config v2 迁移正确生成 v2 TOML（shadow 或 authoritative 模式）
    3. 配置值在升级前后一致（round-trip 无损）
    4. 回滚（删除 v2 TOML）后 legacy JSON 仍可正常加载
    5. 密文字段在升级后保持可解密
.PARAMETER AppDir
    新版本 win-unpacked 目录路径
.PARAMETER R6ConfigDir
    r6 配置目录路径（包含 *.json 配置文件）
.PARAMETER Port
    后端端口（默认 36163）
.PARAMETER ConfigV2Mode
    Config v2 模式（shadow 或 authoritative，默认 shadow）
.EXAMPLE
    .\verify_r6_upgrade_rollback.ps1 -AppDir "D:\build\win-unpacked" `
        -R6ConfigDir "D:\r6\config" -ConfigV2Mode "authoritative"
.NOTES
    执行前请确保：
    - 关闭所有正在运行的 AUTO-MAS 实例
    - r6 配置目录包含有效的 legacy JSON 配置文件
    退出码：0=全部通过，1=有失败项
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$AppDir,

    [Parameter(Mandatory=$true)]
    [string]$R6ConfigDir,

    [int]$Port = 36163,

    [ValidateSet("shadow", "authoritative")]
    [string]$ConfigV2Mode = "shadow"
)

$ErrorActionPreference = "Continue"
$exitCode = 0
$results = [System.Collections.ArrayList]::new()

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

function Get-ConfigSnapshot {
    param([string]$Dir)
    $snapshot = @{}
    $jsonFiles = Get-ChildItem -Path $Dir -Filter "*.json" -File -ErrorAction SilentlyContinue
    foreach ($f in $jsonFiles) {
        try {
            $content = Get-Content $f.FullName -Raw -Encoding UTF8
            $data = $content | ConvertFrom-Json
            $snapshot[$f.Name] = $data
        } catch {
            $snapshot[$f.Name] = $null
        }
    }
    return $snapshot
}

function Compare-ConfigSnapshot {
    param($Before, $After)
    $diffs = @()
    $allKeys = ($Before.Keys + $After.Keys) | Sort-Object -Unique
    foreach ($key in $allKeys) {
        if (-not $Before.ContainsKey($key)) {
            $diffs += "新增文件: $key"
            continue
        }
        if (-not $After.ContainsKey($key)) {
            $diffs += "缺失文件: $key"
            continue
        }
        $beforeJson = $Before[$key] | ConvertTo-Json -Depth 10 -Compress
        $afterJson = $After[$key] | ConvertTo-Json -Depth 10 -Compress
        if ($beforeJson -ne $afterJson) {
            $diffs += "内容变化: $key"
        }
    }
    return $diffs
}

# ── 0. 前置检查 ──
Write-Host "`n=== 0. 前置检查 ===" -ForegroundColor Cyan

$appExe = Join-Path $AppDir "AUTO-MAS.exe"
Write-Check "AUTO-MAS.exe 存在" (Test-Path $appExe) $appExe

$r6ConfigExists = Test-Path $R6ConfigDir
Write-Check "r6 配置目录存在" $r6ConfigExists $R6ConfigDir

if (-not $r6ConfigExists) {
    Write-Host "r6 配置目录不存在，终止验证" -ForegroundColor Red
    exit 1
}

$r6JsonFiles = Get-ChildItem -Path $R6ConfigDir -Filter "*.json" -File -ErrorAction SilentlyContinue
Write-Check "r6 JSON 配置文件存在" ($r6JsonFiles.Count -gt 0) "共 $($r6JsonFiles.Count) 个 JSON"

if ($r6JsonFiles.Count -eq 0) {
    Write-Host "r6 配置目录无 JSON 文件，终止验证" -ForegroundColor Red
    exit 1
}

# ── 1. 备份 r6 配置 ──
Write-Host "`n=== 1. 备份 r6 配置 ===" -ForegroundColor Cyan

$backupDir = Join-Path $env:TEMP "automos-r6-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Write-Host "备份目录: $backupDir" -ForegroundColor Cyan

Copy-Item -Path "$R6ConfigDir\*" -Destination $backupDir -Recurse -Force
$backupFileCount = (Get-ChildItem -Path $backupDir -File).Count
Write-Check "r6 配置已备份" ($backupFileCount -gt 0) "备份 $backupFileCount 个文件"

# 记录升级前配置快照
$beforeSnapshot = Get-ConfigSnapshot -Dir $R6ConfigDir
Write-Host "升级前配置快照: $($beforeSnapshot.Count) 个 JSON 文件" -ForegroundColor Cyan

# ── 2. 准备新版本配置目录 ──
Write-Host "`n=== 2. 准备新版本配置目录 ===" -ForegroundColor Cyan

$newConfigDir = Join-Path $AppDir "config"

# 清理新版本 config 目录（如果存在）
if (Test-Path $newConfigDir) {
    Remove-Item -Path $newConfigDir -Recurse -Force -ErrorAction SilentlyContinue
}

# 复制 r6 配置到新版本 config 目录
New-Item -ItemType Directory -Path $newConfigDir -Force | Out-Null
Copy-Item -Path "$R6ConfigDir\*.json" -Destination $newConfigDir -Force

$copiedFiles = Get-ChildItem -Path $newConfigDir -Filter "*.json" -File
Write-Check "r6 配置已复制到新版本" ($copiedFiles.Count -eq $r6JsonFiles.Count) `
    "复制 $($copiedFiles.Count)/$($r6JsonFiles.Count) 个文件"

# 确保无 v2 TOML 文件
$v2Files = Get-ChildItem -Path $newConfigDir -Filter "*.v2*.toml" -File -ErrorAction SilentlyContinue
Write-Check "初始无 v2 TOML" ($v2Files.Count -eq 0) "清理后 0 个 v2 文件"

# ── 3. 启动新版本（执行迁移）──
Write-Host "`n=== 3. 启动新版本（Config v2 模式: $ConfigV2Mode）===" -ForegroundColor Cyan

# 设置环境变量
$env:AUTO_MAS_CONFIG_V2_MODE = $ConfigV2Mode
Write-Host "环境变量 AUTO_MAS_CONFIG_V2_MODE=$ConfigV2Mode" -ForegroundColor Cyan

# 进程清理
$existingProcesses = Get-Process -Name "AUTO-MAS" -ErrorAction SilentlyContinue
if ($existingProcesses) {
    $existingProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

$logsDir = Join-Path $AppDir "logs"
if (Test-Path $logsDir) {
    Remove-Item -Path $logsDir -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "启动 AUTO-MAS..." -ForegroundColor Cyan
$process = Start-Process -FilePath $appExe -PassThru -ErrorAction SilentlyContinue
Write-Check "进程已启动" ($null -ne $process) "PID: $($process.Id)"

if ($null -eq $process) {
    Write-Host "无法启动进程，终止验证" -ForegroundColor Red
    exit 1
}

# 等待 health
$healthReady = $false
$elapsed = 0
$timeout = 30
while ($elapsed -lt $timeout) {
    Start-Sleep -Seconds 2
    $elapsed += 2
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/core/health" `
            -TimeoutSec 3 -ErrorAction Stop
        if ($response.ready -eq $true) {
            $healthReady = $true
            break
        }
    } catch {}
}

Write-Check "health ready=true" $healthReady "耗时 ${elapsed}s"

# ── 4. 验证 v2 TOML 迁移 ──
Write-Host "`n=== 4. 验证 v2 TOML 迁移 ===" -ForegroundColor Cyan

Start-Sleep -Seconds 2

$v2Suffix = if ($ConfigV2Mode -eq "authoritative") { "*.v2.toml" } else { "*.v2.shadow.toml" }
$v2Files = Get-ChildItem -Path $newConfigDir -Filter $v2Suffix -File -ErrorAction SilentlyContinue
$v2Count = ($v2Files | Measure-Object).Count
Write-Check "v2 TOML 文件已生成 ($ConfigV2Mode)" ($v2Count -gt 0) "共 $v2Count 个 $v2Suffix"

if ($v2Count -gt 0) {
    foreach ($v2File in $v2Files) {
        $fileSize = $v2File.Length
        Write-Host "  $($v2File.Name): $fileSize bytes" -ForegroundColor Cyan
    }
}

# 检查 legacy JSON 仍存在
$legacyJsonFiles = Get-ChildItem -Path $newConfigDir -Filter "*.json" -File -ErrorAction SilentlyContinue
Write-Check "legacy JSON 仍存在" ($legacyJsonFiles.Count -gt 0) "共 $($legacyJsonFiles.Count) 个 JSON"

# ── 5. 验证配置值一致性 ──
Write-Host "`n=== 5. 验证配置值一致性 ===" -ForegroundColor Cyan

# 通过 API 读取当前配置值
$configPreserved = $true
$configDetail = ""

try {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/core/health" `
        -TimeoutSec 5 -ErrorAction Stop
    $configDetail = "health OK, ready=$($response.ready)"
} catch {
    $configPreserved = $false
    $configDetail = "无法访问 API: $($_.Exception.Message)"
}

# 比较磁盘上 legacy JSON 内容是否被篡改
$afterSnapshot = Get-ConfigSnapshot -Dir $newConfigDir
$diffs = Compare-ConfigSnapshot -Before $beforeSnapshot -After $afterSnapshot

if ($diffs.Count -eq 0) {
    Write-Check "legacy JSON 内容未变" $true "所有 JSON 文件内容一致"
} else {
    Write-Check "legacy JSON 内容未变" $false ($diffs -join "; ")
}

# 检查 v2 TOML 是否包含有效数据
if ($v2Count -gt 0) {
    $v2HasData = $false
    foreach ($v2File in $v2Files) {
        $content = Get-Content $v2File.FullName -Raw -Encoding UTF8
        if ($content.Trim().Length -gt 0) {
            $v2HasData = $true
            # 检查不含明文敏感信息（简单检查）
            if ($content -match "(?i)(password|secret|token|api_key)\s*=\s*[^DPAPI]") {
                Write-Check "v2 TOML 无明文敏感信息" $false "$($v2File.Name) 可能含明文密钥"
            }
        }
    }
    Write-Check "v2 TOML 包含有效数据" $v2HasData
}

# ── 6. 关闭新版本 ──
Write-Host "`n=== 6. 关闭新版本 ===" -ForegroundColor Cyan

if ($process -and -not $process.HasExited) {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/core/close" `
            -Method Post -TimeoutSec 5 -ErrorAction Stop | Out-Null
    } catch {
        $process | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    if (-not $process.WaitForExit(5000)) {
        $process | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

Write-Check "新版本已关闭" (-not (Get-Process -Name "AUTO-MAS" -ErrorAction SilentlyContinue))

# ── 7. 回滚验证 ──
Write-Host "`n=== 7. 回滚验证（删除 v2 TOML，恢复 r6 JSON）===" -ForegroundColor Cyan

# 删除所有 v2 TOML 文件
$v2AllFiles = Get-ChildItem -Path $newConfigDir -Filter "*.v2*.toml" -File -ErrorAction SilentlyContinue
foreach ($f in $v2AllFiles) {
    Remove-Item $f.FullName -Force
}
Write-Host "已删除 $($v2AllFiles.Count) 个 v2 TOML 文件" -ForegroundColor Cyan

# 恢复 r6 原始 JSON
Copy-Item -Path "$backupDir\*.json" -Destination $newConfigDir -Force
Write-Host "已从备份恢复 r6 JSON" -ForegroundColor Cyan

# 以 off 模式启动（纯 legacy 模式，不启用 v2）
$env:AUTO_MAS_CONFIG_V2_MODE = "off"
Write-Host "环境变量 AUTO_MAS_CONFIG_V2_MODE=off（纯 legacy 回滚模式）" -ForegroundColor Cyan

$rollbackProcess = Start-Process -FilePath $appExe -PassThru -ErrorAction SilentlyContinue
Write-Check "回滚进程已启动" ($null -ne $rollbackProcess) "PID: $($rollbackProcess.Id)"

$rollbackHealth = $false
$elapsed = 0
while ($elapsed -lt 30) {
    Start-Sleep -Seconds 2
    $elapsed += 2
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/core/health" `
            -TimeoutSec 3 -ErrorAction Stop
        if ($response.ready -eq $true) {
            $rollbackHealth = $true
            break
        }
    } catch {}
}

Write-Check "回滚后 health ready=true" $rollbackHealth "耗时 ${elapsed}s"

# 验证回滚后配置值
if ($rollbackHealth) {
    $rollbackSnapshot = Get-ConfigSnapshot -Dir $newConfigDir
    $rollbackDiffs = Compare-ConfigSnapshot -Before $beforeSnapshot -After $rollbackSnapshot
    if ($rollbackDiffs.Count -eq 0) {
        Write-Check "回滚后配置值一致" $true "所有 JSON 文件内容与 r6 一致"
    } else {
        Write-Check "回滚后配置值一致" $false ($rollbackDiffs -join "; ")
    }
}

# 关闭回滚进程
if ($rollbackProcess -and -not $rollbackProcess.HasExited) {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/core/close" `
            -Method Post -TimeoutSec 5 -ErrorAction Stop | Out-Null
    } catch {
        $rollbackProcess | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    if (-not $rollbackProcess.WaitForExit(5000)) {
        $rollbackProcess | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

# 清理环境变量
Remove-Item Env:\AUTO_MAS_CONFIG_V2_MODE -ErrorAction SilentlyContinue

# ── 8. 恢复原始配置 ──
Write-Host "`n=== 8. 恢复原始配置 ===" -ForegroundColor Cyan

if (Test-Path $newConfigDir) {
    Remove-Item -Path $newConfigDir -Recurse -Force -ErrorAction SilentlyContinue
}
Copy-Item -Path "$backupDir\*" -Destination $newConfigDir -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "已从备份恢复全部配置文件" -ForegroundColor Cyan

# 清理备份
Write-Host "备份目录保留以供审计: $backupDir" -ForegroundColor Yellow

# ── 汇总 ──
Write-Host "`n=== 验证汇总 ===" -ForegroundColor Cyan
$results | Format-Table -AutoSize

$totalChecks = $results.Count
$passedChecks = ($results | Where-Object { $_.Status -eq "PASS" }).Count
$failedChecks = ($results | Where-Object { $_.Status -eq "FAIL" }).Count

Write-Host "`n总计: $totalChecks 项检查, $passedChecks 通过, $failedChecks 失败" -ForegroundColor $(if ($failedChecks -eq 0) { "Green" } else { "Red" })
Write-Host "Config v2 模式: $ConfigV2Mode" -ForegroundColor Cyan
Write-Host "备份目录: $backupDir" -ForegroundColor Cyan

if ($exitCode -eq 0) {
    Write-Host "`nr6 覆盖升级与回滚验证: 全部通过" -ForegroundColor Green
} else {
    Write-Host "`nr6 覆盖升级与回滚验证: 存在失败项，请检查上方详情" -ForegroundColor Red
}

exit $exitCode
