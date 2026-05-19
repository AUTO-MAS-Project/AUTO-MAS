---
name: mas-code-standards
description: Apply AUTO-MAS code standards derived from representative DLmaster_361 commits on dev. Use when editing modules mainly authored by DLmaster_361, especially frontend/electron/services, frontend/electron/ipc, initialization UI code, or when the user asks to follow AUTO-MAS code standards or code conventions.
---

# MAS Code Standards

## 使用场景

对齐 AUTO-MAS 现行实现风格，尤指 `frontend/electron/services`、`frontend/electron/ipc`、`frontend/src/views/Initialization` 及同类编排代码。

## 工作流（摘要）

1. 阅读 [references/style-observations.md](references/style-observations.md)（优先 `e541fa5f`、`727aafb`、`e5d72bdb` 视角）
2. 编辑前对照同目录 2～3 个兄弟文件
3. 保持主路径可读；结果对象显式（如 `{ success, error? }`）
4. 最小改动融入周边，不做纯风格大重构

## 核心风格（摘要）

- 分节 banner 注释；简短中文模块/函数说明
- 分阶段编号编排；边界处捕获并记录可行动日志
- 新脚本类型按现有端到端扩展模式（config / schema / 路由 / task / 前端类型与编辑页）

## 禁止

- 勿改 OpenAPI 生成文件；需更新时提示开发者手动重新生成

## 进一步阅读

- [提交视角与详细风格观察](references/style-observations.md)
- [完整工作流、Avoid 与 Review 清单](references/guide.md)
