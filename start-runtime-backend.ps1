$ErrorActionPreference = 'Stop'

$repo = $PSScriptRoot
$runtime = Join-Path $repo 'AUTO-MAS-Runtime\bin\auto-mas-runtime.exe'

$sid = ([System.Security.Principal.WindowsIdentity]::GetCurrent()).User.Value
$appRoot = Join-Path $env:LOCALAPPDATA "AUTO-MAS\Runtime\$sid"

$port = 36163..36199 |
  Where-Object {
    -not (Get-NetTCPConnection `
      -LocalPort $_ `
      -State Listen `
      -ErrorAction SilentlyContinue)
  } |
  Select-Object -First 1

if (-not $port) {
  throw 'no port can be used'
}

New-Item -ItemType Directory -Force $appRoot | Out-Null

Write-Host "User SID : $sid"
Write-Host "Runtime  : $appRoot"
Write-Host "Backend  : http://127.0.0.1:$port"

Write-Host 'preparing backend...'

& $runtime `
  --app-root $appRoot `
  --output ndjson `
  --protocol 1 `
  environment ensure

if ($LASTEXITCODE -ne 0) {
  throw "Runtime environment ensure failed: $LASTEXITCODE"
}

Write-Host 'starting backend...'

& $runtime `
  --app-root $appRoot `
  --output ndjson `
  --protocol 1 `
  backend supervise `
  --mode development `
  --repo $repo `
  --port $port