# Skills

本目录为 AUTO-MAS 仓库内置的 [Agent Skills](https://www.runoob.com/skills/skills-structure.html)，供贡献者与 AI 助手按需加载。

**上游来源**：[AUTO-MAS-Project/skills](https://github.com/AUTO-MAS-Project/skills)（`mas-*` 系列）。本仓库在集成时按「`SKILL.md` 摘要 + `references/` 全文」整理；同步方法见 [SYNC.md](./SYNC.md)。

## 目录约定

```
skills/<skill-name>/
├── SKILL.md              # 必需：name、description、核心指引（宜短）
├── references/           # 可选：完整规范
│   └── guide.md
├── agents/               # 可选：部分 Agent 平台的接口元数据（来自上游）
│   └── openai.yaml
└── scripts/              # 可选：可执行脚本（上游扩展）
```

## 工程规范（mas-*）

后端 / 前端开发任务请先加载 **`mas-skills`**，再按路由使用子 Skill。

| name | 说明 |
|------|------|
| [mas-skills](./mas-skills/SKILL.md) | 统一入口与路由 |
| [mas-code-standards](./mas-code-standards/SKILL.md) | 代码风格与代表性提交观察 |
| [mas-schema-naming](./mas-schema-naming/SKILL.md) | 共享字段命名 |
| [mas-module-boundary](./mas-module-boundary/SKILL.md) | 模块分层与依赖 |
| [mas-function-design](./mas-function-design/SKILL.md) | 函数设计 |
| [mas-api-contract](./mas-api-contract/SKILL.md) | HTTP / WebSocket 契约 |
| [mas-data-model](./mas-data-model/SKILL.md) | 数据模型 |
| [mas-script-specialized-adapter](./mas-script-specialized-adapter/SKILL.md) | 专项脚本类型端到端适配（MaaEnd / M9A 等） |

## 协作规范（本仓库）

| name | 说明 |
|------|------|
| [github-issue-zh](./github-issue-zh/SKILL.md) | 中文撰写 GitHub Issue |
| [github-pr-zh](./github-pr-zh/SKILL.md) | 中文撰写 GitHub Pull Request |

## 新增 Skill

1. 在 `skills/<skill-name>/` 新建 `SKILL.md`（`name` 为 kebab-case，`description` 含触发场景）。
2. 长文放入 `references/`。
3. 更新本表；必要时更新 `CONTRIBUTING.md` 与 `.github/` 模板。

若与上游 [AUTO-MAS-Project/skills](https://github.com/AUTO-MAS-Project/skills) 对齐，请按 [SYNC.md](./SYNC.md) 同步，并保留本仓库专有的 `github-*` Skill。
