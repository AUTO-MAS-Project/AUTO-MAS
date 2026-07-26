<#
.SYNOPSIS
    验证 AUTO-MAS portable 包内的插件版本与 wheel 契约。
.DESCRIPTION
    对已解压 portable 根目录执行离线只读预检，核对：
    1. integration snapshot 的 plugin-bootstrap 声明与 runtime lock；
    2. runtime-lock.json 与 manifest.json 的插件记录；
    3. 每个插件 wheel 的文件名、大小、SHA256；
    4. 每个插件 wheel 的 METADATA Name/Version；
    5. wheelhouse 目录中不存在孤儿 wheel（磁盘上有但 manifest 未声明的 wheel）。

    脚本不会安装 wheel、访问网络或修改 portable 目录。
.PARAMETER PortableRoot
    已解压 portable 根目录，其中必须包含 resources\integration-snapshot。
.EXAMPLE
    .\scripts\verify_bundled_plugin_contract.ps1 -PortableRoot "D:\AUTO-MAS-v6-alpha.5"
.NOTES
    退出码：0=通过，1=契约不一致或输入无效。
#>

param(
    [Parameter(Mandatory = $true)]
    [string] $PortableRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

[void] (Add-Type -AssemblyName System.IO.Compression.FileSystem)

function ConvertTo-NormalizedDistributionName {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name
    )

    return ([regex]::Replace($Name.Trim().ToLowerInvariant(), '[-_.]+', '-'))
}

function Read-JsonDocument {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,

        [Parameter(Mandatory = $true)]
        [string] $Description
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Description 不存在：$Path"
    }

    try {
        $content = (Get-Content -LiteralPath $Path -Raw -Encoding utf8).TrimStart([char] 0xFEFF)
        return $content | ConvertFrom-Json
    } catch {
        throw "$Description 不是有效 JSON：$Path；$($_.Exception.Message)"
    }
}

function Read-PluginBootstrapDeclarations {
    param(
        [Parameter(Mandatory = $true)]
        [string] $PyProjectPath
    )

    if (-not (Test-Path -LiteralPath $PyProjectPath -PathType Leaf)) {
        throw "integration snapshot pyproject.toml 不存在：$PyProjectPath"
    }

    $source = Get-Content -LiteralPath $PyProjectPath -Raw -Encoding utf8
    $sectionHeader = [regex]::Match(
        $source,
        '^\s*\[tool\.auto-mas\.plugin-bootstrap\]\s*$',
        [System.Text.RegularExpressions.RegexOptions]::Multiline
    )
    if (-not $sectionHeader.Success) {
        throw "pyproject.toml 缺少 [tool.auto-mas.plugin-bootstrap]：$PyProjectPath"
    }

    $remainingSource = $source.Substring($sectionHeader.Index + $sectionHeader.Length)
    $nextSection = [regex]::Match(
        $remainingSource,
        '^\s*\[[^\]]+\]\s*$',
        [System.Text.RegularExpressions.RegexOptions]::Multiline
    )
    $sectionSource = if ($nextSection.Success) {
        $remainingSource.Substring(0, $nextSection.Index)
    } else {
        $remainingSource
    }
    $packagesMatch = [regex]::Match(
        $sectionSource,
        'packages\s*=\s*\[(?<body>[\s\S]*?)\]'
    )
    if (-not $packagesMatch.Success) {
        throw "plugin-bootstrap 缺少 packages 数组：$PyProjectPath"
    }

    $arrayBody = $packagesMatch.Groups['body'].Value
    $declarations = [System.Collections.Generic.List[object]]::new()
    $seen = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )

    $inlineMatches = [regex]::Matches($arrayBody, '\{(?<body>[^{}]+)\}')
    foreach ($inlineMatch in $inlineMatches) {
        $inlineBody = $inlineMatch.Groups['body'].Value
        $nameMatch = [regex]::Match($inlineBody, '\bname\s*=\s*["''](?<value>[^"'']+)["'']')
        if (-not $nameMatch.Success) {
            throw "plugin-bootstrap 内联声明缺少 name：{$inlineBody}"
        }

        $name = $nameMatch.Groups['value'].Value.Trim()
        $normalizedName = ConvertTo-NormalizedDistributionName -Name $name
        if (-not $seen.Add($normalizedName)) {
            throw "plugin-bootstrap 包含重复插件声明：$name"
        }

        $versionMatch = [regex]::Match(
            $inlineBody,
            '\bversion\s*=\s*["''](?<value>[^"'']+)["'']'
        )
        $specifierMatch = [regex]::Match(
            $inlineBody,
            '\bspecifier\s*=\s*["''](?<value>[^"'']+)["'']'
        )
        if ($versionMatch.Success -and $specifierMatch.Success) {
            throw "plugin-bootstrap 插件不能同时声明 version 与 specifier：$name"
        }

        $exactVersion = $null
        if ($versionMatch.Success) {
            $exactVersion = $versionMatch.Groups['value'].Value.Trim()
        } elseif ($specifierMatch.Success) {
            $specifier = $specifierMatch.Groups['value'].Value.Trim()
            $exactSpecifier = [regex]::Match($specifier, '^={2,3}\s*(?<version>[^\s,]+)$')
            if ($exactSpecifier.Success) {
                $exactVersion = $exactSpecifier.Groups['version'].Value
            }
        }

        [void] $declarations.Add([pscustomobject]@{
            name = $name
            normalized_name = $normalizedName
            exact_version = $exactVersion
        })
    }

    $barePackageBody = [regex]::Replace($arrayBody, '\{[^{}]+\}', '')
    $bareMatches = [regex]::Matches(
        $barePackageBody,
        '^\s*["''](?<name>[^"'']+)["'']\s*,?\s*(?:#.*)?$',
        [System.Text.RegularExpressions.RegexOptions]::Multiline
    )
    foreach ($bareMatch in $bareMatches) {
        $name = $bareMatch.Groups['name'].Value.Trim()
        $normalizedName = ConvertTo-NormalizedDistributionName -Name $name
        if (-not $seen.Add($normalizedName)) {
            throw "plugin-bootstrap 包含重复插件声明：$name"
        }
        [void] $declarations.Add([pscustomobject]@{
            name = $name
            normalized_name = $normalizedName
            exact_version = $null
        })
    }

    if ($declarations.Count -eq 0) {
        throw "plugin-bootstrap packages 没有可识别的插件声明：$PyProjectPath"
    }
    return $declarations.ToArray()
}

function Read-ZipEntryText {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.Compression.ZipArchiveEntry] $Entry
    )

    $stream = $Entry.Open()
    try {
        $reader = [System.IO.StreamReader]::new(
            $stream,
            [System.Text.Encoding]::UTF8,
            $true
        )
        try {
            return $reader.ReadToEnd()
        } finally {
            $reader.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

function Read-WheelIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [string] $WheelPath
    )

    $archive = [System.IO.Compression.ZipFile]::OpenRead($WheelPath)
    try {
        $metadataEntries = @(
            $archive.Entries |
                Where-Object { $_.FullName -match '^[^/]+\.dist-info/METADATA$' }
        )
        if ($metadataEntries.Count -ne 1) {
            throw "插件 wheel 必须包含且仅包含一个 dist-info/METADATA：$WheelPath"
        }

        $metadataText = Read-ZipEntryText -Entry $metadataEntries[0]
        $nameMatch = [regex]::Match(
            $metadataText,
            '^Name:\s*(?<value>.+?)\s*$',
            [System.Text.RegularExpressions.RegexOptions]::Multiline
        )
        $versionMatch = [regex]::Match(
            $metadataText,
            '^Version:\s*(?<value>.+?)\s*$',
            [System.Text.RegularExpressions.RegexOptions]::Multiline
        )
        if (-not $nameMatch.Success -or -not $versionMatch.Success) {
            throw "插件 wheel METADATA 缺少 Name 或 Version：$WheelPath"
        }

        return [pscustomobject]@{
            name = $nameMatch.Groups['value'].Value.Trim()
            version = $versionMatch.Groups['value'].Value.Trim()
        }
    } finally {
        $archive.Dispose()
    }
}

function Assert-EqualValue {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Expected,

        [Parameter(Mandatory = $true)]
        [object] $Actual,

        [Parameter(Mandatory = $true)]
        [string] $Description
    )

    if ([string] $Expected -cne [string] $Actual) {
        throw "$Description 不一致：expected $Expected, got $Actual"
    }
}

function Assert-BundledPluginContract {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Root
    )

    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        throw "portable 根目录不存在：$Root"
    }

    $resolvedRoot = (Resolve-Path -LiteralPath $Root).Path
    $snapshotRoot = Join-Path $resolvedRoot 'resources\integration-snapshot'
    $wheelsRoot = Join-Path $snapshotRoot 'plugins\wheels'
    $pyProjectPath = Join-Path $snapshotRoot 'pyproject.toml'
    $runtimeLockPath = Join-Path $wheelsRoot 'runtime-lock.json'
    $manifestPath = Join-Path $wheelsRoot 'manifest.json'

    if (-not (Test-Path -LiteralPath $wheelsRoot -PathType Container)) {
        throw "bundled wheelhouse 不存在：$wheelsRoot"
    }

    $declarations = @(Read-PluginBootstrapDeclarations -PyProjectPath $pyProjectPath)
    $runtimeLock = Read-JsonDocument `
        -Path $runtimeLockPath `
        -Description 'bundled runtime lock'
    $manifest = Read-JsonDocument `
        -Path $manifestPath `
        -Description 'bundled wheel manifest'

    $lockedPlugins = @($runtimeLock.plugins)
    if ($lockedPlugins.Count -eq 0) {
        throw "runtime-lock.json 的 plugins 数组为空：$runtimeLockPath"
    }
    $manifestWheels = @($manifest.wheels)
    if ($manifestWheels.Count -eq 0) {
        throw "manifest.json 的 wheels 数组为空：$manifestPath"
    }

    # 先校验 manifest 对 runtime-lock.json 自身的绑定。
    if ($null -eq $manifest.runtime_lock) {
        throw "manifest.json 缺少 runtime_lock 绑定"
    }
    $runtimeLockFile = Get-Item -LiteralPath $runtimeLockPath
    $runtimeLockHash = (Get-FileHash -LiteralPath $runtimeLockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Assert-EqualValue `
        -Expected ([long] $manifest.runtime_lock.size_bytes) `
        -Actual $runtimeLockFile.Length `
        -Description 'runtime-lock.json 大小'
    Assert-EqualValue `
        -Expected ([string] $manifest.runtime_lock.sha256).ToLowerInvariant() `
        -Actual $runtimeLockHash `
        -Description 'runtime-lock.json SHA256'

    $lockByDistribution = @{}
    $lockByFilename = @{}
    foreach ($plugin in $lockedPlugins) {
        $distribution = [string] $plugin.distribution
        $version = [string] $plugin.version
        $filename = [string] $plugin.filename
        if (
            [string]::IsNullOrWhiteSpace($distribution) -or
            [string]::IsNullOrWhiteSpace($version) -or
            [string]::IsNullOrWhiteSpace($filename)
        ) {
            throw "runtime lock 插件记录缺少 distribution/version/filename"
        }
        if (
            [System.IO.Path]::GetFileName($filename) -cne $filename -or
            -not $filename.EndsWith('.whl', [System.StringComparison]::OrdinalIgnoreCase)
        ) {
            throw "runtime lock 插件 wheel 文件名不安全：$filename"
        }

        $normalizedDistribution = ConvertTo-NormalizedDistributionName -Name $distribution
        if ($lockByDistribution.ContainsKey($normalizedDistribution)) {
            throw "runtime lock 包含重复插件 distribution：$distribution"
        }
        if ($lockByFilename.ContainsKey($filename)) {
            throw "runtime lock 包含重复插件 wheel 文件名：$filename"
        }
        $lockByDistribution[$normalizedDistribution] = $plugin
        $lockByFilename[$filename] = $plugin
    }

    # Alpha .4 的 0.0.3/0.0.4 漂移必须在任何安装动作之前被拒绝。
    foreach ($declaration in $declarations) {
        if (-not $lockByDistribution.ContainsKey($declaration.normalized_name)) {
            throw "plugin-bootstrap 声明的插件不在 runtime lock：$($declaration.name)"
        }
        $lockedPlugin = $lockByDistribution[$declaration.normalized_name]
        if (
            -not [string]::IsNullOrWhiteSpace([string] $declaration.exact_version) -and
            [string] $declaration.exact_version -cne [string] $lockedPlugin.version
        ) {
            throw (
                "plugin-bootstrap 与 bundled runtime lock 不一致：{0} expected {1}, got {2}" -f
                $declaration.normalized_name,
                $declaration.exact_version,
                $lockedPlugin.version
            )
        }
    }

    $manifestPluginRecords = @($manifestWheels | Where-Object { [string] $_.kind -eq 'plugin' })
    if ($manifestPluginRecords.Count -ne $lockedPlugins.Count) {
        throw (
            "manifest plugin 记录数与 runtime lock 不一致：expected {0}, got {1}" -f
            $lockedPlugins.Count,
            $manifestPluginRecords.Count
        )
    }

    foreach ($lockedPlugin in $lockedPlugins) {
        $distribution = [string] $lockedPlugin.distribution
        $version = [string] $lockedPlugin.version
        $filename = [string] $lockedPlugin.filename
        $wheelPath = Join-Path $wheelsRoot $filename
        if (-not (Test-Path -LiteralPath $wheelPath -PathType Leaf)) {
            throw "runtime lock 指定的插件 wheel 不存在：$filename"
        }

        $manifestMatches = @($manifestPluginRecords | Where-Object {
            [string] $_.filename -ceq $filename
        })
        if ($manifestMatches.Count -ne 1) {
            throw "manifest 必须且仅能包含一条插件 wheel 记录：$filename"
        }
        $manifestRecord = $manifestMatches[0]

        Assert-EqualValue `
            -Expected (ConvertTo-NormalizedDistributionName -Name $distribution) `
            -Actual (ConvertTo-NormalizedDistributionName -Name ([string] $manifestRecord.distribution)) `
            -Description "$filename manifest distribution"
        Assert-EqualValue `
            -Expected $version `
            -Actual ([string] $manifestRecord.version) `
            -Description "$filename manifest version"
        Assert-EqualValue `
            -Expected ([long] $lockedPlugin.size_bytes) `
            -Actual ([long] $manifestRecord.size_bytes) `
            -Description "$filename manifest/runtime-lock size"
        Assert-EqualValue `
            -Expected ([string] $lockedPlugin.sha256).ToLowerInvariant() `
            -Actual ([string] $manifestRecord.sha256).ToLowerInvariant() `
            -Description "$filename manifest/runtime-lock SHA256"

        $wheelFile = Get-Item -LiteralPath $wheelPath
        $wheelHash = (Get-FileHash -LiteralPath $wheelPath -Algorithm SHA256).Hash.ToLowerInvariant()
        Assert-EqualValue `
            -Expected ([long] $lockedPlugin.size_bytes) `
            -Actual $wheelFile.Length `
            -Description "$filename 实际大小"
        Assert-EqualValue `
            -Expected ([string] $lockedPlugin.sha256).ToLowerInvariant() `
            -Actual $wheelHash `
            -Description "$filename 实际 SHA256"

        $wheelIdentity = Read-WheelIdentity -WheelPath $wheelPath
        Assert-EqualValue `
            -Expected (ConvertTo-NormalizedDistributionName -Name $distribution) `
            -Actual (ConvertTo-NormalizedDistributionName -Name $wheelIdentity.name) `
            -Description "$filename METADATA Name"
        Assert-EqualValue `
            -Expected $version `
            -Actual $wheelIdentity.version `
            -Description "$filename METADATA Version"
    }

    # 孤儿 wheel 检测：磁盘上存在的 .whl 文件必须全部在 manifest 中声明。
    # manifest.wheels 同时包含 plugin 与 runtime_dependency 两类记录，统一收集 filename。
    $declaredFilenames = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::Ordinal
    )
    foreach ($record in $manifestWheels) {
        $declaredFilename = [string] $record.filename
        if ([string]::IsNullOrWhiteSpace($declaredFilename)) {
            continue
        }
        [void] $declaredFilenames.Add($declaredFilename)
    }

    $diskWheelFiles = @(Get-ChildItem -LiteralPath $wheelsRoot -Filter '*.whl' -File)
    $orphanWheels = @()
    foreach ($diskFile in $diskWheelFiles) {
        if (-not $declaredFilenames.Contains($diskFile.Name)) {
            $orphanWheels += $diskFile.Name
        }
    }
    if ($orphanWheels.Count -gt 0) {
        $orphanList = $orphanWheels -join ', '
        throw (
            "wheelhouse 存在孤儿 wheel（磁盘上有但 manifest 未声明）：{0}（共 {1} 个）" -f
            $orphanList,
            $orphanWheels.Count
        )
    }

    return [pscustomobject]@{
        portable_root = $resolvedRoot
        declared_plugin_count = $declarations.Count
        locked_plugin_count = $lockedPlugins.Count
        verified_plugin_wheel_count = $lockedPlugins.Count
        declared_wheel_count = $declaredFilenames.Count
        disk_wheel_count = $diskWheelFiles.Count
        orphan_wheel_count = $orphanWheels.Count
    }
}

try {
    $result = Assert-BundledPluginContract -Root $PortableRoot
    Write-Host (
        '[PASS] bundled plugin contract：{0} 个声明，{1} 个锁定插件 wheel 已验证，{2} 个 manifest wheel，{3} 个磁盘 wheel，{4} 个孤儿' -f
        $result.declared_plugin_count,
        $result.verified_plugin_wheel_count,
        $result.declared_wheel_count,
        $result.disk_wheel_count,
        $result.orphan_wheel_count
    ) -ForegroundColor Green
    exit 0
} catch {
    Write-Error "[FAIL] bundled plugin contract：$($_.Exception.Message)"
    exit 1
}
