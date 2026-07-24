Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'ArchiveSafety.psm1') -Force
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) "auto-mas-archive-safety-$([Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $testRoot -ErrorAction Stop | Out-Null

function New-TestZip {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [array]$Entries
    )

    $path = Join-Path $testRoot $Name
    $stream = [System.IO.File]::Open(
        $path,
        [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
    $archive = [System.IO.Compression.ZipArchive]::new(
        $stream,
        [System.IO.Compression.ZipArchiveMode]::Create,
        $false
    )
    try {
        foreach ($spec in $Entries) {
            $entry = $archive.CreateEntry($spec.Name)
            if ($null -ne $spec.ExternalAttributes) {
                $entry.ExternalAttributes = $spec.ExternalAttributes
            }
            if ($null -ne $spec.Content) {
                $writer = [System.IO.StreamWriter]::new($entry.Open())
                try {
                    $writer.Write($spec.Content)
                }
                finally {
                    $writer.Dispose()
                }
            }
        }
    }
    finally {
        $archive.Dispose()
        $stream.Dispose()
    }
    return $path
}

function Assert-Rejected {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ArchivePath,
        [Parameter(Mandatory = $true)]
        [string]$CaseName,
        [long]$MaxEntries = 10,
        [long]$MaxExpandedBytes = 1024,
        [long]$MaxFileBytes = 512
    )

    $destination = Join-Path $testRoot "rejected-$CaseName"
    $rejected = $false
    try {
        Expand-VerifiedZip `
            -ArchivePath $ArchivePath `
            -DestinationPath $destination `
            -MaxArchiveBytes 1048576 `
            -MaxEntries $MaxEntries `
            -MaxExpandedBytes $MaxExpandedBytes `
            -MaxFileBytes $MaxFileBytes | Out-Null
    }
    catch {
        $rejected = $true
    }
    if (-not $rejected) {
        throw "Expected archive case '$CaseName' to be rejected"
    }
    if (Test-Path -LiteralPath $destination) {
        throw "Rejected archive case '$CaseName' touched its formal destination"
    }
}

$goodArchive = New-TestZip -Name 'good.zip' -Entries @(
    @{ Name = 'wheelhouse/'; Content = $null; ExternalAttributes = $null },
    @{ Name = 'wheelhouse/manifest.json'; Content = '{}'; ExternalAttributes = $null },
    @{ Name = 'wheelhouse/runtime-lock.json'; Content = '{}'; ExternalAttributes = $null }
)
$goodDestination = Join-Path $testRoot 'good-output'
$result = Expand-VerifiedZip `
    -ArchivePath $goodArchive `
    -DestinationPath $goodDestination `
    -MaxArchiveBytes 1048576 `
    -MaxEntries 10 `
    -MaxExpandedBytes 1024 `
    -MaxFileBytes 512
if ($result.EntryCount -ne 3) {
    throw 'Good archive entry count mismatch'
}
if (-not (Test-Path -LiteralPath (Join-Path $goodDestination 'wheelhouse\manifest.json') -PathType Leaf)) {
    throw 'Good archive did not materialize the expected file'
}

Assert-Rejected `
    -CaseName 'traversal' `
    -ArchivePath (New-TestZip -Name 'traversal.zip' -Entries @(
        @{ Name = '../escape.txt'; Content = 'pwn'; ExternalAttributes = $null }
    ))
Assert-Rejected `
    -CaseName 'ads' `
    -ArchivePath (New-TestZip -Name 'ads.zip' -Entries @(
        @{ Name = 'safe.txt:evil'; Content = 'pwn'; ExternalAttributes = $null }
    ))
Assert-Rejected `
    -CaseName 'symlink' `
    -ArchivePath (New-TestZip -Name 'symlink.zip' -Entries @(
        @{ Name = 'link'; Content = 'target'; ExternalAttributes = (0xA1FF -shl 16) }
    ))
Assert-Rejected `
    -CaseName 'reparse' `
    -ArchivePath (New-TestZip -Name 'reparse.zip' -Entries @(
        @{ Name = 'junction'; Content = 'target'; ExternalAttributes = 0x400 }
    ))
Assert-Rejected `
    -CaseName 'file-budget' `
    -MaxFileBytes 4 `
    -ArchivePath (New-TestZip -Name 'file-budget.zip' -Entries @(
        @{ Name = 'large.txt'; Content = '12345'; ExternalAttributes = $null }
    ))
Assert-Rejected `
    -CaseName 'entry-budget' `
    -MaxEntries 1 `
    -ArchivePath (New-TestZip -Name 'entry-budget.zip' -Entries @(
        @{ Name = 'one.txt'; Content = '1'; ExternalAttributes = $null },
        @{ Name = 'two.txt'; Content = '2'; ExternalAttributes = $null }
    ))

Write-Output "Archive safety tests passed; evidence retained at $testRoot"
