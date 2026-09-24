# 本地打包

使用 PowerShell 7。随桌面安装包分发的 Runtime 版本独立记录在
`res/runtime-version.txt`。Runtime 有自己的发布节奏，因此这里钉死具体版本、不追 `latest`；
需要升级时，先发布并完成联调，再在要构建的分支更新该文件。CI 会从本次构建所选分支读取版本，
并拒绝缺少后台更新协议的二进制，防止生成无法正常启动的安装包。
bump 该文件后，已装用户在下次本体更新时会先换到这一版、再更新源码：桌面端在跑 `bootstrap`
之前（首次初始化与本体更新都是）到目标发布分支上读这份文件（CNB 与 GitHub 并行、先到先用），
与 exe 自报的版本不一致就下载替换（exe 首选 CNB，再 gh-proxy，GitHub 官方兜底；期望哈希只从
GitHub / CNB 的 `SHA256SUMS.txt` 取，代理只负责下 exe）；每次 managed 启动还会按
`<app-root>/repo/res/runtime-version.txt` 兜底核对一次。所以 bump 之前请确认那版 Runtime 能配合
要构建的分支启动。

本地验证可直接使用本次源码构建的 Runtime，不必等待 Release：

```powershell
Set-Location D:/Github/AUTO-MAS-Runtime
$env:GOCACHE = Join-Path $env:TEMP 'auto-mas-runtime-verify'
go build -buildvcs=false -o bin/auto-mas-runtime.exe ./cmd/auto-mas-runtime
if ($LASTEXITCODE -ne 0) { throw 'Runtime build failed' }

Set-Location D:/Github/AUTO-MAS
pwsh -NoProfile -File scripts/build-local-package.ps1 `
  -LocalRuntimePath D:/Github/AUTO-MAS-Runtime/bin/auto-mas-runtime.exe `
  -VerifyRuntimeOnly -SkipInstall
if ($LASTEXITCODE -ne 0) { throw 'Runtime verification failed' }
```

去掉 `-VerifyRuntimeOnly` 后执行完整本地打包。脚本校验源码版本一致性、Runtime SHA-256、
`workspace stage` 和 `bootstrap --if-needed`，然后生成携带指定 Runtime 的安装包和解压目录。
`-SkipInstall` 仅适用于前端依赖已经安装的环境；脚本不会发布或上传安装包。

**运行 `-LocalRuntimePath` 打出来的包时必须设置 `AUTO_MAS_RUNTIME_EXE`。** 桌面端在初始化
与本体更新之前会按目标发布分支上的 `res/runtime-version.txt` 核对 exe 自报的版本，每次
managed 启动还会按 `<app-root>/repo/res/runtime-version.txt` 再核对一次；本地构建的 Runtime
自报 `dev`，与钉扎不一致就会被下载的发布版原地覆盖——之后跑的就不是你要验证的那一份了。
钉扎来自发布分支，安装包不带 `res/runtime-version.txt`，所以打包脚本改不了它；唯一的逃生口
是让桌面端认出这是开发者自带的 Runtime：

```powershell
$env:AUTO_MAS_RUNTIME_EXE = 'D:/Github/AUTO-MAS-Runtime/bin/auto-mas-runtime.exe'
& 'D:/Github/AUTO-MAS/dist/AUTO-MAS-<版本>-local-<时间戳>/win-unpacked/AUTO-MAS.exe'
```

变量要出现在 `AUTO-MAS.exe` 的进程环境里，所以要**从设置了它的管理员 PowerShell 启动**：
双击图标不算，从普通终端启动也不算——`AUTO-MAS.exe` 的清单是 `requireAdministrator`，
未提权时会经 UAC 重新拉起，提权后的进程拿不到调用方的环境变量。
桌面端用它指向的 exe 启动 Runtime，并跳过随本体更新。

运行行为：managed 模式启动后首次检查当前 release 分支，之后每 10 分钟检查一次；
发现更新就后台下载，完成后标题栏提示下次启动生效。下载不改变当前后端和环境；
下次启动替换仓库并同步所需依赖。无更新时跳过依赖同步。依赖同步失败仍需通过已有修复入口重试。
