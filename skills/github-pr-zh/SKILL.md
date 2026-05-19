---
name: github-pr-zh
description: >-
  用中文撰写精简的 GitHub Pull Request 摘要（1～4 条，关联 Issue，不写长背景）。
  在用户写 PR 说明、gh pr create、创建 Pull Request 时使用。
---

# GitHub Pull Request（中文）

## 使用场景

- 新建或代写 Pull Request 正文
- 网页 PR 模板、`gh pr create`

## 核心规则

- **语言**：简体中文。
- **结构**：**摘要**（1～4 条，已实现什么）+ 可选 `Closes #123`。
- **不写**：重复 issue 背景、详细技术方案、文件清单、默认不写 Test plan。
- **篇幅**：约 50～200 字。

## 模板

```markdown
## 摘要

- [实现了什么]

Closes #123
```

## 进一步阅读

- 完整规范：[references/guide.md](references/guide.md)
- 示例对照：[references/examples.md](references/examples.md)

## 提交前自检

- [ ] 全文中文，仅说明「做了什么」
- [ ] 足够短，可扫读
