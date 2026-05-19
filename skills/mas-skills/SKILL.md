---
name: mas-skills
description: Master entrypoint for MAS engineering standards and code conventions. Use when a task needs consistent conventions across code standards, schema naming, module boundaries, function design, API contracts, or data modeling, and route the work to one or more MAS sub-skills.
---

# MAS Skills

## 使用场景

后端 / 前端 / 契约 / 建模类任务需要统一工程规范时，先读本 Skill，再按任务选择子 Skill。

## 子 Skill 索引

| name | 用途 |
|------|------|
| `mas-code-standards` | 代码风格（尤指 `DLmaster_361` 代表性提交） |
| `mas-schema-naming` | 共享 schema 命名语义 |
| `mas-module-boundary` | 模块分层与依赖方向 |
| `mas-function-design` | 函数职责、签名、副作用与错误 |
| `mas-api-contract` | HTTP / WebSocket 契约 |
| `mas-data-model` | schema / config / task 模型 |
| `mas-script-specialized-adapter` | 新增专项脚本类型（MaaEnd / M9A 等）端到端适配 |

## 路由（摘要）

1. 字段命名、术语一致 → `mas-schema-naming`
2. 代码规范、对齐 dev 风格 → `mas-code-standards`
3. 分层、import、代码归属 → `mas-module-boundary`
4. 函数拆分、返回值、错误 → `mas-function-design`
5. 接口入出参、WS 载荷 → `mas-api-contract`
6. 模型结构、类型、兼容演进 → `mas-data-model`
7. 新增专项脚本类型、全量接入某外部程序 → `mas-script-specialized-adapter`

多项并存时建议顺序见 [references/guide.md](references/guide.md)。专项适配在模型与边界清晰后执行，见 `mas-script-specialized-adapter` 内推荐顺序。

## 全局约束（摘要）

- 最小必要改动；对齐触达模块既有风格
- 禁止修改 OpenAPI 生成文件，需改时提示开发者手动重新生成

## 进一步阅读

- [完整路由、组合顺序与检查清单](references/guide.md)
