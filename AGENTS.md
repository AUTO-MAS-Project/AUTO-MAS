# AI 助手说明（维护者与 Agent）

本文档面向 **AI 编码助手**（Copilot、Cursor 等）。终端用户填 Issue / PR 见 [.github/ISSUE_PR_GUIDE.md](.github/ISSUE_PR_GUIDE.md)。

**权威开发规范**：[doc.auto-mas.top · 开发规范](https://doc.auto-mas.top/developer/development-specifications.html)（分支、提交信息、版本记录、注释等）。仓库 [CONTRIBUTING.md](CONTRIBUTING.md) 为社区贡献摘要。

## 分支与 Pull Request（AUTO-MAS-Project/AUTO-MAS）

与[官方 Git 分支说明](https://doc.auto-mas.top/developer/development-specifications.html#git-分支)一致：

- **`main`**：禁止协助用户 push / force push；禁止以 `main` 为 base 创建 PR（会被拒绝）。仅维护者将 **`dev` → `main`** 用于发布。
- **`dev`**：社区贡献的合并目标。引导用户在从 `dev` 拉出的分支上开发，并向 **`dev`** 开 PR，等待开发组审核。
- **`release/{version}`**：一般由发布流程与 cherry-pick 维护，勿引导外部贡献者直接改。
- **开发分支**：较大功能从 `dev` 拉出；合并进 `dev` 后应删除（对外部贡献者优先走 PR，而非直推 `dev`）。

## Issue / Pull Request

- **不要**替用户撰写或提交 Issue、PR，除非明确要求且仅作草稿供其修改后自行发布。
- 用户问如何贡献时：指向 [CONTRIBUTING.md](CONTRIBUTING.md) 与 Issue 模板；**强调 PR base 为 `dev`**。

### Issue 审阅时勿要求的内容

- 实现步骤、API/Schema 设计、代码路径与行号、冗长验收清单、「供开发参考」类元评论。

### 若协助撰写 commit / PR 文案

- Commit：`type(scope): subject`，类型与 scope 规则见[官方提交信息规范](https://doc.auto-mas.top/developer/development-specifications.html#git-提交信息)。
- PR 正文：1～4 条摘要 + `Closes #n`；用户可见变更提醒更新 `res/version.json`。

## 本仓库代码规范（补充）

开发任务先读 [`skills/mas-skills/SKILL.md`](skills/mas-skills/SKILL.md)，再按任务加载 `skills/mas-*`。专项脚本见 [`skills/mas-script-specialized-adapter/SKILL.md`](skills/mas-script-specialized-adapter/SKILL.md)。`mas-*` 同步见 [`skills/SYNC.md`](skills/SYNC.md)。**禁止**手改 OpenAPI 生成文件（见各 Skill）。

后端注释、函数调用风格等以[官方开发规范](https://doc.auto-mas.top/developer/development-specifications.html)为准，不在此重复。
