Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$assertionScript = Join-Path $PSScriptRoot 'Assert-AuthenticodeSignature.ps1'
$placeholder = Join-Path $PSScriptRoot 'unsigned-placeholder.exe'

function Assert-Rejected {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedMessage
    )

    try {
        & $assertionScript @Arguments
    }
    catch {
        if ($_.Exception.Message -notlike $ExpectedMessage) {
            throw "Unexpected rejection: $($_.Exception.Message)"
        }
        return
    }
    throw "Expected signature policy rejection matching: $ExpectedMessage"
}

$missingTestIdentity = @{
    Path = $placeholder
    IsPrerelease = 'true'
    SigningPolicy = 'test-signing'
    ReleaseSubjectAllowlistJson = '["CN=release"]'
    ReleaseThumbprintAllowlistJson = '["1111111111111111111111111111111111111111"]'
    TestSubjectAllowlistJson = ''
    TestThumbprintAllowlistJson = ''
}
Assert-Rejected `
    -Arguments $missingTestIdentity `
    -ExpectedMessage "Explicit certificate allowlists are required for 'test-signing'"

$mismatchedPolicy = $missingTestIdentity.Clone()
$mismatchedPolicy.TestSubjectAllowlistJson = '["CN=test"]'
$mismatchedPolicy.TestThumbprintAllowlistJson = '["2222222222222222222222222222222222222222"]'
$mismatchedPolicy.SigningPolicy = 'release-signing'
Assert-Rejected `
    -Arguments $mismatchedPolicy `
    -ExpectedMessage "Signing policy 'release-signing' does not match prerelease state 'true'"

Write-Output 'Authenticode fail-closed policy tests passed'
