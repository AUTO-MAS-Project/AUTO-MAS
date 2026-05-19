---
name: mas-module-boundary
description: Define and enforce backend module boundaries for Python services. Use when adding or refactoring backend code under app/, reviewing dependency direction, deciding layer ownership, or preventing logic leakage across schema/api/core/services/task/utils modules.
---

# MAS Module Boundary

## 使用场景

在 `app/` 下新增或移动代码、审查 import 方向、决定逻辑应落在哪一层时启用。

## 分层（摘要）

`models/schema` → `api` → `core` / `task` → `services` → `utils`（`utils` 无业务策略）

## 核心要点

- 依赖单向：`api` 不承载业务编排；`task` 不定义对外契约
- 放置对照 dev：`app/api/*.py`、`app/core/*.py`、`app/models/*`、`app/task/{MAA,general,SRC,...}`
- 跨层数据用显式映射，不在底层引用上层
- 与 `mas-api-contract`、`mas-data-model` 配合使用

## 进一步阅读

- [完整依赖表、禁止模式与检查清单](references/guide.md)
