# Build avdshim (stand-in for MuMu's external_renderer_ipc.dll) next to this script.
# AUTO-MAS copies the result into <official emulator root>\mumu-shim\shell\sdk\ and points MAA's
# MuMu screencap path there. Requires MinGW-w64 GCC (x86_64, UCRT); pass -Gcc if it is not on PATH.
param(
    [string]$Gcc = 'gcc'
)

$ErrorActionPreference = 'Stop'
$dll = Join-Path $PSScriptRoot 'external_renderer_ipc.dll'
& $Gcc -O2 -Wall -Wextra -shared -static-libgcc -s -o $dll (Join-Path $PSScriptRoot 'avdshim.c') -lws2_32
if ($LASTEXITCODE -ne 0) { throw "gcc failed ($LASTEXITCODE)" }
Write-Host "built $dll"
