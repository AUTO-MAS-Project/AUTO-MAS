param(
    [Parameter(Mandatory = $true)]
    [string[]]$Path,
    [Parameter(Mandatory = $true)]
    [ValidateSet('true', 'false')]
    [string]$IsPrerelease,
    [Parameter(Mandatory = $true)]
    [ValidateSet('test-signing', 'release-signing')]
    [string]$SigningPolicy,
    [AllowEmptyString()]
    [string]$ReleaseSubjectAllowlistJson,
    [AllowEmptyString()]
    [string]$ReleaseThumbprintAllowlistJson,
    [AllowEmptyString()]
    [string]$TestSubjectAllowlistJson,
    [AllowEmptyString()]
    [string]$TestThumbprintAllowlistJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$expectedPolicy = if ($IsPrerelease -eq 'true') { 'test-signing' } else { 'release-signing' }
if ($SigningPolicy -ne $expectedPolicy) {
    throw "Signing policy '$SigningPolicy' does not match prerelease state '$IsPrerelease'"
}

$subjectJson = if ($IsPrerelease -eq 'true') {
    $TestSubjectAllowlistJson
}
else {
    $ReleaseSubjectAllowlistJson
}
$thumbprintJson = if ($IsPrerelease -eq 'true') {
    $TestThumbprintAllowlistJson
}
else {
    $ReleaseThumbprintAllowlistJson
}
if ([string]::IsNullOrWhiteSpace($subjectJson) -or [string]::IsNullOrWhiteSpace($thumbprintJson)) {
    throw "Explicit certificate allowlists are required for '$SigningPolicy'"
}

try {
    $subjects = @($subjectJson | ConvertFrom-Json -ErrorAction Stop)
    $thumbprints = @($thumbprintJson | ConvertFrom-Json -ErrorAction Stop)
}
catch {
    throw "Certificate allowlist JSON is invalid: $($_.Exception.Message)"
}
$subjects = @($subjects | Where-Object { $_ -is [string] -and -not [string]::IsNullOrWhiteSpace($_) })
$thumbprints = @(
    $thumbprints |
        Where-Object { $_ -is [string] -and $_ -match '^[0-9A-Fa-f]{40}$' } |
        ForEach-Object { $_.ToUpperInvariant() }
)
if ($subjects.Count -eq 0 -or $thumbprints.Count -eq 0) {
    throw "Certificate allowlists for '$SigningPolicy' must contain at least one valid value each"
}

foreach ($candidate in $Path) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Signed artifact is missing: $candidate"
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $candidate
    if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        throw "Authenticode signature is not valid for '$candidate': $($signature.Status)"
    }
    if ($null -eq $signature.SignerCertificate) {
        throw "Authenticode signer certificate is missing for '$candidate'"
    }

    $actualSubject = $signature.SignerCertificate.Subject
    $actualThumbprint = $signature.SignerCertificate.Thumbprint.ToUpperInvariant()
    $subjectAllowed = $false
    foreach ($allowedSubject in $subjects) {
        if ([string]::Equals($actualSubject, $allowedSubject, [System.StringComparison]::OrdinalIgnoreCase)) {
            $subjectAllowed = $true
            break
        }
    }
    if (-not $subjectAllowed) {
        throw "Authenticode subject is not allowlisted for '$candidate': $actualSubject"
    }
    if ($actualThumbprint -notin $thumbprints) {
        throw "Authenticode thumbprint is not allowlisted for '$candidate': $actualThumbprint"
    }

    Write-Output "Verified Authenticode: $candidate [$SigningPolicy] $actualThumbprint"
}
