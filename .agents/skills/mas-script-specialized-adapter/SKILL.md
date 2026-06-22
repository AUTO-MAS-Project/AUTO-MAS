---
name: mas-script-specialized-adapter
description: >-
  Guide specialized AUTO-MAS integration by script frontend architecture (MAA / SRC /
  MXU-line like MaaEnd / MFAA-line like M9A / ok-script like Okww). Before coding: run
  script-architecture intake (prefer repo URL). Surfaces first, then backend. Code norms:
  references/adapter-code-norms.md.
---

# 专项适配（前端表面优先）

## 使用前：脚本架构问诊 → 再开工（必做）

专项适配**按脚本前端架构区分**。加载本 Skill 后、**写任何实现前**：

1. **请用户提供脚本/Git 仓库链接**（多仓可都要）。
2. **Agent 研判** README、目录信号，对照下表归纳架构线。
3. **请用户确认**后再写代码；无仓库则口述 + [script-frontend-architectures.md](references/script-frontend-architectures.md) 问诊项。

### UI 开工前必问

- 图标来源与落地路径（`frontend/src/assets/<slug>.ico`）、替换入口（列表/弹窗/编辑页）。
- 用户可见文案统一写法（如 `ok-ww`）vs 技术标识（`Okww`、`ScriptType`、OpenAPI 名）。

### 落地流程（ok-script 等）

- **先验证**：`General` 跑通启动、日志（可临时预设）。
- **再专项**：新增 `ScriptType`，迁移默认值到专项页。
- **最后清理**：删除 General 临时入口。

### 流程与验证

- **C 策略**：不新增跨模块 helper；规则写入 [adapter-code-norms.md](references/adapter-code-norms.md) 与 `examples-*.md`，**勿**写「现象→根因」排查长文。
- 默认值：`POST /api/scripts/get`；General 临时预设验证后删除；OpenAPI 见 [adapter-code-norms §1](references/adapter-code-norms.md#1-注册与-api)。

---

## 代码规范（必遵守，替代排查叙事）

全仓新增 `ScriptType`：[adapter-code-norms.md](references/adapter-code-norms.md)（注册、前端表面、任务模块、代码质量、Manager 规范、check() 消息、General 对齐原则）。

**Okww 增量**：[examples-okww.md · 实现规范](references/examples-okww.md#实现规范okww-必遵守)。

**通用代码质量规范**（所有适配通用，见 [adapter-code-norms §6-9](references/adapter-code-norms.md#6-任务模块代码质量通用所有专项适配)）：
- hasattr() 消除 → 显式 `__init__` 初始化
- 原子化文件操作（tmp + rename）
- DRY 提取共用恢复逻辑
- 独立 try/except 每操作
- unlock-then-write 顺序
- check() 消息用户可操作

### 架构线速查（细节 [script-frontend-architectures.md](references/script-frontend-architectures.md)）

| 架构线 | 含义 | 本仓 `ScriptType` |
|--------|------|-------------------|
| MAA 线 | MAA 系配置会话、计划表 | `MAA` |
| SRC 线 | 大表单 + Section | `SRC` |
| MXU 线 | MaaEnd + MXU、`mxu-*.json` | `MaaEnd` |
| MFAA 线 | M9A 队列 JSON，无 ScriptConfig 壳 | `M9A` |
| General | 通用路径/进程/日志 | `General` |
| ok-script | `-t`/`-e` CLI + 表单化配置编辑器（纯内置判态，AutoProxy 唯一模式） | `Okww` |

确认架构后读上游 **自启动**（argv vs 写盘）与 **配置落盘**（表单编辑器 vs ScriptConfig GUI vs 仅写 JSON）。MFAA 见 [examples-m9a.md](references/examples-m9a.md)；MXU 见 [examples-maaend.md](references/examples-maaend.md)；ok-script 见 [examples-okww.md](references/examples-okww.md)。

---

## 架构取向

**主要对象是前端表面**（`EditView/`、`Scripts.vue`、Section）；后端 `app/task/Xxx/` 同 PR 补齐。先加载 `mas-skills`，配合 `mas-module-boundary`、`mas-data-model`、`mas-api-contract`、`mas-code-standards`。

### 前端表面清单

| 表面 | 要点 |
|------|------|
| Hub | `Scripts.vue` / `ScriptTable.vue`：`ScriptType` → URL 片段 |
| 脚本/用户编辑 | `EditView/Script/`、`EditView/User/`；Section 单职责 + `@save` |
| 映射 | `types/script.ts`、`useScriptApi.ts`（**含 UserConfig→users[]**） |
| 路由 | `router/index.ts` 与 Hub 片段一致 |
| 配置入口 | ok-script 线：**表单化编辑器**（非 ScriptConfig GUI）；Okww: 全内置判态，无 SuccessLog/ErrorLog；MXU/MAA：ScriptConfig `teleport` 遮罩 + WebSocket |
| 配置 Schema | 表单化编辑器需 `config_schema.py`（字段类型/选项/翻译）+ API 端点 + 前端 Service |

### 后端切面

`XxxConfig` / `XxxUserConfig`、`SCRIPT_BOOK`、`task_manager`、`app/task/Xxx/`（`Manager`、`AutoProxy`；按需 `config_schema.py` 或 `ScriptConfig`；须实现 `final_task` / `on_crash`）。

---

## UI 分段（默认）

脚本编辑三段：基本信息 / 游戏配置 / 运行配置。用户编辑三段：基本 / 任务 / 通知。Okww 游戏段：`Enabled`、`LaunchBeforeTask`、`CloseOnFinish` **独立**；见 [examples-okww · 实现规范](references/examples-okww.md#实现规范okww-必遵守)。

---

## 完整开发工作流（Agent 执行清单）

以下为 Agent 接到「新增 ScriptType」任务时的标准流程：

### 阶段 1：架构确认
1. 获取上游仓库 URL → 读 README、CLI 参数、配置方式
2. 对照 [script-frontend-architectures.md](references/script-frontend-architectures.md) 确认架构线
3. 与用户确认架构线 + UI 文案（如 `ok-ww` vs `Okww`）

### 阶段 2：前端表面
4. `Scripts.vue`：新增 `ScriptType` Hub 分支（handleEditScript / handleAddUser / handleEditUser / handleConfirmAddScript）
5. `ScriptTable.vue`：卡片图标 + 操作按钮
6. `router/index.ts`：新增 URL 片段路由
7. `types/script.ts`：`ScriptType` 枚举、默认 config 结构
8. `useScriptApi.ts`：类型判断 + UserConfig→users[] 两处分支
9. `OkwwScriptEdit.vue`：脚本编辑三段
10. `OkwwUserEdit.vue`：用户编辑 + 配置编辑器（按架构线选型）
11. 图标：`frontend/src/assets/<slug>.ico`

### 阶段 3：后端注册
12. `app/models/config.py`：`XxxConfig` / `XxxUserConfig`
13. `app/models/schema.py`：schema 注册
14. `app/core/config.py`：`isinstance` 分支
15. `app/api/scripts.py`：`SCRIPT_BOOK` / `USER_BOOK`
16. `app/utils/constants.py`：`TYPE_BOOK` 展示文案
17. `yarn openapi` → 确认 `openapi.json` 含新类型

### 阶段 4：任务模块
18. `app/task/Okww/__init__.py`
19. `app/task/Okww/manager.py`：METHOD_BOOK、check/prepare/main_task/final_task/on_crash
20. `app/task/Okww/AutoProxy.py`：__init__、check、prepare、main_task、final_task、on_crash、进程/日志/游戏管理
21. 按需：`config_schema.py` 或 `ScriptConfig.py`
22. `app/core/task_manager.py`：注册

### 阶段 5：自检与清理
23. 对照 [adapter-code-norms.md §10](references/adapter-code-norms.md#10-提交前自检) 逐项检查
24. 对照对应 `examples-*.md` 实现规范
25. 删除 General 临时预设入口（如有）

---

## 原则

- **Agent 必须修改所有相关文件**，不遗漏任何分支（Hub 四处分支、useScriptApi 两处分支、TYPE_BOOK 等）
- 对齐最接近的表面模板；一次打通 Hub + 编辑 + 后端；勿手改 `frontend/src/api/models/*`
- 通用代码质量规范（hasattr 消除、原子 I/O、DRY、独立 try/except）对所有专项适配生效

---

## 进一步阅读

- [**专项适配代码规范**](references/adapter-code-norms.md)（含 §6 代码质量、§7 Manager 规范、§8 check() 消息、§9 General 对齐）
- [脚本前端架构](references/script-frontend-architectures.md)
- [表面目录与检查清单](references/guide.md)
- [多类型表面对照](references/examples-frontend-surfaces.md)
- [SRC](references/examples-src.md) · [MaaEnd](references/examples-maaend.md) · [M9A](references/examples-m9a.md) · [OK-WW](references/examples-okww.md)

---

## 提交前自检

对照 [adapter-code-norms.md](references/adapter-code-norms.md)；Okww 另对照 [examples-okww · 实现规范](references/examples-okww.md#实现规范okww-必遵守)。
