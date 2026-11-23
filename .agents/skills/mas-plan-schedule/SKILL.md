---
name: mas-plan-schedule
description: Use when adding, refactoring, or reviewing AUTO-MAS plan schedule types, including backend PlanConfig registration, plan API/schema contracts, plan combobox consumers, frontend plan type registry, and per-plan table integration.
---

# MAS Plan Schedule

每种计划表类型独立持有自己的模型、配置类、前端表格组件与账号消费路径；公共层只负责类型注册、API 分发、下拉筛选与 CRUD（**不造通用字段渲染引擎**）。`UniversalPlanConfig` 仅限通用脚本，专项计划留在对应适配器。

## 新增计划表类型（固定 8 步）

1. **后端配置类**：在 `app/models/config/plan.py` 声明 `DomainEntry`/`ConfigEntry` + `ConfigGroup`（遵循 `../mas-data-model/references/config-framework.md`）。
2. **派生 API 契约**：在 `app/api/plan.py` 用 `ConfigPayload` / `StrictConfigInput` 派生并扩展 `PlanConfigType`、`PlanCreateType`、`PlanConfigData`、`PlanConfigDataInput`（未知字段严格拒绝归输入契约）。
3. **追加消费方常量（高危陷阱）**：在 `app/utils/common/constants.py` 的 `PLAN_CONSUMER_VALUES` **末尾追加**新 consumer，并按**完全相同顺序**同步更新 `app/models/schema.py` 的 `PlanComboxConsumer` Literal。**严禁在中间插入**——既有 `PLAN_BOOK` 条目按位置索引引用该元组，中间插入会静默错指既有计划类型。
4. **注册 `PLAN_BOOK`**：在 `app/models/config/__init__.py` 登记 `create_type`、`config_class`、`consumer`、`script_class`、`field_group`、`field_name`（CRUD、删除清理与下拉过滤的唯一后端源）。
5. **接入账号消费**：在账号配置字段使用 `ref(...)` 并在解引用前做类型校验；删除计划时只重置绑定消费方的对应 `field_name`。
6. **前端注册表**：在 `frontend/src/utils/planTypeRegistry.ts`（运行时代码，勿移入 `types/`，勿放入 `types/script.ts`）用 `@/api` 生成枚举登记描述符与 `tableComponent`。
7. **前端表格**：在 `frontend/src/views/plan/tables/` 新建专属表格组件。
8. **重生成客户端**：在 `frontend/` 运行 `yarn openapi`（禁手改 `frontend/src/api/`）。

## 审查红线

- 未知计划类型必须明确报错，**禁止默认回退为 `MaaPlan`**。
- 下拉接口只返回匹配 `config_class` 的计划；不加无完整闭环的占位类型（如空 `GeneralPlan`/`CustomPlan`）。
