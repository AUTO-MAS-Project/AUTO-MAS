# 本地打包

使用 PowerShell 7。后台更新需要桌面和 Runtime 同时使用新代码；当前工作流固定的旧 Runtime
版本尚未包含该能力，发布前须先发布新 Runtime，再更新 `.github/workflows/build-app.yml`
的 `RUNTIME_VERSION`。CI 会拒绝缺少后台更新协议的二进制，防止生成无法正常启动的安装包。

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

运行行为：managed 模式启动后首次检查当前 release 分支，之后每 10 分钟检查一次；
发现更新就后台下载，完成后标题栏提示下次启动生效。下载不改变当前后端和环境；
下次启动替换仓库并同步所需依赖。无更新时跳过依赖同步。依赖同步失败仍需通过已有修复入口重试。
