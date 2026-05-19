# 案例：MaaEnd 专项适配

## 已合并 PR

| PR | 说明 |
|----|------|
| [#133](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/133) | 全量接入：任务链路、配置模型、前后端编辑页 |
| [#152](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/152) | 理智任务扩展、基质刷取、`MaaEndPlanConfig`、计划表 UI |
| [#165](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/165) | hotfix：`Emulator` 字段名等小修复 |

## #133 实现的能力（摘要）

- 新增 `app/task/maaend/`：`AutoProxy`、`ScriptConfig`、`manager`、`runtime_bridge`、`tools/notify`
- `MaaEndConfig` / `MaaEndUserConfig` 与 schema 扩展
- 前端 `MaaEndScriptEdit`、`MaaEndUserEdit`、路由与 `Scripts.vue` 入口
- MAAFW `ArknightsPC` 自定义动作命名统一
- ScriptConfig + 用户级/脚本级配置策略；进程清理与重试

## #152 增量（摘要）

- `MaaEndPlanConfig` 与 MAA 计划表并行；`plan.py` / combox 按 consumer 区分
- 前端 `planTypeRegistry`、`MaaEndPlanTable.vue`、协议空间/基质刷取任务选项
- `MaaEndUserConfig` 引用计划；默认等待时间等参数调整

## 本仓库对照路径

```
app/task/MaaEnd/
app/models/config.py          → MaaEndConfig, MaaEndUserConfig
app/api/scripts.py            → MaaEndConfig in SCRIPT_BOOK
app/core/task_manager.py      → MaaEndManager
frontend/src/views/EditView/Script/MaaEndScriptEdit.vue
frontend/src/views/EditView/User/MaaEndUserEdit.vue
frontend/src/router/index.ts  → .../edit/maaend
```

## 常见检查项（MaaEnd 特有）

- `MaaEnd.exe` 与 `config/mxu-MaaEnd.json` 路径校验（`manager.check`）
- `Game.ControllerType`：Win32 与 ADB 模拟器两套分支
- `data/{scriptId}/Default/ConfigFile` 与 per-user `ConfigFile`（简洁模式用 Default）
- 列表页「配置 MaaEnd」与 WebSocket ScriptConfig 会话
