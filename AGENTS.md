# AI 助手说明（维护者与 Agent）

本文档面向 **AI 编码助手**（Copilot、Cursor 等），不是给终端用户填 Issue 用的。用户请参阅 [.github/ISSUE_PR_GUIDE.md](.github/ISSUE_PR_GUIDE.md)。

## Issue / Pull Request

- **不要**替用户撰写或提交 GitHub Issue、PR 正文，除非用户明确要求且仅作草稿供其修改后自行发布。
- 用户询问如何反馈时，指向仓库 Issue 模板（Enhancement / bug / 空白），不要生成冗长模板填空。
- 审阅已有 Issue 时：以**背景 + 期望**（或 bug 的**现象 + 复现**）为准；缺失实现细节是正常的，勿在 Issue 评论中堆砌方案除非维护者索要。

### Issue 中不应出现的内容（审阅/建议时）

- 实现步骤、API/Schema 设计、代码路径与行号
- 验收 checkbox 清单、冗长范围表
- 「供开发参考」类元评论

### Pull Request（代写时若不可避免）

- 仅 **1～4 条摘要** + `Closes #n`；不重复 Issue 背景，不写默认 Test plan。

## 本仓库代码规范

开发任务请先读 [`skills/mas-skills/SKILL.md`](skills/mas-skills/SKILL.md)，再按任务加载 `skills/mas-*` 子 Skill（API 契约、模块边界、数据模型等）。专项脚本适配见 [`skills/mas-script-specialized-adapter/SKILL.md`](skills/mas-script-specialized-adapter/SKILL.md)。上游 `mas-*` 同步见 [`skills/SYNC.md`](skills/SYNC.md)。
