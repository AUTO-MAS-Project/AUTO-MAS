---
name: mas-script-specialized-adapter
description: >-
  Guide end-to-end integration of a new specialized script type (e.g. MaaEnd, M9A) into AUTO-MAS:
  backend task module, config/schema, API books, frontend routes and edit pages, optional plan/queue extensions.
  Use when adding a new ScriptType, feat(Xxx) specialized adaptation PR, or mirroring MAA/MaaEnd/M9A integration patterns.
---

# 专项脚本类型适配

## 使用场景

为 AUTO-MAS 新增一种**专项脚本**（非 General），需端到端接入任务调度、配置持久化、前端编辑与列表入口时启用。典型参考：[#133 MaaEnd](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/133)、[#154 M9A](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/154)、[#152 MaaEnd 计划表](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/152)。

先加载 `mas-skills`，并配合 `mas-module-boundary`、`mas-data-model`、`mas-api-contract`、`mas-code-standards`。

## 端到端切面（必做）

| 切面 | 要点 |
|------|------|
| 配置模型 | `XxxConfig` / `XxxUserConfig`（`config.py`）+ Pydantic `schema.py` |
| 注册表 | `SCRIPT_BOOK` / `USER_BOOK`（`app/api/scripts.py`）；`config.py` 增删用户/脚本分支 |
| 任务调度 | `app/task/Xxx/manager.py` + `METHOD_BOOK`；`task_manager.py` 分支；`app/task/__init__.py` 导出 |
| 任务实现 | `AutoProxy` / `ScriptConfig` / `ManualReview`（按现有类型取舍）+ `tools/` |
| 前端类型 | `ScriptType`、`script.ts` 配置接口、`ScriptIndexItem` 枚举 |
| 路由与入口 | `router/index.ts`；`Scripts.vue` / `ScriptTable.vue` 分支；`useScriptApi.ts` |
| 编辑页 | `EditView/Script/XxxScriptEdit.vue`、`EditView/User/XxxUserEdit.vue`（可拆 Section 组件） |
| 常量与文案 | `constants.py`、列表图标/标签、任务模式中文名 |

## 可选扩展（按专项需要）

- **计划表**：`XxxPlanConfig`、`plan.py` / `info.py` combox 的 `consumer` 过滤；`planTypeRegistry` + 专用 Table（见 MaaEnd #152）
- **队列/调度**：`QueueItem`、scheduler 对 script type 的分支
- **运行时桥接**：`runtime_bridge`、按用户写入 `data/{scriptId}/{userId}/ConfigFile`
- **外部程序集成**：登录/OCR/通知子模块（`tools/login.py`、`notify.py`）
- **MaaFW 自定义动作**：`app/MaaFW/*` 命名带专项后缀

## 原则

- **对齐参照物**：以 `MAA` / `MaaEnd` / `SRC` 中最接近的专项为模板，复制目录结构再改领域逻辑。
- **一次打通**：同一 PR 内完成后端可调度 + 前端可创建/编辑，避免「只有模型没有 Manager」。
- **禁止手改 OpenAPI 生成文件**：`frontend/src/api/models/*` 由开发者重新生成；TypeScript 手写类型放 `types/script.ts` 等。
- **增量 PR**：全量适配与体验优化（#183）可分 PR；计划表等横切能力单独 PR（#152）。

## 进一步阅读

- [完整检查清单与文件映射](references/guide.md)
- [MaaEnd 案例](references/examples-maaend.md)
- [M9A 案例](references/examples-m9a.md)

## 提交前自检

- [ ] 新类型在 `task_manager` 与 `SCRIPT_BOOK` 均已注册
- [ ] `ScriptConfig` 模式可完成全局/用户配置落盘
- [ ] 前端可新建脚本、编辑脚本与用户，路由与列表无遗漏
- [ ] 未修改 OpenAPI 自动生成文件（或已说明需重新生成）
