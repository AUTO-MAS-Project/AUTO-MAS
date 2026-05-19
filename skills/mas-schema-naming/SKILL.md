---
name: mas-schema-naming
description: Standardize naming for shared schema semantics in backend and API contracts. Use when introducing or renaming fields in app/models/schema.py or config models, aligning scriptId/userId/queueId style identifiers, or preventing synonym fields for the same meaning.
---

# MAS Schema Naming

## 使用场景

新增或重命名 API / 配置字段、统一 `scriptId` / `userId` / `queueId` 等共享语义时启用。

## 核心要点

- 同一业务语义只保留一个规范字段名，禁止同义重复字段
- ID 类字段按实体统一（`scriptId`、`userId`、`queueId` 等）
- 对外契约与 config 内部命名一致或可文档化映射
- 重命名优先_additive_ + 过渡读兼容

## 进一步阅读

- [完整命名规则、反模式与检查清单](references/guide.md)
