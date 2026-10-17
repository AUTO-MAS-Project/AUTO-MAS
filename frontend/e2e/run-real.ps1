param(
  [string]$Grep = '',
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$RemainingArguments = @()
)

$ErrorActionPreference = 'Stop'

$env:AUTO_MAS_E2E_REAL = '1'

$target = @('AUTO_MAS_E2E_SCRIPT_ID', 'AUTO_MAS_E2E_USER_ID', 'AUTO_MAS_E2E_ACCOUNT_NAME') |
  Where-Object { -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_)) }
if ($target.Count -eq 0) {
  Write-Host '未指定真实 E2E 目标：自动使用本机 config 里第一个已启用用户。想指定就设 AUTO_MAS_E2E_SCRIPT_ID / USER_ID / ACCOUNT_NAME。'
} else {
  Write-Host "真实 E2E 目标：$($target -join ', ')"
}

Write-Host '运行本机真实专项、游戏和账号 E2E；默认把所选脚本/用户/计划复制到临时数据根（不写你的 config/data），加 --in-place 才就地使用当前 config/data。'
if ([string]::IsNullOrWhiteSpace($Grep)) {
  $Grep = $env:AUTO_MAS_E2E_GREP
}
# 除 --grep 外的参数原样透传给 playwright，--in-place 等开关才不会在这里丢掉
$extra = @()
if ($Grep -eq '--grep') {
  $grepArguments = @($RemainingArguments | Where-Object { $_ -ne '--grep' })
  if ($grepArguments.Count -lt 1) {
    throw '用法: yarn e2e:real --grep <regex> [其余参数透传]'
  }
  $Grep = $grepArguments[0]
  $extra = @($grepArguments | Select-Object -Skip 1)
} else {
  $extra = @($RemainingArguments)
}
if ([string]::IsNullOrWhiteSpace($Grep)) {
  $Grep = '@real'
}
yarn e2e '--grep' $Grep @extra
exit $LASTEXITCODE
