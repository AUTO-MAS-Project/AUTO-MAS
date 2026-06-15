# 脚本前端架构（专项适配分类）

在 AUTO-MAS 仓库语境下，**专项适配**按「外部脚本生态 + 本仓前端承接方式」区分。同一套 Hub / `EditView` / `types` / `useScriptApi` 是**共性**；**差异**在于外部程序的配置形态、是否走 ScriptConfig 会话、计划表与任务队列 UI 等。

---

## 四类前端架构（与现有类型对应）

| 架构代号 | 典型外部生态 / 心智模型 | 本仓 `ScriptType` 参照 | 前端承接特点 |
|----------|-------------------------|------------------------|----------------|
| **MXU 线** | [MaaEnd 项目](https://github.com/MaaEnd/MaaEnd)（MaaFramework）+ [MXU](https://github.com/MistEO/MXU)（PI V2 通用 GUI，`interface.json` / `config/`）；本仓读写 `mxu-*.json`、`__MXU_*` 任务 | `MaaEnd` | `MaaEndUserEdit`：遮罩 + WebSocket ScriptConfig；`SkylandConfigSection` 等；计划表 `MaaEndPlanTable` |
| **MFAA 线** | [M9A 项目](https://github.com/MAA1999/M9A)（MaaFramework 管线）+ 任务列表语义可对照 [MFAAvalonia / MFAA](https://github.com/trler/MFAA) 的 `interface.json`（resource / task / controller）；本仓 `ScriptType` = `M9A` | `M9A` | `M9AUserEdit`：`TaskQueueSection` + draggable；**无**典型 ScriptConfig 全屏遮罩；队列与 scheduler 横切多 |
| **MAA 线** | MAA 系：关卡、理智、计划、MAA 配置会话 | `MAA` | `MAAUserEdit`：遮罩 + ScriptConfig；`StageConfigSection`；`MaaPlanTable` |
| **SRC 线** | Alas / SRC 系（如 [StarRailCopilot](https://github.com/LmeSzinc/StarRailCopilot)：下一代 Alas、`tasks`/`webapp`/`config` 形态）；本仓对接 **SRC.exe 系**可执行体 | `SRC` | `SRCScriptEdit` 单文件大表单；`SRCUserEdit` + Section；详见 [examples-src.md](./examples-src.md) |
| **General** | 非专项：通用路径/进程/日志 | `General` | `GeneralScriptEdit` / `GeneralUserEdit`；作兜底或渐进专项化的起点 |
| **ok-script 线** | [ok-script](https://github.com/ok-oldking/ok-wuthering-waves) 系（如 **OK-WW**）：Python + 自带 GUI，`configs/`，README 提供 **`-t` / `-e` CLI** | 落地前可用 `General`；目标 `Okww`（规划） | 对齐 **General + 启动参数自启** + **ScriptConfig 调 exe**；见 [examples-okww.md](./examples-okww.md) |

> **命名说明**：「MXU 线」「MFAA 线」指**本仓已落地的对接形态**（MaaEnd / M9A）；「ok-script 线」指**非 MAA/SRC/MXU/MFAA**、但 CLI/GUI 形态清晰的 ok-script 项目（OK-WW 为首选案例）。

---

## 专项适配之间的**相同点**（不论哪条线）

1. **入口一致**：`ScriptType` → `Scripts.vue` / `ScriptTable.vue` → `router` 片段（`maa` / `src` / `maaend` / `m9a` / `general`）。
2. **表面骨架一致**：`EditView/Script/XxxScriptEdit.vue` + `EditView/User/XxxUserEdit.vue` +（按需）`views/XxxUserEdit/*Section.vue`。
3. **类型与 API 扩展一致**：`types/script.ts`、`useScriptApi.ts`、`SCRIPT_BOOK` / `USER_BOOK`、`task_manager` 分支；**禁止手改** OpenAPI 生成模型目录。
4. **一次打通**：Hub + 路由 + 编辑页与后端注册、任务模块同 PR，避免「只有 task 没有 EditView」。

---

## 专项适配之间的**不同点**（按架构线对比）

| 维度 | MAA 线 | SRC 线 | MXU 线（MaaEnd） | MFAA 线（M9A） |
|------|--------|--------|-----------------|----------------|
| 脚本编辑页 | 中等复杂度 | **单文件大表单**为主 | 中等 | 相对较薄 |
| 用户页 ScriptConfig 遮罩 | **有**（MAA 配置会话） | 通常无 | **有**（MaaEnd 配置会话） | **通常无** |
| 计划表 | `MaaPlanTable` | 无 | `MaaEndPlanTable` + `MaaEndPlanConfig` | 无 |
| 任务/队列 UI | 关卡、理智等 Section | Stage 等 | `TaskConfigSection`、Skyland 等 | **任务队列 JSON**、`TaskQueueSection`、draggable |
| 后端侧重 | MAA 进程与实例 | SRC.exe / Alas 任务栈、notify、模拟器与 Stage | `runtime_bridge`、MXU 配置路径、切号 | 管线、实例目录、队列消费 |
| 参照 PR 心智 | MAA 历史 PR | #727aafb SRC | #133、#152 MaaEnd | #154 M9A |

---

## 确认架构后：自启动方案与配置落盘方案（Agent 必排）

架构线与用户对齐后，**再回到上游仓库**（或本地等价物）查清**启动参数 / 命令行**与**配置入口**，再落 AUTO-MAS 设计。两件事拆开想：

| 问题 | 要决定的产物 |
|------|----------------|
| **启动后如何自动跑任务** | 是否拼 `argv`、`open_process(exe, *args)`；或只启动 `exe`、靠**预写配置文件**触发「启动后自动执行」；壳层是否有 `--autostart` / `--quit-after-run` 等（示例：[MXU README](https://github.com/MistEO/MXU)）。 |
| **用户改专项配置如何持久化** | 仅 **AUTO-MAS 写 JSON + schema**（无原生配置 UI）；或 **ScriptConfig / 子进程** 调起**脚本本体**保存；或 **SRC 式大表单**直接映射到磁盘。 |

### 按架构线的常态（本仓已落地）

| 架构线 | 自动跑任务（典型） | 用户专项配置（典型） |
|--------|-------------------|----------------------|
| **MFAA 线（`M9A`）** | 上游**不宜依赖**「一条 CLI 就把本次队列跑完」；`AutoProxy` **写**助手目录下任务/运行 JSON，再 `open_process(exe)`，由程序读盘并按内置逻辑执行（与 MFAA/M9A 文档中的**启动后自动运行**类行为一致）。 | **不**通过 ScriptConfig 调起 Avalonia 壳；用户在 Vue 的 `TaskQueueSection` 等改 `M9AUserConfig`，后端写盘。详见 [examples-m9a.md](./examples-m9a.md)。 |
| **MXU 线（`MaaEnd`）** | `mxu-*.json` 等可设 **`autoRunOnLaunch` / `autoStartInstanceId`** 等，与 [MXU](https://github.com/MistEO/MXU) 壳语义对齐；必要时可对照其 **CLI**（`--autostart`、`--instance`、`--quit-after-run`）是否在 AUTO-MAS 中要拼进启动行。 | 复杂项常 **ScriptConfig** 拉起 `MaaEnd.exe` 会话保存；日常字段在 Section + `runtime_bridge` / 用户目录同步。详见 [examples-maaend.md](./examples-maaend.md)。 |
| **MAA 线** | 依 MAA 文档与现有 `MAA` 任务；常见 **ScriptConfig** 路径。 | **ScriptConfig** 调 MAA 本体 + 关卡/plan 等 Section。 |
| **SRC 线** | 依 `SRC.exe` 与 Alas/SRC 文档（`module`/`config` 等）。 | 多为 **大表单 + Section** 写映射配置；按需是否子进程。参见 [examples-src.md](./examples-src.md)。 |
| **General** | 先最小 `open_process` + 日志；再按上游补 argv。 | 通用路径与简单字段；专项化后再分叉。 |
| **ok-script 线（如 OK-WW）** | README：**`-t N -e`** 自动跑第 N 个任务并退出；`AutoProxy` 拼 CLI，**不要**套 M9A 写盘无参启动。 | **ScriptConfig** 拉起 `ok-ww.exe`（无 `-t`/`-e`）改 GUI / `configs/`；用户级只选任务序号等。详见 [examples-okww.md](./examples-okww.md)。 |

> **建议实施顺序（避免污染通用脚本）**：先用 `General` 验证对接可行 → 再新增 `Okww` 专项类型承载默认值与 UI → 最后删除 `General` 页中的临时预设入口。

新专项若仓库 README **没有任何 CLI**，且外置 GUI 为 **MFAAvalonia**，优先按 **MFAA 线** 审：避免臆造启动参数，改为**文件契约 + 设置项**（与 M9A 一致）。  
若 README 有 **`-t` / `--task`** 一类参数且基于 **ok-script**，优先 **ok-script 线**，勿判为 MFAA 线。

---

## 新专项适配前：脚本架构问诊（Agent 必做）

**推荐顺序**：先请用户给出**脚本或 GUI 壳的 Git 仓库 URL** → Agent 读仓库后**给出架构线判断摘要** → 用户**确认或纠错** → 再改 AUTO-MAS。用户不便给仓库时再改用下方「口述问诊」。

### Agent 读仓库时建议捕捉的信号

| 若仓库中出现… | 倾向架构线 | 备注 |
|---------------|-----------|------|
| README/依赖写明 **MXU**、**PI V2**、`interface.json`，或顶层 **Tauri** + **React/TS**（类 [MXU](https://github.com/MistEO/MXU)） | **MXU 线**（本仓常对齐 `MaaEnd`） | 区分：壳仓 vs 纯资源/agent 的游戏项目仓（如 [MaaEnd](https://github.com/MaaEnd/MaaEnd) 可能多仓协作） |
| **Avalonia** / **MFAA**、`interface.json` 且 C# 客户端，或文档指向 [MFAA](https://github.com/trler/MFAA) 任务语义 | **MFAA 线**（本仓对齐 `M9A`） | 与 MXU（Tauri）勿混 |
| **Alas** / `webapp` / `module` / `tasks` 等经典 SRC 布局，或明确 **SRC.exe** 生态 | **SRC 线** | 对照 [examples-src.md](./examples-src.md) |
| 对外说明为 **MAA** 助手、关卡/理智/方舟生态 | **MAA 线** | 仍以用户最终说明为准 |
| 仅脚本/自动化、`config` 简单、无上述专项 GUI | **General** 或后续再专项化 | |
| **`from ok import OK`**、`ok-script`、`ok-ww.exe`、README 含 **`-t` / `-e`**（如 [OK-WW](https://github.com/ok-oldking/ok-wuthering-waves)） | **ok-script 线** | 非 Maa/SRC/MXU/MFAA；见 [examples-okww.md](./examples-okww.md) |

可配合：`package.json` 脚本名、是否有 `src-tauri`、`go`/`python` 为主的游戏管线目录、Release 资产中的 exe 名称。读不到或私有不开放时，走口述问诊。

### 与用户对齐结论前还须问清（可合并进同一条回复）

1. **`ScriptType` 字面量**（在 AUTO-MAS 中的正式类型名，与路由片段、目录名一致）。  
2. **外部程序形态**：单 exe、目录+多实例、是否要本仓 **ScriptConfig** 拉起外置配置会话。  
3. **是否复用**：计划表、任务队列 UI、通知 Section 等是否对齐现有 `MAA` / `MaaEnd` / `M9A` / `SRC`。  
4. **自启动与配置落盘**（确认架构后**回到仓库**查 README、`--help`；亦见上文「确认架构后：自启动与配置落盘」）：有无 CLI/自启动参数；自动跑靠 **写 JSON** 还是 **拼 argv**；改配置是 **仅 AUTO-MAS 表单单写盘** 还是 **调脚本本体**。**MFAA 线**勿臆造「启动参数传队列」。

### 无仓库时的口述问诊（备选）

请用户勾选或说明：

1. **脚本前端架构归属**（必选其一或说明混合）  
   - [ ] **MAA 线**  
   - [ ] **SRC 线**（同框架扩展见 [examples-src.md](./examples-src.md)）  
   - [ ] **MXU 线**（[MaaEnd](https://github.com/MaaEnd/MaaEnd) + [MXU](https://github.com/MistEO/MXU)）  
   - [ ] **MFAA 线**（[M9A](https://github.com/MAA1999/M9A) + [MFAA](https://github.com/trler/MFAA)）  
   - [ ] **仅 General 起步**  
   - [ ] **混合**（请说明）

2. 同上一节 1～3。

未与用户对齐架构结论前，**不猜测**为 M9A 或 MaaEnd；确认后再打开 `examples-*.md` 与 `guide.md` 中的具体清单。

---

## 选型速查（确认架构后）

| 用户选择 | 优先打开的案例 / 表面 |
|----------|------------------------|
| MFAA 线 | [examples-m9a.md](./examples-m9a.md)（含 [M9A](https://github.com/MAA1999/M9A) / [MFAA](https://github.com/trler/MFAA) 对照）、`M9AUserEdit`、`TaskQueueSection` |
| MXU 线 | [examples-maaend.md](./examples-maaend.md)（含 [MaaEnd](https://github.com/MaaEnd/MaaEnd) / [MXU](https://github.com/MistEO/MXU)）、遮罩 + `MaaEndPlanTable`（若需计划） |
| MAA 线 | `MAAUserEdit`、`MaaPlanTable`、`MAAScriptEdit` |
| SRC 线 | [examples-src.md](./examples-src.md)、`SRCScriptEdit.vue` |
| General | `GeneralScriptEdit` / `GeneralUserEdit`，再逐项专项化 |
| ok-script 线（OK-WW） | [examples-okww.md](./examples-okww.md)；过渡期用 `General` + `-t`/`-e` |

更多表面对照见 [examples-frontend-surfaces.md](./examples-frontend-surfaces.md)。
