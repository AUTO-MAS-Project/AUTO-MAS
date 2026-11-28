#Requires -Version 7.0

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('Check', 'Start', 'Test')]
    [string]$Mode = 'Check',

    [ValidateSet('Runtime', 'Test')]
    [string]$Target = 'Runtime',

    [string]$AppRoot,

    [switch]$PythonPathOnly,

    [string[]]$PytestArgs = @('tests', '-q')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$rootKey = 'automas.backendAppRoot'

function Get-VenvPython([string]$Venv) {
    if (!(Test-Path -LiteralPath (Join-Path $Venv 'pyvenv.cfg') -PathType Leaf)) {
        throw "找不到已准备的虚拟环境：$Venv"
    }
    $relative = if ($IsWindows) { 'Scripts/python.exe' } else { 'bin/python' }
    $python = Join-Path $Venv $relative
    if (!(Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "找不到虚拟环境的 Python：$python"
    }
    return $python
}

function Assert-OutsideWorktrees([string]$Directory) {
    $comparison = if ($IsWindows) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
    $separator = [IO.Path]::DirectorySeparatorChar
    $candidate = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($Directory))
    $records = git -C $repo worktree list --porcelain -z
    if ($LASTEXITCODE -ne 0) { throw '无法读取当前 Git 工作树列表。' }
    foreach ($field in (($records -join "`n") -split "`0")) {
        if (!$field.StartsWith('worktree ', [StringComparison]::Ordinal)) { continue }
        $tree = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($field.Substring(9)))
        if ($tree.Equals($candidate, $comparison) -or
            $tree.StartsWith($candidate.TrimEnd($separator) + $separator, $comparison) -or
            $candidate.StartsWith($tree.TrimEnd($separator) + $separator, $comparison)) {
            throw "测试包或共享环境不能与工作树重叠：$tree"
        }
    }
}

function Invoke-Child([string]$File, [string[]]$Arguments, [hashtable]$Environment = @{}) {
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $File
    $start.WorkingDirectory = $repo
    $start.UseShellExecute = $false
    foreach ($arg in $Arguments) { $start.ArgumentList.Add($arg) }
    foreach ($name in @(
            'AUTO_MAS_BACKEND_REPO', 'AUTO_MAS_BACKEND_RUNTIME_ROOT', 'AUTO_MAS_DEVELOPER_HOME',
            'AUTO_MAS_DEVELOPER_AUTOMATION', 'AUTO_MAS_RUNTIME_MODE', 'AUTO_MAS_RUNTIME_EXE',
            'AUTO_MAS_HTTP_PORT', 'AUTO_MAS_ENV', 'UV_PROJECT_ENVIRONMENT', 'VIRTUAL_ENV',
            'PYTHONHOME', 'PYTHONPATH', 'PYTHONUSERBASE',
            'PYTEST_ADDOPTS', 'PYTEST_PLUGINS'
        )) {
        $null = $start.Environment.Remove($name)
    }
    foreach ($entry in $Environment.GetEnumerator()) {
        $start.Environment[$entry.Key] = $entry.Value
    }
    $child = [Diagnostics.Process]::Start($start)
    try {
        $child.WaitForExit()
        return $child.ExitCode
    } finally {
        $child.Dispose()
    }
}

if (($Mode -ne 'Check' -and $Target -ne 'Runtime') -or ($AppRoot -and ($Mode -eq 'Test' -or $Target -eq 'Test'))) {
    throw '仅 Check 可以指定 -Target；-AppRoot 仅适用于 Runtime。'
}
if ($PythonPathOnly) {
    if ($Mode -ne 'Check') { throw '仅 Check 支持 -PythonPathOnly。' }
    # stdout 是供 dev_doctor 读取的路径，不能随 Windows 控制台代码页变化。
    [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
}
$test = ($Mode -eq 'Test' -or $Target -eq 'Test')

$version = (Get-Content -LiteralPath (Join-Path $repo '.python-version') -Raw).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw "不支持的 .python-version：$version" }
$platform = if ($IsWindows) { 'win32' } elseif ($IsMacOS) { 'darwin' } else { 'linux' }
$architecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
$uv = Get-Command uv -CommandType Application -ErrorAction Stop | Select-Object -First 1
if ($test) {
    if ($IsWindows -and [string]::IsNullOrWhiteSpace($env:AUTO_MAS_DEV_ENV_ROOT)) {
        $registered = @(
            [Environment]::GetEnvironmentVariable('AUTO_MAS_DEV_ENV_ROOT', 'User')
            [Environment]::GetEnvironmentVariable('AUTO_MAS_DEV_ENV_ROOT', 'Machine')
        ) | Where-Object { ![string]::IsNullOrWhiteSpace($_) }
        if ($registered) {
            throw 'Windows 已登记 AUTO_MAS_DEV_ENV_ROOT，但当前终端未继承；请核对用户与系统设置，再在新终端或本次进程中选定共享池。'
        }
    }
    if (!$env:AUTO_MAS_DEV_ENV_ROOT -or ![IO.Path]::IsPathFullyQualified($env:AUTO_MAS_DEV_ENV_ROOT)) {
        throw '请将 AUTO_MAS_DEV_ENV_ROOT 设置为所有源码和安装包之外的绝对目录。'
    }
    Assert-OutsideWorktrees $env:AUTO_MAS_DEV_ENV_ROOT
    $hash = (Get-FileHash -LiteralPath (Join-Path $repo 'uv.lock') -Algorithm SHA256).Hash.ToLowerInvariant()
    $venv = Join-Path $env:AUTO_MAS_DEV_ENV_ROOT "$platform-$architecture-$version-$hash"
    if (!$PythonPathOnly) { Write-Host "共享测试环境：$venv" }
} else {
    if (!$IsWindows) { throw '安装包检查和启动仅支持 Windows。' }
    if (!$AppRoot) {
        $AppRoot = git -C $repo config --local --get $rootKey
        if ($LASTEXITCODE -ne 0 -or !$AppRoot) { throw "请登记专用测试包：git config --local $rootKey '<绝对路径>'" }
    }
    if (![IO.Path]::IsPathFullyQualified($AppRoot)) { throw "测试包路径必须为绝对路径：$AppRoot" }
    $AppRoot = (Resolve-Path -LiteralPath $AppRoot).Path
    Assert-OutsideWorktrees $AppRoot
    foreach ($relative in @('.automas-dev-install', 'AUTO-MAS.exe', 'resources/auto-mas-runtime.exe')) {
        if (!(Test-Path -LiteralPath (Join-Path $AppRoot $relative) -PathType Leaf)) {
            throw "测试包缺少 $relative；请先准备专用测试包，不要使用日常安装。"
        }
    }
    # 能力标记由 Electron 打包产出，兼容的 Python/Runtime 不能证明旧桌面程序会隔离数据。
    $profileCapability = Join-Path $AppRoot 'resources/worktree-profile-isolation.json'
    $profileError = '该测试包不支持 worktree 桌面数据隔离；请换用包含新版 Electron 的测试包，不要手工添加能力标记。'
    if (!(Test-Path -LiteralPath $profileCapability -PathType Leaf)) { throw $profileError }
    try {
        $capabilities = Get-Content -LiteralPath $profileCapability -Raw | ConvertFrom-Json -AsHashtable
    } catch {
        throw $profileError
    }
    if ($capabilities -isnot [System.Collections.IDictionary] -or $capabilities['worktreeProfileIsolation'] -cne 1) {
        throw $profileError
    }
    $venv = Join-Path $AppRoot 'runtime/environment/venv'
}

$python = Get-VenvPython $venv
$verifier = Join-Path $PSScriptRoot 'verify-dev-backend.py'
$arguments = @('-I', '-B', '-X', 'utf8', $verifier, '--repo', $repo, '--venv', $venv,
    '--uv', $uv.Source, '--platform', $platform, '--architecture', $architecture, '--version', $version)
if ($test) {
    $arguments += @('--test', '--pool-root', $env:AUTO_MAS_DEV_ENV_ROOT)
} else {
    $arguments += @('--app-root', $AppRoot)
}
if ($PythonPathOnly) { $arguments += '--quiet' }
if ((Invoke-Child $python $arguments) -ne 0) { exit 1 }
if ($Mode -eq 'Check') {
    if ($PythonPathOnly) { Write-Output $python }
    exit 0
}

if ($Mode -eq 'Test') {
    exit (Invoke-Child $python (@('-E', '-s', '-B', '-m', 'pytest') + $PytestArgs) @{
        AUTO_MAS_ENV = 'development'
    })
}

$account = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($account)
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '请从管理员 PowerShell 明确启动；不会自动触发 UAC 后用日常模式启动。'
}
$runtime = Join-Path $AppRoot 'resources/auto-mas-runtime.exe'
$superviseHelp = & $runtime backend supervise --help
if ($LASTEXITCODE -ne 0 -or ($superviseHelp -join "\n") -notmatch '--reuse-managed-environment') {
    throw '此测试包的 Runtime 不支持复用发行虚拟环境，请换用包含 #2054 的完整测试包。'
}
# 所有 Start 实例共用开发端口；锁覆盖 GUI 生命周期，不因 worktree 用户目录不同而失效。
$mutex = [Threading.Mutex]::new($false, 'Global\AUTO-MAS.DeveloperBackend.36164')
$owned = $false
try {
    try {
        $owned = $mutex.WaitOne(0)
    } catch [Threading.AbandonedMutexException] {
        $owned = $true
    }
    if (!$owned) { throw '已有通过此入口启动的开发实例，请先关闭再切换 worktree。' }
    $exitCode = Invoke-Child (Join-Path $AppRoot 'AUTO-MAS.exe') @() @{
        AUTO_MAS_BACKEND_REPO = $repo
        AUTO_MAS_BACKEND_RUNTIME_ROOT = $AppRoot
        AUTO_MAS_DEVELOPER_HOME = (Join-Path $repo '.automas-dev-electron')
        AUTO_MAS_ENV = 'development'
        AUTO_MAS_HTTP_PORT = '36164'
    }
} finally {
    if ($owned) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
exit $exitCode
