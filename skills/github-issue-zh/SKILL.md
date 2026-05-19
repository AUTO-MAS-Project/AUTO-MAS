---
name: github-issue-zh
description: >-
  用中文撰写精简的 GitHub Issue（背景与期望，多分点，不写实现细节）。
  在用户起草 issue、提交功能建议/缺陷、gh issue create 时使用。
---

# GitHub Issue（中文）

## 使用场景

- 新建或代写 GitHub Issue（含本仓库及 AUTO-MAS-Project 下属仓库）
- 网页模板、`gh issue create`、任意 AI 助手起草正文

## 核心规则

- **语言**：简体中文。
- **结构**：**背景**（为何需要）+ **期望**（用户可见能力）；多个功能须**分点/小标题**，勿挤成一段。
- **不写**：实现方案、API/Schema、代码路径、验收 checkbox 清单、参考代码索引。
- **篇幅**：约 150～400 字；过长则拆 issue。

## 模板

```markdown
## 背景

[现状与痛点]

## 期望

### [功能点 1]

- [要点]

### [功能点 2]

- [要点]
```

## 进一步阅读

- 完整规范：[references/guide.md](references/guide.md)
- 示例对照：[references/examples.md](references/examples.md)

## 提交前自检

- [ ] 全文中文，不读代码也能理解「要什么」
- [ ] 无实现细节；多功能已分点
