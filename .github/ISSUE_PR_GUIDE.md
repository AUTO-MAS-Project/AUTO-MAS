# 提交 Issue 与 PR（开发者）

请用**简体中文**、**本人填写**。AI 助手边界见 [AGENTS.md](../AGENTS.md)。  
分支、提交信息、版本记录等完整规范：[开发规范](https://doc.auto-mas.top/developer/development-specifications.html)。

## 选模板

| 入口 | 何时用 |
|------|--------|
| **[Enhancement]** | 功能或改进 |
| **[bug]** | 缺陷 |
| **Blank issue** | 其它 |

## Issue 怎么写

**Enhancement**：背景 → 期望 → 备注（选填）。

**Bug**：问题描述 → 版本号 → 日志（建议）→ 备注（选填）；截图提交后拖进正文。

篇幅宜短；多个独立需求请拆 Issue。

## PR 流程（必读）

1. **Base 选 `dev`**，不要选 `main`（向 `main` 的 PR 会被拒绝）。
2. 在从 `dev` 拉出的分支上开发，向官方仓库 **`dev`** 提 PR，等待开发组审核。
3. **禁止**向上游 `main` push。
4. 提交说明遵循 Conventional Commits，例如 `feat(api): 简述`（详见[官方规范](https://doc.auto-mas.top/developer/development-specifications.html#git-提交信息)）。
5. 用户可见变更请更新 [`res/version.json`](../res/version.json)（见[版本记录](https://doc.auto-mas.top/developer/development-specifications.html#版本记录)）。

## PR 正文怎么写

**摘要** 1～4 条，写**已经做了什么**；有关联 Issue 时文末写 `Closes #123`。

不必重复 Issue 长背景，也不必列变更文件清单（除非维护者要求）。
