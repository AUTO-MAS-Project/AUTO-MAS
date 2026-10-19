# 本地打包

使用 PowerShell 7。随桌面安装包分发的 Runtime 版本记录在 `res/runtime-version.txt`，它只是
**打包时内置的那一版**：CI 从本次构建所选分支读取它，下载对应 Release 的 exe、按同一 Release
的 `SHA256SUMS.txt` 校验后捆绑进安装包，并拒绝缺少后台更新协议的二进制。内置版本只用于离线
兜底；用户机器上实际运行哪一版由应用在**完整初始化**时决定。

完整初始化（首次安装、本体更新及初始化重试）会在跑 `bootstrap` 之前，从 CNB / GitHub 的
Release 列表解析线上最新版本（CNB 优先、GitHub 兜底），比现有 exe 新就下载替换（exe 首选 CNB，
再 gh-proxy，GitHub 官方兜底；期望哈希只从 GitHub / CNB 的 `SHA256SUMS.txt` 取，代理只负责下
exe）。只升不降：本地版本更高时保留本地。日常直接启动不检查、不更新 Runtime。

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

**运行 `-LocalRuntimePath` 打出来的包时必须设置 `AUTO_MAS_RUNTIME_EXE`。** 桌面端在完整初始化
（首次安装、本体更新）时会解析线上最新 Runtime，比现有 exe 新就替换；本地构建的 Runtime 自报
`dev`，不设置这个变量就会在下次完整初始化时被线上最新版原地覆盖——之后跑的就不是你要验证的
那一份了。安装包内置的 `res/runtime-version.txt` 只决定兜底版本，改不了这个行为；唯一的逃生口
是让桌面端认出这是开发者自带的 Runtime（它连版本都不解析、直接启动）：

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
