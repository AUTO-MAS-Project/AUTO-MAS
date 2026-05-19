---
name: mas-function-design
description: Define backend function design standards for Python services. Use when implementing or refactoring functions in app/, choosing function boundaries, designing signatures and return contracts, controlling side effects, and reviewing correctness/readability in core/task/services/api modules.
---

# MAS Function Design

## 使用场景

在 `app/` 内实现或重构函数、划分职责、设计签名与返回值、控制副作用时启用。

## 核心要点

- 一函数一主要职责；数据流通过入参与返回值显式表达
- 签名明确；避免含糊的布尔位参数；返回领域结果而非传输层对象
- 领域层抛语义异常；仅在 API 边界转换为对外错误
- 副作用（IO/进程/全局状态）集中、可见；纯函数避免隐藏 IO
- 放置遵循 `mas-module-boundary`；命名动词开头（`load_*`、`check_*`、`prepare_*`）

## 进一步阅读

- [完整分层放置、异步、重构触发与检查清单](references/guide.md)
