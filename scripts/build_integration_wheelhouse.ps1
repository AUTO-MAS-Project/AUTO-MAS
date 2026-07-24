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
    [string] $StagingDirectory,
    [ValidateRange(0, [long]::MaxValue)]
    [long] $SourceDateEpoch = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[void] (Add-Type -AssemblyName System.IO.Compression.FileSystem)

$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$script:ExcludedSourceDirectoryNames = @(
    '.git',
    '.mypy_cache',
    '.pytest_cache',
    '.ruff_cache',
    '.tox',
    '.venv',
    '__pycache__',
    'build',
    'dist',
    'venv'
)

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

function Assert-ExistingFile {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [Parameter(Mandatory = $true)]
        [string] $Description
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Description does not exist: $Path"
    }
}

function Assert-ExistingDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [Parameter(Mandatory = $true)]
        [string] $Description
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Description does not exist: $Path"
    }
}

function Test-PathWithinDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [Parameter(Mandatory = $true)]
        [string] $Directory
    )

    $fullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    $fullDirectory = [System.IO.Path]::GetFullPath($Directory).TrimEnd('\', '/')
    if ($fullPath.Equals($fullDirectory, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }

    $directoryPrefix = $fullDirectory + [System.IO.Path]::DirectorySeparatorChar
    return $fullPath.StartsWith($directoryPrefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string] $FilePath,
        [Parameter(Mandatory = $true)]
        [string[]] $ArgumentList,
        [Parameter(Mandatory = $true)]
        [string] $Description,
        [string] $LogPath
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 wraps every native stderr line in a terminating
        # NativeCommandError when the caller uses Stop, even if the process exits 0.
        $ErrorActionPreference = 'Continue'
        $output = @(& $FilePath @ArgumentList 2>&1 | ForEach-Object { $_.ToString() })
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if (-not [string]::IsNullOrWhiteSpace($LogPath)) {
        $logText = if ($output.Count -eq 0) { '' } else { ($output -join [Environment]::NewLine) + [Environment]::NewLine }
        [System.IO.File]::WriteAllText($LogPath, $logText, $script:Utf8NoBom)
    }

    if ($exitCode -ne 0) {
        $details = if ($output.Count -eq 0) { '<no output>' } else { $output -join [Environment]::NewLine }
        throw "$Description failed with exit code ${exitCode}: $details"
    }

    return $output
}

function Invoke-ExternalCommandResult {
    param(
        [Parameter(Mandatory = $true)]
        [string] $FilePath,
        [Parameter(Mandatory = $true)]
        [string[]] $ArgumentList
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& $FilePath @ArgumentList 2>&1 | ForEach-Object { $_.ToString() })
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return [pscustomobject]@{
        exit_code = $exitCode
        output = $output
    }
}

function ConvertTo-NormalizedDistributionName {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name
    )

    return ([regex]::Replace($Name.Trim().ToLowerInvariant(), '[-_.]+', '-'))
}

function ConvertTo-WheelDistributionComponent {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name
    )

    return ([regex]::Replace($Name.Trim(), '[-_.]+', '_'))
}

function ConvertTo-WheelVersionComponent {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Version
    )

    return ([regex]::Replace($Version.Trim(), '[^A-Za-z0-9.]+', '_'))
}

function Get-ProjectMetadata {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot
    )

    $pyprojectPath = Join-Path $ProjectRoot 'pyproject.toml'
    Assert-ExistingFile -Path $pyprojectPath -Description 'Plugin pyproject.toml'

    $section = ''
    $name = $null
    $version = $null
    $entryPoints = New-Object System.Collections.Generic.List[object]
    $assignmentPattern = '^\s*(?:"(?<dqkey>[^"]+)"|''(?<sqkey>[^'']+)''|(?<barekey>[A-Za-z0-9_.-]+))\s*=\s*(?:"(?<dqvalue>[^"]*)"|''(?<sqvalue>[^'']*)'')\s*(?:#.*)?$'

    foreach ($line in (Get-Content -Encoding utf8 -LiteralPath $pyprojectPath)) {
        if ($line -match '^\s*\[(?<section>[^]]+)\]\s*(?:#.*)?$') {
            $section = $Matches.section.Trim()
            continue
        }

        if ($line -notmatch $assignmentPattern) {
            continue
        }

        $key = if ($Matches['dqkey']) {
            $Matches['dqkey']
        } elseif ($Matches['sqkey']) {
            $Matches['sqkey']
        } else {
            $Matches['barekey']
        }
        $value = if ($Matches['dqvalue']) { $Matches['dqvalue'] } else { $Matches['sqvalue'] }

        if ($section -eq 'project') {
            if ($key -eq 'name') {
                $name = $value
            } elseif ($key -eq 'version') {
                $version = $value
            }
            continue
        }

        if ($section -match '^project\.entry-points\.(?:"(?<dqgroup>[^"]+)"|''(?<sqgroup>[^'']+)'')$') {
            $group = if ($Matches['dqgroup']) { $Matches['dqgroup'] } else { $Matches['sqgroup'] }
            [void] $entryPoints.Add([pscustomobject]@{
                group = $group
                name = $key
                value = $value
            })
        }
    }

    if ([string]::IsNullOrWhiteSpace($name)) {
        throw "Cannot parse [project].name from $pyprojectPath"
    }
    if ([string]::IsNullOrWhiteSpace($version)) {
        throw "Cannot parse [project].version from $pyprojectPath"
    }

    return [pscustomobject]@{
        distribution = $name
        normalized_distribution = ConvertTo-NormalizedDistributionName -Name $name
        version = $version
        entry_points = $entryPoints.ToArray()
    }
}

function Read-ZipEntryText {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.Compression.ZipArchiveEntry] $Entry
    )

    $stream = $Entry.Open()
    try {
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8, $true)
        try {
            return $reader.ReadToEnd()
        } finally {
            $reader.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

function Get-WheelMetadata {
    param(
        [Parameter(Mandatory = $true)]
        [string] $WheelPath
    )

    $archive = [System.IO.Compression.ZipFile]::OpenRead($WheelPath)
    try {
        $metadataEntries = @($archive.Entries | Where-Object {
            $_.FullName -match '^[^/]+\.dist-info/METADATA$'
        })
        if ($metadataEntries.Count -ne 1) {
            throw "Wheel must contain exactly one dist-info/METADATA entry: $WheelPath"
        }

        $metadataText = Read-ZipEntryText -Entry $metadataEntries[0]
        $distribution = $null
        $version = $null
        foreach ($line in ($metadataText -split "`r?`n")) {
            if ($null -eq $distribution -and $line -match '^Name:\s*(?<value>.+?)\s*$') {
                $distribution = $Matches.value
            } elseif ($null -eq $version -and $line -match '^Version:\s*(?<value>.+?)\s*$') {
                $version = $Matches.value
            }
            if ($null -ne $distribution -and $null -ne $version) {
                break
            }
        }
        if ([string]::IsNullOrWhiteSpace($distribution) -or [string]::IsNullOrWhiteSpace($version)) {
            throw "Wheel METADATA is missing Name or Version: $WheelPath"
        }

        $entryPointEntries = @($archive.Entries | Where-Object {
            $_.FullName -match '^[^/]+\.dist-info/entry_points\.txt$'
        })
        if ($entryPointEntries.Count -gt 1) {
            throw "Wheel contains multiple dist-info/entry_points.txt entries: $WheelPath"
        }

        $entryPoints = New-Object System.Collections.Generic.List[object]
        if ($entryPointEntries.Count -eq 1) {
            $entryPointText = Read-ZipEntryText -Entry $entryPointEntries[0]
            $group = $null
            foreach ($line in ($entryPointText -split "`r?`n")) {
                $trimmedLine = $line.Trim()
                if ([string]::IsNullOrWhiteSpace($trimmedLine) -or $trimmedLine.StartsWith('#')) {
                    continue
                }
                if ($trimmedLine -match '^\[(?<group>[^]]+)\]$') {
                    $group = $Matches.group.Trim()
                    continue
                }
                if ($null -eq $group -or $trimmedLine -notmatch '^(?<name>[^=]+?)\s*=\s*(?<value>.+?)\s*$') {
                    throw "Cannot parse wheel entry_points.txt line '$trimmedLine' in $WheelPath"
                }
                [void] $entryPoints.Add([pscustomobject]@{
                    group = $group
                    name = $Matches.name.Trim()
                    value = $Matches.value.Trim()
                })
            }
        }

        return [pscustomobject]@{
            distribution = $distribution
            normalized_distribution = ConvertTo-NormalizedDistributionName -Name $distribution
            version = $version
            entry_points = $entryPoints.ToArray()
        }
    } finally {
        $archive.Dispose()
    }
}

function Get-EntryPointKeys {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]] $EntryPoints
    )

    return @($EntryPoints | ForEach-Object {
        '{0}|{1}|{2}' -f $_.group, $_.name, $_.value
    } | Sort-Object)
}

function Test-ExcludedSourcePath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RelativePath
    )

    foreach ($segment in ($RelativePath -split '/')) {
        if ($script:ExcludedSourceDirectoryNames -contains $segment) {
            return $true
        }
        if ($segment.EndsWith('.egg-info', [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }

    return $false
}

function Get-ProjectFileRecords {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot
    )

    $rootPrefix = $ProjectRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    $paths = New-Object System.Collections.Generic.List[string]
    $filesByRelativePath = @{}

    $pendingDirectories = New-Object System.Collections.Generic.Stack[string]
    $pendingDirectories.Push($ProjectRoot)
    while ($pendingDirectories.Count -gt 0) {
        $currentDirectory = $pendingDirectories.Pop()
        foreach ($item in (Get-ChildItem -LiteralPath $currentDirectory -Force)) {
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Reparse points are not allowed in a reproducible project snapshot: $($item.FullName)"
            }

            if ($item.PSIsContainer) {
                $relativeDirectory = $item.FullName.Substring($rootPrefix.Length).Replace('\', '/')
                if (-not (Test-ExcludedSourcePath -RelativePath $relativeDirectory)) {
                    $pendingDirectories.Push($item.FullName)
                }
                continue
            }

            if (-not $item.FullName.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Project file escaped the project root: $($item.FullName)"
            }

            $relativePath = $item.FullName.Substring($rootPrefix.Length).Replace('\', '/')
            if (Test-ExcludedSourcePath -RelativePath $relativePath) {
                continue
            }

            [void] $paths.Add($relativePath)
            $filesByRelativePath[$relativePath] = $item.FullName
        }
    }

    $orderedPaths = $paths.ToArray()
    [Array]::Sort($orderedPaths, [System.StringComparer]::Ordinal)
    $records = New-Object System.Collections.Generic.List[object]

    foreach ($relativePath in $orderedPaths) {
        $filePath = $filesByRelativePath[$relativePath]
        $fileInfo = Get-Item -Force -LiteralPath $filePath
        $sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $filePath).Hash.ToLowerInvariant()
        [void] $records.Add([pscustomobject]@{
            relative_path = $relativePath
            source_path = $filePath
            size_bytes = [long] $fileInfo.Length
            sha256 = $sha256
        })
    }

    if ($records.Count -eq 0) {
        throw "Project has no buildable source files: $ProjectRoot"
    }

    return $records.ToArray()
}

function Get-SourceDigest {
    param(
        [Parameter(Mandatory = $true)]
        [object[]] $FileRecords
    )

    $stream = New-Object System.IO.MemoryStream
    try {
        foreach ($record in $FileRecords) {
            $pathBytes = $script:Utf8NoBom.GetBytes([string] $record.relative_path)
            $pathLengthBytes = [System.BitConverter]::GetBytes([int] $pathBytes.Length)
            $sizeBytes = [System.BitConverter]::GetBytes([long] $record.size_bytes)
            if (-not [System.BitConverter]::IsLittleEndian) {
                [Array]::Reverse($pathLengthBytes)
                [Array]::Reverse($sizeBytes)
            }
            $hashBytes = [System.Text.Encoding]::ASCII.GetBytes([string] $record.sha256)

            $stream.Write($pathLengthBytes, 0, $pathLengthBytes.Length)
            $stream.Write($pathBytes, 0, $pathBytes.Length)
            $stream.Write($sizeBytes, 0, $sizeBytes.Length)
            $stream.Write($hashBytes, 0, $hashBytes.Length)
        }

        $sha = [System.Security.Cryptography.SHA256]::Create()
        try {
            $digestBytes = $sha.ComputeHash($stream.ToArray())
        } finally {
            $sha.Dispose()
        }
    } finally {
        $stream.Dispose()
    }

    return [pscustomobject]@{
        algorithm = 'sha256-path-length-size-content-hash-v1'
        sha256 = ([System.BitConverter]::ToString($digestBytes)).Replace('-', '').ToLowerInvariant()
        file_count = $FileRecords.Count
    }
}

function Copy-ProjectSnapshot {
    param(
        [Parameter(Mandatory = $true)]
        [object[]] $FileRecords,
        [Parameter(Mandatory = $true)]
        [string] $DestinationRoot
    )

    if (Test-Path -LiteralPath $DestinationRoot) {
        throw "Staged project directory already exists; refusing to overwrite: $DestinationRoot"
    }
    [void] (New-Item -ItemType Directory -Path $DestinationRoot)

    foreach ($record in $FileRecords) {
        $relativeWindowsPath = ([string] $record.relative_path).Replace('/', '\')
        $destinationPath = Join-Path $DestinationRoot $relativeWindowsPath
        $destinationParent = Split-Path -Parent $destinationPath
        if (-not (Test-Path -LiteralPath $destinationParent -PathType Container)) {
            [void] (New-Item -ItemType Directory -Path $destinationParent)
        }
        [System.IO.File]::Copy([string] $record.source_path, $destinationPath, $false)
    }
}

function Get-RepositoryMetadata {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RepositoryId,
        [Parameter(Mandatory = $true)]
        [string] $RepositoryRoot,
        [Parameter(Mandatory = $true)]
        [string] $RelativeProjectPath,
        [Parameter(Mandatory = $true)]
        [string] $GitExecutable
    )

    $headLines = @(Invoke-ExternalCommand -FilePath $GitExecutable -ArgumentList @('-C', $RepositoryRoot, 'rev-parse', 'HEAD') -Description "Read $RepositoryId HEAD")
    $headTimestampLines = @(Invoke-ExternalCommand -FilePath $GitExecutable -ArgumentList @('-C', $RepositoryRoot, 'show', '-s', '--format=%ct', 'HEAD') -Description "Read $RepositoryId HEAD timestamp")
    if ($headLines.Count -ne 1 -or $headTimestampLines.Count -ne 1) {
        throw "$RepositoryId returned unexpected HEAD metadata"
    }
    $head = $headLines[0].Trim()
    $headTimestampText = $headTimestampLines[0].Trim()
    $headTimestamp = 0L
    if (-not [long]::TryParse($headTimestampText, [ref] $headTimestamp)) {
        throw "$RepositoryId HEAD timestamp is not a valid Unix timestamp: $headTimestampText"
    }

    $projectStatus = @(Invoke-ExternalCommand -FilePath $GitExecutable -ArgumentList @('-C', $RepositoryRoot, 'status', '--porcelain=v1', '--untracked-files=all', '--', $RelativeProjectPath) -Description "Read $RepositoryId project status")
    $repositoryStatus = @(Invoke-ExternalCommand -FilePath $GitExecutable -ArgumentList @('-C', $RepositoryRoot, 'status', '--porcelain=v1', '--untracked-files=all') -Description "Read $RepositoryId repository status")
    $originResult = Invoke-ExternalCommandResult -FilePath $GitExecutable -ArgumentList @('-C', $RepositoryRoot, 'config', '--get', 'remote.origin.url')
    $repositoryUrl = if ($originResult.exit_code -eq 0 -and $originResult.output.Count -gt 0) {
        $originResult.output[0].Trim()
    } else {
        $null
    }

    return [pscustomobject]@{
        repository_id = $RepositoryId
        repository_url = $repositoryUrl
        relative_path = $RelativeProjectPath.Replace('\', '/')
        head = $head
        head_timestamp_epoch = $headTimestamp
        dirty = ($projectStatus.Count -gt 0)
        repository_dirty = ($repositoryStatus.Count -gt 0)
    }
}

function Get-ManifestToolPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [Parameter(Mandatory = $true)]
        [string] $RepositoryRoot
    )

    $rootPrefix = $RepositoryRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    if ($Path.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $Path.Substring($rootPrefix.Length).Replace('\', '/')
    }
    return $Path.Replace('\', '/')
}

function Get-InstalledDistributionVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string] $SitePackagesPath,
        [Parameter(Mandatory = $true)]
        [string] $Distribution
    )

    $metadataFiles = @(Get-ChildItem -LiteralPath $SitePackagesPath -Directory -Filter "$Distribution-*.dist-info" | ForEach-Object {
        Join-Path $_.FullName 'METADATA'
    } | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
    if ($metadataFiles.Count -ne 1) {
        throw "Expected one installed $Distribution METADATA file, got $($metadataFiles.Count)"
    }

    foreach ($line in (Get-Content -Encoding utf8 -LiteralPath $metadataFiles[0])) {
        if ($line -match '^Version:\s*(?<version>.+?)\s*$') {
            return $Matches.version
        }
    }
    throw "Installed $Distribution METADATA does not declare Version"
}

$defaultHostRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($HostRepositoryRoot)) {
    $HostRepositoryRoot = $defaultHostRoot
}
$HostRepositoryRoot = Get-FullPath -Path $HostRepositoryRoot
Assert-ExistingDirectory -Path $HostRepositoryRoot -Description 'AUTO-MAS integration worktree'

$organizationRoot = Get-FullPath -Path '..\..\..' -BasePath $HostRepositoryRoot
if ([string]::IsNullOrWhiteSpace($HsrRepositoryRoot)) {
    $HsrRepositoryRoot = Join-Path $organizationRoot 'plugins\automas-hsr'
}
if ([string]::IsNullOrWhiteSpace($M9aRepositoryRoot)) {
    $M9aRepositoryRoot = Join-Path $organizationRoot 'plugins\automas-m9a'
}
if ([string]::IsNullOrWhiteSpace($MaaFwRepositoryRoot)) {
    $MaaFwRepositoryRoot = Join-Path $organizationRoot 'plugins\automas-maafw'
}
if ([string]::IsNullOrWhiteSpace($MxuImportRepositoryRoot)) {
    $MxuImportRepositoryRoot = Join-Path $organizationRoot 'plugins\automas_mxu_import'
}
if ([string]::IsNullOrWhiteSpace($MaaEndAdapterRepositoryRoot)) {
    $MaaEndAdapterRepositoryRoot = Join-Path $organizationRoot 'plugins\automas-maaend-adapter'
}
if ([string]::IsNullOrWhiteSpace($MaaScriptRepositoryRoot)) {
    $MaaScriptRepositoryRoot = Join-Path $organizationRoot 'plugins\automas_script_maa'
}
$HsrRepositoryRoot = Get-FullPath -Path $HsrRepositoryRoot -BasePath $HostRepositoryRoot
$M9aRepositoryRoot = Get-FullPath -Path $M9aRepositoryRoot -BasePath $HostRepositoryRoot
$MaaFwRepositoryRoot = Get-FullPath -Path $MaaFwRepositoryRoot -BasePath $HostRepositoryRoot
$MxuImportRepositoryRoot = Get-FullPath -Path $MxuImportRepositoryRoot -BasePath $HostRepositoryRoot
$MaaEndAdapterRepositoryRoot = Get-FullPath -Path $MaaEndAdapterRepositoryRoot -BasePath $HostRepositoryRoot
$MaaScriptRepositoryRoot = Get-FullPath -Path $MaaScriptRepositoryRoot -BasePath $HostRepositoryRoot
Assert-ExistingDirectory -Path $HsrRepositoryRoot -Description 'HSR plugin repository'
Assert-ExistingDirectory -Path $M9aRepositoryRoot -Description 'M9A plugin repository'
Assert-ExistingDirectory -Path $MaaFwRepositoryRoot -Description 'MaaFW plugin repository'
Assert-ExistingDirectory -Path $MxuImportRepositoryRoot -Description 'MXU import plugin repository'
Assert-ExistingDirectory -Path $MaaEndAdapterRepositoryRoot -Description 'MaaEnd adapter plugin repository'
Assert-ExistingDirectory -Path $MaaScriptRepositoryRoot -Description 'MAA script plugin repository'

if ([string]::IsNullOrWhiteSpace($EnvironmentRoot)) {
    $EnvironmentRoot = Join-Path $HostRepositoryRoot 'build\environment-tar\environment'
}
$EnvironmentRoot = Get-FullPath -Path $EnvironmentRoot -BasePath $HostRepositoryRoot
if ([string]::IsNullOrWhiteSpace($UvPath)) {
    $UvPath = Join-Path $EnvironmentRoot 'python\Scripts\uv.exe'
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
Assert-ExistingFile -Path $UvPath -Description 'Bundled uv.exe'
Assert-ExistingFile -Path $PythonPath -Description 'Bundled python.exe'
Assert-ExistingFile -Path $GitPath -Description 'Bundled git.exe'

$runId = '{0}-{1}' -f ([DateTimeOffset]::UtcNow.ToString('yyyyMMdd-HHmmss')), ([Guid]::NewGuid().ToString('N'))
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $HostRepositoryRoot "build\wheelhouse\integration-$runId"
}
$OutputDirectory = Get-FullPath -Path $OutputDirectory -BasePath $HostRepositoryRoot
if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Output directory already exists; use a new directory to avoid overwriting wheels: $OutputDirectory"
}

if ([string]::IsNullOrWhiteSpace($StagingDirectory)) {
    $StagingDirectory = Join-Path ([System.IO.Path]::GetTempPath()) "AUTO-MAS-wheelhouse-$runId"
}
$StagingDirectory = Get-FullPath -Path $StagingDirectory -BasePath $HostRepositoryRoot
if (Test-Path -LiteralPath $StagingDirectory) {
    throw "Staging directory already exists; refusing to overwrite: $StagingDirectory"
}

$outputParent = Split-Path -Parent $OutputDirectory
$publishDirectory = Join-Path $outputParent ('.{0}.publish-{1}' -f (Split-Path -Leaf $OutputDirectory), $runId)
if (Test-Path -LiteralPath $publishDirectory) {
    throw "Publish staging directory already exists; refusing to overwrite: $publishDirectory"
}

$projectSpecs = @(
    [pscustomobject]@{ repository_id = 'AUTO-MAS'; repository_root = $HostRepositoryRoot; relative_path = 'plugins/auto_mas_core'; expected_distribution = 'auto-mas-core' },
    [pscustomobject]@{ repository_id = 'AUTO-MAS'; repository_root = $HostRepositoryRoot; relative_path = 'plugins/browser'; expected_distribution = 'automas-plugin-browser' },
    [pscustomobject]@{ repository_id = 'AUTO-MAS'; repository_root = $HostRepositoryRoot; relative_path = 'plugins/ok_script_adapter'; expected_distribution = 'automas_plugin_ok_script_adapter' },
    [pscustomobject]@{ repository_id = 'AUTO-MAS'; repository_root = $HostRepositoryRoot; relative_path = 'plugins/okww_adapter'; expected_distribution = 'automas_plugin_okww_adapter' },
    [pscustomobject]@{ repository_id = 'automas-hsr'; repository_root = $HsrRepositoryRoot; relative_path = 'packages/automas_hsr'; expected_distribution = 'automas-hsr' },
    [pscustomobject]@{ repository_id = 'automas-hsr'; repository_root = $HsrRepositoryRoot; relative_path = 'packages/automas_script_hsr'; expected_distribution = 'automas-script-hsr' },
    [pscustomobject]@{ repository_id = 'automas-hsr'; repository_root = $HsrRepositoryRoot; relative_path = 'packages/automas_hsr_adapter_m7a'; expected_distribution = 'automas-hsr-adapter-m7a' },
    [pscustomobject]@{ repository_id = 'automas-hsr'; repository_root = $HsrRepositoryRoot; relative_path = 'packages/automas_hsr_adapter_sra'; expected_distribution = 'automas-hsr-adapter-sra' },
    [pscustomobject]@{ repository_id = 'automas-m9a'; repository_root = $M9aRepositoryRoot; relative_path = 'packages/automas_m9a'; expected_distribution = 'automas-m9a' },
    [pscustomobject]@{ repository_id = 'automas-m9a'; repository_root = $M9aRepositoryRoot; relative_path = 'packages/automas_script_maafw_pack_m9a'; expected_distribution = 'automas-script-maafw-pack-m9a' },
    [pscustomobject]@{ repository_id = 'automas-maafw'; repository_root = $MaaFwRepositoryRoot; relative_path = 'packages/automas_maafw_agent_env'; expected_distribution = 'automas-maafw-agent-env' },
    [pscustomobject]@{ repository_id = 'automas-maafw'; repository_root = $MaaFwRepositoryRoot; relative_path = 'packages/automas_maafw_controller_adb'; expected_distribution = 'automas-maafw-controller-adb' },
    [pscustomobject]@{ repository_id = 'automas-maafw'; repository_root = $MaaFwRepositoryRoot; relative_path = 'packages/automas_maafw_controller_win32'; expected_distribution = 'automas-maafw-controller-win32' },
    [pscustomobject]@{ repository_id = 'automas-maafw'; repository_root = $MaaFwRepositoryRoot; relative_path = 'packages/automas_maafw_interface'; expected_distribution = 'automas-maafw-interface' },
    [pscustomobject]@{ repository_id = 'automas-maafw'; repository_root = $MaaFwRepositoryRoot; relative_path = 'packages/automas_maafw_project_store'; expected_distribution = 'automas-maafw-project-store' },
    [pscustomobject]@{ repository_id = 'automas-maafw'; repository_root = $MaaFwRepositoryRoot; relative_path = 'packages/automas_maafw_project_update'; expected_distribution = 'automas-maafw-project-update' },
    [pscustomobject]@{ repository_id = 'automas-maafw'; repository_root = $MaaFwRepositoryRoot; relative_path = 'packages/automas_maafw_runtime_pool'; expected_distribution = 'automas-maafw-runtime-pool' },
    [pscustomobject]@{ repository_id = 'automas-maafw'; repository_root = $MaaFwRepositoryRoot; relative_path = 'packages/automas_maafw_runner'; expected_distribution = 'automas-maafw-runner' },
    [pscustomobject]@{ repository_id = 'automas-maafw'; repository_root = $MaaFwRepositoryRoot; relative_path = 'packages/automas_script_maafw'; expected_distribution = 'automas-script-maafw' },
    [pscustomobject]@{ repository_id = 'automas-maafw'; repository_root = $MaaFwRepositoryRoot; relative_path = 'packages/automas_script_maafw_managed'; expected_distribution = 'automas-script-maafw-managed' },
    [pscustomobject]@{ repository_id = 'automas_mxu_import'; repository_root = $MxuImportRepositoryRoot; relative_path = '.'; expected_distribution = 'automas-plugin-mxu-import' },
    [pscustomobject]@{ repository_id = 'automas-maaend-adapter'; repository_root = $MaaEndAdapterRepositoryRoot; relative_path = '.'; expected_distribution = 'automas_plugin_maaend_adapter' },
    [pscustomobject]@{ repository_id = 'automas_script_maa'; repository_root = $MaaScriptRepositoryRoot; relative_path = '.'; expected_distribution = 'automas_script_maa' }
)

$expectedEntryPoints = @(
    'auto_mas.plugins|auto_mas_core|auto_mas_core.plugin:Plugin',
    'auto_mas.plugins|browser|automas_plugin_browser.plugin:Plugin',
    'auto_mas.plugins|ok_script_adapter|ok_script_adapter.plugin:Plugin',
    'auto_mas.plugins|okww_adapter|okww_adapter.plugin:Plugin',
    'auto_mas.plugins|automas_script_hsr|automas_script_hsr.plugin:Plugin',
    'auto_mas.plugins|automas_hsr_adapter_m7a|automas_hsr_adapter_m7a.plugin:Plugin',
    'auto_mas.plugins|automas_hsr_adapter_sra|automas_hsr_adapter_sra.plugin:Plugin',
    'auto_mas.plugins|automas_script_maafw_pack_m9a|automas_script_maafw_pack_m9a.plugin:Plugin',
    'auto_mas.plugins|automas_maafw_agent_env|automas_maafw_agent_env.plugin:Plugin',
    'auto_mas.plugins|automas_maafw_controller_adb|automas_maafw_controller_adb.plugin:Plugin',
    'auto_mas.plugins|automas_maafw_controller_win32|automas_maafw_controller_win32.plugin:Plugin',
    'auto_mas.plugins|automas_maafw_interface|automas_maafw_interface.plugin:Plugin',
    'auto_mas.plugins|automas_maafw_project_store|automas_maafw_project_store.plugin:Plugin',
    'auto_mas.plugins|automas_maafw_project_update|automas_maafw_project_update.plugin:Plugin',
    'auto_mas.plugins|automas_maafw_runtime_pool|automas_maafw_runtime_pool.plugin:Plugin',
    'auto_mas.plugins|automas_maafw_runner|automas_maafw_runner.plugin:Plugin',
    'auto_mas.plugins|automas_script_maafw|automas_script_maafw.plugin:Plugin',
    'auto_mas.plugins|automas_script_maafw_managed|automas_script_maafw_managed.plugin:Plugin',
    'auto_mas.plugins|mxu_import|automas_plugin_mxu_import.plugin:Plugin',
    'auto_mas.plugins|maaend_adapter|maaend_adapter.plugin:Plugin',
    'auto_mas.plugins|script_MAA|script_maa.plugin:Plugin'
)

if ($projectSpecs.Count -ne 23) {
    throw "Unexpected project count; expected 23, got $($projectSpecs.Count)"
}
if ($expectedEntryPoints.Count -ne 21) {
    throw "Unexpected entry-point baseline count; expected 21, got $($expectedEntryPoints.Count)"
}

if ((Test-PathWithinDirectory -Path $StagingDirectory -Directory $OutputDirectory) -or
    (Test-PathWithinDirectory -Path $OutputDirectory -Directory $StagingDirectory) -or
    (Test-PathWithinDirectory -Path $StagingDirectory -Directory $publishDirectory) -or
    (Test-PathWithinDirectory -Path $publishDirectory -Directory $StagingDirectory)) {
    throw 'Output, publish staging, and build staging directories must not overlap'
}
foreach ($spec in $projectSpecs) {
    $sourceProjectRoot = Get-FullPath -Path $spec.relative_path -BasePath $spec.repository_root
    foreach ($artifactPath in @($OutputDirectory, $publishDirectory, $StagingDirectory)) {
        if (Test-PathWithinDirectory -Path $artifactPath -Directory $sourceProjectRoot) {
            throw "Artifact path must not be inside a source project: $artifactPath"
        }
    }
}
if (-not (Test-Path -LiteralPath $outputParent -PathType Container)) {
    [void] (New-Item -ItemType Directory -Path $outputParent)
}
[void] (New-Item -ItemType Directory -Path $StagingDirectory)
[void] (New-Item -ItemType Directory -Path $publishDirectory)

$projects = New-Object System.Collections.Generic.List[object]
foreach ($spec in $projectSpecs) {
    $projectRoot = Get-FullPath -Path $spec.relative_path -BasePath $spec.repository_root
    Assert-ExistingDirectory -Path $projectRoot -Description "$($spec.expected_distribution) project directory"
    $metadata = Get-ProjectMetadata -ProjectRoot $projectRoot
    $expectedNormalized = ConvertTo-NormalizedDistributionName -Name $spec.expected_distribution
    if ($metadata.normalized_distribution -ne $expectedNormalized) {
        throw "$projectRoot distribution drifted; expected $($spec.expected_distribution), got $($metadata.distribution)"
    }

    $repository = Get-RepositoryMetadata -RepositoryId $spec.repository_id -RepositoryRoot $spec.repository_root -RelativeProjectPath $spec.relative_path -GitExecutable $GitPath
    [void] $projects.Add([pscustomobject]@{
        spec = $spec
        project_root = $projectRoot
        metadata = $metadata
        repository = $repository
    })
}

$duplicateDistributions = @($projects | Group-Object { $_.metadata.normalized_distribution } | Where-Object Count -gt 1)
if ($duplicateDistributions.Count -gt 0) {
    throw "Duplicate distributions: $(($duplicateDistributions.Name | Sort-Object) -join ', ')"
}

$actualEntryPointKeys = New-Object System.Collections.Generic.List[string]
foreach ($project in $projects) {
    foreach ($entryPoint in $project.metadata.entry_points) {
        [void] $actualEntryPointKeys.Add(('{0}|{1}|{2}' -f $entryPoint.group, $entryPoint.name, $entryPoint.value))
    }
}
$duplicateEntryPoints = @($actualEntryPointKeys | Group-Object { ($_ -split '\|', 3)[0..1] -join '|' } | Where-Object Count -gt 1)
if ($duplicateEntryPoints.Count -gt 0) {
    throw "Duplicate plugin entry-point group/name pairs: $(($duplicateEntryPoints.Name | Sort-Object) -join ', ')"
}

$missingEntryPoints = @($expectedEntryPoints | Where-Object { $actualEntryPointKeys -notcontains $_ } | Sort-Object)
$unexpectedEntryPoints = @($actualEntryPointKeys | Where-Object { $expectedEntryPoints -notcontains $_ } | Sort-Object)
if ($actualEntryPointKeys.Count -ne 21 -or $missingEntryPoints.Count -gt 0 -or $unexpectedEntryPoints.Count -gt 0) {
    throw "Expected 21 plugin entry points. Missing: $($missingEntryPoints -join ', '); unexpected: $($unexpectedEntryPoints -join ', ')"
}

if ($SourceDateEpoch -eq 0) {
    $SourceDateEpoch = [long] (($projects | ForEach-Object { $_.repository.head_timestamp_epoch } | Measure-Object -Maximum).Maximum)
}

$uvVersion = (@(Invoke-ExternalCommand -FilePath $UvPath -ArgumentList @('--version') -Description 'Read uv version') -join ' ').Trim()
$gitVersion = (@(Invoke-ExternalCommand -FilePath $GitPath -ArgumentList @('--version') -Description 'Read Git version') -join ' ').Trim()
$pythonFileVersion = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($PythonPath).FileVersion
$sitePackagesPath = Join-Path $EnvironmentRoot 'python\Lib\site-packages'
Assert-ExistingDirectory -Path $sitePackagesPath -Description 'Bundled Python site-packages'
$setuptoolsVersion = Get-InstalledDistributionVersion -SitePackagesPath $sitePackagesPath -Distribution 'setuptools'
$wheelVersion = Get-InstalledDistributionVersion -SitePackagesPath $sitePackagesPath -Distribution 'wheel'
$wheelRecords = New-Object System.Collections.Generic.List[object]
$previousSourceDateEpoch = [Environment]::GetEnvironmentVariable('SOURCE_DATE_EPOCH', 'Process')
$previousPythonHashSeed = [Environment]::GetEnvironmentVariable('PYTHONHASHSEED', 'Process')

try {
    [Environment]::SetEnvironmentVariable('SOURCE_DATE_EPOCH', [string] $SourceDateEpoch, 'Process')
    [Environment]::SetEnvironmentVariable('PYTHONHASHSEED', '0', 'Process')

    foreach ($project in ($projects | Sort-Object { $_.metadata.normalized_distribution })) {
        $distribution = $project.metadata.distribution
        Write-Host "Building $distribution $($project.metadata.version)"

        $sourceRecords = @(Get-ProjectFileRecords -ProjectRoot $project.project_root)
        $sourceDigest = Get-SourceDigest -FileRecords $sourceRecords
        $safeProjectName = ConvertTo-WheelDistributionComponent -Name $distribution
        $projectStagingRoot = Join-Path $StagingDirectory $safeProjectName
        $snapshotRoot = Join-Path $projectStagingRoot 'source'
        $buildOutputRoot = Join-Path $projectStagingRoot 'wheel'
        [void] (New-Item -ItemType Directory -Path $projectStagingRoot)
        Copy-ProjectSnapshot -FileRecords $sourceRecords -DestinationRoot $snapshotRoot

        $snapshotRecords = @(Get-ProjectFileRecords -ProjectRoot $snapshotRoot)
        $snapshotDigest = Get-SourceDigest -FileRecords $snapshotRecords
        if ($snapshotDigest.sha256 -ne $sourceDigest.sha256 -or $snapshotDigest.file_count -ne $sourceDigest.file_count) {
            throw "$distribution staged snapshot digest differs from source; source may have changed during staging"
        }

        [void] (New-Item -ItemType Directory -Path $buildOutputRoot)
        $buildLogPath = Join-Path $projectStagingRoot 'uv-build.log'
        $uvArguments = @(
            'build',
            '--wheel',
            '--offline',
            '--no-config',
            '--no-sources',
            '--no-build-isolation',
            '--python', $PythonPath,
            '--out-dir', $buildOutputRoot,
            $snapshotRoot
        )
        [void] (Invoke-ExternalCommand -FilePath $UvPath -ArgumentList $uvArguments -Description "Build $distribution" -LogPath $buildLogPath)

        $builtWheels = @(Get-ChildItem -LiteralPath $buildOutputRoot -Filter '*.whl' -File)
        if ($builtWheels.Count -ne 1) {
            throw "$distribution must produce exactly one wheel; got $($builtWheels.Count)"
        }

        $wheel = $builtWheels[0]
        $expectedWheelPrefix = '{0}-{1}-' -f (ConvertTo-WheelDistributionComponent -Name $distribution), (ConvertTo-WheelVersionComponent -Version $project.metadata.version)
        if (-not $wheel.Name.StartsWith($expectedWheelPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "$distribution wheel filename does not match pyproject metadata: $($wheel.Name)"
        }

        $wheelMetadata = Get-WheelMetadata -WheelPath $wheel.FullName
        if ($wheelMetadata.normalized_distribution -ne $project.metadata.normalized_distribution -or
            $wheelMetadata.version -ne $project.metadata.version) {
            throw "$distribution wheel METADATA does not match pyproject name/version"
        }
        $sourceEntryPointKeys = @(Get-EntryPointKeys -EntryPoints $project.metadata.entry_points)
        $wheelEntryPointKeys = @(Get-EntryPointKeys -EntryPoints $wheelMetadata.entry_points)
        $missingWheelEntryPoints = @($sourceEntryPointKeys | Where-Object { $wheelEntryPointKeys -notcontains $_ })
        $unexpectedWheelEntryPoints = @($wheelEntryPointKeys | Where-Object { $sourceEntryPointKeys -notcontains $_ })
        if ($missingWheelEntryPoints.Count -gt 0 -or $unexpectedWheelEntryPoints.Count -gt 0) {
            throw "$distribution wheel entry points differ from pyproject declarations"
        }

        $publishedWheelPath = Join-Path $publishDirectory $wheel.Name
        if (Test-Path -LiteralPath $publishedWheelPath) {
            throw "Duplicate wheel filename; refusing to overwrite: $($wheel.Name)"
        }
        [System.IO.File]::Copy($wheel.FullName, $publishedWheelPath, $false)
        $publishedWheel = Get-Item -LiteralPath $publishedWheelPath
        $wheelSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $publishedWheelPath).Hash.ToLowerInvariant()

        [void] $wheelRecords.Add([pscustomobject]@{
            distribution = $distribution
            version = $project.metadata.version
            entry_points = @($wheelMetadata.entry_points | Sort-Object group, name, value)
            source = [pscustomobject]@{
                repository_id = $project.repository.repository_id
                repository_url = $project.repository.repository_url
                relative_path = $project.repository.relative_path
                head = $project.repository.head
                head_timestamp_epoch = $project.repository.head_timestamp_epoch
                dirty = $project.repository.dirty
                repository_dirty = $project.repository.repository_dirty
                digest = $sourceDigest
            }
            filename = $publishedWheel.Name
            size_bytes = [long] $publishedWheel.Length
            sha256 = $wheelSha256
        })
    }
} finally {
    [Environment]::SetEnvironmentVariable('SOURCE_DATE_EPOCH', $previousSourceDateEpoch, 'Process')
    [Environment]::SetEnvironmentVariable('PYTHONHASHSEED', $previousPythonHashSeed, 'Process')
}

$duplicateWheelNames = @($wheelRecords | Group-Object filename | Where-Object Count -gt 1)
if ($wheelRecords.Count -ne 23 -or $duplicateWheelNames.Count -gt 0) {
    throw "Wheelhouse validation failed: $($wheelRecords.Count) wheels and $($duplicateWheelNames.Count) duplicate filenames"
}

$publishedWheelFiles = @(Get-ChildItem -LiteralPath $publishDirectory -Filter '*.whl' -File)
if ($publishedWheelFiles.Count -ne $wheelRecords.Count) {
    throw "Published wheel count differs from manifest: $($publishedWheelFiles.Count) files and $($wheelRecords.Count) records"
}

$manifest = [ordered]@{
    schema_version = 2
    generator = 'scripts/build_integration_wheelhouse.ps1'
    generated_at = [DateTimeOffset]::UtcNow.ToString('o')
    source_date_epoch = $SourceDateEpoch
    artifact_scope = 'plugin-seed-only'
    runtime_complete = $false
    completion_script = 'scripts/complete_integration_wheelhouse.ps1'
    expected_distribution_count = 23
    expected_entry_point_count = 21
    build_environment = [ordered]@{
        mode = 'offline-no-build-isolation-no-sources'
        environment_root = Get-ManifestToolPath -Path $EnvironmentRoot -RepositoryRoot $HostRepositoryRoot
        uv = [ordered]@{
            version = $uvVersion
            path = Get-ManifestToolPath -Path $UvPath -RepositoryRoot $HostRepositoryRoot
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $UvPath).Hash.ToLowerInvariant()
        }
        python = [ordered]@{
            file_version = $pythonFileVersion
            path = Get-ManifestToolPath -Path $PythonPath -RepositoryRoot $HostRepositoryRoot
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $PythonPath).Hash.ToLowerInvariant()
        }
        build_backend = [ordered]@{
            setuptools = $setuptoolsVersion
            wheel = $wheelVersion
        }
        git = [ordered]@{
            version = $gitVersion
            path = Get-ManifestToolPath -Path $GitPath -RepositoryRoot $HostRepositoryRoot
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $GitPath).Hash.ToLowerInvariant()
        }
        powershell = $PSVersionTable.PSVersion.ToString()
        operating_system = [Environment]::OSVersion.VersionString
        generator_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $PSCommandPath).Hash.ToLowerInvariant()
    }
    wheels = @($wheelRecords | Sort-Object distribution)
}

$manifestPath = Join-Path $publishDirectory 'manifest.json'
$manifestJson = $manifest | ConvertTo-Json -Depth 12
[System.IO.File]::WriteAllText($manifestPath, $manifestJson + [Environment]::NewLine, $script:Utf8NoBom)

if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Output directory appeared before publish; refusing to overwrite: $OutputDirectory"
}
[System.IO.Directory]::Move($publishDirectory, $OutputDirectory)

Write-Host "Wheelhouse generated: $OutputDirectory"
Write-Host 'Validated 23 distributions and 21 unique plugin entry points.'
Write-Host 'This is a plugin seed only; run scripts/complete_integration_wheelhouse.ps1 before packaging.'
Write-Host "Build staging retained for audit and not automatically deleted: $StagingDirectory"
