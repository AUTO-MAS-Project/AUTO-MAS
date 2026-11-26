#Requires -Version 7.0

<#
.SYNOPSIS
把 MFW 插件族的六个插件包和三块库按本地源码接进这棵宿主树。

.DESCRIPTION
宿主已不内置 MaaFW / M9A / MSS，这三类托管由插件 maafw_adapter / m9a_adapter / mss_adapter
接手。只用发行版的，宿主会从 PyPI 装（见 docs\mfw-plugins-local-integration.md 开头）；
要改插件包源码时，用本脚本按「本地源码布局 + 库 wheel 目录」接入：

1. 在本树 plugins\ 下给六个插件包各建一个目录联接（junction），宿主把 plugins\ 下
   每个带 pyproject.toml 和 src\ 的子目录当本地插件发现：
     plugins\maafw_agent_env      → auto-mas-maafw-agent-env 包目录
     plugins\maafw_runner         → auto-mas-maafw-runner 包目录
     plugins\maafw_project_update → auto-mas-maafw-project-update 包目录
     plugins\maafw_adapter        → AUTO-MAS-MaaFW-Adapter 仓库根
     plugins\m9a_adapter          → AUTO-MAS-M9A-Adapter 仓库根
     plugins\mss_adapter          → AUTO-MAS-MSS-Adapter 仓库根
2. 写一份 uv.toml（默认放在 wheel 目录里），[pip] find-links 指向库的 wheel 目录。
   起后端时用环境变量 UV_CONFIG_FILE 指向它：宿主解析插件依赖时命令行自带 --find-links，
   UV_FIND_LINKS 会被盖掉，只有 UV_CONFIG_FILE 里的 find-links 会和命令行的合并。
   三块库（auto-mas-maafw-interface、auto-mas-maafw-native、auto-mas-maafw-adapter-kit）
   由此从 wheel 装进 plugins\pypi\site-packages。库的版本号和 PyPI 上已发的相同时，
   uv 可能拿 PyPI 那份，装好后要按说明第 4 节核对一次。

脚本可以重复执行：联接已指向同一目录就跳过，指向别处就只换联接（不碰目标目录），
plugins\ 下同名的是普通目录或文件时报错退出、不做任何改动。uv.toml 内容没变就不重写。

.PARAMETER AgentEnv
maafw_agent_env 的包目录（含 pyproject.toml 和 src\maafw_agent_env），
例如 <积木仓库>\packages\auto-mas-maafw-agent-env。

.PARAMETER Runner
maafw_runner 的包目录，例如 <积木仓库>\packages\auto-mas-maafw-runner。

.PARAMETER ProjectUpdate
maafw_project_update 的包目录，例如 <积木仓库>\packages\auto-mas-maafw-project-update。

.PARAMETER MaaFWAdapter
maafw_adapter 的仓库根（含 pyproject.toml 和 src\maafw_adapter）。

.PARAMETER M9AAdapter
m9a_adapter 的仓库根。

.PARAMETER MssAdapter
mss_adapter 的仓库根。

.PARAMETER WheelDir
库 wheel 所在目录，里面要有 auto_mas_maafw_interface-*.whl、
auto_mas_maafw_native-*.whl 和 auto_mas_maafw_adapter_kit-*.whl。打法：
  & D:\MAS\code\main\environment\python\Scripts\uv.exe build --wheel <库的包目录> --out-dir <WheelDir>

.PARAMETER UvConfig
生成的 uv.toml 路径，默认 <WheelDir>\uv.toml（放在树外，不进版本库）。

.PARAMETER RefreshLibraries
库重新打过 wheel（版本号没变）时加上：删掉 plugins\pypi\environment.json，
并清掉 uv 缓存里的三块库，下次起后端会重新解析、重装。插件源码改了不用加。

.PARAMETER Unlink
只拆掉本脚本建的六个联接（只删联接本身，不碰目标目录），不写 uv.toml。

.EXAMPLE
pwsh -NoProfile -File scripts\dev\link_mfw_plugins.ps1 `
  -AgentEnv <积木仓库>\packages\auto-mas-maafw-agent-env `
  -Runner <积木仓库>\packages\auto-mas-maafw-runner `
  -ProjectUpdate <积木仓库>\packages\auto-mas-maafw-project-update `
  -MaaFWAdapter <AUTO-MAS-MaaFW-Adapter 仓库根> `
  -M9AAdapter <AUTO-MAS-M9A-Adapter 仓库根> `
  -MssAdapter <AUTO-MAS-MSS-Adapter 仓库根> `
  -WheelDir <库 wheel 目录>

接好以后从树根起后端（脚本最后会把这几行按实际路径打印出来）：
  $env:AUTO_MAS_ENV = 'dev'
  $env:AUTO_MAS_UV_EXE = '<uv.exe>'
  $env:UV_CONFIG_FILE = '<库 wheel 目录>\uv.toml'
  & .\.venv\Scripts\python.exe main.py
首次启动宿主会联合解析插件依赖（看 debug\app.log 里「插件依赖」相关的行）。然后在插件中心
启用三个专项（会按 requires 先启用上游积木），再建托管、导入项目、跑一轮。
配置里已有 MaaFW / M9A / MSS 托管时，启动期会自动启用对应专项。

注意：
- 没装插件时宿主照常能起来；配置里已有这三类托管的原样旁挂保留、不能运行，
  启动通知里会提示。插件接好后重启即可接手。
- 积木（agent_env / runner / project_update）改了要重启后端；专项可以在插件中心重载。
- 不要把这些联接提交进版本库（plugins\* 已被 .gitignore 忽略）。
#>

[CmdletBinding(DefaultParameterSetName = "Link")]
param(
    [Parameter(Mandatory, ParameterSetName = "Link")][string]$AgentEnv,
    [Parameter(Mandatory, ParameterSetName = "Link")][string]$Runner,
    [Parameter(Mandatory, ParameterSetName = "Link")][string]$ProjectUpdate,
    [Parameter(Mandatory, ParameterSetName = "Link")][string]$MaaFWAdapter,
    [Parameter(Mandatory, ParameterSetName = "Link")][string]$M9AAdapter,
    [Parameter(Mandatory, ParameterSetName = "Link")][string]$MssAdapter,
    [Parameter(Mandatory, ParameterSetName = "Link")][string]$WheelDir,
    [Parameter(ParameterSetName = "Link")][string]$UvConfig,
    [Parameter(ParameterSetName = "Link")][switch]$RefreshLibraries,
    [Parameter(Mandatory, ParameterSetName = "Unlink")][switch]$Unlink
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$treeRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pluginsRoot = Join-Path $treeRoot "plugins"
$uvExe = if ($env:AUTO_MAS_UV_EXE) { $env:AUTO_MAS_UV_EXE } else { [string](Get-Command uv -ErrorAction SilentlyContinue)?.Source }
$linkNames = @(
    "maafw_agent_env",
    "maafw_runner",
    "maafw_project_update",
    "maafw_adapter",
    "m9a_adapter",
    "mss_adapter"
)
$libraryPackages = @("auto-mas-maafw-interface", "auto-mas-maafw-native", "auto-mas-maafw-adapter-kit")

function Get-LinkTarget {
    param([string]$Path)
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.LinkType -ne "Junction" -and $item.LinkType -ne "SymbolicLink") {
        return $null
    }
    return [string]($item.Target | Select-Object -First 1)
}

function Remove-Link {
    param([string]$Path)
    # DirectoryInfo.Delete() 不递归：对联接只删联接本身，目标目录原样保留。
    (Get-Item -LiteralPath $Path -Force).Delete()
}

function Test-PluginPackage {
    param([string]$Name, [string]$Directory)
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) {
        throw "$Name 的目录不存在：$Directory"
    }
    $resolved = (Resolve-Path -LiteralPath $Directory).Path
    if (-not (Test-Path -LiteralPath (Join-Path $resolved "pyproject.toml") -PathType Leaf)) {
        throw "$Name 的目录里没有 pyproject.toml：$resolved"
    }
    $package = Join-Path $resolved "src\$Name\__init__.py"
    if (-not (Test-Path -LiteralPath $package -PathType Leaf)) {
        throw "$Name 的目录里没有 src\$Name\__init__.py：$resolved"
    }
    $tops = @(Get-ChildItem -LiteralPath (Join-Path $resolved "src") -Force |
        Where-Object { ($_.PSIsContainer -and (Test-Path (Join-Path $_.FullName "__init__.py"))) -or $_.Extension -eq ".py" })
    if ($tops.Count -ne 1) {
        throw "$Name 的 src\ 下顶层模块不唯一（宿主会拒绝加载）：$($tops.Name -join ', ')"
    }
    return $resolved
}

if ($Unlink) {
    foreach ($name in $linkNames) {
        $link = Join-Path $pluginsRoot $name
        if (-not (Test-Path -LiteralPath $link)) {
            continue
        }
        if ($null -eq (Get-LinkTarget $link)) {
            Write-Warning "plugins\$name 不是联接，跳过（不删普通目录）"
            continue
        }
        Remove-Link $link
        Write-Host "已拆除 plugins\$name"
    }
    return
}

$targets = [ordered]@{
    "maafw_agent_env"      = $AgentEnv
    "maafw_runner"         = $Runner
    "maafw_project_update" = $ProjectUpdate
    "maafw_adapter"        = $MaaFWAdapter
    "m9a_adapter"          = $M9AAdapter
    "mss_adapter"          = $MssAdapter
}

# 先全部校验，任何一项不对都不动盘。
$resolvedTargets = [ordered]@{}
foreach ($name in $targets.Keys) {
    $resolvedTargets[$name] = Test-PluginPackage -Name $name -Directory $targets[$name]
}
if (-not (Test-Path -LiteralPath $WheelDir -PathType Container)) {
    throw "wheel 目录不存在：$WheelDir"
}
$wheelRoot = (Resolve-Path -LiteralPath $WheelDir).Path
foreach ($stem in @("auto_mas_maafw_interface", "auto_mas_maafw_native", "auto_mas_maafw_adapter_kit")) {
    $wheels = @(Get-ChildItem -LiteralPath $wheelRoot -Filter "$stem-*.whl" -File)
    if ($wheels.Count -eq 0) {
        throw "wheel 目录里没有 $stem-*.whl：$wheelRoot"
    }
    if ($wheels.Count -gt 1) {
        Write-Warning "wheel 目录里有多个 $stem 的 wheel，uv 会按版本挑最高的：$($wheels.Name -join ', ')"
    }
}
foreach ($name in $resolvedTargets.Keys) {
    $link = Join-Path $pluginsRoot $name
    if ((Test-Path -LiteralPath $link) -and $null -eq (Get-LinkTarget $link)) {
        throw "plugins\$name 已存在且不是联接，不覆盖。请先自己确认并挪走它：$link"
    }
}

New-Item -ItemType Directory -Force -Path $pluginsRoot | Out-Null
foreach ($name in $resolvedTargets.Keys) {
    $link = Join-Path $pluginsRoot $name
    $target = $resolvedTargets[$name]
    if (Test-Path -LiteralPath $link) {
        $current = Get-LinkTarget $link
        if ($current -and [string]::Equals(
                [IO.Path]::GetFullPath($current).TrimEnd("\"),
                $target.TrimEnd("\"),
                [StringComparison]::OrdinalIgnoreCase)) {
            Write-Host "plugins\$name 已指向 $target"
            continue
        }
        Remove-Link $link
        Write-Host "plugins\$name 原先指向 $current，改接"
    }
    New-Item -ItemType Junction -Path $link -Target $target | Out-Null
    Write-Host "plugins\$name -> $target"
}

if (-not $UvConfig) {
    $UvConfig = Join-Path $wheelRoot "uv.toml"
}
$UvConfig = [IO.Path]::GetFullPath($UvConfig)
$marker = "# 由 AUTO-MAS scripts\dev\link_mfw_plugins.ps1 生成，重复执行会覆盖。"
$findLinks = $wheelRoot.Replace("\", "/")
$content = @(
    $marker,
    "[pip]",
    "find-links = [`"$findLinks`"]",
    ""
) -join "`n"
if (Test-Path -LiteralPath $UvConfig -PathType Leaf) {
    $existing = [IO.File]::ReadAllText($UvConfig)
    if (-not $existing.StartsWith($marker)) {
        throw "$UvConfig 已存在且不是本脚本生成的，不覆盖。换一个 -UvConfig 路径，或自己确认后删掉它。"
    }
}
if (-not (Test-Path -LiteralPath $UvConfig -PathType Leaf) -or [IO.File]::ReadAllText($UvConfig) -ne $content) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $UvConfig) | Out-Null
    [IO.File]::WriteAllText($UvConfig, $content, [Text.UTF8Encoding]::new($false))
    Write-Host "已写 $UvConfig"
} else {
    Write-Host "$UvConfig 无变化"
}

if ($RefreshLibraries) {
    $environmentMarker = Join-Path $pluginsRoot "pypi\environment.json"
    if (Test-Path -LiteralPath $environmentMarker -PathType Leaf) {
        Remove-Item -LiteralPath $environmentMarker
        Write-Host "已删 plugins\pypi\environment.json，下次启动重新准备插件依赖"
    }
    if ($uvExe -and (Test-Path -LiteralPath $uvExe -PathType Leaf)) {
        & $uvExe cache clean @libraryPackages
        if ($LASTEXITCODE -ne 0) {
            throw "uv cache clean 失败（退出码 $LASTEXITCODE）"
        }
    } else {
        Write-Warning "找不到 uv（$uvExe），没清 uv 缓存；可设 AUTO_MAS_UV_EXE 后重跑"
    }
}

Write-Host ""
Write-Host "接好了。从树根起后端："
Write-Host "  Set-Location '$treeRoot'"
Write-Host "  `$env:AUTO_MAS_ENV = 'dev'"
Write-Host "  `$env:AUTO_MAS_UV_EXE = '$uvExe'"
Write-Host "  `$env:UV_CONFIG_FILE = '$UvConfig'"
Write-Host "  & .\.venv\Scripts\python.exe main.py"
