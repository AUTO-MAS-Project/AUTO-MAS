# 专项适配（完整说明）

对应 Skill：`mas-script-specialized-adapter`。  
**主视角**：前端专项表面；**次视角**：后端 `app/task/Xxx` 与注册表。  
**按脚本前端架构分类**（MAA / SRC / MXU 线 / MFAA 线）：见 [script-frontend-architectures.md](./script-frontend-architectures.md)。**推荐**：专项适配开场先问要 **脚本/Git 仓库链接**，由 Agent 读仓库后给出架构判断，再请用户确认；无仓库时再口述选型。确认后再实现。  

**确认架构后**：回到仓库读 **启动参数 / CLI / `--help`** 与 **配置落盘方式**，分别拟定 **「启动后自动跑」**（`argv` vs 仅写 JSON 再启动）与 **「设置脚本配置」**（ScriptConfig 调本体 vs 仅 AUTO-MAS 写文件）。**MFAA 线**通常无可靠 CLI 编排，对齐 M9A：**写运行配置 + 启动 exe**，不靠调壳做配置；**MAA/MXU/SRC** 等常兼有 **启动参数或壳内 auto-run 字段** 与 **调起脚本保存**。详见 [script-frontend-architectures.md](./script-frontend-architectures.md) 「自启动与配置落盘」。  

参考 PR：[#133 MaaEnd](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/133)、[#152](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/152)、[#154 M9A](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/154)、[#727aafb SRC 风格](https://github.com/AUTO-MAS-Project/AUTO-MAS/commit/727aafbaf5e21fc81e85e795a5cd5b77ac508e60)。**实现必遵守**：[adapter-code-norms.md](./adapter-code-norms.md)。**SRC**：[examples-src.md](./examples-src.md)。**MFAA**：[examples-m9a.md](./examples-m9a.md)。**MXU**：[examples-maaend.md](./examples-maaend.md)。**ok-script**：[examples-okww.md](./examples-okww.md)（含 [实现规范](./examples-okww.md#实现规范okww-必遵守)）。

### 配置来源的三级语义

专项适配不再把“简洁/详细”当作通用产品概念。涉及脚本原生配置时，优先使用 **脚本 / 用户 / 直控** 三级选择器：

- **脚本**：使用脚本级共享的 MAS 适配配置，适合所有用户共用的一套高频设置。
- **用户**：使用当前用户的 MAS 适配配置，适合高频设置存在差异的用户。
- **直控**：优先读取脚本原有配置，复杂配置由脚本原生 GUI 维护；不因为“直控”就复制一份 MAS 全量配置。

专项可以按上游能力特调这三种来源，但不能把本规则未经确认地套到 MaaEnd、MAA、OkNte 或其他模块。若专项提供“快速配置”，开关开启时快速配置只覆盖该专项明确拥有的高频字段；关闭时应保留脚本原生完整配置。运行前必须备份原配置，成功、失败、取消、超时和异常路径都要恢复或按已确认策略回写。

---

## 核心要义：围绕用户最短路径做适配

专项适配的完成标准不是“把外部脚本所有字段接进来”，而是让用户更快完成可用配置，并在脚本做不到时由 MAS 可靠补位。

### 1. 先降低用户使用门槛

先记录用户从安装到第一次成功运行的手工步骤，再按收益排序处理：

| 用户阻力 | 适配目标 | 已有参照 |
| --- | --- | --- |
| 不知道该选哪个脚本目录或游戏入口 | 一键发现、导入、校验，并在多个候选时给出可操作选择 | Okww：脚本目录与游戏启动器双路径一键导入 |
| 原生配置面板复杂、字段过多 | 提供 MAS 快速配置，只暴露完成高频任务所需的最小字段；复杂场景再进入原生配置会话 | MaaEnd：快速配置开关与用户级配置来源 |
| 用户需要手动拼任务顺序或反复切换模式 | 用已有任务/计划表表达高频路径，并让 MAS 负责保存、调度和状态反馈 | MAA：剿灭与日常分段执行 |

验收问题：普通用户是否少做了一步真实操作？如果只是换了字段名称、增加了一个空壳页面，不能算降低门槛。

### 2. 明确脚本能力与 MAS 补位边界

按下表给每项能力定 owner，再开始实现：

| 能力归属 | 判定 | 实施规则 |
| --- | --- | --- |
| 脚本原生 | 脚本已有稳定入口、配置和结果判定 | 复用脚本能力，MAS 只做导入、编排、状态反馈；脚本配置是唯一事实来源 |
| MAS 适配层 | 脚本有能力，但用户入口分散或难以安全调用 | MAS 提供最小封装，例如路径发现、默认值、配置会话和原子写回；不复制一套平行配置模型 |
| MAS 补位 | 脚本明确无法提供，而 MAS 能依靠稳定数据和任务边界可靠完成 | 在 `manager` / `AutoProxy` / 计划或任务层实现，并明确输入、失败提示、回退和清理；例如 MAA 活动关优先 |
| 暂不支持 | 需要猜测上游内部状态、改写脚本引擎或无法稳定验证 | 显式提示限制，不添加看似可用但运行时不消费的字段 |

MAS 补位的边界是“补用户价值”，不是“接管脚本全部职责”：不得修改游戏本体，不得把脚本已有的权威设置重复暴露，也不得为了统一界面重写外部脚本的任务引擎。

### 3. 交付前的最小验收

- [ ] 写清减少了哪一段用户手工操作，或补足了哪项脚本缺口。
- [ ] 每个新增字段和按钮都有实际运行时消费者；没有只存在于 schema 或表单的假功能。
- [ ] 脚本原生、MAS 适配层、MAS 补位三者的 owner 已确定，保存和恢复路径只有一个事实来源。
- [ ] 补位能力有失败提示、可回退行为和结束清理；上游不支持时不会静默误报成功。
- [ ] 优先运行对应的最小专项测试；没有用户价值的额外测试和入口不随适配提交。

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
