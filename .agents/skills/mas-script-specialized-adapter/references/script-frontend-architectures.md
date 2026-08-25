# 架构线判据

专项适配按「外部脚本生态 + 本仓前端承接方式」分线。Hub / `EditView` / `types` / `useScriptApi` 是**共性**；差异在配置形态、是否走 ScriptConfig 会话、计划表与队列 UI。

具体文件名、路由片段、Section 目录现场 `rg` 确认——本文件只记判据与陷阱。

## 定线（读上游仓库时的信号）

| 上游信号 | 架构线 | 本仓参照 |
| --- | --- | --- |
| `from ok import OK`、`ok-script`、README 含 `-t` / `-e` | **ok-script 线** | `Okww`（鸣潮）、`OkNte`（异环） |
| README/依赖写明 MXU、PI V2、`interface.json`，或 Tauri + React/TS 壳 | **MXU 线** | `MaaEnd` |
| Avalonia / MFAA，`interface.json` + C# 客户端 | **MFAA 线** | `M9A` |
| Alas / `webapp` / `module` / `tasks` 布局，或 SRC.exe 生态 | **SRC 线** | `SRC` |
| 对外说明为 MAA 助手、关卡/理智/方舟生态 | **MAA 线** | `MAA` |
| 同一游戏有多个成熟且功能重叠的上游，用户按任务挑用不同脚本 | **多引擎编排线** | `HSR` |
| 仅脚本自动化、config 简单、无上述生态 | **General** 起步，再专项化 | `General` |

辅助信号：`package.json` 脚本名、有无 `src-tauri`、Release 资产 exe 名、管线目录语言。

**易错处**：

- MXU（Tauri）与 MFAA（Avalonia）勿混。
- README 有 `-t` / `--task` 且基于 ok-script → **ok-script 线**，别判成 MFAA。
- 无任何 CLI 且外置 GUI 是 MFAAvalonia → **MFAA 线**，改走文件契约 + 设置项，**不要臆造启动参数**。
- 多引擎线是唯一「一对多」：先确认「按模块换引擎」是真实用户需求，单一上游即使复杂也不归此线。
- 壳仓 vs 纯资源/agent 仓要分清（可能多仓协作）。

**未与用户确认架构线前不猜类型、不动手。**

## 定线后必排的两件事

回到上游仓库查 `README` / `--help`，把两件事拆开想：

| 问题 | 产物 |
| --- | --- |
| 启动后如何自动跑任务 | 拼 `argv`？还是只启 exe、靠**预写配置**触发自动执行？壳层有无 `--autostart` / `--quit-after-run`？ |
| 用户改专项配置如何持久化 | 仅 MAS 写 JSON + schema？还是 ScriptConfig 调**脚本本体**保存？还是大表单直接映射磁盘？ |

各线常态：

| 线 | 自动跑 | 用户改配置 |
| --- | --- | --- |
| ok-script | 以子项目实际 CLI 为准；Okww / OkNte 当前均为 `-t N -e` | **按子项目分两路**：Okww 仅 ScriptConfig 遮罩调本体 GUI；OkNte 动态表单 REST + 遮罩并存 |
| MFAA（M9A） | **不宜依赖单条 CLI 跑完队列**；写任务/运行 JSON 再启 exe | 不用 ScriptConfig 调 Avalonia 壳；Vue 改 config、后端写盘 |
| MXU（MaaEnd） | `mxu-*.json` 可设 autoRun 类字段；必要时对照壳 CLI | 常 ScriptConfig 拉起本体会话；日常字段走 Section |
| MAA | 依 MAA 文档，常见 ScriptConfig 路径 | ScriptConfig 调本体 + 关卡/plan Section |
| SRC | 依 SRC.exe / Alas 文档 | 多为大表单 + Section 写映射配置 |
| HSR（多引擎） | 按模块先定引擎再分别调用；切号统一走 SRA | **无** ScriptConfig；托管字段后端下发前端动态渲染，直控导入加密快照 |
| General | 先最小 `open_process` + 日志，再按上游补 argv | 通用路径与简单字段 |

**实施顺序建议**：先用 `General` 验证对接可行 → 再新增专项 `ScriptType` 承载默认值与 UI → 最后删掉 General 页的临时预设入口。

## 与用户对齐时还须问清

1. `ScriptType` 字面量（与路由片段、目录名一致）。
2. 外部程序形态：单 exe / 目录多实例 / 是否需 ScriptConfig 拉起外置配置会话。
3. 是否复用计划表、队列 UI、通知 Section。
4. 自启动与配置落盘（见上表）。**MFAA 线勿臆造「启动参数传队列」。**

## 各线前端承接差异

| 维度 | MAA | SRC | MaaEnd | M9A | Okww | OkNte | HSR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 外部程序数 | 1 | 1 | 1 | 1 | 1 | 1 | **2** |
| ScriptConfig 遮罩 | 有 | 视需求 | 有 | 通常无 | 有（脚本级+用户级+直控） | **有，且另有 REST 动态表单** | **无** |
| 计划表 | 有 | 无 | 有 | 无 | 无 | 无 | 无 |
| 任务/队列 UI | 关卡理智 Section | Stage Section | TaskConfig + Skyland | **队列 JSON + draggable** | TaskIndex + 高频字段 | 动态表单（后端下发字段） | 后端下发托管字段动态渲染 |
| 后端侧重 | 进程与实例 | 任务栈、模拟器、Stage | runtime_bridge、MXU 路径、切号 | 管线、实例目录、队列消费 | 三态来源、working 备份恢复 | 半自动 schema、双通道配置 | 模块→引擎分配、双份配置备份、路径锁 |

## 前端表面通用约定

- **Hub 分支必须补全所有入口**（编辑脚本、加用户、编辑用户、创建脚本及复制）。漏一处即"列表能点、创建不能进"。路由片段字面量集中在创建流的 `EDIT_SEGMENT_BY_TYPE`。
- 延续既有 `if (script.type === …)` 链，**不抽 `routeByScriptType` 这类抽象**除非已有先例。
- 编排页只接线：`formData` + `handleFieldSave(group, key, value)` 局部更新；Section 收 `props` 发 `emit('save')`，**不直接调 API**。表单自然分块再拆，编排页不写数百行表单项。
- 用户 **add** 流程：先 `addUser` 再 `router.replace` 到带 `userId` 的路由。
- `useScriptApi` 要改**两处**分支（脚本类型 + UserConfig→users[]），漏后者列表 NO DATA。
- WebSocket 用既有 composable，不另造客户端。
- 展示文案与技术标识分离：文案可写 `ok-ww`，`ScriptType` / 路由 / OpenAPI 名保持 `Okww`。
- **禁止手改 OpenAPI 生成模型目录**；后端改 schema 后跑生成器。
- 后端下发字段定义的专项（HSR、OkNte），**新增字段扩展后端定义，不在 Vue 里加硬编码分支**。

**反模式**：为"支持所有 ScriptType"造动态表单引擎；只加后端 Manager 而不改 Hub（Hub + 路由 + 编辑页 + 后端注册 + 任务模块应同 PR 打通）。

## 与 General 的边界

General 是通用脚本表面 + `app/task/general/`，路径/日志模式通用。专项有独立 `EditView` 与 Section 目录，强绑定外部程序——**勿把专项 UI 塞进 General 编辑页**。

专项 schema 只在 UI/运行时契约确实不同且需收窄字段时才独立定义：不为改名复制 General 模型，不让 schema 暴露运行时未消费的字段。跨类型重构仅当已有多个真实调用者时才上提共用逻辑，专项差异保留在所属模块。
