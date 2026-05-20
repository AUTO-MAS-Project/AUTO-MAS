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

- **先验证**：`General` 跑通启动、日志、ScriptConfig（可临时预设）。
- **再专项**：新增 `ScriptType`，迁移默认值到专项页。
- **最后清理**：删除 General 临时入口。

### 流程与验证

- **C 策略**：不新增跨模块 helper；规则写入 [adapter-code-norms.md](references/adapter-code-norms.md) 与 `examples-*.md`，**勿**写「现象→根因」排查长文。
- 默认值：`POST /api/scripts/get`；General 临时预设验证后删除；OpenAPI 见 [adapter-code-norms §1](references/adapter-code-norms.md#1-注册与-api)。

## 代码规范（必遵守，替代排查叙事）

全仓新增 `ScriptType`：[adapter-code-norms.md](references/adapter-code-norms.md)（注册、前端表面、任务模块、简洁/详细）。**Okww 增量**：[examples-okww.md · 实现规范](references/examples-okww.md#实现规范okww-必遵守)。

**架构线速查**（细节 [script-frontend-architectures.md](references/script-frontend-architectures.md)）：

| 架构线 | 含义 | 本仓 `ScriptType` |
|--------|------|-------------------|
| MAA 线 | MAA 系配置会话、计划表 | `MAA` |
| SRC 线 | 大表单 + Section | `SRC` |
| MXU 线 | MaaEnd + MXU、`mxu-*.json` | `MaaEnd` |
| MFAA 线 | M9A 队列 JSON，无 ScriptConfig 壳 | `M9A` |
| General | 通用路径/进程/日志 | `General` |
| ok-script | `-t`/`-e` CLI + 自带 GUI | `Okww` |

确认架构后读上游 **自启动**（argv vs 写盘）与 **配置落盘**（ScriptConfig vs 仅写 JSON）。MFAA 见 [examples-m9a.md](references/examples-m9a.md)；MXU 见 [examples-maaend.md](references/examples-maaend.md)。

## 架构取向

**主要对象是前端表面**（`EditView/`、`Scripts.vue`、Section）；后端 `app/task/Xxx/` 同 PR 补齐。先加载 `mas-skills`，配合 `mas-module-boundary`、`mas-data-model`、`mas-api-contract`、`mas-code-standards`。

### 前端表面清单

| 表面 | 要点 |
|------|------|
| Hub | `Scripts.vue` / `ScriptTable.vue`：`ScriptType` → URL 片段 |
| 脚本/用户编辑 | `EditView/Script/`、`EditView/User/`；Section 单职责 + `@save` |
| 映射 | `types/script.ts`、`useScriptApi.ts`（**含 UserConfig→users[]**） |
| 路由 | `router/index.ts` 与 Hub 片段一致 |
| ScriptConfig | `teleport` 遮罩 + WebSocket；按钮在脚本卡片（非编辑页） |

### 后端切面

`XxxConfig` / `XxxUserConfig`、`SCRIPT_BOOK`、`task_manager`、`app/task/Xxx/`（`Manager`、`AutoProxy`、`ScriptConfig` 须实现 `final_task` / `on_crash`）。

## UI 分段（默认）

脚本编辑三段：基本信息 / 游戏配置 / 运行配置。用户编辑三段：基本 / 任务 / 通知。Okww 游戏段：`Enabled` 与 `CloseOnFinish` **独立**；见 [examples-okww · 实现规范](references/examples-okww.md#实现规范okww-必遵守)。

## 简洁 / 详细（除 M9A 外默认）

- **简洁**：脚本卡片 ScriptConfig → `data/{scriptId}/Default/ConfigFile`
- **详细**：用户页 ScriptConfig → `data/{scriptId}/{userId}/ConfigFile`；`AutoProxy.check()` 按 `Mode` 校验；用户页仅详细模式显示配置按钮

详见 [adapter-code-norms §4](references/adapter-code-norms.md#4-简洁--详细除-m9a)。

## 原则

- 对齐最接近的表面模板；一次打通 Hub + 编辑 + 后端；勿手改 `frontend/src/api/models/*`。

## 进一步阅读

- [**专项适配代码规范**](references/adapter-code-norms.md)
- [脚本前端架构](references/script-frontend-architectures.md)
- [表面目录与检查清单](references/guide.md)
- [多类型表面对照](references/examples-frontend-surfaces.md)
- [SRC](references/examples-src.md) · [MaaEnd](references/examples-maaend.md) · [M9A](references/examples-m9a.md) · [OK-WW](references/examples-okww.md)

## 提交前自检

对照 [adapter-code-norms.md](references/adapter-code-norms.md)；Okww 另对照 [examples-okww · 实现规范](references/examples-okww.md#实现规范okww-必遵守)。
