Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-PositiveInt64 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [long]$Value
    )

    if ($Value -le 0) {
        throw "$Name must be a positive integer"
    }
}

function Invoke-BoundedHttpsDownload {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [Uri]$Uri,
        [Parameter(Mandatory = $true)]
        [string]$DestinationPath,
        [Parameter(Mandatory = $true)]
        [long]$MaxBytes
    )

    Assert-PositiveInt64 -Name 'MaxBytes' -Value $MaxBytes
    Add-Type -AssemblyName System.Net.Http
    if ($Uri.Scheme -ne 'https') {
        throw 'Archive download URL must use HTTPS'
    }
    if (Test-Path -LiteralPath $DestinationPath) {
        throw "Refusing to overwrite an existing download: $DestinationPath"
    }

    $destinationParent = Split-Path -Parent $DestinationPath
    if ($destinationParent) {
        New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
    }

    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $true
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromMinutes(30)
    $response = $null
    $inputStream = $null
    $outputStream = $null
    try {
        $response = $client.GetAsync(
            $Uri,
            [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead
        ).GetAwaiter().GetResult()
        $response.EnsureSuccessStatusCode()
        if ($response.RequestMessage.RequestUri.Scheme -ne 'https') {
            throw 'Archive download redirected away from HTTPS'
        }

        $declaredLength = $response.Content.Headers.ContentLength
        if ($null -ne $declaredLength -and $declaredLength -gt $MaxBytes) {
            throw "Archive Content-Length $declaredLength exceeds limit $MaxBytes"
        }

        $inputStream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $outputStream = [System.IO.File]::Open(
            $DestinationPath,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        $buffer = [byte[]]::new(1024 * 1024)
        [long]$written = 0
        while (($read = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $written += $read
            if ($written -gt $MaxBytes) {
                throw "Downloaded archive exceeds limit $MaxBytes"
            }
            $outputStream.Write($buffer, 0, $read)
        }
        $outputStream.Flush($true)
        return $written
    }
    finally {
        if ($null -ne $outputStream) {
            $outputStream.Dispose()
        }
        if ($null -ne $inputStream) {
            $inputStream.Dispose()
        }
        if ($null -ne $response) {
            $response.Dispose()
        }
        $client.Dispose()
        $handler.Dispose()
    }
}

function Test-ArchiveEntryPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$EntryName,
        [Parameter(Mandatory = $true)]
        [string]$DestinationRoot
    )

    if ([string]::IsNullOrWhiteSpace($EntryName) -or $EntryName.Contains([char]0)) {
        throw 'ZIP contains an empty or NUL-bearing entry name'
    }

    $normalized = $EntryName.Replace('\', '/')
    if (
        $normalized.StartsWith('/') -or
        $normalized.StartsWith('//') -or
        $normalized -match '^[A-Za-z]:' -or
        [System.IO.Path]::IsPathRooted($normalized)
    ) {
        throw "ZIP entry is absolute: $EntryName"
    }

    $isDirectory = $normalized.EndsWith('/')
    $trimmed = $normalized.TrimEnd('/')
    $segments = $trimmed.Split('/')
    if ($segments.Count -eq 0) {
        throw "ZIP entry has no path segments: $EntryName"
    }
    foreach ($segment in $segments) {
        if (
            [string]::IsNullOrEmpty($segment) -or
            $segment -eq '.' -or
            $segment -eq '..' -or
            $segment.Contains(':') -or
            $segment.EndsWith('.') -or
            $segment.EndsWith(' ')
        ) {
            throw "ZIP entry has an unsafe path segment: $EntryName"
        }
        $baseName = $segment.Split('.')[0]
        if ($baseName -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$') {
            throw "ZIP entry uses a reserved Windows path: $EntryName"
        }
    }

    $root = [System.IO.Path]::GetFullPath($DestinationRoot)
    $rootPrefix = $root.TrimEnd(
        [char[]]@(
            [System.IO.Path]::DirectorySeparatorChar,
            [System.IO.Path]::AltDirectorySeparatorChar
        )
    ) + [System.IO.Path]::DirectorySeparatorChar
    $candidate = [System.IO.Path]::GetFullPath(
        [System.IO.Path]::Combine($root, $trimmed.Replace('/', [System.IO.Path]::DirectorySeparatorChar))
    )
    if (-not $candidate.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "ZIP entry escapes extraction root: $EntryName"
    }

    return @{
        IsDirectory = $isDirectory
        TargetPath = $candidate
        CanonicalKey = $candidate.ToUpperInvariant()
    }
}

function Expand-VerifiedZip {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ArchivePath,
        [Parameter(Mandatory = $true)]
        [string]$DestinationPath,
        [Parameter(Mandatory = $true)]
        [long]$MaxArchiveBytes,
        [Parameter(Mandatory = $true)]
        [long]$MaxEntries,
        [Parameter(Mandatory = $true)]
        [long]$MaxExpandedBytes,
        [Parameter(Mandatory = $true)]
        [long]$MaxFileBytes
    )

    Assert-PositiveInt64 -Name 'MaxArchiveBytes' -Value $MaxArchiveBytes
    Assert-PositiveInt64 -Name 'MaxEntries' -Value $MaxEntries
    Assert-PositiveInt64 -Name 'MaxExpandedBytes' -Value $MaxExpandedBytes
    Assert-PositiveInt64 -Name 'MaxFileBytes' -Value $MaxFileBytes
    if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) {
        throw "ZIP archive does not exist: $ArchivePath"
    }
    if (Test-Path -LiteralPath $DestinationPath) {
        throw "Refusing to overwrite an existing extraction destination: $DestinationPath"
    }

    $archiveLength = (Get-Item -LiteralPath $ArchivePath).Length
    if ($archiveLength -gt $MaxArchiveBytes) {
        throw "ZIP archive size $archiveLength exceeds limit $MaxArchiveBytes"
    }

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
    $validatedEntries = [System.Collections.Generic.List[object]]::new()
    $canonicalPaths = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    [long]$declaredExpandedBytes = 0
    try {
        if ($archive.Entries.Count -gt $MaxEntries) {
            throw "ZIP entry count $($archive.Entries.Count) exceeds limit $MaxEntries"
        }

        foreach ($entry in $archive.Entries) {
            $pathInfo = Test-ArchiveEntryPath -EntryName $entry.FullName -DestinationRoot $DestinationPath
            if (-not $canonicalPaths.Add($pathInfo.CanonicalKey)) {
                throw "ZIP contains duplicate destination paths: $($entry.FullName)"
            }

            $unixType = (($entry.ExternalAttributes -shr 16) -band 0xF000)
            $windowsAttributes = ($entry.ExternalAttributes -band 0xFFFF)
            if ($unixType -eq 0xA000) {
                throw "ZIP contains a symbolic link: $($entry.FullName)"
            }
            if (($windowsAttributes -band [int][System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "ZIP contains a reparse-point entry: $($entry.FullName)"
            }
            if ($unixType -ne 0 -and $unixType -ne 0x4000 -and $unixType -ne 0x8000) {
                throw "ZIP contains an unsupported special-file entry: $($entry.FullName)"
            }

            if ($pathInfo.IsDirectory) {
                if ($entry.Length -ne 0) {
                    throw "ZIP directory entry has data: $($entry.FullName)"
                }
            }
            else {
                if ($entry.Length -gt $MaxFileBytes) {
                    throw "ZIP entry $($entry.FullName) exceeds per-file limit $MaxFileBytes"
                }
                if ($entry.Length -gt ($MaxExpandedBytes - $declaredExpandedBytes)) {
                    throw "ZIP declared expanded size exceeds limit $MaxExpandedBytes"
                }
                $declaredExpandedBytes += $entry.Length
            }

            $validatedEntries.Add(
                [pscustomobject]@{
                    Entry = $entry
                    IsDirectory = $pathInfo.IsDirectory
                    RelativePath = $entry.FullName.Replace('\', '/').TrimEnd('/')
                    DeclaredLength = $entry.Length
                }
            )
        }

        $destinationParent = Split-Path -Parent ([System.IO.Path]::GetFullPath($DestinationPath))
        New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
        $stagingPath = Join-Path $destinationParent ".archive-stage-$([Guid]::NewGuid().ToString('N'))"
        New-Item -ItemType Directory -Path $stagingPath -ErrorAction Stop | Out-Null

        [long]$actualExpandedBytes = 0
        foreach ($validated in $validatedEntries) {
            $stagePathInfo = Test-ArchiveEntryPath `
                -EntryName $validated.Entry.FullName `
                -DestinationRoot $stagingPath
            if ($validated.IsDirectory) {
                New-Item -ItemType Directory -Path $stagePathInfo.TargetPath -Force | Out-Null
                continue
            }

            $parent = Split-Path -Parent $stagePathInfo.TargetPath
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
            $inputStream = $validated.Entry.Open()
            $outputStream = [System.IO.File]::Open(
                $stagePathInfo.TargetPath,
                [System.IO.FileMode]::CreateNew,
                [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::None
            )
            [long]$fileBytes = 0
            try {
                $buffer = [byte[]]::new(1024 * 1024)
                while (($read = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                    $fileBytes += $read
                    $actualExpandedBytes += $read
                    if ($fileBytes -gt $MaxFileBytes) {
                        throw "Extracted entry $($validated.Entry.FullName) exceeds per-file limit"
                    }
                    if ($actualExpandedBytes -gt $MaxExpandedBytes) {
                        throw "Extracted ZIP exceeds total expanded-size limit"
                    }
                    $outputStream.Write($buffer, 0, $read)
                }
                $outputStream.Flush($true)
            }
            finally {
                $outputStream.Dispose()
                $inputStream.Dispose()
            }
            if ($fileBytes -ne $validated.DeclaredLength) {
                throw "Extracted size mismatch for $($validated.Entry.FullName)"
            }
        }

        $materialized = @(Get-ChildItem -LiteralPath $stagingPath -Force -Recurse)
        if ($materialized.Count -gt $MaxEntries) {
            throw "Materialized entry count exceeds limit $MaxEntries"
        }
        foreach ($item in $materialized) {
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Extracted tree contains a reparse point: $($item.FullName)"
            }
        }

        Move-Item -LiteralPath $stagingPath -Destination $DestinationPath -ErrorAction Stop
        return [pscustomobject]@{
            ArchiveBytes = $archiveLength
            EntryCount = $archive.Entries.Count
            ExpandedBytes = $actualExpandedBytes
            DestinationPath = [System.IO.Path]::GetFullPath($DestinationPath)
        }
    }
    finally {
        $archive.Dispose()
    }
}

Export-ModuleMember -Function Invoke-BoundedHttpsDownload, Expand-VerifiedZip
