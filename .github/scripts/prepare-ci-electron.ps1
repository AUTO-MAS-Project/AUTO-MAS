# 仅用于 Windows CI：从备用镜像获取 Electron，校验官方发布摘要。
# 交给 electronDist 的是已验证的原始 ZIP，不关闭完整性检查。
param(
    [Parameter(Mandatory = $true)][string]$PackageJson,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$package = Get-Content -LiteralPath $PackageJson -Raw | ConvertFrom-Json
$version = [string]$package.devDependencies.electron
if ($version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Electron 版本必须为固定的 X.Y.Z，实际：$version"
}

$assetName = "electron-v$version-win32-x64.zip"
$releaseUrl = "https://api.github.com/repos/electron/electron/releases/tags/v$version"
$headers = @{ 'User-Agent' = 'AUTO-MAS-CI' }
if ($env:GITHUB_TOKEN) {
    $headers['Authorization'] = "Bearer $env:GITHUB_TOKEN"
}
$release = Invoke-RestMethod -Uri $releaseUrl -Headers $headers -TimeoutSec 45
$assets = @($release.assets | Where-Object { $_.name -eq $assetName })
if ($assets.Count -ne 1) {
    throw "Electron 官方 Release 中未找到唯一归档：$assetName"
}

$digest = [string]$assets[0].digest
if ($digest -notmatch '^sha256:[0-9a-fA-F]{64}$') {
    throw "Electron 官方 Release 缺少合法的 SHA-256 摘要：$assetName"
}
$expected = $digest.Substring(7).ToLowerInvariant()
New-Item -Path $OutputDirectory -ItemType Directory -Force | Out-Null
$archive = Join-Path $OutputDirectory $assetName
$partial = "$archive.partial"
$mirror = "https://npmmirror.com/mirrors/electron/$version/$assetName"

for ($attempt = 1; $attempt -le 2; $attempt++) {
    try {
        Write-Host "从 Electron 文档列出的备用镜像下载 $assetName（$attempt/2）"
        Invoke-WebRequest -Uri $mirror -OutFile $partial -TimeoutSec 300
        $actual = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expected) {
            throw "Electron 镜像归档 SHA-256 校验失败"
        }
        Move-Item -LiteralPath $partial -Destination $archive -Force
        Write-Host "Electron 镜像归档已与官方 SHA-256 校验一致"
        return
    } catch {
        Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
        if ($_.Exception.Message -match 'SHA-256 校验失败' -or $attempt -eq 2) {
            throw
        }
        Write-Warning "镜像下载失败，将重试一次：$($_.Exception.Message)"
        Start-Sleep -Seconds 10
    }
}
