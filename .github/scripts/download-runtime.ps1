param([switch]$RequireAlpha)
$ErrorActionPreference = 'Stop'
$runtimeVersion = (Get-Content -LiteralPath res/runtime-version.txt -Raw).Trim()
if ($runtimeVersion -notmatch '^v\d+(\.\d+)*([-+][0-9A-Za-z.-]+)?$') { throw 'Runtime 钉扎格式无效' }
New-Item -ItemType Directory -Force runtime | Out-Null
$exeName = "auto-mas-runtime-$runtimeVersion.exe"
gh release download $runtimeVersion -R AUTO-MAS-Project/AUTO-MAS-Runtime -D runtime -p $exeName -p SHA256SUMS.txt --clobber
if ($LASTEXITCODE -ne 0) { throw '下载 Runtime 失败' }
$records = @(Get-Content runtime/SHA256SUMS.txt | Where-Object { $_ -match ('^[0-9a-fA-F]{64}\s+\*?' + [regex]::Escape($exeName) + '$') })
if ($records.Count -ne 1) { throw 'Runtime 校验清单缺失或重复' }
$expected = ($records[0] -split '\s+')[0]
if ((Get-FileHash "runtime/$exeName" -Algorithm SHA256).Hash -ne $expected) { throw 'Runtime 哈希不符' }
Move-Item "runtime/$exeName" runtime/auto-mas-runtime.exe -Force
$events = @(& ./runtime/auto-mas-runtime.exe version --output ndjson | ForEach-Object { $_ | ConvertFrom-Json })
if ($LASTEXITCODE -ne 0) { throw 'Runtime version 检查失败' }
$result = $events | Where-Object type -EQ result | Select-Object -Last 1
if (-not $result.success -or $result.details.runtimeVersion -ne $runtimeVersion) { throw 'Runtime 自报版本与钉扎不符' }
if ($RequireAlpha -and $result.details.alphaBackend -ne 'dev') { throw '钉扎的 Runtime 不支持 alpha dev 后端，请先发布新版 Runtime 并更新钉扎' }
