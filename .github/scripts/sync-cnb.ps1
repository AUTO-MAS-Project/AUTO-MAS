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
    git fetch --no-tags origin
    if ($LASTEXITCODE -ne 0) { throw '拉取源码失败' }
    git fetch --no-tags origin 'refs/tags/v*:refs/tags/v*'
    if ($LASTEXITCODE -ne 0) { throw '拉取版本 tag 失败' }
    $refspecs = @(git for-each-ref '--format=%(refname)' refs/remotes/origin | Where-Object { $_ -ne 'refs/remotes/origin/HEAD' } | ForEach-Object {
        "$($_):refs/heads/$($_.Substring('refs/remotes/origin/'.Length))"
    })
    $refspecs += @(git tag --list 'v*' | ForEach-Object { "refs/tags/$($_):refs/tags/$_" })
    if ($refspecs.Count -eq 0) { throw '没有可同步的源码引用' }
    # 历史分叉只影响该引用，不能把 dev 和新 release 的同步一起挡住。
    $rejected = @()
    foreach ($refspec in $refspecs) {
        git -c $config push $target $refspec
        if ($LASTEXITCODE -ne 0) {
            $rejected += $refspec.Split(':', 2)[1]
            $global:LASTEXITCODE = 0
            Write-Warning "CNB 拒绝 $($rejected[-1])，继续同步其他引用，禁止强推。"
        }
    }
    if ($rejected.Count -gt 0) { throw "CNB 部分引用同步被拒：$($rejected -join ', ')；其余引用已处理，须维护者检查分叉" }
}
if ($LASTEXITCODE -ne 0) { throw 'CNB 源码同步被拒，须维护者检查分叉；禁止强推' }
