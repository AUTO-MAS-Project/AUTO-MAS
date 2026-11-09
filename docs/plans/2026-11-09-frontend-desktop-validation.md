# 前端重构真实桌面验证记录

## 对象与隔离

2026-11-09 在 Windows 主工作区验证未提交的前端重构；分支为 `refactor/frontend-adapter-registry-20261108`，HEAD 为 `00e1e01766d624909ccbe8983b9efa4db3b7645f`。重构范围和此前发现的数字输入回归见[批次记录](2026-11-09-frontend-batch-refactor.md)。

使用 `yarn build --dir` 成功产出的 `frontend/dist/win-unpacked/AUTO-MAS.exe`，运行原始 EXE、ASAR、preload 和 `file:` 生产页面。没有使用浏览器 bridge 配置替身，没有替换 `loadConfig`、`saveConfig` 或文件读写实现。

每次运行由既有 `frontend/e2e/run.mjs` 创建临时根和 development 后端。整个桌面发行目录复制到临时根，前端配置随 EXE 目录隔离；另指定独立 `--user-data-dir`，提前写入 `current` 标记，跳过真实用户资料迁移。桌面使用 `--connect-existing-backend`，确认生产前端连接隔离的外部开发后端。关闭副本的遥测、自动更新、桌宠和启动选项，不启动游戏、真实账号、模拟器或计划。

实际配置样本来自仓库的 `config/frontend_config.json`，其版本标记为 `v5.8.0-beta.3`。该标记只能说明配置内容，不能证明运行了 beta.3 二进制。真实样本原来没有双音频或零音量，后续边界数据须单独标注。

## 当前包执行结果

命令从 `frontend/` 执行，仍通过项目唯一 E2E 启动器：

```powershell
yarn e2e --config debug/desktop-verification/playwright.config.ts
```

一次性本机脚本放在 Git 忽略的 `frontend/debug/desktop-verification/`，不加入默认浏览器套件或另建通用测试框架。当前包完整流程通过：测试体 12.6 秒，整条 Playwright 运行 21.1 秒，退出码 0。

| 场景 | 实际断言与结果 |
| --- | --- |
| 原始生产包与隔离 | `isPackaged=true`，真实 EXE/ASAR、userData/sessionData 均在临时根；页面为 ASAR 内的 `file:` 页面，环境为 production、后端归属为 external；复制前后 EXE/ASAR 哈希相同，包内 main 与本次构建产物相同 |
| 现有配置读取 | 通过真实 `load-config` IPC 读取 beta.3 标记及原音效预设、音量，值保留 |
| 保存及重启 | 界面修改启用、预设、音量，实际 JSON 变化；应用正常退出码 0，新进程从磁盘读回相同值 |
| 自定义音频 | 导入实际 7,982 字节 WAV，经真实文件读取 IPC 取得内容，调用原始媒体播放；收到可信的 `playing` 和 `ended`，时长 0.18 秒、readyState 4、无媒体错误 |
| 超限拒绝 | 实际 1,048,577 字节文件被拒绝，已保存的音效值及原路径不变 |
| 文件系统异常 | 临时把副本配置文件路径变为目录，触发真实文件系统错误，界面提示保存失败并回滚；恢复文件后重试成功，再次退出、启动仍读回成功值 |
| 五类脚本运行限制 | General、BetterGI、OkNte、Okww、ZzzOd 的真实打包表单将重试 0 修正为 1、清空硬时限恢复 120；逐字段 HTTP 补丁、公开 API 回读、真实 YAML 最终落盘和页面重载均一致 |

媒体验证只在系统文件选择对话框这一边界提供预定文件路径；后续 select-file、read-file-base64、save-config IPC、文件内容和播放均实际执行。媒体完成事件不等同于人工确认扬声器可闻。

文件系统异常发生在保存流程读取现有文件时；没有验证磁盘耗尽、权限拒绝或写入中断。YAML 保存沿用既有后台延迟落盘，验证以有界轮询等待实际文件内容，不把 HTTP 成功直接视为落盘完成。

## 原安装包替换与账号保存

在同一条桌面流程中补充 General 和 OkNte 账号编辑：前者的名称别名与后者的直接字段均通过真实输入、失焦保存，名称和备注各只发送对应的单字段补丁；公开 API、实际 `scripts.yaml` 的 `UserData` 及页面重载一致。它们覆盖两类保存调用，不代表九种专项的全部字段都已真实操作。OkNte 未配置上游安装路径，会出现其原生配置读取提示；本次只验收账号名称和备注，没有声称上游专项配置已可用。

之后实际运行 `D:/AUTO-MAS` 原安装目录中发行文件的隔离副本，再替换为本次构建：

1. 按新包发行结构收集 97 个文件，只从旧安装目录读取对应 EXE、ASAR、DLL、locales 和资源文件。不复制旧安装的 config、data、repo 或 Runtime，也不写入原安装目录。
2. 启动旧二进制，在旧界面导入两份实际 WAV，保存双音频模式、音量 0、两个文件名与路径，写入独立 Chromium profile 的验证标记，然后正常退出。
3. 保持相同临时 EXE 目录和 profile，只覆盖发行文件。替换前后配置文件字节及资料目录标记相同，新 EXE/ASAR 哈希与本次构建相同。
4. 启动新包，确认旧包保存的双音频、音量 0、名称、路径及 Chromium 验证标记全部保留，真实 `load-config` 读回相同值。
5. 预览继承的双音频，两个不同音源分别收到可信的 `playing`、`ended`，媒体音量均为 0；再用新包将音量保存为 0.05，正常退出，新进程完整读回。

双音频和零音量是本次用旧程序界面构造的边界样本，不冒充原配置本来就有这些值。新旧程序名义版本都为 `v5.8.0-beta.4`，没有修改版本号；实际 ASAR 不同：

| 发行对象 | ASAR SHA-256 |
| --- | --- |
| 原安装版副本 | `d79d6d630a743dafd63976741456d7d72540485043e47a9fe4aed67d11ffad2d` |
| 本次重构构建 | `a6f675a512ea4efb51a20e65e310d1c491d023fec6ab7073f36cba5d24bb0dbb` |

这条完整扩展流程已通过，包括两个音源的独立事件断言。最终截图版于本地 08:44:27–08:44:51 执行，测试体 23.8 秒、整条运行 31.7 秒，退出码 0；六个测试自有 Electron 主进程均正常退出码 0，五个临时托管脚本及两个账号已删除，公开 API 确认剩余脚本为 0。没有发现需要进一步修改生产逻辑的回归。

## 证据与校验

本机证据在 `frontend/debug/desktop-verification/`：

- `run-current.log`、`last-summary.json`：最终执行日志和逐步断言结果。
- `report/index.html`：最终 Playwright HTML 报告。
- `evidence/`：七张稳定命名截图，包括设置失败、重启回读、General 运行限制和账号、旧包双音频/零音量、新包继承及再保存回读。
- `current-pass/`、`upgrade-pass-01/`：此前通过的阶段报告。
- `harness-failure-01/` 至 `harness-failure-04/`：最初四轮中止记录，分别来自验收脚本的退出后进程对象读取、带图标按钮的可访问名、并存消息的严格定位、立即读取延迟落盘文件；修正脚本后重跑，没有因此修改生产逻辑。
- `cleanup.json`：测试临时目录清理被自动审批拒绝的原文及八个保留目录清单。

独立源保护记录在 `.dev/frontend-governance/20261109-desktop-validation/` 的 `source-snapshot.json` 和 `source-after.json`。08:46 再次核对：原始前端配置、新旧发行 EXE/ASAR 共五个文件 SHA-256 均不变；原有四个应用进程的 PID 和启动时刻均相同，36174/5174 无监听。原始配置 SHA-256 仍为 `ED9A11D5979B7D9F2E429C087A198F39099B12EF88E2365E995806EDE75477F2`。最终桌面流程未捕获页面异常。

## 临时目录清理状态

测试正常结束后，八个目录均确认属于本轮、直接位于 TEMP、没有 reparse point，也没有对应的运行进程。自动审批拒绝了已核实路径的批量递归删除；收窄为单个明确绝对路径的原生 PowerShell `Remove-Item -LiteralPath` 仍被拒绝。工具只返回 `rejected: blocked by policy`，没有更具体原因。已停止删除，没有改用其他方式绕过审查。

因此八个临时目录仍保留，原生日志与主要证据已另外归档。08:50 独立复核结果在 `.dev/frontend-governance/20261109-desktop-validation/cleanup-after.json`：对应进程为 0、测试端口监听为 0，保留目录的文件逻辑大小合计 3,712,660,812 字节（约 3.46 GiB）。此为文件残留，不是仍在运行的测试服务。

## 尚未覆盖

这次使用打包目录运行，尚不代表官方安装器升级或管理员系统功能通过。测试对子进程使用 `RunAsInvoker`；独立资料目录的 `current` 标记也意味着没有验证历史 userData 迁移。没有执行真实游戏或调度任务，没有操作系统文件选择窗口，也没有人工听音。
