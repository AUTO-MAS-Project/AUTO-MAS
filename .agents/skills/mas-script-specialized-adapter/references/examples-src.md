# 案例：SRC 专项（SRC 线 · #727aafb）

**架构线**：SRC 线（Alas / SRC 系：Python 任务栈 + `webapp` 配置形态 + 脚本大表单 + 用户 Section；本仓 `ScriptType` = `SRC`）。与 `mas-code-standards` · `727aafb` 一致。

> **上游参照**：[StarRailCopilot](https://github.com/LmeSzinc/StarRailCopilot)（星穹铁道脚本，README 写明基于**下一代 Alas 框架**；目录含 `module/`、`route/`、`tasks/`、`webapp/`、`config/` 等，与经典 Alas/SRC 系仓库结构同类）。AUTO-MAS 的 SRC 专项适配面向「**由 AUTO-MAS 拉起、监控日志的 SRC 兼容可执行体**」，不要求本仓内嵌其完整源码，但**对接与排障时应理解其框架习惯**。

## 一、SRC 线在本仓的定位

| 概念 | 说明 |
|------|------|
| **SRC 线** | 前端：`SRCScriptEdit` 大块 + `SRCUserEdit` Section；后端：`app/task/SRC/` 的 `METHOD_BOOK` 生命周期 |
| **与 MAA/MXU/MFAA 的差异** | 通常**无** MAA/MaaEnd 式全屏 ScriptConfig 遮罩；**无** M9A 式任务队列 JSON 编辑；**无** MaaEnd 专用计划表；侧重 **exe 路径、模拟器、Stage、通知** |
| **新游戏、仍属 Alas/SRC 系** | 若与现有 `SrcConfig`/`SrcUserConfig` **字段与语义一致**，可继续用 `ScriptType === 'SRC'`；若配置模型或任务模式分叉，应 **新建 `ScriptType`** + **复制 `app/task/SRC` 骨架** + **新 EditView**（仍走 SRC **线**的表面模式，见下文「同框架新专项流程」） |

---

## 二、前端表面（优先阅读）

| 表面 | 路径 |
|------|------|
| ScriptEdit（大块） | `frontend/src/views/EditView/Script/SRCScriptEdit.vue` |
| UserEdit 编排 | `frontend/src/views/EditView/User/SRCUserEdit.vue` |
| Sections | `frontend/src/views/SRCUserEdit/BasicInfoSection.vue`、`StageConfigSection.vue`、`NotifyConfigSection.vue` |
| Header | `frontend/src/views/SRCUserEdit/SRCUserEditHeader.vue` |
| Hub | `Scripts.vue` 中 `SRC` → `src` |
| 路由 | `router/index.ts` → `SRCScriptEdit`、`SRCUserAdd` / `SRCUserEdit` |

### 风格要点

1. **SRCScriptEdit**：单组件内 `form-section`，字段 `@blur` 触发 `handleChange`；不急于拆文件。  
2. **Section**：`emit('save')` + 明确中文 label/tooltip。  
3. **Hub**：与 MAA 相同分支模式，复制改类型即可。

---

## 三、后端（随表面对齐）

| 项 | 路径 |
|----|------|
| 配置 | `SrcConfig`、`SrcUserConfig` in `config.py` / `schema.py` |
| API | `SCRIPT_BOOK` / `USER_BOOK` |
| 调度 | `app/task/SRC/manager.py`：`METHOD_BOOK`（`AutoProxy` / `ManualReview` / `ScriptConfig`） |
| 主任务 | `app/task/SRC/AutoProxy.py`（日志监看、进程、登录等） |
| 配置任务 | `app/task/SRC/ScriptConfig.py` |
| 人工排查 | `app/task/SRC/ManualReview.py` |
| 工具 | `app/task/SRC/tools/notify.py`、`login.py`、`poor_yaml.py` |

`manager.check()` 已体现 SRC 共性：**任务模式 ∈ METHOD_BOOK**、配置类型为 `SrcConfig`、**模拟器 Id/Index** 必填等——新 Alas 系脚本若接入，须在 `check` 与前端表单中**同步**同类前置条件。

---

## 四、与 StarRailCopilot / Alas 系的**概念对照**（排障与扩展用）

以下为**心智模型对照**，非文件级一一映射：

| 上游（Alas/SRC 系，如 [StarRailCopilot](https://github.com/LmeSzinc/StarRailCopilot)） | AUTO-MAS SRC 专项关注点 |
|----------------------------------------------------------------------------------------|-------------------------|
| `tasks/`、`module/`、`route/` 任务与调度 | `AutoProxy` 主循环、任务模式、`METHOD_BOOK` |
| `webapp/` 或 GUI 配置 | **不在**本仓复刻；由 `SRCScriptEdit` / `SRCUserEdit` 写回 `SrcConfig`/`SrcUserConfig` |
| `config/` 与运行数据目录 | 与 `ScriptConfig`、用户目录、`poor_yaml` 等读写路径对齐；注意与 `data/{scriptId}/...` 约定一致 |
| 模拟器 + 包名/进程 | `SrcConfig` 模拟器字段、`manager.check`；业务常量见 `app/utils/constants.py`（如星铁包名等） |
| 通知、推送 | `tools/notify.py` 与 `StageConfigSection` / 用户通知字段一致 |

对接新仓库时，先读对方 **README「开发」/ 配置目录说明**，再对照本仓 `Src*` 字段是否够用。

---

## 五、同框架下「新专项」推荐流程（SRC 线）

适用于：**仍是 Alas/SRC 系可执行体**，但可能是新游戏、新二进制名、或配置块与现网 `SRC` 不完全相同。

### 5.1 与维护者 / 用户确认（Agent 必问）

1. 可执行体是否与当前 `SRC` **共用同一套配置 schema**？是 → 可能仍用 `ScriptType 'SRC'`；否 → 新类型名 + 复制任务目录。  
2. 是否需要新任务模式（`METHOD_BOOK` 外）？需要则扩展 `METHOD_BOOK` + 前端任务模式选项 + `constants.py` 中文名。  
3. 模拟器、登录、包名是否与现有常量/分支冲突？  
4. 用户侧是否仍只需 **BasicInfo + Stage + Notify**？若多出新大块（类似 M9A 队列），评估是否已接近 **MFAA 线**，勿硬塞进 SRC Section。

### 5.2 实现顺序（建议）

1. **配置与 schema**：`config.py` / `schema.py`（新类型则 `XxxConfig` 复制 `Src*` 结构再改）。  
2. **API 书**：`SCRIPT_BOOK` / `USER_BOOK`。  
3. **任务**：复制 `app/task/SRC/` → `app/task/Xxx/`，改 `check`、路径、常量；保留 `METHOD_BOOK` 形状 unless 明确要删模式。  
4. **task_manager**：`isinstance` → `XxxManager`。  
5. **前端**：复制 `SRCScriptEdit` / `SRCUserEdit` / `SRCUserEdit/*` → `Xxx*`，改 `ScriptType`、路由片段、Hub 分支。  
6. **OpenAPI**：改 schema 后由开发者重新生成模型；**勿手改** `frontend/src/api/models/*`。

### 5.3 仍应复用的 SRC 线**不变量**

- Hub / 路由 / `useScriptApi` 四处分支补全。  
- 脚本页可保持「**单文件大表单**」直到真放不下再拆。  
- Section 通过 `@save` 聚合写库，避免 Section 内直接散落 API。

---

## 六、与 MaaEnd / M9A 的差异（速查）

| 维度 | SRC 线 | MaaEnd（MXU） | M9A（MFAA） |
|------|--------|---------------|-------------|
| ScriptEdit | 单文件为主 | 中等 | 较薄 |
| ScriptConfig 遮罩 | 通常无（另有 `ScriptConfigTask` 模式） | 有（用户页常见） | 无 |
| 用户任务 UI | Stage 等 | Task + Skyland | TaskQueue + draggable |
| 计划表 | 无 | `MaaEndPlanTable` | 无 |

新增专项若**脚本级字段很多**、**无队列 JSON 编辑**，优先 SRC 线；若出现**强队列 + 管线**，重新评估是否 MFAA 线。
