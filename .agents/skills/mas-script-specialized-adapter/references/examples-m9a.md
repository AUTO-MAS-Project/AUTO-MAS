# 案例：M9A 专项适配（MFAA 线）

**架构线**：MFAA 线 —— 以 **MaaFramework 管线 + 任务列表/队列** 为核心；本仓 `ScriptType` = `M9A`。  
**上游仓库**（读源码 / 排障时对照）：

| 仓库 | 角色 | 技术栈 / 要点 |
|------|------|----------------|
| [**M9A**（重返未来：1999 小助手）](https://github.com/MAA1999/M9A) | 游戏侧 **MaaFramework** 项目本体 | Python、`agent/`、`tools/`、`pyproject.toml`；README 标明由 **MaaFramework** 驱动；鸣谢中列出 **MFAAvalonia**、**MXU** 等 **外部 GUI**（与 AUTO-MAS 内 Vue 表面是不同壳） |
| [**MFAA**（MFAAvalonia）](https://github.com/trler/MFAA) | **MaaFramework 通用 GUI**（fork [MaaXYZ/MFAAvalonia](https://github.com/MaaXYZ/MFAAvalonia)） | Avalonia / C#、`MFAAvalonia/`、`interface.json` 声明 **resource / task / controller**；任务勾选、顺序、重复次数等与「任务列表」语义一致 |

> **命名区分**：GitHub 上的 **M9A** 仓库是**游戏助手项目名**；AUTO-MAS 里的 **`ScriptType` `'M9A'`** 表示「按本仓已落地的 **MFAA 线** 对接该生态」。排障时勿与 `MaaEnd`（MXU 线）混淆。

新专项若仍为 **MaaFramework + 任务队列 JSON** 形态，先与用户确认 **MFAA 线**，再对照本文 + 上游；若外置 UI 改为 **MXU（Tauri+React）** 而 AUTO-MAS 仍只接配置与进程，则评估是否更接近 **MXU 线**（`MaaEnd` 模式）而非本线。

---

## 已合并 / 相关 PR

| PR | 状态 | 说明 |
|----|------|------|
| [#154](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/154) | merged | 全量表面 + 后端 |
| [#183](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/183) | closed Draft | 用户编辑体验、预设（可单独 PR） |
| [#181](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/181) | closed Draft | 虚拟用户与自动更新 |

---

## 上游概念 ↔ AUTO-MAS（排障用）

### [M9A 仓库](https://github.com/MAA1999/M9A)

- **MaaFramework**：任务管线、资源、控制器（ADB/Win32 等）由框架与资源包约定；AUTO-MAS `app/task/M9A/` 负责**拉起、目录、日志、队列消费**，不重复实现识别节点逻辑。
- **`agent/`、`tools/`**：与 CLI/管线相关；对接时关注 **工作目录、实例路径、MuX** 等与 `manager.check`、前端路径提示一致。
- **文档**：README 链到「开发文档」与 **MaaFramework 主仓库**；行为不一致时优先以 **M9A 发行版 + 资源版本** 为准。

### [MFAA / MFAAvalonia（trler/MFAA）](https://github.com/trler/MFAA)

README 中的 **`interface.json`** 与 AUTO-MAS 用户侧 **「可选任务 + 顺序 + 是否启用」** 同构（表达层不同、语义对齐）：

| `interface.json`（MFAAvalonia） | AUTO-MAS M9A 侧 |
|--------------------------------|-----------------|
| `task[]`：`name`、`entry`、`default_check`、`repeatable`、`repeat_count` | `AvailableTasks` / 任务元数据；勾选与默认选中 |
| 任务 **顺序**（列表顺序） | `Task.Queue` JSON + `TaskQueueSection` + **vuedraggable** |
| `resource[]`：多服路径叠加 | 脚本/用户目录、资源根路径等（见 `M9AConfig` / 用户配置） |
| `controller[]`：Adb / Win32 / PlayCover 等 | 模拟器与连接方式；与 `manager.check`、ADB 分支一致 |
| `focus` 旧/新协议（日志、Toast、节点事件） | AUTO-MAS 以 **LogMonitor + 前端 message** 为主；不必复刻 MFAA 富文本日志格式，但**阶段语义**应对齐便于用户理解 |

**结论**：读 **MFAA** 文档与 `interface.json` 有助于设计 **任务列表 UI 与默认值**；读 **M9A** 仓库有助于 **管线、资源、agent** 行为对齐。AUTO-MAS **不嵌入** Avalonia 运行时；Vue 表面独立实现，字段与后端 `M9AUserConfig` 一致即可。

### AUTO-MAS 侧：启动后自动跑 & 配置保存（MFAA 线特征）

与本仓 **MAA / MaaEnd（MXU 线）** 等不同，**MFAA/M9A 形态**通常**不把「本次要跑的任务队列」托付给一条启动参数**；编排依赖：

1. **写盘**：`AutoProxy` **在启动进程前**把队列、模拟器等写入 M9A 目录下的运行 JSON（如 `write_m9a_config` → 助手读到的任务文件）。
2. **启动**：`open_process(m9a_exe_path)` **无额外 CLI**（或仅环境/路径类，以仓库 README 为准）。
3. **自动跑**：由 **助手程序内部**读取已写入的配置，在启动后进入执行（与用户在其设置里见到的 **「启动后自动运行」** 类语义一致；具体字段名以上游为准）。

**用户改配置**：在 **AUTO-MAS** 的 `M9AUserEdit` / `TaskQueueSection` 等完成；**不**走 ScriptConfig 全屏拉起 MFAAvalonia 来「点保存」。若新专项仍属 MFAA 线，应对齐该模式，勿硬套「命令行自启 + 调本体 UI 保存」。

---

## 前端表面（主路径）

| 表面 | 路径 / 说明 |
|------|-------------|
| UserEdit 编排 | `EditView/User/M9AUserEdit.vue` — `taskQueue` ref，**无** ScriptConfig 全屏遮罩 |
| Sections | `M9AUserEdit/BasicInfoSection`、`TaskQueueSection`、`NotifyConfigSection` |
| 任务渲染 | `TaskOptionRenderer.vue` — checkbox / 任务选项 |
| Header | `M9AUserEditHeader.vue` |
| ScriptEdit | `EditView/Script/M9AScriptEdit.vue`（脚本级较薄） |
| Hub | `Scripts.vue` → `m9a` |
| 队列 | scheduler / `QueueItem` 对 `M9A` 分支（#154） |

### 风格要点

- `Task.Queue` / `AvailableTasks` JSON 与 `TaskQueueSection` **双向绑定**  
- `vuedraggable` 任务顺序（注意拖拽后状态清理，#154 修复）  
- Logger：`window.electronAPI.getLogger('M9A用户编辑')`  
- import 路径可见 `.ts` 后缀（与部分旧页并存，新代码宜与邻近文件一致）

---

## 后端（实现层）

- `app/task/M9A/`：`Manager`、`AutoProxy`、`ScriptConfig`、模拟器 ADB 等  
- `config.py` / `schema.py`：`M9AConfig`、`M9AUserConfig`  
- pipeline / 任务队列 JSON 与前端 `M9ATaskQueueItem` **严格对齐**（与上游任务入口 `entry` 变更同步时尤须回归）

---

## 常见检查（M9A）

- [ ] Hub 四处分支含 `m9a`  
- [ ] 任务队列持久化 ↔ `AutoProxy` 消费  
- [ ] MuX / instances 目录校验提示（`manager.check`）  
- [ ] 未手改 `frontend/src/api/models/*`  
- [ ] 上游 [M9A](https://github.com/MAA1999/M9A) 发版变更（资源/任务名）后，核对 `TaskOptionRenderer` 与默认队列是否需同步  

---

## 同框架新专项流程（MFAA 线扩展）

1. **与用户确认**：仍为 MaaFramework + 任务列表/队列 JSON？→ 复制 `M9A` 线；若外置 GUI 仅换为 MXU 而配置模型不同 → 重新评估 **MXU 线**。  
2. **读上游**：[M9A](https://github.com/MAA1999/M9A) 任务与目录；[MFAA](https://github.com/trler/MFAA) 的 `interface.json` 任务与 controller 声明。  
3. **本仓**：复制 `app/task/M9A` → `app/task/Xxx`、`EditView`/`M9AUserEdit` → `Xxx*`，改 `ScriptType`、Hub、`types/script.ts`。  
4. **OpenAPI**：schema 变更后由开发者重新生成；勿手改生成模型。

---

## 参照建议

需要 **任务队列 + draggable + 复杂 Task Section** → 首选 **本仓 M9A 表面**；脚本级字段少时可保持薄 `M9AScriptEdit`。

**建议 PR 切分**：P0 #154 形态全量表面 + 后端；体验类 (#183) 单独 PR。
