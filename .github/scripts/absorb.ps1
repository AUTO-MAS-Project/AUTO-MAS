# 仅用于 Actions 一次性检出；推送竞争时从 dev 顶端重新编译。
param([switch]$Offline)
$ErrorActionPreference = 'Stop'
if ((git branch --show-current).Trim() -ne 'dev') { throw '入账只允许 dev' }
if ($LASTEXITCODE -ne 0) { throw '无法确认分支' }
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
for ($attempt = 1; $attempt -le 3; $attempt++) {
    git fetch --no-tags --quiet origin refs/heads/dev:refs/remotes/origin/dev
    if ($LASTEXITCODE -ne 0) { throw '拉取 dev 失败' }
    git reset --hard --quiet origin/dev
    if ($LASTEXITCODE -ne 0) { throw '检出 dev 顶端失败' }
    $summary = Join-Path $env:RUNNER_TEMP 'absorb.json'
    Remove-Item -LiteralPath $summary -ErrorAction SilentlyContinue
    $arguments = @('scripts/changelog.py', 'absorb', '--repo', $env:GITHUB_REPOSITORY, '--summary-file', $summary)
    if ($Offline) { $arguments += '--offline' }
    python @arguments
    if ($LASTEXITCODE -ne 0) { throw '编译碎片失败' }
    git add --all changelog.d CHANGELOG.md res/version.json
    if ($LASTEXITCODE -ne 0) { throw '暂存入账结果失败' }
    git diff --cached --quiet
    $diffExit = $LASTEXITCODE
    if ($diffExit -eq 0) {
        Add-Content -LiteralPath $env:GITHUB_OUTPUT -Value 'pushed=false'
        exit 0
    }
    if ($diffExit -ne 1) { throw '检查入账差异失败' }
    $prs = ((Get-Content -LiteralPath $summary -Raw | ConvertFrom-Json).absorbed | Where-Object pr | ForEach-Object { "#$($_.pr)" }) -join ' '
    if (-not $prs) { $prs = '碎片' }
    git commit --quiet -m "chore(changelog): 入账 $prs"
    if ($LASTEXITCODE -ne 0) { throw '创建入账提交失败' }
    git push origin HEAD:refs/heads/dev
    if ($LASTEXITCODE -eq 0) {
        Add-Content -LiteralPath $env:GITHUB_OUTPUT -Value 'pushed=true'
        exit 0
    }
    $global:LASTEXITCODE = 0
    Write-Host "推送被拒，第 $attempt 次，从 dev 顶端重新编译"
}
throw '三次推送失败，请手动重跑 dev 入账'
