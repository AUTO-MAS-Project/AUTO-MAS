---
name: mas-code-standards
description: Use when implementing, fixing, refactoring, or reviewing non-generated AUTO-MAS code, or when preparing code-style guidance, comments, docstrings, version notes, or Conventional Commit wording. Skip read-only diagnosis, explanation, exploration, and planning unless code conventions are requested.
---

# MAS Code Standards

动手前先读同目录 2–3 个相邻文件，保持风格与周边一致；详细样本见 [references/style-observations.md](references/style-observations.md)。

## 本地代码风格约定

- **提交信息**：Conventional Commits `<type>(<scope>): <subject>`（`feat`/`fix`/`docs`/`style`/`refactor`/`perf`/`test`/`chore`/`build`/`ci`），单文件改动用文件名作 scope，多文件用父目录名。
- **日志与注释**：使用 `getLogger('中文名')` 与简短中文操作日志；后端需要说明的函数写 Google-style docstring；配置字段用精确 Pydantic 类型与中文 `Field(description=...)`。
- **显式直白**：保持主流程自上而下可读，不抽只用一次的 `builder`/`loader` 壳；有限分支优先小字典/注册表映射；禁止把别的专项的特殊日志/超时/绕过分支盲抄到新模块。
- **保留有用注释（红线）**：清理或重构时**禁止顺手删掉**解释业务意图、配置字段含义、步骤顺序（如「第一步/第二步」）、兼容性决策或非显而易见不变量的注释；仅删除或改写确已过时、误导或随代码一并删除的注释。
- **不顺手乱改无关代码**：不因风格洁癖扩大 diff；后端 schema 变更须重生成 OpenAPI 客户端（禁手改 `frontend/src/api/**`）；用户可见改动带 1 条 `changelog.d/` 碎片。
