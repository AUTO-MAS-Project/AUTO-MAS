# 同步源码与正式/beta tag；滚动 nightly dev tag 不进入镜像，避免重建后需要强推。
param([string]$VersionTag, [string]$SourceSha)
$ErrorActionPreference = 'Stop'
if (-not $env:CNB_GIT_TOKEN) { throw '缺少 GIT_PASSWORD' }
$auth = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("cnb:$env:CNB_GIT_TOKEN"))
$config = "http.https://cnb.cool/.extraHeader=Authorization: Basic $auth"
$target = 'https://cnb.cool/AUTO-MAS-Project/AUTO-MAS.git'
if ($VersionTag) {
    if ($VersionTag -notmatch '^v\d+\.\d+\.\d+(-beta\.\d+)?$' -or $SourceSha -notmatch '^[a-f0-9]{40}$') { throw '发布源码标识无效' }
    git -c $config push --atomic $target "$($SourceSha):refs/heads/release/$VersionTag" "refs/tags/$($VersionTag):refs/tags/$VersionTag"
} else {
    git fetch origin
    if ($LASTEXITCODE -ne 0) { throw '拉取源码失败' }
    git fetch origin --tags
    if ($LASTEXITCODE -ne 0) { throw '拉取版本 tag 失败' }
    $refspecs = @(git for-each-ref '--format=%(refname)' refs/remotes/origin | Where-Object { $_ -ne 'refs/remotes/origin/HEAD' } | ForEach-Object {
        "$($_):refs/heads/$($_.Substring('refs/remotes/origin/'.Length))"
    })
    $refspecs += @(git tag --list 'v*' | ForEach-Object { "refs/tags/$($_):refs/tags/$_" })
    if ($refspecs.Count -eq 0) { throw '没有可同步的源码引用' }
    git -c $config push --atomic $target @refspecs
}
if ($LASTEXITCODE -ne 0) { throw 'CNB 源码同步被拒，须维护者检查分叉；禁止强推' }
