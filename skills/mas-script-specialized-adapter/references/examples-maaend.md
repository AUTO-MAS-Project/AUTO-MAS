# 案例：MaaEnd 专项适配（MXU 线）

**架构线**：MXU 线 —— **MaaFramework PI V2** 生态 + **MXU 通用 GUI** 承载配置与会话；本仓 `ScriptType` = `MaaEnd`。  
**上游仓库**（读源码 / 排障时对照）：

| 仓库 | 角色 | 技术栈 / 要点 |
|------|------|----------------|
| [**MaaEnd**（终末地小助手）](https://github.com/MaaEnd/MaaEnd) | 游戏侧 **MaaFramework 项目本体** | Python / Go / C++ 等；`agent/`、`tools/`、`assets/`；README：**Powered by MaaFramework & MXU**；发行目录含 `MaaEnd.exe` 与资源 |
| [**MXU**（MaaFramework Next UI）](https://github.com/MistEO/MXU) | **PI V2 通用 GUI 客户端** | Tauri + React + TypeScript；解析 `interface.json`（支持 **PI v2.5**）；任务拖拽排序、多实例、controller（Adb/Win32/PlayCover 等）、用户配置在 `config/` |

> **命名区分**  
> - **MXU**：可对接任意符合 PI V2 的 Maa 项目的**外置图形界面**（`mxu.exe` + `maafw/` + `interface.json` + `resource/`）。  
> - **MaaEnd**：某一具体游戏助手仓库；AUTO-MAS 里 **`MaaEnd` 类型**指「按本仓已落地的 **MXU 线** 对接 **MaaEnd.exe 生态**」。  
> - 本仓常见落盘：`config/mxu-MaaEnd.json`、任务名前缀 `__MXU_*`（与 MXU 内置任务约定一致）。

新专项若为 **另一款 PI V2 + MXU 壳** 的游戏助手，先确认是否仍走 **MXU 线**（遮罩 + ScriptConfig + `mxu-*.json`），再决定复制 `MaaEnd` 还是新建 `ScriptType`。

---

## 已合并 / 相关 PR

| PR | 说明 |
|----|------|
| [#133](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/133) | 全量：表面对接 + 任务链路 |
| [#152](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/152) | 计划表表面 + `MaaEndPlanConfig` |
| [#165](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/165) | hotfix：字段名等 |

---

## 上游概念 ↔ AUTO-MAS（排障用）

### [MaaEnd 仓库](https://github.com/MaaEnd/MaaEnd)

- **管线与资源**：任务逻辑在 MaaFramework 资源与 agent 中；AUTO-MAS **不实现识别节点**，负责进程、目录、`mxu-MaaEnd.json` 读写、`runtime_bridge` 等。
- **可执行体**：`MaaEnd.exe`（路径在 `manager.check` 与 `SRCScriptEdit`/`MaaEndScriptEdit` 中校验）。
- **与 MXU 关系**：官方 GUI 由 MXU 提供；用户也可在 MXU 里直接改配置。AUTO-MAS 通过 **ScriptConfig 任务 + 全屏遮罩** 引导「去外置 UI 配完再保存」，与在 MXU 里手动改 `config/` 目的一致、入口不同。

### [MXU 仓库](https://github.com/MistEO/MXU)

README 与目录结构要点：

| MXU 侧 | AUTO-MAS MaaEnd 侧 |
|--------|-------------------|
| `interface.json` + `resource/`（PI V2 / v2.5） | 不内嵌 MXU 前端；字段映射在 `MaaEndConfig` / `MaaEndUserConfig` |
| `config/` 用户实例配置 | `data/{scriptId}/{userId}/` 与 `Default/ConfigFile`；`ScriptConfig` 写回 |
| 任务列表可视化、拖拽排序 | 用户页 `TaskConfigSection` 等（业务字段），非 1:1 复刻 MXU UI |
| `mxu.exe` + `maafw/` 运行库 | AUTO-MAS 启动的是 **MaaEnd.exe** 及其目录布局，但读写 **`mxu-MaaEnd.json`** 与 `__MXU_*` 任务名 |
| 多 controller：Adb / Win32 / PlayCover / Gamepad | `Game.ControllerType`、模拟器配置与 `manager.check` |
| 定时任务、实时截图、Agent 日志 | 调度在 AUTO-MAS 队列/计划表；日志走 `LogMonitor` |

**结论**：读 **MaaEnd** 弄清游戏任务与资源版本；读 **MXU** 弄清 **PI 协议、interface.json、config 目录语义**。AUTO-MAS 用 **Vue 表面 + WebSocket ScriptConfig** 承接，**不打包** Tauri/React 的 MXU 应用。

### 启动后自动跑 vs 用户改配置（与 MFAA 线对照）

| 维度 | MXU 线（本仓 `MaaEnd`） | MFAA 线（`M9A`） |
|------|-------------------------|------------------|
| **代理/调度启动** | `set_maaend` 等在 **`mxu-MaaEnd.json`** 写入 **`autoRunOnLaunch`、`autoStartInstanceId`** 等，再启动 `MaaEnd.exe`；可与 [MXU 文档](https://github.com/MistEO/MXU) 中的 **`--autostart` / `--quit-after-run`** 等 CLI 对照，决定是否在本仓拼启动参数。 | **写**助手目录任务 JSON 后启动 `exe`；**不依赖** CLI 传队列；见 [examples-m9a.md](./examples-m9a.md)。 |
| **用户改专项设置** | 常用 **ScriptConfig** 拉起 **MaaEnd.exe** 保存复杂项；其余 Section 写用户目录 / `runtime_bridge`。 | **仅** AUTO-MAS Vue + 后端写 `M9AUserConfig` / 任务文件；**不调** Avalonia 壳做配置会话。 |

---

## 前端表面（主路径）

| 表面 | 路径 / 说明 |
|------|-------------|
| UserEdit 编排 | `EditView/User/MaaEndUserEdit.vue` — ScriptConfig 遮罩、`useWebSocket` |
| Sections | `MaaEndUserEdit/BasicInfoSection`、`TaskConfigSection`、`SkylandConfigSection`、`NotifyConfigSection` |
| Header | `MaaEndUserEditHeader.vue` — 「配置 MaaEnd」 |
| ScriptEdit | `EditView/Script/MaaEndScriptEdit.vue` |
| Hub | `Scripts.vue` → `maaend`；列表「配置 MaaEnd」 |
| 计划表 | `plan/tables/MaaEndPlanTable.vue`（#152）、`planTypeRegistry` |

### 表面特有交互（MXU 线标志）

- **全屏遮罩**：`showMaaEndConfigMask` + `handleSaveMaaEndConfig`（类 MAA 配置会话，对象改为 MaaEnd/MXU）  
- **字段保存**：Section `@save` → `handleFieldSave`  
- **简洁模式**：用户级 vs `Default/ConfigFile`（与 `ScriptConfig`、MXU `config/` 语义对齐）

与 **MFAA 线（M9A）** 对比：MXU 线**有**该遮罩；MFAA 线以任务队列 JSON 为主、通常无此会话。

---

## 后端（实现层）

```
app/task/MaaEnd/          AutoProxy, ScriptConfig, manager, runtime_bridge
app/models/config.py      MaaEndConfig, MaaEndUserConfig
app/api/scripts.py        SCRIPT_BOOK
app/core/task_manager.py  MaaEndManager
```

### 本仓与 MXU 协议相关的落点（便于搜代码）

| 路径 / 符号 | 说明 |
|-------------|------|
| `config/mxu-MaaEnd.json` | MXU 侧实例配置 JSON；`AutoProxy` / `ScriptConfig` 读写 |
| `__MXU_*` 任务名 | 如 `__MXU_KILLPROC__`；与 MXU 内置选项约定一致（见 `app/utils/constants.py`） |
| `runtime_bridge` | 运行前生成/同步外置程序所需配置 |
| `MaaEnd.exe` | 进程启停、静默隐藏窗口等 |

---

## 常见检查（MaaEnd / MXU 线）

- [ ] Hub / 路由 / 遮罩 / Header「配置 MaaEnd」闭环  
- [ ] `MaaEnd.exe` 与 `config/mxu-MaaEnd.json` 路径校验（`manager.check`）  
- [ ] `Game.ControllerType` Win32 / ADB 与表单、MXU controller 类型一致  
- [ ] 计划表 consumer 与 `MaaEndPlanTable` 已注册（若做 #152 范围）  
- [ ] 上游 [MaaEnd](https://github.com/MaaEnd/MaaEnd) 发版后，核对 `mxu-MaaEnd.json` 字段与 `__MXU_*` 任务是否变更  

---

## 同框架新专项流程（MXU 线扩展）

适用于：**新游戏**仍发布为 `MaaEnd.exe` + `mxu-{Project}.json` + PI V2，或 fork [MaaEnd](https://github.com/MaaEnd/MaaEnd) 改资源。

1. **与用户确认**：外置 GUI 是 **MXU**（PI V2）还是误用 **MFAAvalonia**（C# `interface.json`）？后者更接近 **MFAA 线**，勿套 MXU 遮罩流程。  
2. **读上游**：[MaaEnd](https://github.com/MaaEnd/MaaEnd) 任务与目录；[MXU](https://github.com/MistEO/MXU) 的 `interface.json` / `config/` 说明。  
3. **本仓**：复制 `app/task/MaaEnd`、`MaaEndUserEdit` 表面 → 改 `ScriptType`、Hub、`mxu-*.json` 文件名常量。  
4. **计划表**：若游戏需要横切计划，参照 #152 `MaaEndPlanConfig`。

---

## 与 MFAA 线（M9A）选型对照

| 维度 | MXU 线（MaaEnd） | MFAA 线（M9A） |
|------|------------------|----------------|
| 外置 GUI | [MXU](https://github.com/MistEO/MXU)（Tauri+React，PI V2） | [MFAAvalonia](https://github.com/trler/MFAA)（Avalonia，interface.json） |
| 游戏项目 | [MaaEnd](https://github.com/MaaEnd/MaaEnd) 等 | [M9A](https://github.com/MAA1999/M9A) 等 |
| AUTO-MAS 用户页 | ScriptConfig **遮罩** + Section | **TaskQueueSection** + draggable，无典型遮罩 |
| 配置 JSON | `mxu-*.json` | `Task.Queue` / `AvailableTasks` 等 |

---

## 参照建议

外置 **MaaEnd.exe** + **MXU 配置会话** + 多 Section 用户页 → **首选本仓 MaaEnd 表面**；计划表参照 #152。  
若用户明确只有 **MFAAvalonia** 而无 MXU，改看 [examples-m9a.md](./examples-m9a.md)（MFAA 线）。
