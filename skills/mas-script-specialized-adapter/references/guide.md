# 专项适配（完整说明）

对应 Skill：`mas-script-specialized-adapter`。  
**主视角**：前端专项表面；**次视角**：后端 `app/task/Xxx` 与注册表。  
**按脚本前端架构分类**（MAA / SRC / MXU 线 / MFAA 线）：见 [script-frontend-architectures.md](./script-frontend-architectures.md)。**推荐**：专项适配开场先问要 **脚本/Git 仓库链接**，由 Agent 读仓库后给出架构判断，再请用户确认；无仓库时再口述选型。确认后再实现。  

**确认架构后**：回到仓库读 **启动参数 / CLI / `--help`** 与 **配置落盘方式**，分别拟定 **「启动后自动跑」**（`argv` vs 仅写 JSON 再启动）与 **「设置脚本配置」**（ScriptConfig 调本体 vs 仅 AUTO-MAS 写文件）。**MFAA 线**通常无可靠 CLI 编排，对齐 M9A：**写运行配置 + 启动 exe**，不靠调壳做配置；**MAA/MXU/SRC** 等常兼有 **启动参数或壳内 auto-run 字段** 与 **调起脚本保存**。详见 [script-frontend-architectures.md](./script-frontend-architectures.md) 「自启动与配置落盘」。  

参考 PR：[#133 MaaEnd](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/133)、[#152](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/152)、[#154 M9A](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/154)、[#727aafb SRC 风格](https://github.com/AUTO-MAS-Project/AUTO-MAS/commit/727aafbaf5e21fc81e85e795a5cd5b77ac508e60)。**实现必遵守**：[adapter-code-norms.md](./adapter-code-norms.md)。**SRC**：[examples-src.md](./examples-src.md)。**MFAA**：[examples-m9a.md](./examples-m9a.md)。**MXU**：[examples-maaend.md](./examples-maaend.md)。**ok-script**：[examples-okww.md](./examples-okww.md)（含 [实现规范](./examples-okww.md#实现规范okww-必遵守)）。

---

## 0. 为何以前端表面为专项单位

仓库里 `ScriptType` 在后端对应 `app/task/<Name>/`，但在**架构与协作**上：

- 贡献者主要**新增/修改的是 Vue 表面**（编辑页、Section、列表跳转、计划表）。
- 这些表面通过 **Hub 分支**（`Scripts.vue`）与 **路由** 绑定到类型，形成稳定「专项入口」。
- 后端模块是实现细节：字段须与表单的 `formData` 结构一致，但**不应先写 task 再补一个空壳前端**。

```
用户操作 → Scripts.vue (Hub) → router → EditView/* → *UserEdit/*Section
                ↓
         useScriptApi / useUserApi → API → config.py / task/Xxx
```

---

## 1. 前端表面目录

### 1.1 Hub（列表与导航）

| 文件 | 职责 |
|------|------|
| `frontend/src/views/Scripts.vue` | 创建脚本、复制、跳转 `edit/{slug}`、`users/add|edit/{slug}` |
| `frontend/src/components/ScriptTable.vue` | 类型图标、专项操作按钮 |

**URL 片段约定**（与 `router/index.ts` 一致）：

| ScriptType | 片段 |
|------------|------|
| MAA | `maa` |
| SRC | `src` |
| MaaEnd | `maaend` |
| M9A | `m9a` |
| General | `general` |

新增类型时：**四处同步** — `handleEditScript`、`handleAddUser`、`handleEditUser`、`handleConfirmAddScript`（及复制脚本）中的分支。

**风格**：延续 `if (script.type === …)` 链（`e5d72bdb`），不抽过度抽象的 `routeByScriptType` 除非已有先例。

### 1.2 脚本编辑表面（Script Edit Shell）

路径：`frontend/src/views/EditView/Script/XxxScriptEdit.vue`

| 模式 | 代表 | 说明 |
|------|------|------|
| **单文件大块** | `SRCScriptEdit.vue` | `form-section` + `@blur` 字段保存；适合字段多、交互集中 |
| **较薄壳** | `M9AScriptEdit.vue` | 脚本级字段较少时 |
| **通用模板** | `GeneralScriptEdit.vue` | 游戏/脚本路径、日志等通用块 |

### 1.3 用户编辑表面（User Edit Orchestrator + Sections）

**编排页**：`EditView/User/XxxUserEdit.vue`  
- `reactive` / `ref` 的 `formData`  
- `useUserApi`：`addUser` / `updateUser`  
- `handleFieldSave` 分段保存（常见模式）  
- 可选：`teleport` + WebSocket + ScriptConfig 任务（MAA、MaaEnd）

**Section 目录**：`frontend/src/views/XxxUserEdit/`

| Section 类型 | 常见文件名 | 职责 |
|--------------|------------|------|
| Header | `XxxUserEditHeader.vue` | 返回、专项动作按钮 |
| 基本信息 | `BasicInfoSection.vue` | `Info.*` |
| 任务/关卡 | `TaskConfigSection.vue`、`StageConfigSection.vue`、`TaskQueueSection.vue` | 领域差异最大 |
| 通知 | `NotifyConfigSection.vue` | 多类型结构类似，可对照复制 |
| 专项 | `SkylandConfigSection.vue`（MaaEnd）等 | 仅该类型需要 |

**拆分原则**（`mas-code-standards` UI 笔记）：表单自然分块再拆；编排页只接线，不写数百行表单项。

### 1.4 计划表表面（可选）

- `frontend/src/views/plan/tables/MaaPlanTable.vue`（MaaEnd #152）
- `planTypeRegistry`、后端 `plan.py` / combox `consumer`

### 1.5 类型与 Composable

- `frontend/src/types/script.ts`：`ScriptType`、`*ScriptConfig`、`*User` 默认结构  
- `frontend/src/composables/useScriptApi.ts`：类型判断、默认 config、读写  
- **禁止**手改 `frontend/src/api/models/*`

---

## 2. 代码风格倾向（观察自 dev）

来源：`mas-code-standards` · `style-observations.md`，专项相关信号：

| 倾向 | 说明 | 信号文件 |
|------|------|----------|
| 扩展注册表与分支 | 新类型进 `SCRIPT_BOOK`、`Scripts.vue` 分支，非新框架 | `e5d72bdb` |
| 单文件 ScriptEdit 可接受 | 先落地再拆 | `SRCScriptEdit.vue` @ `727aafb` |
| Section 小而显式 | `props` + `emit('save')` | `SRCUserEdit/BasicInfoSection.vue` |
| 中文 logger / 标签 | `window.electronAPI.getLogger('M9A用户编辑')` | `M9AUserEdit.vue` |
| 行为优先 | 窄改动、不重命名邻域 | `e541fa5f`（后端，同理适用于表面小改） |
| 表面对齐后端字段 | `formData` 键与 `config.py` ConfigItem 组一致 | 各 `*UserEdit` |

**反模式**：为「支持所有 ScriptType」造动态表单引擎；在未改 Hub 的情况下只加后端 Manager。

---

## 3. 后端检查清单（随表面补齐）

与 [原 checklist](./guide.md) 相同逻辑，顺序建议：**schema/config → API 书 → task → task_manager**。

### 3.1 模型与 API

- [ ] `config.py` / `schema.py`：`XxxConfig`、`XxxUserConfig`
- [ ] `app/core/config.py`：`isinstance` 分支
- [ ] `app/api/scripts.py`：`SCRIPT_BOOK`、`USER_BOOK`

### 3.2 任务

- [ ] `app/task/Xxx/manager.py`：`METHOD_BOOK`、`check/prepare/...`
- [ ] `AutoProxy` / `ScriptConfig` / `tools/` 按参照类型取舍
- [ ] `app/core/task_manager.py` 注册

### 3.3 横切（按需）

- [ ] `runtime_bridge`、`app/MaaFW/*`、计划 consumer、队列 script type 分支

---

## 4. 推荐 PR 拆分

| 阶段 | 前端 | 后端 |
|------|------|------|
| P0 | Hub + 路由 + Script/User Edit + Section 最小集 | 模型 + Manager + BOOK |
| P1 | 计划表 / 队列 UI | plan / queue 分支 |
| P2 | 体验优化、预设、虚拟用户 | 可与 P2 仅前端（#183） |

---

## 5. 与 General 的边界

- **General**：通用脚本表面 + `app/task/general/`，路径/日志模式通用。  
- **专项**：独立 `EditView` + `views/XxxUserEdit/`，强绑定外部程序；**勿**把专项 UI 塞进 `GeneralUserEdit`。

---

## 6. 执行顺序

1. **与用户确认脚本前端架构**（见 [script-frontend-architectures.md](./script-frontend-architectures.md) 必问题清单）  
2. `mas-code-standards`  
3. 阅读 [examples-frontend-surfaces.md](./examples-frontend-surfaces.md) 选参照表面  
4. `mas-module-boundary` + `mas-data-model`  
5. [adapter-code-norms.md](./adapter-code-norms.md) 逐表实现；Okww 另对照 [examples-okww · 实现规范](./examples-okww.md#实现规范okww-必遵守)  
6. 本 Skill — 表面 + 后端  
7. `mas-api-contract` + `mas-function-design`
