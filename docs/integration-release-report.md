# AUTO-MAS v6 Experimental Alpha（NEXUS OVERDRIVE）r6 发布报告

日期：2026-07-23

分支：`integration/dev-v2-dev-all-plugins`

宿主基线：`upstream/dev_v2@b5e872815a3ea5eef81fc3fd34eb0dc71db32d4e`
`upstream/dev@e012f284374021e227f3d85e822df612b248b345` 已确认是该 dev_v2 基线的祖先。

## 结论

产品展示版本为 `v6.0.0-alpha.NEXUS-OVERDRIVE.20260722.1`，Python/Core 兼容版本为 `6.0.0a1`。r6 是本轮按“最近稳定包”冻结的最终候选：源码集成、23 个插件 distribution、Windows x64 / CPython 3.12 wheel 闭包、洁净离线安装、21 个插件入口、真实后端/API、前端门禁、Electron 打包和最终 Full ZIP 初始化烟测均已通过。r5 真实 GUI 日志暴露的插件页面声明 `401` 与退出态 WS 无效重连也已在 r6 修复并进入最终 ASAR。在当前定义的发布门禁内未发现已知 P0/P1 阻断项。

本报告不把“门禁通过”表述为所有设备与所有游戏环境中的绝对零缺陷。没有执行真实游戏账号、真实设备/模拟器或自动化任务 E2E；HSR、M9A、MAA、MaaFW、MaaEnd、MXU、OK 系列和 Browser 的本轮结论来自构建、导入、生命周期、资源、路由、API 与离线运行时验证。

## 可交付产物

产物根目录：`D:\trae_projects\AUTO-MAS-Projects\_alpha_build\a1\release-nexus-a1-r6\artifacts`。

| 产物 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `AUTO-MAS-Lite-v6.0.0-alpha.NEXUS-OVERDRIVE.20260722.1-x64.zip` | 346,914,760 | `D8690E124127A4447C623F48DBE435DF118812444B6F576163AE5FF190BD5B78` |
| `AUTO-MAS-Full-v6.0.0-alpha.NEXUS-OVERDRIVE.20260722.1-x64.zip` | 461,339,377 | `9F9E2EF8FB9E8D00FBD14F385AFB032FA5A1C7E8965468BF80F5E2D79A2FF941` |
| `AUTO-MAS-NEXUS-OVERDRIVE-6.0.0-alpha.NEXUS-OVERDRIVE.20260722.1-x64.exe` | 298,196,478 | `1845F7DCC2E8F1ED5A1D117B2CEE47B9B80E1C9B93D85DDBCD7C654B77464525` |
| `AUTO-MAS-NEXUS-OVERDRIVE-6.0.0-alpha.NEXUS-OVERDRIVE.20260722.1-x64.exe.blockmap` | 306,294 | `303EE1A3DFB2856F876CBE60585B343E7B9CDAB4A7200F96EC79352233E38016` |

r6 的 unpacked 主程序 `AUTO-MAS.exe` 为 204,679,168 字节，SHA-256 `2F038F940AEFCC4223322FFA2BEDA52662493628B190183C08D6438A6CCB2F2C`；`resources/app.asar` 为 61,004,775 字节，SHA-256 `873D021F151D8B25134F844896154026CD4A0A52E661E404B3DBA6BF179F3A53`。

Lite staging 有 724 个文件、600,395,398 字节；Full staging 及最终 ZIP 的全新解压副本均为 8,560 个文件、894,744,388 字节。Full 包包含 EXE、ASAR、集成快照、完整 wheelhouse 和官方运行环境，其中：

- uv SHA-256 为 `2773193FF0F378C8B0C7E1417FB35F63A50DBD9FA9A09174AEF7CCE313E7789E`；
- 官方 `environment.integration.zip` 来源 SHA-256 为 `CFA5FFF882B6C81BD90AABB9F5EF2B9A135C1D1CBAA6AC5B21222F549967190A`。

安装器的 Authenticode 状态为 `NotSigned`，Lite/Full ZIP 也未做数字签名；它们属于实验性 Alpha 测试产物，不应被描述为正式签名发行版。

## Wheelhouse

最终 c2 wheelhouse 的权威构建源位于 `build/w/c2`，打包后位于 `resources/integration-snapshot/plugins/wheels`：

- 127 个 wheel、131 个发布文件；
- 23 个插件 distribution、21 个唯一 `auto_mas.plugins` entry point；
- 31 个宿主直接依赖；
- 洁净运行时核对为 95/95 宿主依赖、32/32 插件依赖；
- 15/15 显式 no-config 契约有效配置为 `{}`；
- `manifest.json` SHA-256 `7123F7CA99A843E34C189F99744CECB568BD82A348B1457ED634438CECAD199B`；
- `runtime-lock.json` SHA-256 `8A1CA0B31634AE2E63E55440C34C3A38998E3D20F68CA55CB6E620DA94EF3069`；
- editable/source 回退为 0。

## 验证结果

### 源码与前端门禁

- 宿主回归测试：161 项通过；
- Config v2 聚焦测试：23 项通过；
- HSR/M9A/MaaFW 等插件专项测试：79 项通过；
- 前端 Vitest：174/174 通过；
- 前端 TypeScript typecheck 通过；
- ESLint 为 0 error，Electron `build:main` 通过。

### r6 前端生产修复

- `AppLayout.vue` 的启动快照 `POST /api/plugins/get` 改用 `authenticatedApiFetch`，不再绕过进程令牌；HTTP 认证定向测试 4/4 通过；
- `useWebSocket.ts` 在应用退出态收到 `1012` 时清理定时器、禁用新连接并跳过自动重连；对应纯函数回归已覆盖“退出态不重连/运行态仍重连”；
- 最终 renderer 中 `/api/plugins/get` 调用已解析到令牌注入 helper，最终 ASAR 解包内容与冻结的 renderer/main 逐文件 SHA-256 比对差异为 0；
- r5 GUI 会话其余告警均已复核为发布目录无 `.git` 的预期降级、页面离开时的 WS 断连或关闭期日志噪声，没有额外功能缺陷。

### `dependencyService` 的 Windows EPERM 修复

r4 的首次 Full 初始化在完成 staging 依赖校验后，Windows 短暂锁住 `.venv-stage-*`，导致 `renameSync` 抛出 `EPERM`；随后 `finally` 中的同步清理又抛出 `EPERM`，覆盖了更准确的主错误。对该 staging Python 的独立只读核对已确认 95/95 依赖匹配、无 mismatch 或 extra，因此这不是 wheelhouse 缺失。

r5 在 `frontend/electron/services/dependencyService.ts` 中加入以下有界恢复：

- 仅对 `EACCES`、`EBUSY`、`ENOTEMPTY`、`EPERM` 重试；
- 最多 10 次，按 100 ms 线性退避；
- rename/remove/recovery 改为异步等待；
- finally 清理失败不再掩盖主错误；
- 新增“两次 EPERM 后成功”的回归测试，聚焦测试 6/6 通过。

r4 与 r5 的 ASAR 精确比较只有 `dist-electron/services/dependencyService.js` 改变，最终 ASAR 中该文件与 r5 Electron 编译输出哈希一致；r6 继续包含该修复。

### 最终 Full ZIP 初始化烟测

最终 Full ZIP 解压到 `D:\trae_projects\AUTO-MAS-Projects\_alpha_build\a1\smoke-r6-auth-final`，对应 ASAR 解压到 `D:\trae_projects\AUTO-MAS-Projects\_alpha_build\a1\verify-r6-asar`。烟测直接执行最终 ASAR 中的初始化服务代码，并跳过后端启动以隔离依赖部署链：

- 总体结果 `success=true`；
- 集成快照部署 441.10 ms；
- 宿主运行时安装 12,352.16 ms；
- 插件运行时安装 7,405.77 ms；
- 宿主安装成功、插件安装成功；
- 安装插件 21，失败 0，warning 0，缺失运行时路径 0；
- active venv、插件 state 与 site-packages 均存在；
- 残留 `.venv-stage-*` 为 0，恢复 journal 不存在，烟测进程与 36163 监听均为 0。

### 后端启动速度与退出基准

最终证据：`D:\trae_projects\AUTO-MAS-Projects\_alpha_build\a1\benchmark-backend-r5-fixed-r2-result.json`。该基准明确分类为“同一 Windows 会话内的首次运行 + 4 次 warm”，不是重启系统后定义的严格 cold benchmark。

| 样本 | core ready | background ready | shutdown |
| --- | ---: | ---: | ---: |
| 同会话首次运行 | 3,793 ms | 6,615 ms | 472 ms |
| 4 次 warm 范围 | 1,539–1,545 ms | 1,884–1,996 ms | 405–520 ms |
| 4 次 warm 均值 | 1,541.75 ms | 1,962.25 ms | 437.5 ms |

5/5 样本均满足 owner contract、authenticated graceful shutdown、exit code 0、`error=null`。

早期基准脚本曾报告 `Backend PID ... exited with code `（退出码为空）。这不是已证实的产品退出故障，而是 Windows PowerShell 5.1 在重定向 stdout/stderr 时，带超时的 `WaitForExit(30000)` 已返回进程退出、但流完成与 `ExitCode` 发布尚未同步完成所造成的测试工具误报。fixed-r2 在确认进程退出后补充无参数 `WaitForExit()` 并刷新进程对象；随后 5/5 正常退出。旧失败记录保留用于审计，不计入产品失败样本。

### Config v2 边界

Config v2 当前仍以 shadow/preflight 模式运行，legacy JSON 保持权威写路径；事务、原子持久化、敏感字段加密与 outbox 锁已经验证，但尚未执行权威存储切换。`model_dump()` 向前端传输解密值属于当前设计预期，前提是明文不进入日志、磁盘或未认证通道。插件开发热重载尚未接入 Config v2 的 owner/generation 清理；当前插件未依赖该切换链，因此记为后续集成项，而不是本 Alpha 的 P0 阻断。

## 发布限制与保留现场

- 产物未签名；Windows 可能显示未知发布者提示；
- 未执行真实游戏账号、真实设备/模拟器或自动化任务 E2E；
- Config v2 仍是 shadow/preflight，legacy JSON 仍为权威；
- 启动基准不是重启系统后的严格 cold benchmark；
- 前端视觉重构不属于本轮冻结范围。

r4/r5/r6 打包目录、最终 ASAR 解包、Full ZIP 解压烟测、初始化结果、基准脚本及各轮日志均保留在 `D:\trae_projects\AUTO-MAS-Projects\_alpha_build\a1`，未删除或覆盖失败证据。本轮没有 commit、push、reset、stash drop 或清理备份。按用户要求，本轮在 r6 最近稳定包完成后停止，不继续前端重构或新增功能。

## 2026-07-23 启动与发布链差量收口

冻结的 r6 产物未被修改。本节只记录后续源码发布链的差量结果，不把本地审计等同于一次新的正式发布。

- 集成发布命令新增 `--dry-run` 和 `--unpacked-only`。命令计划始终使用参数数组与 `shell: false`，保留含空格路径，并为 TypeScript、wheelhouse 校验、renderer 构建和 Electron 打包分别设置 5、10、10、45 分钟硬超时；超时会终止子进程树。
- `build-app.yml` 不再假定 Git checkout 自带本地 `plugins/wheels`。手动发布必须提供 HTTPS wheelhouse ZIP 与其 SHA-256；Actions 先核对归档哈希，再由 snapshot contract 对解压内容执行逐 wheel、runtime-lock、23 distribution、21 entry point、Core 版本和 marker 哈希校验。
- Actions 只生成 `win-unpacked` 作为 SignPath 主程序签名输入，再从同一 staging 生成 Lite/Full ZIP 与安装器，避免重复构建一个随后被丢弃的 Electron 安装器。所有 staging 引用统一到 `frontend/dist-package/win-unpacked`。
- Alpha 等任意 SemVer 预发布后缀现在会被标记为 GitHub prerelease，不再只有 `-beta` 才进入预发布签名/发布策略。
- 管理员重启不再把 EXE 路径和参数拼接进 PowerShell 源码；改为 `EncodedCommand`、已按 Windows argv 规则引用的环境传值和 `shell: false`，覆盖含空格、Unicode 与引号的安装路径/参数。生产包依据 `requireAdministrator` manifest 不再做冗余磁盘探测，开发态唯一文件探测也已移到窗口创建之后，不再阻塞首屏。
- 本地专项验证：Electron TypeScript `--noEmit` 通过；Electron/发布专项 Vitest 11 个文件、117 项通过；本次发布脚本定向 ESLint 通过；Actions YAML 可被 PyYAML 解析；含空格输出路径的只读 release dry-run 通过。

当前真实阻断仍然存在：工作树 `plugins/wheels` 是 125 wheels、`auto-mas-core 5.4.0b1`，而冻结 r6/c2 marker 要求 127 wheels、`auto-mas-core 6.0.0a1` 及对应 manifest/runtime-lock 哈希。严格校验按设计失败，不能把这套 125-wheel 目录打成 v6 通过包。权威 `build/w/c2` 对同一严格校验通过；在主线原子导入或重新构建 127-wheel wheelhouse 后，必须重新执行：

```powershell
node.exe frontend/scripts/validate-wheelhouse.mjs --wheelhouse '<权威 127-wheel 目录>' --require-snapshot-contract
```

尚未执行 GitHub Actions 真机运行、SignPath 签名、全新 Windows 虚拟机安装/卸载、SmartScreen、断网首启和真实重启后的 cold benchmark。因此这些仍是外部门禁；本节不宣称 clean-Windows、签名或正式发布已经通过。
