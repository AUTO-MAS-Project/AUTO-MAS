# AUTO-MAS v6 Experimental Alpha 离线首次启动说明

> 状态：`unverified`。此文档提供手测流程，不把脚本结构检查、进程存活或单次日志视为离线可用的自动化证明。

## 适用范围

仅适用于独立的 Experimental Alpha **Full** 产物及其新建测试副本。不得用于冻结 r6、稳定安装目录、正在使用的用户数据目录或 Lite 包。

当前 Alpha 契约预期包含：

- `AUTO-MAS-v6-Experimental-Alpha.exe`；
- `resources/integration-snapshot/manifest.json`；
- `resources/integration-snapshot/source-provenance.json`；
- `resources/integration-snapshot/plugins/wheels/manifest.json` 与 `runtime-lock.json`；
- `environment/python/python.exe` 与 `environment/python/Scripts/uv.exe`。

实际目录必须以候选包内容为准。缺少任一项时，停止并记录失败，不要从稳定安装目录复制文件补齐。

## 前置条件

1. 核对 Alpha Full 便携 ZIP 的 SHA-256 与同一次构建的 `SHA256SUMS`。
2. 解压或复制到一个新的 A 测目录；目录内不得已有 `config`、`debug`、`logs` 等运行时数据。
3. 确认冻结 r6 目录不在本次测试路径中，且 r6 文件没有被改动。
4. 断开网络，或使用防火墙阻断测试目录中 Electron/Python 的出站连接；记录采用的方式。
5. 确认本机没有同名 Alpha 进程，且后端固定端口 `36163` 未被监听。不要终止无关进程来“让检查通过”。

## 结构预检与人工启动

若随包或受控测试材料提供了 `verify_offline_first_start.ps1`，可由测试者以实际文件路径执行下列形式的命令：

```powershell
& '<verify_offline_first_start.ps1 的实际路径>' -AppDir '<Alpha Full 的独立测试目录>' -AssumeOffline
```

该辅助脚本的预期职责是检查 Full 布局、wheelhouse/runtime lock、端口和进程冲突，并在启动窗口后要求人工完成初始化。它不会替代以下人工判断：

1. Alpha UI 是否出现并能完成首次初始化。
2. bundled snapshot 是否被使用，插件是否在无网络时显示可理解的状态。
3. 首页与基础导航是否可用，是否出现网络依赖失败或白屏。
4. 新生成配置/日志是否位于 Alpha 测试目录，且未触及 r6。
5. 退出后是否有残留进程、异常日志或不可恢复的配置状态。

## 结果记录

每次测试至少保存：

- 包文件名、SHA-256、来源记录和 runtime-lock 的路径/哈希；
- Windows 版本、网络隔离方式、测试目录；
- 预检控制台全文；
- 首次初始化截图、首页截图和本次新增日志；
- 成功、失败或中止的准确步骤，以及未验证项。

任何“离线可用”的结论都必须同时有结构预检和人工 UI 记录。网络未真正隔离、复用了已有配置、或没有保留日志时，结果只能记为 `unverified`。
