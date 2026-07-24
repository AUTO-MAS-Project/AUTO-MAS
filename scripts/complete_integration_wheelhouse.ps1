[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $PluginWheelhouseDirectory,
    [Parameter(Mandatory = $true)]
    [string] $HostPyProjectPath,
    [Parameter(Mandatory = $true)]
    [string] $UvPath,
    [Parameter(Mandatory = $true)]
    [string] $PythonPath,
    [Parameter(Mandatory = $true)]
    [string] $OutputDirectory,
    [string] $StagingDirectory,
    [string] $DefaultIndex = 'https://pypi.org/simple',
    [string] $TargetPythonVersion = '3.12',
    [ValidateSet('x86_64-pc-windows-msvc')]
    [string] $TargetPlatform = 'x86_64-pc-windows-msvc',
    [string] $ExcludeNewer
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[void] (Add-Type -AssemblyName System.IO.Compression.FileSystem)
[void] (Add-Type -AssemblyName System.Runtime.Serialization)

$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

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
    return $fullPath.StartsWith(
        $fullDirectory + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

function Assert-SafeArtifactFilename {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Filename,
        [Parameter(Mandatory = $true)]
        [string] $Description
    )

    if ([string]::IsNullOrWhiteSpace($Filename) -or
        $Filename -ne $Filename.Trim() -or
        $Filename -eq '.' -or
        $Filename -eq '..' -or
        $Filename.Length -gt 255 -or
        [System.IO.Path]::IsPathRooted($Filename) -or
        $Filename.IndexOfAny([System.IO.Path]::GetInvalidFileNameChars()) -ge 0 -or
        $Filename.Contains([System.IO.Path]::DirectorySeparatorChar) -or
        $Filename.Contains([System.IO.Path]::AltDirectorySeparatorChar) -or
        [System.IO.Path]::GetFileName($Filename) -ne $Filename -or
        $Filename.EndsWith('.', [System.StringComparison]::Ordinal) -or
        $Filename.EndsWith(' ', [System.StringComparison]::Ordinal)) {
        throw "$Description is not a safe filename: $Filename"
    }

    $deviceName = ($Filename -split '\.', 2)[0]
    if ($deviceName -match '^(?i:con|prn|aux|nul|clock\$|conin\$|conout\$|com[0-9]|lpt[0-9])$') {
        throw "$Description uses a reserved Windows device name: $Filename"
    }
    return $Filename
}

function Get-ContainedChildPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Directory,
        [Parameter(Mandatory = $true)]
        [string] $Filename,
        [Parameter(Mandatory = $true)]
        [string] $Description
    )

    $safeFilename = Assert-SafeArtifactFilename -Filename $Filename -Description $Description
    $resolvedPath = [System.IO.Path]::GetFullPath((Join-Path $Directory $safeFilename))
    if (-not (Test-PathWithinDirectory -Path $resolvedPath -Directory $Directory)) {
        throw "$Description escapes its required directory: $Filename"
    }
    return $resolvedPath
}

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string] $FilePath,
        [Parameter(Mandatory = $true)]
        [string[]] $ArgumentList,
        [Parameter(Mandatory = $true)]
        [string] $Description,
        [string] $LogPath,
        [string] $WorkingDirectory,
        [hashtable] $EnvironmentVariables
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $previousEnvironment = @{}
    if ($null -ne $EnvironmentVariables) {
        foreach ($name in $EnvironmentVariables.Keys) {
            $previousEnvironment[[string] $name] = [Environment]::GetEnvironmentVariable(
                [string] $name,
                [EnvironmentVariableTarget]::Process
            )
            [Environment]::SetEnvironmentVariable(
                [string] $name,
                [string] $EnvironmentVariables[$name],
                [EnvironmentVariableTarget]::Process
            )
        }
    }
    try {
        # Windows PowerShell 5.1 reports native stderr as NativeCommandError under
        # Stop. Capture it as ordinary diagnostic text and trust the exit code.
        $ErrorActionPreference = 'Continue'
        $locationPushed = $false
        try {
            if (-not [string]::IsNullOrWhiteSpace($WorkingDirectory)) {
                Push-Location -LiteralPath $WorkingDirectory
                $locationPushed = $true
            }
            $output = @(& $FilePath @ArgumentList 2>&1 | ForEach-Object { $_.ToString() })
            $exitCode = $LASTEXITCODE
        } finally {
            if ($locationPushed) {
                Pop-Location
            }
        }
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
        foreach ($name in $previousEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable(
                [string] $name,
                $previousEnvironment[$name],
                [EnvironmentVariableTarget]::Process
            )
        }
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

function ConvertTo-NormalizedDistributionName {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name
    )

    return [regex]::Replace($Name.Trim().ToLowerInvariant(), '[-_.]+', '-')
}

function ConvertFrom-TomlQuotedString {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Value
    )

    $trimmed = $Value.Trim()
    if ($trimmed.Length -lt 2) {
        throw "Invalid TOML string: $Value"
    }
    if ($trimmed[0] -eq "'" -and $trimmed[$trimmed.Length - 1] -eq "'") {
        return $trimmed.Substring(1, $trimmed.Length - 2)
    }
    if ($trimmed[0] -ne '"' -or $trimmed[$trimmed.Length - 1] -ne '"') {
        throw "Invalid TOML string: $Value"
    }

    $jsonBytes = $script:Utf8NoBom.GetBytes($trimmed)
    $stream = New-Object System.IO.MemoryStream(, $jsonBytes)
    try {
        $serializer = New-Object System.Runtime.Serialization.Json.DataContractJsonSerializer([string])
        return [string] $serializer.ReadObject($stream)
    } finally {
        $stream.Dispose()
    }
}

function Get-HostProjectDependencies {
    param(
        [Parameter(Mandatory = $true)]
        [string] $PyProjectPath
    )

    $section = ''
    $collecting = $false
    $dependencies = New-Object System.Collections.Generic.List[string]
    $quotedStringPattern = '(?<value>"(?:\\.|[^"\\])*"|''[^'']*'')'

    foreach ($line in (Get-Content -Encoding utf8 -LiteralPath $PyProjectPath)) {
        if (-not $collecting -and $line -match '^\s*\[(?<section>[^]]+)\]\s*$') {
            $section = $Matches.section.Trim()
            continue
        }
        if (-not $collecting -and $section -eq 'project' -and $line -match '^\s*dependencies\s*=\s*\[') {
            $collecting = $true
        }
        if (-not $collecting) {
            continue
        }

        foreach ($match in [regex]::Matches($line, $quotedStringPattern)) {
            [void] $dependencies.Add((ConvertFrom-TomlQuotedString -Value $match.Groups['value'].Value))
        }
        if ($line -match '^\s*\]\s*(?:#.*)?$') {
            break
        }
    }

    if (-not $collecting -or $dependencies.Count -eq 0) {
        throw "Cannot parse non-empty [project].dependencies from $PyProjectPath"
    }
    return $dependencies.ToArray()
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
        $metadataEntries = @($archive.Entries | Where-Object { $_.FullName -match '^[^/]+\.dist-info/METADATA$' })
        if ($metadataEntries.Count -ne 1) {
            throw "Wheel must contain exactly one dist-info/METADATA entry: $WheelPath"
        }
        $metadataText = Read-ZipEntryText -Entry $metadataEntries[0]
        $distribution = $null
        $version = $null
        $requirements = New-Object System.Collections.Generic.List[string]
        foreach ($line in ($metadataText -split "`r?`n")) {
            if ($null -eq $distribution -and $line -match '^Name:\s*(?<value>.+?)\s*$') {
                $distribution = $Matches.value
            } elseif ($null -eq $version -and $line -match '^Version:\s*(?<value>.+?)\s*$') {
                $version = $Matches.value
            } elseif ($line -match '^Requires-Dist:\s*(?<value>.+?)\s*$') {
                [void] $requirements.Add($Matches.value)
            }
        }
        if ([string]::IsNullOrWhiteSpace($distribution) -or [string]::IsNullOrWhiteSpace($version)) {
            throw "Wheel METADATA is missing Name or Version: $WheelPath"
        }

        $entryPoints = New-Object System.Collections.Generic.List[object]
        $entryPointEntries = @($archive.Entries | Where-Object { $_.FullName -match '^[^/]+\.dist-info/entry_points\.txt$' })
        if ($entryPointEntries.Count -gt 1) {
            throw "Wheel contains multiple entry_points.txt files: $WheelPath"
        }
        if ($entryPointEntries.Count -eq 1) {
            $group = $null
            foreach ($line in ((Read-ZipEntryText -Entry $entryPointEntries[0]) -split "`r?`n")) {
                $trimmed = $line.Trim()
                if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith('#')) {
                    continue
                }
                if ($trimmed -match '^\[(?<group>[^]]+)\]$') {
                    $group = $Matches.group.Trim()
                    continue
                }
                if ($null -eq $group -or $trimmed -notmatch '^(?<name>[^=]+?)\s*=\s*(?<value>.+?)\s*$') {
                    throw "Cannot parse wheel entry point '$trimmed' in $WheelPath"
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
            requires_dist = $requirements.ToArray()
            entry_points = $entryPoints.ToArray()
        }
    } finally {
        $archive.Dispose()
    }
}

function Get-RequirementName {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Requirement
    )

    if ($Requirement -notmatch '^\s*(?<name>[A-Za-z0-9][A-Za-z0-9._-]*)') {
        throw "Cannot parse requirement name: $Requirement"
    }
    return $Matches.name
}

function ConvertTo-ComparableVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Version
    )

    $normalized = $Version.Trim().ToLowerInvariant() -replace '^v', ''
    if ($normalized -notmatch '^(?<release>\d+(?:\.\d+)*)(?<suffix>.*)$') {
        throw "Unsupported version: $Version"
    }
    $release = @($Matches.release.Split('.') | ForEach-Object { [int] $_ })
    $suffix = $Matches.suffix.TrimStart('-', '_', '.')
    $precedence = 3
    $preNumber = 0
    $postNumber = 0
    if ($suffix -match '^(?<label>a|alpha|b|beta|rc|c|pre|preview)[-_.]?(?<number>\d*)') {
        $label = $Matches.label
        if ($label -eq 'a' -or $label -eq 'alpha') {
            $precedence = 0
        } elseif ($label -eq 'b' -or $label -eq 'beta') {
            $precedence = 1
        } else {
            $precedence = 2
        }
        if ($Matches.number) {
            $preNumber = [int] $Matches.number
        }
    }
    if ($suffix -match '(?:post|rev|r)[-_.]?(?<number>\d+)') {
        $postNumber = [int] $Matches.number
    }
    return [pscustomobject]@{
        release = $release
        precedence = $precedence
        pre_number = $preNumber
        post_number = $postNumber
    }
}

function Compare-PackageVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Left,
        [Parameter(Mandatory = $true)]
        [string] $Right
    )

    $leftVersion = ConvertTo-ComparableVersion -Version $Left
    $rightVersion = ConvertTo-ComparableVersion -Version $Right
    $length = [Math]::Max($leftVersion.release.Count, $rightVersion.release.Count)
    for ($index = 0; $index -lt $length; $index++) {
        $leftPart = if ($index -lt $leftVersion.release.Count) { $leftVersion.release[$index] } else { 0 }
        $rightPart = if ($index -lt $rightVersion.release.Count) { $rightVersion.release[$index] } else { 0 }
        if ($leftPart -gt $rightPart) { return 1 }
        if ($leftPart -lt $rightPart) { return -1 }
    }
    foreach ($property in @('precedence', 'pre_number', 'post_number')) {
        if ($leftVersion.$property -gt $rightVersion.$property) { return 1 }
        if ($leftVersion.$property -lt $rightVersion.$property) { return -1 }
    }
    return 0
}

function Test-RequirementAllowsVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Requirement,
        [Parameter(Mandatory = $true)]
        [string] $Version
    )

    $withoutMarker = ($Requirement -split ';', 2)[0].Trim()
    if ($withoutMarker -notmatch '^\s*[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[^]]+\])?\s*(?<specifier>.*)$') {
        throw "Cannot parse local requirement: $Requirement"
    }
    $specifier = $Matches.specifier.Trim()
    if (-not $specifier) {
        return $true
    }
    if ($specifier.StartsWith('@')) {
        throw "Direct references are not allowed for local plugin dependencies: $Requirement"
    }

    foreach ($clause in ($specifier -split ',')) {
        $trimmed = $clause.Trim()
        if ($trimmed -notmatch '^(?<operator>===|==|!=|>=|<=|>|<)\s*(?<version>[^\s*]+)$') {
            throw "Unsupported local plugin version clause: $trimmed"
        }
        $comparison = Compare-PackageVersion -Left $Version -Right $Matches.version
        $allowed = switch ($Matches.operator) {
            '===' { $Version -eq $Matches.version }
            '==' { $comparison -eq 0 }
            '!=' { $comparison -ne 0 }
            '>=' { $comparison -ge 0 }
            '<=' { $comparison -le 0 }
            '>' { $comparison -gt 0 }
            '<' { $comparison -lt 0 }
        }
        if (-not $allowed) {
            return $false
        }
    }
    return $true
}

function Get-PyLockPackages {
    param(
        [Parameter(Mandatory = $true)]
        [string] $LockPath
    )

    # uv emits standards-compliant PEP 751 TOML with inline wheel arrays.  Use
    # the pinned CPython 3.12 stdlib parser instead of maintaining a partial
    # line-oriented TOML parser that would silently miss valid wheel records.
    $tomlReader = @'
import json
from pathlib import Path
import posixpath
import sys
import tomllib
from urllib.parse import unquote, urlsplit

lock_path = Path(sys.argv[1])
with lock_path.open('rb') as stream:
    source = tomllib.load(stream)

packages = []

def locked_artifact(record):
    if not isinstance(record, dict):
        return None
    hashes = record.get('hashes', {})
    if not isinstance(hashes, dict):
        hashes = {}
    url = record.get('url')
    name = record.get('name')
    if not name and isinstance(url, str):
        parsed_url = urlsplit(url)
        if parsed_url.scheme.lower() == 'https' and parsed_url.netloc and not parsed_url.username:
            name = posixpath.basename(unquote(parsed_url.path))
    return {
        'name': name,
        'url': url,
        'size': record.get('size'),
        'sha256': hashes.get('sha256'),
    }

for package in source.get('packages', []):
    wheels = []
    for wheel in package.get('wheels', []):
        wheels.append(locked_artifact(wheel))
    packages.append({
        'name': package.get('name'),
        'version': package.get('version'),
        'wheels': wheels,
        'sdist': locked_artifact(package.get('sdist')),
    })

print(json.dumps({
    'lock_version': source.get('lock-version'),
    'packages': packages,
}, separators=(',', ':')))
'@
    $jsonOutput = @(
        Invoke-ExternalCommand `
            -FilePath $PythonPath `
            -ArgumentList @('-I', '-c', $tomlReader, $LockPath) `
            -Description 'Parse standards-compliant pylock.toml'
    )
    $jsonText = ($jsonOutput -join [Environment]::NewLine).Trim()
    if ([string]::IsNullOrWhiteSpace($jsonText)) {
        throw "Python TOML parser returned no pylock data: $LockPath"
    }
    try {
        $parsed = $jsonText | ConvertFrom-Json
    } catch {
        throw "Cannot decode parsed pylock data from ${LockPath}: $($_.Exception.Message)"
    }
    if ([string] $parsed.lock_version -ne '1.0') {
        throw "Unsupported pylock version $($parsed.lock_version) in $LockPath"
    }

    $packages = @($parsed.packages | ForEach-Object {
        $name = [string] $_.name
        $version = [string] $_.version
        if ([string]::IsNullOrWhiteSpace($name) -or [string]::IsNullOrWhiteSpace($version)) {
            throw "pylock package is missing name/version in $LockPath"
        }
        [pscustomobject]@{
            name = $name
            normalized_name = ConvertTo-NormalizedDistributionName -Name $name
            version = $version
            wheels = @($_.wheels)
            sdist = $_.sdist
        }
    })
    $duplicates = @($packages | Group-Object normalized_name | Where-Object Count -gt 1)
    if ($duplicates.Count -gt 0) {
        throw "Target-specific pylock contains duplicate package names: $(($duplicates.Name | Sort-Object) -join ', ')"
    }
    return $packages
}

function Get-WheelCompatibilityScore {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Filename
    )

    if (-not $Filename.EndsWith('.whl', [System.StringComparison]::OrdinalIgnoreCase)) {
        return -1
    }
    $parts = $Filename.Substring(0, $Filename.Length - 4).Split('-')
    if ($parts.Count -lt 5) {
        return -1
    }
    $pythonTags = $parts[$parts.Count - 3].Split('.')
    $abiTags = $parts[$parts.Count - 2].Split('.')
    $platformTags = $parts[$parts.Count - 1].Split('.')
    $best = -1

    foreach ($platformTag in $platformTags) {
        $platformScore = if ($platformTag -eq 'win_amd64') { 100 } elseif ($platformTag -eq 'any') { 20 } else { -1 }
        if ($platformScore -lt 0) { continue }
        foreach ($pythonTag in $pythonTags) {
            foreach ($abiTag in $abiTags) {
                $pythonScore = -1
                $abiScore = -1
                if ($pythonTag -eq 'cp312') {
                    $pythonScore = 60
                    if ($abiTag -eq 'cp312') { $abiScore = 40 }
                    elseif ($abiTag -eq 'abi3') { $abiScore = 30 }
                    elseif ($abiTag -eq 'none') { $abiScore = 20 }
                } elseif ($pythonTag -match '^cp(?<major>3)(?<minor>\d+)$' -and $abiTag -eq 'abi3') {
                    $minor = [int] $Matches.minor
                    if ($minor -le 12) {
                        $pythonScore = 30 + $minor
                        $abiScore = 30
                    }
                } elseif ($pythonTag -eq 'py312' -and $abiTag -eq 'none') {
                    $pythonScore = 50
                    $abiScore = 20
                } elseif (($pythonTag -eq 'py3' -or $pythonTag -eq 'py2.py3') -and $abiTag -eq 'none') {
                    $pythonScore = 30
                    $abiScore = 20
                }
                if ($pythonScore -ge 0 -and $abiScore -ge 0) {
                    $best = [Math]::Max($best, $platformScore + $pythonScore + $abiScore)
                }
            }
        }
    }
    return $best
}

function ConvertTo-LockedSourceArtifact {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Package,
        [Parameter(Mandatory = $true)]
        [object] $Record,
        [Parameter(Mandatory = $true)]
        [ValidateSet('wheel', 'sdist')]
        [string] $ArtifactType
    )

    if ($null -eq $Record -or
        [string]::IsNullOrWhiteSpace([string] $Record.name) -or
        [string]::IsNullOrWhiteSpace([string] $Record.url) -or
        $null -eq $Record.size -or
        [string]::IsNullOrWhiteSpace([string] $Record.sha256)) {
        throw "Incomplete locked $ArtifactType metadata for $($Package.name) $($Package.version)"
    }

    $filename = Assert-SafeArtifactFilename `
        -Filename ([string] $Record.name) `
        -Description "Locked $ArtifactType filename for $($Package.name) $($Package.version)"
    if ($ArtifactType -eq 'wheel') {
        if (-not $filename.EndsWith('.whl', [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Locked wheel has an invalid extension: $filename"
        }
    } elseif (-not ($filename.EndsWith('.tar.gz', [System.StringComparison]::OrdinalIgnoreCase) -or
        $filename.EndsWith('.zip', [System.StringComparison]::OrdinalIgnoreCase))) {
        throw "Locked sdist must be a .tar.gz or .zip source archive: $filename"
    }

    [Uri] $uri = $null
    if (-not [Uri]::TryCreate([string] $Record.url, [UriKind]::Absolute, [ref] $uri) -or
        $uri.Scheme -ne 'https' -or
        [string]::IsNullOrWhiteSpace($uri.Host) -or
        -not [string]::IsNullOrEmpty($uri.UserInfo)) {
        throw "Only absolute HTTPS registry artifact URLs without credentials are allowed: $($Record.url)"
    }
    $sizeBytes = [long] $Record.size
    $sha256 = ([string] $Record.sha256).ToLowerInvariant()
    if ($sizeBytes -le 0 -or $sha256 -notmatch '^[0-9a-f]{64}$') {
        throw "Locked $ArtifactType has an invalid size or SHA-256 for $($Package.name) $($Package.version)"
    }

    return [pscustomobject]@{
        distribution = $Package.name
        normalized_distribution = $Package.normalized_name
        version = $Package.version
        source_kind = $ArtifactType
        source_filename = $filename
        source_url = $uri.AbsoluteUri
        source_size_bytes = $sizeBytes
        source_sha256 = $sha256
    }
}

function Select-CompatibleLockedArtifact {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Package
    )

    $candidates = New-Object System.Collections.Generic.List[object]
    foreach ($wheel in $Package.wheels) {
        $artifact = ConvertTo-LockedSourceArtifact -Package $Package -Record $wheel -ArtifactType 'wheel'
        $score = Get-WheelCompatibilityScore -Filename $artifact.source_filename
        if ($score -ge 0) {
            [void] $candidates.Add([pscustomobject]@{ score = $score; artifact = $artifact })
        }
    }
    if ($candidates.Count -gt 0) {
        $candidateArray = $candidates.ToArray()
        $bestScore = ($candidateArray | Measure-Object score -Maximum).Maximum
        $best = @($candidateArray | Where-Object score -eq $bestScore)
        if ($best.Count -ne 1) {
            throw "Ambiguous compatible wheels for $($Package.name) $($Package.version): $((@($best | ForEach-Object { $_.artifact.source_filename }) | Sort-Object) -join ', ')"
        }
        return $best[0].artifact
    }

    if ($null -eq $Package.sdist) {
        throw "No CPython 3.12 Windows x64 wheel or complete sdist is locked for $($Package.name) $($Package.version)"
    }
    return ConvertTo-LockedSourceArtifact -Package $Package -Record $Package.sdist -ArtifactType 'sdist'
}

function Save-LockedSourceArtifact {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Artifact,
        [Parameter(Mandatory = $true)]
        [string] $DestinationDirectory
    )

    $filename = Assert-SafeArtifactFilename `
        -Filename ([string] $Artifact.source_filename) `
        -Description "Locked $($Artifact.source_kind) download filename"
    [Uri] $uri = $null
    if (-not [Uri]::TryCreate([string] $Artifact.source_url, [UriKind]::Absolute, [ref] $uri) -or
        $uri.Scheme -ne 'https' -or
        [string]::IsNullOrWhiteSpace($uri.Host) -or
        -not [string]::IsNullOrEmpty($uri.UserInfo)) {
        throw "Only absolute HTTPS registry artifact URLs without credentials are allowed: $($Artifact.source_url)"
    }
    $destinationPath = Get-ContainedChildPath `
        -Directory $DestinationDirectory `
        -Filename $filename `
        -Description 'Locked artifact download path'
    if (Test-Path -LiteralPath $destinationPath) {
        throw "Download destination already exists; refusing to overwrite: $destinationPath"
    }

    $successfulAttemptPath = $null
    $failureMessages = @()
    $maximumAttempts = 4
    for ($attempt = 1; $attempt -le $maximumAttempts; $attempt++) {
        $attemptFilename = 'download-{0}.part' -f ([Guid]::NewGuid().ToString('N'))
        $attemptPath = Get-ContainedChildPath `
            -Directory $DestinationDirectory `
            -Filename $attemptFilename `
            -Description 'Locked artifact download attempt path'
        $requestArguments = @{
            Uri = $uri
            OutFile = $attemptPath
            UserAgent = 'AUTO-MAS reproducible wheelhouse builder'
            TimeoutSec = 120
        }
        if ($PSVersionTable.PSVersion.Major -lt 6) {
            $requestArguments.UseBasicParsing = $true
        }

        try {
            [void] (Invoke-WebRequest @requestArguments)
            $file = Get-Item -LiteralPath $attemptPath
            if ([long] $file.Length -ne [long] $Artifact.source_size_bytes) {
                throw "size mismatch (expected $($Artifact.source_size_bytes), got $($file.Length))"
            }
            $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $attemptPath).Hash.ToLowerInvariant()
            if ($actualHash -ne $Artifact.source_sha256) {
                throw "SHA-256 mismatch (expected $($Artifact.source_sha256), got $actualHash)"
            }
            $successfulAttemptPath = $attemptPath
            break
        } catch {
            $message = "attempt $attempt/$maximumAttempts failed: $($_.Exception.Message)"
            $failureMessages += $message
            Write-Warning "Locked artifact download $message"
            if ($attempt -lt $maximumAttempts) {
                Start-Sleep -Seconds ([Math]::Pow(2, $attempt))
            }
        }
    }

    if ([string]::IsNullOrWhiteSpace($successfulAttemptPath)) {
        throw "Cannot download verified $($Artifact.source_kind) $filename after $maximumAttempts attempts: $($failureMessages -join '; ')"
    }
    if (Test-Path -LiteralPath $destinationPath) {
        throw "Download destination appeared during transfer; refusing to overwrite: $destinationPath"
    }
    Move-Item -LiteralPath $successfulAttemptPath -Destination $destinationPath
    return $destinationPath
}

function Build-WheelFromLockedSdist {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Artifact,
        [Parameter(Mandatory = $true)]
        [string] $DownloadedSourcePath,
        [Parameter(Mandatory = $true)]
        [string] $DownloadDirectory,
        [Parameter(Mandatory = $true)]
        [string] $StagingRoot,
        [Parameter(Mandatory = $true)]
        [long] $SourceDateEpoch
    )

    if ($Artifact.source_kind -ne 'sdist') {
        throw "Cannot build a non-sdist locked artifact: $($Artifact.source_filename)"
    }
    $resolvedSourcePath = [System.IO.Path]::GetFullPath($DownloadedSourcePath)
    if (-not (Test-PathWithinDirectory -Path $resolvedSourcePath -Directory $DownloadDirectory)) {
        throw "Locked sdist source escapes the download directory: $DownloadedSourcePath"
    }
    Assert-ExistingFile -Path $resolvedSourcePath -Description 'Verified locked sdist'

    # Keep this path deliberately short. pip appends an ephemeral cache and a
    # hashed wheel path that can otherwise exceed the legacy Windows MAX_PATH.
    $buildDirectoryName = 'b{0}' -f ([Guid]::NewGuid().ToString('N').Substring(0, 12))
    $buildDirectory = Get-ContainedChildPath `
        -Directory $StagingRoot `
        -Filename $buildDirectoryName `
        -Description 'sdist build directory'
    if (Test-Path -LiteralPath $buildDirectory) {
        throw "sdist build directory already exists; refusing to reuse it: $buildDirectory"
    }
    [void] (New-Item -ItemType Directory -Path $buildDirectory)
    $wheelOutputDirectory = Get-ContainedChildPath `
        -Directory $buildDirectory `
        -Filename 'w' `
        -Description 'sdist wheel output directory'
    [void] (New-Item -ItemType Directory -Path $wheelOutputDirectory)
    $systemTempDirectory = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $pipTempDirectory = Get-ContainedChildPath `
        -Directory $systemTempDirectory `
        -Filename ('p{0}' -f ([Guid]::NewGuid().ToString('N').Substring(0, 12))) `
        -Description 'sdist pip short temporary directory'
    if (Test-Path -LiteralPath $pipTempDirectory) {
        throw "sdist pip temporary directory already exists; refusing to reuse it: $pipTempDirectory"
    }
    [void] (New-Item -ItemType Directory -Path $pipTempDirectory)
    $buildLogPath = Get-ContainedChildPath `
        -Directory $buildDirectory `
        -Filename 'build.log' `
        -Description 'sdist build log'

    $pipArguments = @(
        '-m', 'pip', 'wheel',
        '--no-deps',
        '--no-build-isolation',
        '--no-index',
        '--no-cache-dir',
        '--wheel-dir', $wheelOutputDirectory,
        $resolvedSourcePath
    )
    [void] (Invoke-ExternalCommand `
        -FilePath $PythonPath `
        -ArgumentList $pipArguments `
        -Description "Build locked sdist $($Artifact.distribution) $($Artifact.version)" `
        -LogPath $buildLogPath `
        -WorkingDirectory $buildDirectory `
        -EnvironmentVariables @{
            SOURCE_DATE_EPOCH = [string] $SourceDateEpoch
            PYTHONHASHSEED = '0'
            PIP_DISABLE_PIP_VERSION_CHECK = '1'
            PIP_NO_CACHE_DIR = '1'
            PIP_NO_INDEX = '1'
            TEMP = $pipTempDirectory
            TMP = $pipTempDirectory
        })

    $builtFiles = @(Get-ChildItem -LiteralPath $wheelOutputDirectory -File)
    if ($builtFiles.Count -ne 1 -or
        -not $builtFiles[0].Name.EndsWith('.whl', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "sdist build must produce exactly one wheel for $($Artifact.distribution) $($Artifact.version)"
    }
    $builtFilename = Assert-SafeArtifactFilename `
        -Filename $builtFiles[0].Name `
        -Description 'Built wheel filename'
    $builtWheelPath = Get-ContainedChildPath `
        -Directory $wheelOutputDirectory `
        -Filename $builtFilename `
        -Description 'Built wheel path'
    if ((Get-WheelCompatibilityScore -Filename $builtFilename) -lt 0) {
        throw "sdist produced an incompatible CPython 3.12 Windows x64 wheel: $builtFilename"
    }
    $metadata = Get-WheelMetadata -WheelPath $builtWheelPath
    if ($metadata.normalized_distribution -ne $Artifact.normalized_distribution -or
        $metadata.version -ne $Artifact.version) {
        throw "sdist-built wheel METADATA does not match the lock: $builtFilename"
    }
    return $builtWheelPath
}

function Get-FinalRuntimeWheelArtifact {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Artifact,
        [Parameter(Mandatory = $true)]
        [string] $DownloadedSourcePath,
        [Parameter(Mandatory = $true)]
        [string] $DownloadDirectory,
        [Parameter(Mandatory = $true)]
        [string] $StagingRoot,
        [Parameter(Mandatory = $true)]
        [long] $SourceDateEpoch
    )

    if ($Artifact.source_kind -ne 'wheel' -and $Artifact.source_kind -ne 'sdist') {
        throw "Unknown locked artifact type: $($Artifact.source_kind)"
    }
    $resolvedDownloadedSourcePath = [System.IO.Path]::GetFullPath($DownloadedSourcePath)
    if (-not (Test-PathWithinDirectory -Path $resolvedDownloadedSourcePath -Directory $DownloadDirectory)) {
        throw "Locked artifact source escapes the download directory: $DownloadedSourcePath"
    }
    $wheelPath = $resolvedDownloadedSourcePath
    if ($Artifact.source_kind -eq 'sdist') {
        $wheelPath = Build-WheelFromLockedSdist `
            -Artifact $Artifact `
            -DownloadedSourcePath $DownloadedSourcePath `
            -DownloadDirectory $DownloadDirectory `
            -StagingRoot $StagingRoot `
            -SourceDateEpoch $SourceDateEpoch
    }
    Assert-ExistingFile -Path $wheelPath -Description 'Final runtime wheel candidate'
    $wheelFile = Get-Item -LiteralPath $wheelPath
    $wheelFilename = Assert-SafeArtifactFilename -Filename $wheelFile.Name -Description 'Final runtime wheel filename'
    if ((Get-WheelCompatibilityScore -Filename $wheelFilename) -lt 0) {
        throw "Final runtime artifact is not a compatible CPython 3.12 Windows x64 wheel: $wheelFilename"
    }
    $metadata = Get-WheelMetadata -WheelPath $wheelFile.FullName
    if ($metadata.normalized_distribution -ne $Artifact.normalized_distribution -or
        $metadata.version -ne $Artifact.version) {
        throw "Final runtime wheel METADATA does not match the lock: $wheelFilename"
    }
    $finalWheelHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $wheelFile.FullName).Hash.ToLowerInvariant()
    if ($Artifact.source_kind -eq 'wheel' -and
        (([long] $wheelFile.Length) -ne ([long] $Artifact.source_size_bytes) -or
        $finalWheelHash -ne $Artifact.source_sha256)) {
        throw "Downloaded locked wheel changed before publication: $wheelFilename"
    }

    $sourceProvenance = [ordered]@{
        lock = 'pylock.combined.toml'
        artifact_type = $Artifact.source_kind
        filename = $Artifact.source_filename
        url = $Artifact.source_url
        size_bytes = [long] $Artifact.source_size_bytes
        sha256 = $Artifact.source_sha256
    }
    if ($Artifact.source_kind -eq 'sdist') {
        $sourceProvenance['build'] = [ordered]@{
            python = 'CPython 3.12'
            command = 'python -m pip wheel --no-deps --no-build-isolation --no-index --no-cache-dir'
            source_date_epoch = $SourceDateEpoch
            pythonhashseed = '0'
        }
    }
    return [pscustomobject]@{
        distribution = $metadata.distribution
        normalized_distribution = $metadata.normalized_distribution
        version = $metadata.version
        filename = $wheelFilename
        size_bytes = [long] $wheelFile.Length
        sha256 = $finalWheelHash
        wheel_path = $wheelFile.FullName
        source = [pscustomobject] $sourceProvenance
    }
}

function New-LockEntry {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Artifact,
        [Parameter(Mandatory = $true)]
        [string] $Scope
    )

    return [pscustomobject]@{
        distribution = $Artifact.distribution
        version = $Artifact.version
        scope = $Scope
        filename = $Artifact.filename
        size_bytes = [long] $Artifact.size_bytes
        sha256 = $Artifact.sha256
        source = $Artifact.source
    }
}

$PluginWheelhouseDirectory = Get-FullPath -Path $PluginWheelhouseDirectory
$HostPyProjectPath = Get-FullPath -Path $HostPyProjectPath
$UvPath = Get-FullPath -Path $UvPath
$PythonPath = Get-FullPath -Path $PythonPath
$OutputDirectory = Get-FullPath -Path $OutputDirectory
Assert-ExistingDirectory -Path $PluginWheelhouseDirectory -Description 'Plugin seed wheelhouse'
Assert-ExistingFile -Path $HostPyProjectPath -Description 'Host pyproject.toml'
Assert-ExistingFile -Path $UvPath -Description 'uv.exe'
Assert-ExistingFile -Path $PythonPath -Description 'Python interpreter'
if ($TargetPythonVersion -ne '3.12') {
    throw "This deterministic compatibility contract only supports CPython 3.12; got $TargetPythonVersion"
}
if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Output directory already exists; refusing to overwrite: $OutputDirectory"
}

$runId = '{0}-{1}' -f ([DateTimeOffset]::UtcNow.ToString('yyyyMMdd-HHmmss')), ([Guid]::NewGuid().ToString('N'))
if ([string]::IsNullOrWhiteSpace($StagingDirectory)) {
    $StagingDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ('a{0}' -f ([Guid]::NewGuid().ToString('N').Substring(0, 12)))
}
$StagingDirectory = Get-FullPath -Path $StagingDirectory
if (Test-Path -LiteralPath $StagingDirectory) {
    throw "Staging directory already exists; refusing to overwrite: $StagingDirectory"
}
if ((Test-PathWithinDirectory -Path $OutputDirectory -Directory $PluginWheelhouseDirectory) -or
    (Test-PathWithinDirectory -Path $PluginWheelhouseDirectory -Directory $OutputDirectory) -or
    (Test-PathWithinDirectory -Path $StagingDirectory -Directory $PluginWheelhouseDirectory) -or
    (Test-PathWithinDirectory -Path $PluginWheelhouseDirectory -Directory $StagingDirectory) -or
    (Test-PathWithinDirectory -Path $StagingDirectory -Directory $OutputDirectory) -or
    (Test-PathWithinDirectory -Path $OutputDirectory -Directory $StagingDirectory)) {
    throw 'Plugin seed, output, and staging directories must not overlap'
}

$defaultIndexUri = [Uri] $DefaultIndex
if ($defaultIndexUri.Scheme -ne 'https' -or -not [string]::IsNullOrEmpty($defaultIndexUri.UserInfo)) {
    throw "Default package index must use HTTPS: $DefaultIndex"
}
if (-not [string]::IsNullOrWhiteSpace($ExcludeNewer)) {
    $parsedExcludeNewer = [DateTimeOffset]::MinValue
    if (-not [DateTimeOffset]::TryParse($ExcludeNewer, [ref] $parsedExcludeNewer)) {
        throw "ExcludeNewer is not a valid RFC 3339 timestamp: $ExcludeNewer"
    }
    $ExcludeNewer = $parsedExcludeNewer.ToUniversalTime().ToString('o')
}

$outputParent = Split-Path -Parent $OutputDirectory
if (-not (Test-Path -LiteralPath $outputParent -PathType Container)) {
    [void] (New-Item -ItemType Directory -Path $outputParent)
}
$publishDirectory = Join-Path $outputParent ('.{0}.publish-{1}' -f (Split-Path -Leaf $OutputDirectory), $runId)
if (Test-Path -LiteralPath $publishDirectory) {
    throw "Publish staging directory already exists: $publishDirectory"
}
[void] (New-Item -ItemType Directory -Path $StagingDirectory)
[void] (New-Item -ItemType Directory -Path $publishDirectory)
$downloadDirectory = Join-Path $StagingDirectory 'downloaded-wheels'
[void] (New-Item -ItemType Directory -Path $downloadDirectory)

$seedManifestPath = Join-Path $PluginWheelhouseDirectory 'manifest.json'
Assert-ExistingFile -Path $seedManifestPath -Description 'Plugin seed manifest'
$seedManifest = Get-Content -Raw -Encoding utf8 -LiteralPath $seedManifestPath | ConvertFrom-Json
if ([int] $seedManifest.schema_version -ne 2 -or
    [string] $seedManifest.artifact_scope -ne 'plugin-seed-only' -or
    [bool] $seedManifest.runtime_complete -ne $false -or
    [int] $seedManifest.expected_distribution_count -ne 23 -or
    [int] $seedManifest.expected_entry_point_count -ne 21) {
    throw 'Plugin seed manifest does not declare the required schema 2 / 23 distributions / 21 entry points contract'
}
if ($null -eq $seedManifest.wheels -or @($seedManifest.wheels).Count -ne 23) {
    throw 'Plugin seed manifest must contain exactly 23 wheels'
}
$sourceDateEpoch = [long] $seedManifest.source_date_epoch
if ($sourceDateEpoch -le 0) {
    throw 'Plugin seed manifest must provide a positive source_date_epoch for reproducible sdist wheel builds'
}
if ([string]::IsNullOrWhiteSpace($ExcludeNewer)) {
    $ExcludeNewer = [DateTimeOffset]::FromUnixTimeSeconds($sourceDateEpoch).ToUniversalTime().ToString('o')
}

$pluginRecords = New-Object System.Collections.Generic.List[object]
$pluginByName = @{}
$seedDeclaredFilenames = New-Object System.Collections.Generic.HashSet[string]([System.StringComparer]::OrdinalIgnoreCase)
$pluginEntryPointKeys = New-Object System.Collections.Generic.HashSet[string]([System.StringComparer]::Ordinal)
foreach ($record in @($seedManifest.wheels)) {
    $recordFilename = Assert-SafeArtifactFilename `
        -Filename ([string] $record.filename) `
        -Description 'Plugin seed manifest wheel filename'
    if (-not $recordFilename.EndsWith('.whl', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Plugin seed manifest contains an invalid wheel filename'
    }
    if (-not $seedDeclaredFilenames.Add($recordFilename)) {
        throw "Plugin seed manifest contains a duplicate wheel: $recordFilename"
    }
    $sourceWheelPath = Get-ContainedChildPath `
        -Directory $PluginWheelhouseDirectory `
        -Filename $recordFilename `
        -Description 'Plugin seed wheel source path'
    Assert-ExistingFile -Path $sourceWheelPath -Description 'Plugin seed wheel'
    $sourceFile = Get-Item -LiteralPath $sourceWheelPath
    $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceWheelPath).Hash.ToLowerInvariant()
    if ([long] $sourceFile.Length -ne [long] $record.size_bytes -or $sourceHash -ne ([string] $record.sha256).ToLowerInvariant()) {
        throw "Plugin seed wheel does not match manifest: $($record.filename)"
    }
    $metadata = Get-WheelMetadata -WheelPath $sourceWheelPath
    if ($pluginByName.ContainsKey($metadata.normalized_distribution)) {
        throw "Plugin seed contains duplicate distribution: $($metadata.distribution)"
    }
    if ([string] $record.version -ne $metadata.version -or
        (ConvertTo-NormalizedDistributionName -Name ([string] $record.distribution)) -ne $metadata.normalized_distribution) {
        throw "Plugin seed metadata mismatch: $($record.filename)"
    }
    foreach ($entryPoint in $metadata.entry_points) {
        if ($entryPoint.group -eq 'auto_mas.plugins' -or $entryPoint.group -eq 'automas.plugins') {
            $key = '{0}|{1}' -f $entryPoint.group, $entryPoint.name
            if (-not $pluginEntryPointKeys.Add($key)) {
                throw "Duplicate plugin entry point: $key"
            }
        }
    }
    $publishedPath = Get-ContainedChildPath `
        -Directory $publishDirectory `
        -Filename $recordFilename `
        -Description 'Plugin seed wheel publish path'
    [System.IO.File]::Copy($sourceWheelPath, $publishedPath, $false)
    $pluginRecord = [pscustomobject]@{
        distribution = $metadata.distribution
        normalized_distribution = $metadata.normalized_distribution
        version = $metadata.version
        filename = $recordFilename
        size_bytes = [long] $record.size_bytes
        sha256 = ([string] $record.sha256).ToLowerInvariant()
        requires_dist = @($metadata.requires_dist)
        entry_points = @($metadata.entry_points)
        seed_record = $record
    }
    $pluginByName[$metadata.normalized_distribution] = $pluginRecord
    [void] $pluginRecords.Add($pluginRecord)
}

$actualSeedWheelFiles = @(Get-ChildItem -LiteralPath $PluginWheelhouseDirectory -File -Filter '*.whl')
if ($actualSeedWheelFiles.Count -ne 23 -or $pluginEntryPointKeys.Count -ne 21) {
    throw "Plugin seed must contain exactly 23 wheels and 21 plugin entry points; got $($actualSeedWheelFiles.Count) and $($pluginEntryPointKeys.Count)"
}
foreach ($wheelFile in $actualSeedWheelFiles) {
    if (-not $seedDeclaredFilenames.Contains($wheelFile.Name)) {
        throw "Plugin seed contains an undeclared wheel: $($wheelFile.Name)"
    }
}

$hostDependencies = @(Get-HostProjectDependencies -PyProjectPath $HostPyProjectPath)
foreach ($dependency in $hostDependencies) {
    $withoutMarker = ($dependency -split ';', 2)[0].Trim()
    if ($withoutMarker -notmatch '^\s*[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[^]]+\])?\s*==\s*[^\s]+$') {
        throw "Host direct dependency is not exactly pinned with ==: $dependency"
    }
}

$combinedRequirements = New-Object System.Collections.Generic.HashSet[string]([System.StringComparer]::Ordinal)
foreach ($dependency in $hostDependencies) {
    [void] $combinedRequirements.Add($dependency)
}
foreach ($plugin in $pluginRecords) {
    foreach ($requirement in $plugin.requires_dist) {
        $requirementName = Get-RequirementName -Requirement $requirement
        $normalizedRequirementName = ConvertTo-NormalizedDistributionName -Name $requirementName
        if ($pluginByName.ContainsKey($normalizedRequirementName)) {
            $localPlugin = $pluginByName[$normalizedRequirementName]
            if (-not (Test-RequirementAllowsVersion -Requirement $requirement -Version $localPlugin.version)) {
                throw "$($plugin.distribution) requires incompatible local plugin $requirement; bundled version is $($localPlugin.version)"
            }
        } else {
            [void] $combinedRequirements.Add($requirement)
        }
    }
}

$hostInputPath = Join-Path $StagingDirectory 'host-runtime.in'
$combinedInputPath = Join-Path $StagingDirectory 'combined-runtime.in'
[System.IO.File]::WriteAllLines($hostInputPath, @($hostDependencies | Sort-Object), $script:Utf8NoBom)
[System.IO.File]::WriteAllLines($combinedInputPath, @($combinedRequirements | Sort-Object), $script:Utf8NoBom)
$hostPyLockPath = Join-Path $StagingDirectory 'pylock.host.toml'
$combinedPyLockPath = Join-Path $StagingDirectory 'pylock.combined.toml'

$commonCompileArguments = @(
    '--format', 'pylock.toml',
    '--python', $PythonPath,
    '--python-version', $TargetPythonVersion,
    '--python-platform', $TargetPlatform,
    '--default-index', $DefaultIndex,
    '--exclude-newer', $ExcludeNewer,
    '--generate-hashes',
    '--no-sources',
    '--no-config',
    '--no-python-downloads',
    '--no-header'
)

$hostCompileArguments = @('pip', 'compile', $hostInputPath, '--output-file', $hostPyLockPath) + $commonCompileArguments
[void] (Invoke-ExternalCommand -FilePath $UvPath -ArgumentList $hostCompileArguments -Description 'Resolve host runtime closure' -LogPath (Join-Path $StagingDirectory 'uv-compile-host.log'))
$hostPackages = @(Get-PyLockPackages -LockPath $hostPyLockPath)
if ($hostPackages.Count -eq 0) {
    throw 'Host runtime lock resolved no packages'
}

$hostConstraintsPath = Join-Path $StagingDirectory 'host-constraints.txt'
$hostConstraints = @($hostPackages | ForEach-Object { '{0}=={1}' -f $_.name, $_.version } | Sort-Object)
[System.IO.File]::WriteAllLines($hostConstraintsPath, $hostConstraints, $script:Utf8NoBom)
$combinedCompileArguments = @(
    'pip', 'compile', $combinedInputPath,
    '--output-file', $combinedPyLockPath,
    '--constraint', $hostConstraintsPath
) + $commonCompileArguments
[void] (Invoke-ExternalCommand -FilePath $UvPath -ArgumentList $combinedCompileArguments -Description 'Resolve combined runtime closure' -LogPath (Join-Path $StagingDirectory 'uv-compile-combined.log'))
$combinedPackages = @(Get-PyLockPackages -LockPath $combinedPyLockPath)
if ($combinedPackages.Count -lt $hostPackages.Count) {
    throw 'Combined runtime closure is smaller than the host closure'
}

$hostArtifacts = @{}
foreach ($package in $hostPackages) {
    $hostArtifacts[$package.normalized_name] = Select-CompatibleLockedArtifact -Package $package
}
$combinedArtifacts = @{}
foreach ($package in $combinedPackages) {
    $combinedArtifacts[$package.normalized_name] = Select-CompatibleLockedArtifact -Package $package
}
foreach ($normalizedName in $hostArtifacts.Keys) {
    if (-not $combinedArtifacts.ContainsKey($normalizedName)) {
        throw "Combined closure removed host distribution: $normalizedName"
    }
    $hostArtifact = $hostArtifacts[$normalizedName]
    $combinedArtifact = $combinedArtifacts[$normalizedName]
    if ($hostArtifact.version -cne $combinedArtifact.version -or
        $hostArtifact.source_kind -cne $combinedArtifact.source_kind -or
        $hostArtifact.source_filename -cne $combinedArtifact.source_filename -or
        $hostArtifact.source_url -cne $combinedArtifact.source_url -or
        ([long] $hostArtifact.source_size_bytes) -ne ([long] $combinedArtifact.source_size_bytes) -or
        $hostArtifact.source_sha256 -cne $combinedArtifact.source_sha256) {
        throw "Plugin dependency resolution changed the protected host lock source: $normalizedName"
    }
}
foreach ($pluginName in $pluginByName.Keys) {
    if ($combinedArtifacts.ContainsKey($pluginName)) {
        throw "Registry closure unexpectedly contains local plugin distribution: $pluginName"
    }
}

$runtimeDependencyRecords = New-Object System.Collections.Generic.List[object]
$hostLockEntries = New-Object System.Collections.Generic.List[object]
$pluginRuntimeLockEntries = New-Object System.Collections.Generic.List[object]
foreach ($normalizedName in @($combinedArtifacts.Keys | Sort-Object)) {
    $lockedArtifact = $combinedArtifacts[$normalizedName]
    Write-Host "Downloading locked runtime $($lockedArtifact.source_kind) $($lockedArtifact.distribution) $($lockedArtifact.version)"
    $downloadedPath = Save-LockedSourceArtifact -Artifact $lockedArtifact -DestinationDirectory $downloadDirectory
    $artifact = Get-FinalRuntimeWheelArtifact `
        -Artifact $lockedArtifact `
        -DownloadedSourcePath $downloadedPath `
        -DownloadDirectory $downloadDirectory `
        -StagingRoot $StagingDirectory `
        -SourceDateEpoch $sourceDateEpoch

    $publishedPath = Get-ContainedChildPath `
        -Directory $publishDirectory `
        -Filename $artifact.filename `
        -Description 'Runtime wheel publish path'
    if (Test-Path -LiteralPath $publishedPath) {
        throw "Runtime wheel filename collides with plugin wheel: $($artifact.filename)"
    }
    if (-not (Test-PathWithinDirectory -Path $artifact.wheel_path -Directory $StagingDirectory)) {
        throw "Final runtime wheel source escapes staging: $($artifact.filename)"
    }
    [System.IO.File]::Copy($artifact.wheel_path, $publishedPath, $false)
    $scope = if ($hostArtifacts.ContainsKey($normalizedName)) { 'host_runtime' } else { 'plugin_runtime' }
    $lockEntry = New-LockEntry -Artifact $artifact -Scope $scope
    if ($scope -eq 'host_runtime') {
        [void] $hostLockEntries.Add($lockEntry)
    } else {
        [void] $pluginRuntimeLockEntries.Add($lockEntry)
    }
    $manifestSource = [ordered]@{
        index = $defaultIndexUri.GetLeftPart([UriPartial]::Authority)
        lock = 'pylock.combined.toml'
        artifact_type = $artifact.source.artifact_type
        filename = $artifact.source.filename
        url = $artifact.source.url
        size_bytes = [long] $artifact.source.size_bytes
        sha256 = $artifact.source.sha256
    }
    if ($null -ne $artifact.source.PSObject.Properties['build']) {
        $manifestSource['build'] = $artifact.source.build
    }
    [void] $runtimeDependencyRecords.Add([pscustomobject]@{
        kind = 'runtime_dependency'
        scopes = @($scope)
        distribution = $artifact.distribution
        version = $artifact.version
        entry_points = @()
        source = [pscustomobject] $manifestSource
        filename = $artifact.filename
        size_bytes = [long] $artifact.size_bytes
        sha256 = $artifact.sha256
    })
}

$pluginLockEntries = @($pluginRecords | ForEach-Object {
    [pscustomobject]@{
        distribution = $_.distribution
        version = $_.version
        scope = 'plugin'
        filename = $_.filename
        size_bytes = [long] $_.size_bytes
        sha256 = $_.sha256
        entry_points = @($_.entry_points | Sort-Object group, name, value)
    }
} | Sort-Object distribution)
$expectedPluginEntryPoints = @($pluginRecords | ForEach-Object { @($_.entry_points) } | ForEach-Object { $_ } | Where-Object {
    $_.group -eq 'auto_mas.plugins' -or $_.group -eq 'automas.plugins'
} | Sort-Object group, name, value)
if ($expectedPluginEntryPoints.Count -ne 21) {
    throw "Runtime lock requires exactly 21 plugin entry points; got $($expectedPluginEntryPoints.Count)"
}

$runtimeLock = [ordered]@{
    schema_version = 1
    generated_at = [DateTimeOffset]::FromUnixTimeSeconds($sourceDateEpoch).ToUniversalTime().ToString('o')
    target = [ordered]@{
        implementation = 'cpython'
        python_version = $TargetPythonVersion
        platform = 'win32'
        architecture = 'x86_64'
        uv_platform = $TargetPlatform
    }
    resolution = [ordered]@{
        default_index = $defaultIndexUri.GetLeftPart([UriPartial]::Authority)
        exclude_newer = $ExcludeNewer
        host_input_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $hostInputPath).Hash.ToLowerInvariant()
        combined_input_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $combinedInputPath).Hash.ToLowerInvariant()
        host_pylock_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $hostPyLockPath).Hash.ToLowerInvariant()
        combined_pylock_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $combinedPyLockPath).Hash.ToLowerInvariant()
    }
    install_contract = [ordered]@{
        resolver_allowed = $false
        index_allowed = $false
        required_arguments = @('--no-index', '--no-deps')
        forbidden_arguments = @('--upgrade', '--index', '--index-url', '--default-index', '--extra-index-url')
        host_target = '.venv'
        plugin_target = 'plugins/pypi/site-packages'
        protected_host_distributions = @($hostLockEntries.distribution | Sort-Object)
    }
    host_runtime = @($hostLockEntries | Sort-Object distribution)
    plugin_runtime = @($pluginRuntimeLockEntries | Sort-Object distribution)
    plugins = $pluginLockEntries
    expected_plugin_entry_points = $expectedPluginEntryPoints
}

$runtimeLockPath = Join-Path $publishDirectory 'runtime-lock.json'
$runtimeLockJson = $runtimeLock | ConvertTo-Json -Depth 12
[System.IO.File]::WriteAllText($runtimeLockPath, $runtimeLockJson + [Environment]::NewLine, $script:Utf8NoBom)
[System.IO.File]::Copy($hostPyLockPath, (Join-Path $publishDirectory 'pylock.host.toml'), $false)
[System.IO.File]::Copy($combinedPyLockPath, (Join-Path $publishDirectory 'pylock.combined.toml'), $false)

$pluginManifestRecords = @($pluginRecords | ForEach-Object {
    [pscustomobject]@{
        kind = 'plugin'
        scopes = @('plugin')
        distribution = $_.distribution
        version = $_.version
        entry_points = @($_.entry_points)
        source = $_.seed_record.source
        filename = $_.filename
        size_bytes = [long] $_.size_bytes
        sha256 = $_.sha256
    }
})
$allManifestRecords = @($pluginManifestRecords + $runtimeDependencyRecords.ToArray()) | Sort-Object distribution
$duplicateFinalDistributions = @($allManifestRecords | Group-Object { ConvertTo-NormalizedDistributionName -Name $_.distribution } | Where-Object Count -gt 1)
$duplicateFinalFilenames = @($allManifestRecords | Group-Object filename | Where-Object Count -gt 1)
if ($duplicateFinalDistributions.Count -gt 0 -or $duplicateFinalFilenames.Count -gt 0) {
    throw 'Final wheelhouse contains duplicate distributions or filenames'
}

$runtimeLockFile = Get-Item -LiteralPath $runtimeLockPath
$finalManifest = [ordered]@{
    schema_version = 3
    generator = 'scripts/complete_integration_wheelhouse.ps1'
    generated_at = [DateTimeOffset]::FromUnixTimeSeconds($sourceDateEpoch).ToUniversalTime().ToString('o')
    artifact_scope = 'complete-windows-x64-runtime-wheelhouse'
    expected_plugin_distribution_count = 23
    expected_plugin_entry_point_count = 21
    runtime_lock = [ordered]@{
        filename = 'runtime-lock.json'
        size_bytes = [long] $runtimeLockFile.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $runtimeLockPath).Hash.ToLowerInvariant()
    }
    source_locks = @(
        [ordered]@{
            filename = 'pylock.host.toml'
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $publishDirectory 'pylock.host.toml')).Hash.ToLowerInvariant()
        },
        [ordered]@{
            filename = 'pylock.combined.toml'
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $publishDirectory 'pylock.combined.toml')).Hash.ToLowerInvariant()
        }
    )
    wheels = $allManifestRecords
}
$finalManifestPath = Join-Path $publishDirectory 'manifest.json'
$finalManifestJson = $finalManifest | ConvertTo-Json -Depth 12
[System.IO.File]::WriteAllText($finalManifestPath, $finalManifestJson + [Environment]::NewLine, $script:Utf8NoBom)

$actualFinalWheels = @(Get-ChildItem -LiteralPath $publishDirectory -File -Filter '*.whl')
if ($actualFinalWheels.Count -ne $allManifestRecords.Count) {
    throw "Final wheel count differs from manifest: $($actualFinalWheels.Count) files and $($allManifestRecords.Count) records"
}
foreach ($record in $allManifestRecords) {
    $wheelPath = Get-ContainedChildPath `
        -Directory $publishDirectory `
        -Filename ([string] $record.filename) `
        -Description 'Final manifest wheel path'
    Assert-ExistingFile -Path $wheelPath -Description 'Final locked wheel'
    $wheelFile = Get-Item -LiteralPath $wheelPath
    $wheelHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $wheelPath).Hash.ToLowerInvariant()
    if ([long] $wheelFile.Length -ne [long] $record.size_bytes -or $wheelHash -ne $record.sha256) {
        throw "Final wheel verification failed: $($record.filename)"
    }
}

if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Output directory appeared before publish; refusing to overwrite: $OutputDirectory"
}
[System.IO.Directory]::Move($publishDirectory, $OutputDirectory)

Write-Host "Complete runtime wheelhouse generated: $OutputDirectory"
Write-Host "Host runtime wheels: $($hostLockEntries.Count)"
Write-Host "Plugin-only runtime wheels: $($pluginRuntimeLockEntries.Count)"
Write-Host "Plugin wheels: $($pluginLockEntries.Count)"
Write-Host "Staging retained for audit and not automatically deleted: $StagingDirectory"
