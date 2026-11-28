param(
    [string]$Executable,
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$source = (Get-Item -LiteralPath (Join-Path $PSScriptRoot '..')).FullName
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$interactive = !$Executable
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)

try {
    if (!$WhatIf -and !$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        $arguments = "-NoProfile -STA -ExecutionPolicy Bypass -File `"$PSCommandPath`""
        if ($Executable) { $arguments += " -Executable `"$([IO.Path]::GetFullPath($Executable))`"" }
        Start-Process -FilePath $powershell -Verb RunAs -ArgumentList $arguments
        return
    }

    if (!$Executable) {
        Add-Type -AssemblyName System.Windows.Forms
        $picker = New-Object Windows.Forms.OpenFileDialog
        try {
            $picker.Title = '选择用来运行当前源码后端的 AUTO-MAS.exe'
            $picker.Filter = 'AUTO-MAS 发行程序 (AUTO-MAS.exe)|AUTO-MAS.exe'
            $picker.CheckFileExists = $true
            if ($picker.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { return }
            $Executable = $picker.FileName
        } finally {
            $picker.Dispose()
        }
    }

    $file = Get-Item -LiteralPath $Executable
    if ($file.PSIsContainer -or $file.Name -ne 'AUTO-MAS.exe') {
        throw '请选择发行版目录里的 AUTO-MAS.exe。'
    }
    $base = $file.Directory.FullName
    $managedRepo = [IO.Path]::Combine($base, 'repo')
    if ($source -eq $base -or $source -eq $managedRepo -or
        $source.StartsWith($managedRepo + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw '请在独立的源码目录运行这个入口。'
    }
    foreach ($name in @('main.py', 'pyproject.toml', 'uv.lock')) {
        if (!(Test-Path -LiteralPath (Join-Path $source $name) -PathType Leaf)) {
            throw "当前源码目录缺少 $name。"
        }
    }
    foreach ($name in @('resources\auto-mas-runtime.exe', 'runtime\environment\venv\pyvenv.cfg',
            'runtime\environment\venv\Scripts\python.exe')) {
        if (!(Test-Path -LiteralPath (Join-Path $base $name) -PathType Leaf)) {
            throw '请先正常启动所选发行版完成初始化，再从托盘退出。'
        }
    }

    $state = Join-Path $base 'runtime-state\backend.json'
    if (Test-Path -LiteralPath $state -PathType Leaf) {
        try { $owner = Get-Content -LiteralPath $state -Raw -Encoding UTF8 | ConvertFrom-Json }
        catch { $owner = $null }
        $runtimePid = 0
        if ($owner.command -eq 'backend supervise' -and [int]::TryParse($owner.pid, [ref]$runtimePid) -and $runtimePid -gt 0) {
            $running = Get-Process -Id $runtimePid -ErrorAction SilentlyContinue
            if ($running.ProcessName -like 'auto-mas-runtime*') {
                throw '这份发行版的后端正在运行。请从系统托盘退出当前 AUTO-MAS 后重试。'
            }
        }
    }

    if ($WhatIf) {
        Write-Output "源码目录 $source"
        Write-Output "发行版 $($file.FullName)"
        return
    }
    # 只修改子进程环境：使用与本次预检一致的 Runtime 根，不继承旧的路径覆盖。
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $file.FullName
    $start.WorkingDirectory = $base
    $start.UseShellExecute = $false
    $start.EnvironmentVariables['AUTO_MAS_BACKEND_REPO'] = $source
    $start.EnvironmentVariables['AUTO_MAS_BACKEND_RUNTIME_ROOT'] = $base
    $child = [Diagnostics.Process]::Start($start)
    $child.Dispose()
} catch {
    if (!$WhatIf -and $interactive) {
        Add-Type -AssemblyName System.Windows.Forms
        [void][Windows.Forms.MessageBox]::Show($_.Exception.Message, '源码后端启动失败')
    }
    Write-Error $_.Exception.Message -ErrorAction Continue
    exit 1
}
