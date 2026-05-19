---
name: mas-data-model
description: Define backend data modeling standards for Python services. Use when designing or refactoring models in app/models (schema/config/task), normalizing shared fields, choosing types/defaults/validation strategy, and evolving model contracts with backward compatibility.
---

# MAS Data Model

## 使用场景

设计或修改 `app/models` 下 schema / config / task 模型、统一字段语义或做兼容演进时启用。

## 模型归属（摘要）

| 层 | 职责 |
|----|------|
| `schema` | 对外 API 契约 |
| `config` | 持久化配置与校验 |
| `task` | 运行时执行状态 |

## 核心要点

- 按领域分块（`Info` / `Run` / `Notify` / `Data`）；共享字段名遵循 `mas-schema-naming`
- 类型明确；可选仅在有业务含义时使用；集合默认值安全
- 敏感字段隔离；不在 schema 中泄露密码/token
- 变更优先 additive；重命名须保留读兼容

## 进一步阅读

- [完整类型/默认值/校验/演进规则与检查清单](references/guide.md)
