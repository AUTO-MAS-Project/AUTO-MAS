param(
  [string]$Grep = ''
)

$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ([string]::IsNullOrWhiteSpace($env:AUTO_MAS_E2E_TEMPLATE_ROOT)) {
  $env:AUTO_MAS_E2E_TEMPLATE_ROOT = $repositoryRoot
}
$env:AUTO_MAS_E2E_REAL = '1'

$required = @(
  'AUTO_MAS_E2E_SCRIPT_ID',
  'AUTO_MAS_E2E_USER_ID',
  'AUTO_MAS_E2E_ACCOUNT_NAME'
)
$missing = @($required | Where-Object { [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_)) })
if ($missing.Count -gt 0) {
  throw "缺少本机真实 E2E 配置: $($missing -join ', ')"
}

Write-Host '运行本机真实专项、游戏和账号 E2E；按所选脚本绑定的资源执行，测试会使用隔离临时目录，不修改当前 config/data。'
if ([string]::IsNullOrWhiteSpace($Grep)) {
  $Grep = $env:AUTO_MAS_E2E_GREP
}
if ([string]::IsNullOrWhiteSpace($Grep)) {
  $Grep = '@real'
}
yarn e2e --grep $Grep
exit $LASTEXITCODE
