# 本地打包与 Runtime 验证

本文说明如何在本地构建 AUTO-MAS 桌面验证包，以及如何联调本地源码编译的 Runtime。

## 快速开始

在仓库根目录使用 PowerShell 7 运行：

```powershell
pwsh -NoProfile -File scripts/build-local-package.ps1
```

生成的测试包首次初始化会拉取 `dev` 分支后端，之后按同分支更新流程跟进新提交；脚本不会自动发布或上传产物。

## Runtime 版本与更新策略

- **打包内置版本**：记录在 `res/runtime-version.txt`。CI 按该文件下载对应 Release 的 Runtime、校验 `SHA256SUMS.txt` 并打入安装包。内置版本**仅作离线兜底**。
- **完整初始化时的版本决策**：首次安装、本体更新及初始化重试时，应用会在 `bootstrap` 之前解析线上最新 Runtime（CNB 优先、GitHub 兜底；哈希校验只取官方 `SHA256SUMS.txt`）。仅当线上版本高于本地时替换，日常启动不检查 Runtime 更新。
- **后端自动更新（managed 模式）**：启动后首次检查当前后端分支，之后每 10 分钟检查一次。发现新提交后后台下载并在标题栏提示「下次启动生效」，下次启动时再替换仓库并同步依赖。

## 联调本地编译的 Runtime

可以先编译本地 Runtime 并做快速校验，无需等待官方 Release：

```powershell
# 1. 编译本地 Runtime
Set-Location <AUTO-MAS-Runtime 路径>
$env:GOCACHE = Join-Path $env:TEMP 'auto-mas-runtime-verify'
go build -buildvcs=false -o bin/auto-mas-runtime.exe ./cmd/auto-mas-runtime
if ($LASTEXITCODE -ne 0) { throw 'Runtime build failed' }

# 2. 仅校验 Runtime 能力与打包前置条件（不生成完整安装包）
Set-Location <AUTO-MAS 路径>
pwsh -NoProfile -File scripts/build-local-package.ps1 `
  -LocalRuntimePath '<AUTO-MAS-Runtime 路径>/bin/auto-mas-runtime.exe' `
  -VerifyRuntimeOnly -SkipInstall
if ($LASTEXITCODE -ne 0) { throw 'Runtime verification failed' }
```

去掉 `-VerifyRuntimeOnly` 即执行完整本地打包（校验源码版本一致性、Runtime SHA-256、alpha 后端能力、`workspace stage` 与 `bootstrap --if-needed`，并输出安装包与解压目录）。`-SkipInstall` 仅在前端依赖已安装时使用。

## 运行本地验证包的注意事项

运行带 `-LocalRuntimePath` 打出的验证包时，**必须设置 `AUTO_MAS_RUNTIME_EXE` 并从管理员 PowerShell 启动**：

```powershell
$env:AUTO_MAS_RUNTIME_EXE = '<AUTO-MAS-Runtime 路径>/bin/auto-mas-runtime.exe'
& '<AUTO-MAS 路径>/dist/AUTO-MAS-<版本>-local-<时间戳>/win-unpacked/AUTO-MAS.exe'
```

原因如下：

1. 本地编译的 Runtime 自报版本为 `dev`；若不设置 `AUTO_MAS_RUNTIME_EXE`，下次完整初始化时会被线上最新版原地覆盖。设置该变量后，桌面端会直接启动指定 exe 并跳过随本体更新。
2. `AUTO-MAS.exe` 的清单要求 `requireAdministrator`。双击图标或从普通终端启动会触发 UAC 重新拉起，导致子进程丢失普通终端里的环境变量。
