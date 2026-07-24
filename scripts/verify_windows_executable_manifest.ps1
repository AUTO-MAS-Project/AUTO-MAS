[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $ExecutablePath,

    [string] $PackageJsonPath,

    [ValidateSet('asInvoker', 'highestAvailable', 'requireAdministrator')]
    [string] $ExpectedLevel = 'asInvoker'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$resolvedExecutable = [System.IO.Path]::GetFullPath($ExecutablePath)
if (-not (Test-Path -LiteralPath $resolvedExecutable -PathType Leaf)) {
    throw "Executable does not exist: $resolvedExecutable"
}

if (-not [string]::IsNullOrWhiteSpace($PackageJsonPath)) {
    $resolvedPackageJson = [System.IO.Path]::GetFullPath($PackageJsonPath)
    if (-not (Test-Path -LiteralPath $resolvedPackageJson -PathType Leaf)) {
        throw "package.json does not exist: $resolvedPackageJson"
    }
    $package = Get-Content -LiteralPath $resolvedPackageJson -Raw | ConvertFrom-Json
    $configuredLevel = [string] $package.build.win.requestedExecutionLevel
    if ($configuredLevel -ne $ExpectedLevel) {
        throw "package.json execution level is $configuredLevel; expected $ExpectedLevel"
    }
}

function Test-ByteSequence {
    param(
        [Parameter(Mandatory = $true)]
        [byte[]] $Haystack,
        [Parameter(Mandatory = $true)]
        [byte[]] $Needle
    )

    if ($Needle.Length -eq 0 -or $Haystack.Length -lt $Needle.Length) {
        return $false
    }
    for ($offset = 0; $offset -le $Haystack.Length - $Needle.Length; $offset++) {
        $matches = $true
        for ($index = 0; $index -lt $Needle.Length; $index++) {
            if ($Haystack[$offset + $index] -ne $Needle[$index]) {
                $matches = $false
                break
            }
        }
        if ($matches) {
            return $true
        }
    }
    return $false
}

$bytes = [System.IO.File]::ReadAllBytes($resolvedExecutable)
$levels = @('asInvoker', 'highestAvailable', 'requireAdministrator')
$detectedLevels = [System.Collections.Generic.List[string]]::new()
foreach ($level in $levels) {
    $fragment = 'level="{0}"' -f $level
    $ascii = [System.Text.Encoding]::ASCII.GetBytes($fragment)
    $utf16 = [System.Text.Encoding]::Unicode.GetBytes($fragment)
    if ((Test-ByteSequence -Haystack $bytes -Needle $ascii) -or
        (Test-ByteSequence -Haystack $bytes -Needle $utf16)) {
        [void] $detectedLevels.Add($level)
    }
}

if ($detectedLevels.Count -eq 0) {
    throw 'No requestedExecutionLevel resource marker was found in the executable'
}
if ($detectedLevels.Count -ne 1) {
    throw "Executable contains ambiguous execution levels: $($detectedLevels -join ', ')"
}
if ($detectedLevels[0] -ne $ExpectedLevel) {
    throw "Executable execution level is $($detectedLevels[0]); expected $ExpectedLevel"
}

$hash = (Get-FileHash -LiteralPath $resolvedExecutable -Algorithm SHA256).Hash
Write-Host "Windows executable manifest verified: $resolvedExecutable"
Write-Host "requestedExecutionLevel=$ExpectedLevel"
Write-Host "sha256=$hash"
