---
name: mas-api-contract
description: Define backend API contract standards for FastAPI services. Use when adding or refactoring HTTP/WebSocket endpoints in app/api, designing request/response schemas in app/models/schema.py, standardizing status/error contracts, and maintaining backward compatibility for clients.
---

# MAS API Contract

## 使用场景

新增或修改 `app/api/*`、设计 `app/models/schema.py` 中的 `*In`/`*Out`、统一错误与 WebSocket 载荷时启用。

## 核心要点

- 每端点一个清晰契约；请求/响应类型显式，`response_model` 必须声明
- 请求 `*In`、响应 `*Out`；业务失败用统一 `code` / `status` / `message`
- WebSocket 保持 `id` / `type` / `data` 信封；字段命名遵循 `mas-schema-naming`
- 契约变更优先 additive；破坏性变更须说明兼容策略
- `api` 只做传输映射；业务在 `core` / `task` / `services`

## 进一步阅读

- [完整契约原则、命名、错误、WS 与检查清单](references/guide.md)
